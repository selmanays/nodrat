"""NER entity extraction worker (#667 Faz 6).

Article cleaned_text + title + subtitle'dan DeepSeek ile özel ad entity'leri
çıkarır. Cost: ~$0.0008/article DeepSeek V4 Flash (300-500 input + 100 output token).

bge-m3 embedding niş entity disambiguation'da zayıf. NER pipeline ile direct
exact match yapıyoruz → embedding bypass → retrieval recall sıçraması.

Pipeline:
  1. article.status = 'cleaned' olduktan sonra extract_article_entities
     dispatch edilir (chunk_article zincirine eklenir)
  2. DeepSeek JSON output: kişi/yer/kurum/etkinlik/sayı
  3. entity_normalized: lower + strip_quote_variants (#647 ile uyumlu)
  4. UPSERT — aynı article'da aynı entity bir kez (mention_count ile)

Anti-pattern:
  - LLM call fail → article skip (article'a hata bırakma, status bozma)
  - Aynı entity duplicate INSERT (UNIQUE constraint + ON CONFLICT)
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text as sa_text

from app.core.prompts_store import prompts_store
from app.core.retrieval import strip_quote_variants
from app.prompts.ner import SYSTEM_PROMPT as _NER_PROMPT_DEFAULT
from app.providers.base import Message
from app.workers.celery_app import celery_app
from app.workers.tasks.embedding import _ensure_providers, _get_session_factory, _run_async

logger = logging.getLogger(__name__)


# Entity tipleri — genel sınıflandırma. NER literatür PER/LOC/ORG/MISC standardı
# + bizim domain (event, money, number).
VALID_ENTITY_TYPES = {"person", "place", "org", "event", "money", "number", "misc"}


def _build_user_payload(title: str, subtitle: str, body: str) -> str:
    """LLM input: title + subtitle + body excerpt.

    Body excerpt 6000 char — DeepSeek context window büyük, niş entity'lerin
    article ortasında geçme durumunu (Rodos, vs.) yakalamak için. Cost
    +~30% ama recall sıçraması mantıklı trade-off.
    """
    parts = [f"BAŞLIK: {title}"]
    if subtitle:
        parts.append(f"ALT BAŞLIK: {subtitle}")
    parts.append(f"İÇERİK:\n{body[:6000]}")
    return "\n\n".join(parts)


def _normalize_entity(text: str) -> str:
    """Entity'yi normalize et — quote variants strip + lower."""
    return strip_quote_variants(text.lower()).strip()


def _detect_position(entity_text: str, title: str, subtitle: str, body: str) -> str:
    """Entity ilk olarak nerede geçiyor (title > subtitle > body)?"""
    et = entity_text.lower()
    if et in (title or "").lower():
        return "title"
    if et in (subtitle or "").lower():
        return "subtitle"
    return "body"


async def _extract_article_entities_async(article_id: UUID) -> dict:
    """Article'dan NER entity çıkar ve entities tablosuna kaydet."""
    _ensure_providers()
    factory = _get_session_factory()

    summary: dict[str, Any] = {
        "article_id": str(article_id),
        "status": "unknown",
    }

    async with factory() as db:
        # Provider — #778 per-operation routing (default DeepSeek, admin'den Gemma seçilebilir)
        from app.providers.registry import resolve_chat_provider

        try:
            provider = await resolve_chat_provider(db, op_name="ner", tier="free")
        except RuntimeError as exc:
            summary["status"] = "no_provider"
            summary["error"] = str(exc)
            return summary

        row = (
            (
                await db.execute(
                    sa_text(
                        """
                    SELECT title, subtitle, clean_text, status
                    FROM articles WHERE id = :aid
                    """
                    ),
                    {"aid": str(article_id)},
                )
            )
            .mappings()
            .first()
        )

        if not row:
            summary["status"] = "not_found"
            return summary
        if row["status"] != "cleaned":
            summary["status"] = "skipped_not_cleaned"
            return summary

        title = (row["title"] or "").strip()
        subtitle = (row["subtitle"] or "").strip()
        body = (row["clean_text"] or "").strip()

        if not (title or body):
            summary["status"] = "skipped_empty"
            return summary

        # LLM call
        user_payload = _build_user_payload(title, subtitle, body)
        # #720: prompts_store override → admin /prompts üzerinden runtime editable
        system_prompt = await prompts_store.get(db, "ner_extraction", _NER_PROMPT_DEFAULT)
        try:
            resp = await provider.generate_text(
                messages=[
                    Message(role="system", content=system_prompt),
                    Message(role="user", content=user_payload),
                ],
                max_tokens=800,
                temperature=0.1,
                json_mode=True,
            )
        except Exception as exc:
            summary["status"] = "llm_failed"
            summary["error"] = str(exc)
            return summary

        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json\n"):
                text = text[5:]
            text = text.rstrip("`").strip()

        try:
            entities_raw = json.loads(text)
        except json.JSONDecodeError as exc:
            summary["status"] = "json_parse_failed"
            summary["error"] = str(exc)
            return summary

        if not isinstance(entities_raw, list):
            summary["status"] = "invalid_format"
            return summary

        # Önce article'ın eski entity'lerini sil (idempotent)
        await db.execute(
            sa_text("DELETE FROM entities WHERE article_id = :aid"),
            {"aid": str(article_id)},
        )

        # INSERT
        inserted = 0
        skipped = 0
        seen_keys: set[tuple[str, str]] = set()  # dedup (normalized, type)
        for ent in entities_raw[:40]:  # cap 40 entity/article (numeric için ek alan)
            if not isinstance(ent, dict):
                skipped += 1
                continue
            etext = str(ent.get("text", "")).strip()
            etype = str(ent.get("type", "misc")).lower().strip()
            if etype not in VALID_ENTITY_TYPES:
                etype = "misc"
            if not etext or len(etext) < 2 or len(etext) > 200:
                skipped += 1
                continue
            norm = _normalize_entity(etext)
            if not norm or len(norm) < 2:
                skipped += 1
                continue
            key = (norm, etype)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            position = _detect_position(etext, title, subtitle, body)
            mention_count = (title + " " + subtitle + " " + body).lower().count(etext.lower()) or 1
            try:
                await db.execute(
                    sa_text(
                        """
                        INSERT INTO entities
                            (article_id, entity_text, entity_normalized,
                             entity_type, mention_count, first_position)
                        VALUES (:aid, :etext, :enorm, :etype, :mc, :pos)
                        ON CONFLICT (article_id, entity_normalized, entity_type)
                        DO UPDATE SET mention_count = EXCLUDED.mention_count
                        """
                    ),
                    {
                        "aid": str(article_id),
                        "etext": etext,
                        "enorm": norm,
                        "etype": etype,
                        "mc": min(mention_count, 999),
                        "pos": position,
                    },
                )
                inserted += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("entity insert failed: %s", exc)
                skipped += 1

        await db.commit()
        summary["status"] = "extracted"
        summary["inserted"] = inserted
        summary["skipped"] = skipped
        return summary


@celery_app.task(
    name="tasks.entities.extract_article_entities",
    bind=True,
    max_retries=2,
)
def extract_article_entities(self, article_id: str) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_extract_article_entities_async(UUID(article_id)))


async def _backfill_entities_async(*, batch_size: int = 50, dry_run: bool = False) -> dict:
    """Tüm cleaned article'lar için entity extraction dispatch."""
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "status": "unknown",
        "dispatched": 0,
        "dry_run": dry_run,
    }

    async with factory() as db:
        total = (
            await db.execute(
                sa_text(
                    """
                    SELECT COUNT(*) FROM articles a
                    WHERE a.status = 'cleaned'
                      AND NOT EXISTS (
                          SELECT 1 FROM entities e WHERE e.article_id = a.id
                      )
                    """
                )
            )
        ).scalar() or 0
        summary["total_eligible"] = int(total)

        if dry_run or total == 0:
            summary["status"] = "dry_run" if dry_run else "no_eligible"
            return summary

        dispatched = 0
        offset = 0
        while True:
            rows = (
                (
                    await db.execute(
                        sa_text(
                            """
                        SELECT a.id::text AS aid
                        FROM articles a
                        WHERE a.status = 'cleaned'
                          AND NOT EXISTS (
                              SELECT 1 FROM entities e WHERE e.article_id = a.id
                          )
                        ORDER BY a.created_at DESC
                        LIMIT :limit OFFSET :offset
                        """
                        ),
                        {"limit": batch_size, "offset": offset},
                    )
                )
                .mappings()
                .all()
            )

            if not rows:
                break

            for r in rows:
                try:
                    extract_article_entities.apply_async(args=[r["aid"]])
                    dispatched += 1
                except Exception as exc:
                    logger.warning("dispatch ner failed aid=%s err=%s", r["aid"], exc)

            offset += len(rows)

        summary["dispatched"] = dispatched
        summary["status"] = "dispatched"
        return summary


@celery_app.task(
    name="tasks.entities.backfill",
    bind=True,
)
def backfill_entities(  # type: ignore[no-untyped-def]
    self,
    batch_size: int = 50,
    dry_run: bool = False,
) -> dict:
    """Tüm cleaned article'lar için entity extraction dispatch."""
    return _run_async(_backfill_entities_async(batch_size=batch_size, dry_run=dry_run))
