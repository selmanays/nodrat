"""PromptsStore — runtime-tunable LLM prompts (#270 PR-B, MVP-1.2).

Admin paneli üzerinden prompt güncellenir, deploy gerektirmez. Version history
korunur (rollback için). Cache layers:
    L1: process-local dict (TTL 30s)
    L2: Postgres (current version)
    Archive: app_prompt_history

Cache invalidation: Redis pub/sub `prompts:invalidate` channel.

Usage:
    from app.core.prompts_store import prompts_store

    text = await prompts_store.get(db, "agenda_card", default=AGENDA_CARD_PROMPT)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

logger = logging.getLogger(__name__)


INVALIDATE_CHANNEL = "prompts:invalidate"
L1_TTL_SECONDS = 30.0


@dataclass
class _CacheEntry:
    content: str
    expires_at: float


@dataclass
class PromptMeta:
    name: str
    version: int
    content: str
    description: str | None
    model_hint: str | None
    updated_at: str | None
    updated_by: str | None


@dataclass
class PromptHistoryEntry:
    id: str
    name: str
    version: int
    content: str
    updated_by: str | None
    created_at: str


class PromptsStore:
    """Singleton prompts accessor."""

    def __init__(self) -> None:
        self._l1: dict[str, _CacheEntry] = {}
        self._redis: aioredis.Redis | None = None
        self._listener_task: asyncio.Task | None = None
        self._listener_started = False

    def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            s = get_settings()
            self._redis = aioredis.from_url(s.redis_url, decode_responses=True)
        return self._redis

    def _l1_get(self, name: str) -> str | None:
        entry = self._l1.get(name)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            self._l1.pop(name, None)
            return None
        return entry.content

    def _l1_set(self, name: str, content: str) -> None:
        self._l1[name] = _CacheEntry(
            content=content,
            expires_at=time.monotonic() + L1_TTL_SECONDS,
        )

    def _l1_invalidate(self, name: str) -> None:
        self._l1.pop(name, None)

    def _l1_invalidate_all(self) -> None:
        self._l1.clear()

    async def start_listener(self) -> None:
        if self._listener_started:
            return
        self._listener_started = True
        self._listener_task = asyncio.create_task(self._listen_invalidations())

    async def _listen_invalidations(self) -> None:
        try:
            redis = self._get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(INVALIDATE_CHANNEL)
            logger.info("prompts_store: listening for invalidations")
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                name = message.get("data") or ""
                if name == "*":
                    self._l1_invalidate_all()
                else:
                    self._l1_invalidate(name)
        except Exception as exc:  # pragma: no cover
            logger.warning("prompts_store: listener crashed: %s", exc)
            self._listener_started = False

    async def get(self, db: AsyncSession, name: str, default: str) -> str:
        cached = self._l1_get(name)
        if cached is not None:
            return cached
        try:
            row = (
                await db.execute(
                    sa_text("SELECT content FROM app_prompts WHERE name = :n"),
                    {"n": name},
                )
            ).first()
        except Exception as exc:
            logger.warning("prompts_store.get DB fail name=%s err=%s", name, exc)
            return default
        if row is None:
            self._l1_set(name, default)
            return default
        content = row[0]
        self._l1_set(name, content)
        return content

    async def set(
        self,
        db: AsyncSession,
        *,
        name: str,
        content: str,
        description: str | None = None,
        model_hint: str | None = None,
        user_id: UUID | None = None,
    ) -> int:
        """Update + history entry. Returns new version number."""
        # Read current version
        row = (
            await db.execute(
                sa_text("SELECT version, content FROM app_prompts WHERE name = :n"),
                {"n": name},
            )
        ).first()
        if row is None:
            new_version = 1
            await db.execute(
                sa_text(
                    """
                    INSERT INTO app_prompts
                        (name, version, content, description, model_hint,
                         updated_by, updated_at)
                    VALUES (:n, 1, :c, :d, :m, :u, NOW())
                    """
                ),
                {
                    "n": name,
                    "c": content,
                    "d": description,
                    "m": model_hint,
                    "u": str(user_id) if user_id else None,
                },
            )
        else:
            current_version, old_content = row
            new_version = current_version + 1
            # Archive previous version
            await db.execute(
                sa_text(
                    """
                    INSERT INTO app_prompt_history
                        (name, version, content, updated_by)
                    VALUES (:n, :v, :c, :u)
                    """
                ),
                {
                    "n": name,
                    "v": current_version,
                    "c": old_content,
                    "u": str(user_id) if user_id else None,
                },
            )
            # Update current
            await db.execute(
                sa_text(
                    """
                    UPDATE app_prompts SET
                        version = :v,
                        content = :c,
                        description = COALESCE(:d, description),
                        model_hint = COALESCE(:m, model_hint),
                        updated_by = :u,
                        updated_at = NOW()
                    WHERE name = :n
                    """
                ),
                {
                    "n": name,
                    "v": new_version,
                    "c": content,
                    "d": description,
                    "m": model_hint,
                    "u": str(user_id) if user_id else None,
                },
            )

        self._l1_invalidate(name)
        try:
            await self._get_redis().publish(INVALIDATE_CHANNEL, name)
        except Exception as exc:  # pragma: no cover
            logger.warning("prompts_store.set publish fail: %s", exc)
        return new_version

    async def reset(self, db: AsyncSession, name: str) -> None:
        """Mevcut row'u sil → caller fallback kod-tarafı default'a döner.
        History korunur (geri yükleme için)."""
        await db.execute(
            sa_text("DELETE FROM app_prompts WHERE name = :n"),
            {"n": name},
        )
        self._l1_invalidate(name)
        try:
            await self._get_redis().publish(INVALIDATE_CHANNEL, name)
        except Exception as exc:  # pragma: no cover
            logger.warning("prompts_store.reset publish fail: %s", exc)

    async def list(self, db: AsyncSession) -> list[PromptMeta]:
        rows = (
            await db.execute(
                sa_text(
                    """
                    SELECT name, version, content, description, model_hint,
                           updated_at, updated_by
                    FROM app_prompts
                    ORDER BY name
                    """
                )
            )
        ).all()
        out: list[PromptMeta] = []
        for r in rows:
            out.append(
                PromptMeta(
                    name=r[0],
                    version=r[1],
                    content=r[2],
                    description=r[3],
                    model_hint=r[4],
                    updated_at=r[5].isoformat() if r[5] else None,
                    updated_by=str(r[6]) if r[6] else None,
                )
            )
        return out

    async def history(
        self, db: AsyncSession, name: str, limit: int = 20
    ) -> list[PromptHistoryEntry]:
        rows = (
            await db.execute(
                sa_text(
                    """
                    SELECT id, name, version, content, updated_by, created_at
                    FROM app_prompt_history
                    WHERE name = :n
                    ORDER BY version DESC
                    LIMIT :limit
                    """
                ),
                {"n": name, "limit": limit},
            )
        ).all()
        return [
            PromptHistoryEntry(
                id=str(r[0]),
                name=r[1],
                version=r[2],
                content=r[3],
                updated_by=str(r[4]) if r[4] else None,
                created_at=r[5].isoformat() if r[5] else "",
            )
            for r in rows
        ]


prompts_store = PromptsStore()
