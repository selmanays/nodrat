"""SettingsStore — runtime-tunable config (#262/#264, MVP-1.2).

Hardcoded `config.py` değerlerinin DB-backed alternatifi. Cache layers:
    L1: process-local dict, TTL 30s — cold-start sonrası DB hit yok
    L2: Redis JSON, TTL 5min — multi-container koordinasyon (reload trigger)

Cache invalidation: Redis pub/sub kanalı `settings:invalidate`. set/reset
çağrısı tüm container'lara key broadcast eder; listener L1'i temizler.

Usage:
    from app.core.settings_store import settings_store

    val = await settings_store.get_float("rerank.min_combined_score", 0.15)
    await settings_store.set("rerank.min_combined_score", 0.20, user_id=admin.id)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INVALIDATE_CHANNEL = "settings:invalidate"
L1_TTL_SECONDS = 30.0


@dataclass
class SettingValue:
    """Process-local cache entry."""

    value: Any
    expires_at: float


@dataclass
class SettingMeta:
    """Setting metadata for admin UI."""

    key: str
    value: Any
    type: str
    group_name: str
    description: str | None
    min_value: float | None
    max_value: float | None
    allowed_values: list | None
    requires_restart: bool
    updated_at: str | None
    updated_by: str | None


# ---------------------------------------------------------------------------
# SettingsStore
# ---------------------------------------------------------------------------


class SettingsStore:
    """Singleton runtime-config accessor."""

    def __init__(self) -> None:
        self._l1: dict[str, SettingValue] = {}
        self._redis: aioredis.Redis | None = None
        self._listener_task: asyncio.Task | None = None
        self._listener_started = False

    # -- Internal --------------------------------------------------------

    def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            s = get_settings()
            self._redis = aioredis.from_url(s.redis_url, decode_responses=True)
        return self._redis

    def _l1_get(self, key: str) -> SettingValue | None:
        entry = self._l1.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            self._l1.pop(key, None)
            return None
        return entry

    def _l1_set(self, key: str, value: Any) -> None:
        self._l1[key] = SettingValue(
            value=value,
            expires_at=time.monotonic() + L1_TTL_SECONDS,
        )

    def _l1_invalidate(self, key: str) -> None:
        self._l1.pop(key, None)

    def _l1_invalidate_all(self) -> None:
        self._l1.clear()

    # -- Pub/sub listener -------------------------------------------------

    async def start_listener(self) -> None:
        """Start Redis pub/sub listener (call once per process)."""
        if self._listener_started:
            return
        self._listener_started = True
        self._listener_task = asyncio.create_task(self._listen_invalidations())

    async def _listen_invalidations(self) -> None:
        """Background coroutine — watches `settings:invalidate` channel."""
        try:
            redis = self._get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(INVALIDATE_CHANNEL)
            logger.info("settings_store: listening for invalidations")
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                key = message.get("data") or ""
                if key == "*":
                    self._l1_invalidate_all()
                    logger.info("settings_store: full L1 invalidate")
                else:
                    self._l1_invalidate(key)
                    logger.debug("settings_store: invalidate key=%s", key)
        except Exception as exc:  # pragma: no cover
            logger.warning("settings_store: listener crashed: %s", exc)
            self._listener_started = False

    # -- DB access -------------------------------------------------------

    async def _db_get(self, db: AsyncSession, key: str) -> Any | None:
        row = (
            await db.execute(
                sa_text("SELECT value FROM app_settings WHERE key = :k"),
                {"k": key},
            )
        ).first()
        return row[0] if row else None

    async def _db_set(
        self,
        db: AsyncSession,
        *,
        key: str,
        value: Any,
        type_: str,
        group_name: str,
        user_id: UUID | None = None,
    ) -> None:
        await db.execute(
            sa_text(
                """
                INSERT INTO app_settings
                    (key, value, type, group_name, updated_by, updated_at)
                VALUES (:k, CAST(:v AS jsonb), :t, :g, :u, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                """
            ),
            {
                "k": key,
                "v": json.dumps(value),
                "t": type_,
                "g": group_name,
                "u": str(user_id) if user_id else None,
            },
        )

    # -- Public API ------------------------------------------------------

    async def get(
        self,
        db: AsyncSession,
        key: str,
        default: Any = None,
    ) -> Any:
        """Return setting value (L1 → DB), fall back to default."""
        cached = self._l1_get(key)
        if cached is not None:
            return cached.value

        try:
            value = await self._db_get(db, key)
        except Exception as exc:
            logger.warning("settings_store.get DB fail key=%s err=%s", key, exc)
            return default

        if value is None:
            self._l1_set(key, default)
            return default

        self._l1_set(key, value)
        return value

    async def get_float(self, db: AsyncSession, key: str, default: float) -> float:
        v = await self.get(db, key, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    async def get_int(self, db: AsyncSession, key: str, default: int) -> int:
        v = await self.get(db, key, default)
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    async def get_bool(self, db: AsyncSession, key: str, default: bool) -> bool:
        v = await self.get(db, key, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)

    async def set(
        self,
        db: AsyncSession,
        *,
        key: str,
        value: Any,
        type_: str,
        group_name: str,
        user_id: UUID | None = None,
    ) -> None:
        """Update DB + invalidate L1 + broadcast pub/sub."""
        await self._db_set(
            db,
            key=key,
            value=value,
            type_=type_,
            group_name=group_name,
            user_id=user_id,
        )
        self._l1_invalidate(key)
        try:
            await self._get_redis().publish(INVALIDATE_CHANNEL, key)
        except Exception as exc:  # pragma: no cover
            logger.warning("settings_store.set publish fail key=%s err=%s", key, exc)

    async def reset(self, db: AsyncSession, key: str, user_id: UUID | None = None) -> None:
        """Delete row → caller fall back to default."""
        await db.execute(
            sa_text("DELETE FROM app_settings WHERE key = :k"),
            {"k": key},
        )
        self._l1_invalidate(key)
        try:
            await self._get_redis().publish(INVALIDATE_CHANNEL, key)
        except Exception as exc:  # pragma: no cover
            logger.warning("settings_store.reset publish fail: %s", exc)

    async def list(self, db: AsyncSession, group: str | None = None) -> list[SettingMeta]:
        """Admin UI list (mevcut kayıtlar). Default değerler için
        SETTING_REGISTRY iterate edilir."""
        clause = "WHERE group_name = :g" if group else ""
        params = {"g": group} if group else {}
        rows = (
            await db.execute(
                sa_text(
                    f"""
                    SELECT key, value, type, group_name, description,
                           min_value, max_value, allowed_values,
                           requires_restart, updated_at, updated_by
                    FROM app_settings
                    {clause}
                    ORDER BY group_name, key
                    """  # noqa: S608
                ),
                params,
            )
        ).all()
        out: list[SettingMeta] = []
        for r in rows:
            out.append(
                SettingMeta(
                    key=r[0],
                    value=r[1],
                    type=r[2],
                    group_name=r[3],
                    description=r[4],
                    min_value=float(r[5]) if r[5] is not None else None,
                    max_value=float(r[6]) if r[6] is not None else None,
                    allowed_values=r[7],
                    requires_restart=bool(r[8]),
                    updated_at=r[9].isoformat() if r[9] else None,
                    updated_by=str(r[10]) if r[10] else None,
                )
            )
        return out


# Singleton instance
settings_store = SettingsStore()
