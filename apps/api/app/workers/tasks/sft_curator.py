"""SFT data curator — generations log → training_samples ETL (#567).

Trendyol-LLM-7B-chat-v4.1.0 üzerine domain-spesifik fine-tune için
altın etiketlenmiş (sft_eligible=true) generations satırlarını ChatML
format'ında curated training_samples tablosuna dönüştürür.

Beat schedule: günlük 02:45 UTC (RAPTOR 02:00 ile body_html_drop 03:00
arası boşluk; backup 04:00'tan önce). Settings flag:
sft.curator.enabled (default false — kill switch).

Kanonik mimari: wiki/concepts/sft-data-pipeline.md
Locked karar: wiki/decisions/own-slm-strategy.md

Adımlar:
  1. sft_eligible=true VE created_at >= NOW()-24h satırları çek
  2. PII secondary scan (defense-in-depth) — hit varsa skip +
     sft_excluded_reason='pii_secondary_hit' set
  3. Quality signals hesapla
  4. ChatML format'a serialize (input_payload, output_payload)
  5. Deterministic split: hash(generation_id) % 100 → train/val/test
  6. INSERT INTO training_samples (UNIQUE constraint idempotent)

Idempotent: aynı (generation_id, task_type) için 2. çağrı duplicate
eklemez (UNIQUE constraint integrity error).

KVKK md.11 cascade: user revoke → generations sft_eligible=false +
sft_excluded_reason='consent_revoked' (#566 endpoint). User soft delete
veya generation delete → training_samples FK CASCADE.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.pii import redact
from app.core.settings_store import settings_store
from app.models.generation import Generation
from app.models.training_sample import TrainingSample
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _get_session_factory, _run_async


logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# MVP-1.7 default — sadece content_generator task'ı SFT'e dahil.
# query_planner ve style_analyzer Faz 1+'da eklenecek.
DEFAULT_TASK_TYPE = "content_generator"
DEFAULT_PROMPT_VERSION = "1.1.0"

# Deterministic split bucket'ları
SPLIT_TRAIN_BUCKET = 80   # 0..79  → train
SPLIT_VAL_BUCKET = 90     # 80..89 → val (kalanı 90..99 test)


# =============================================================================
# Celery task
# =============================================================================


@celery_app.task(
    name="tasks.sft_curator.run",
    queue="embedding_queue",
)
def run_sft_curator(batch: int | None = None) -> dict[str, Any]:
    """SFT curator nightly run.

    Args:
        batch: Override admin setting `sft.curator.daily_max_samples`.
               None → setting'ten oku.

    Returns: {scanned, ingested, skipped_pii, skipped_existing,
              skipped_duplicate, errors}

    Settings flag `sft.curator.enabled` False ise no-op.
    """
    return _run_async(_sft_curator_async(batch))


# =============================================================================
# Async core
# =============================================================================


async def _sft_curator_async(batch_override: int | None) -> dict[str, Any]:
    enabled = await settings_store.get_bool("sft.curator.enabled", False)
    if not enabled:
        logger.info("sft_curator: disabled (sft.curator.enabled=false), skipping")
        return {"status": "disabled", "scanned": 0, "ingested": 0}

    daily_max = (
        batch_override
        if batch_override is not None
        else await settings_store.get_int("sft.curator.daily_max_samples", 1000)
    )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "status": "ok",
        "scanned": 0,
        "ingested": 0,
        "skipped_pii": 0,
        "skipped_duplicate": 0,
        "errors": 0,
    }

    async with factory() as db:
        result = await db.execute(
            select(Generation)
            .where(Generation.sft_eligible.is_(True))
            .where(Generation.created_at >= cutoff)
            .order_by(Generation.created_at.asc())
            .limit(daily_max)
        )
        rows = list(result.scalars().all())
        summary["scanned"] = len(rows)

        for gen in rows:
            try:
                # Step 1 — PII secondary scan
                text_to_scan = (gen.request_text or "") + "\n" + json.dumps(
                    gen.output_json or {}, ensure_ascii=False
                )
                redact_result = redact(text_to_scan)
                if redact_result.has_redactions:
                    await db.execute(
                        update(Generation)
                        .where(Generation.id == gen.id)
                        .values(
                            sft_eligible=False,
                            sft_excluded_reason="pii_secondary_hit",
                        )
                    )
                    summary["skipped_pii"] += 1
                    continue

                # Step 2 — Quality signals
                signals = _compute_quality_signals(gen)

                # Step 3 — ChatML serialize
                input_payload = _build_input_payload(gen)
                output_payload = _build_output_payload(gen)

                # Step 4 — Deterministic split
                sft_split = _assign_split(gen.id)

                # Step 5 — INSERT (UNIQUE constraint → idempotent)
                sample = TrainingSample(
                    generation_id=gen.id,
                    user_id=gen.user_id,
                    task_type=DEFAULT_TASK_TYPE,
                    prompt_version=DEFAULT_PROMPT_VERSION,
                    input_payload=input_payload,
                    output_payload=output_payload,
                    edited_output=gen.edited_text,
                    quality_signals=signals,
                    sft_split=sft_split,
                )
                db.add(sample)
                try:
                    await db.flush()
                    summary["ingested"] += 1
                except IntegrityError:
                    await db.rollback()
                    summary["skipped_duplicate"] += 1
            except Exception as exc:  # pragma: no cover — defense-in-depth
                logger.exception(
                    "sft_curator: row failed gen_id=%s err=%s", gen.id, exc
                )
                summary["errors"] += 1
                await db.rollback()

        await db.commit()

    logger.info("sft_curator run summary: %s", summary)
    return summary


# =============================================================================
# Helpers
# =============================================================================


def _assign_split(generation_id: UUID) -> str:
    """Deterministic train/val/test split.

    `hash(generation_id) % 100` — same generation always maps same split.
    Distribution: train=80%, val=10%, test=10%.
    """
    h = hashlib.sha256(str(generation_id).encode()).hexdigest()[:8]
    bucket = int(h, 16) % 100
    if bucket < SPLIT_TRAIN_BUCKET:
        return "train"
    if bucket < SPLIT_VAL_BUCKET:
        return "val"
    return "test"


def _compute_quality_signals(gen: Generation) -> dict[str, Any]:
    """Generation row'dan quality_signals JSONB üret.

    Signals:
      - edit_distance       (float | None) — Levenshtein normalize
      - time_to_action_sec  (int | None)
      - char_count          (int) — output text uzunluğu
      - source_count        (int) — used_agenda_card_ids array length
      - schema_valid        (bool) — output_json varlığı (eligible ⇒ True)
      - json_parse_ok       (bool) — eligible olmasının ön şartı (True)
    """
    output = gen.output_json or {}
    output_text = _extract_output_text(output)

    return {
        "edit_distance": (
            float(gen.edit_distance) if gen.edit_distance is not None else None
        ),
        "time_to_action_sec": gen.time_to_action_sec,
        "char_count": len(output_text),
        "source_count": len(gen.used_agenda_card_ids or []),
        "schema_valid": bool(gen.output_json),
        "json_parse_ok": True,
    }


def _build_input_payload(gen: Generation) -> dict[str, Any]:
    """ChatML input payload — system + user messages.

    NOT: System prompt'un tam metni eğitim sırasında uygulanır;
    burada sadece prompt_version + user_payload yapısı tutulur.
    Eğitim aşaması (Faz 3) prompt_version'a göre system prompt'u
    `apps/api/app/prompts/content_generator.py` const'larından
    re-render edebilir.
    """
    user_content = {
        "request_text": gen.request_text,
        "mode": gen.mode,
        "output_type": gen.output_type,
        "tone": gen.tone,
        "length": gen.length,
        "show_sources": gen.show_sources,
        "used_agenda_card_count": len(gen.used_agenda_card_ids or []),
    }
    return {
        "messages": [
            {
                "role": "system",
                "content": f"<content_generator-{DEFAULT_PROMPT_VERSION}>",
            },
            {
                "role": "user",
                "content": json.dumps(user_content, ensure_ascii=False),
            },
        ],
    }


def _build_output_payload(gen: Generation) -> dict[str, Any]:
    """ChatML output payload — assistant message + raw_output.

    Eğer kullanıcı edited_text vermişse onu kullan (DPO için altın),
    yoksa output_json'dan extract et.
    """
    text = gen.edited_text or _extract_output_text(gen.output_json or {})
    return {
        "messages": [
            {"role": "assistant", "content": text},
        ],
        "raw_output": gen.output_json or {},
    }


def _extract_output_text(output: dict[str, Any]) -> str:
    """output_json'dan kullanıcıya gösterilen text'i çıkar.

    Aynı extractor app_generate.py:_extract_original_text ile (DRY
    için ortak fn olabilir, şimdilik kopya — coupling minimum tutuluyor
    workers ↔ api boundary'sini bozmamak için).
    """
    posts = output.get("posts")
    if isinstance(posts, list):
        texts: list[str] = []
        for p in posts:
            if isinstance(p, dict):
                t = p.get("text") or p.get("post") or ""
                if isinstance(t, str) and t:
                    texts.append(t)
        if texts:
            return "\n\n".join(texts)

    summary_doc = output.get("summary_doc")
    if isinstance(summary_doc, dict):
        parts: list[str] = []
        title = summary_doc.get("title")
        if isinstance(title, str) and title:
            parts.append(title)
        items = summary_doc.get("items", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    event = item.get("event")
                    if isinstance(event, str) and event:
                        parts.append(event)
        if parts:
            return "\n".join(parts)

    summary_text = output.get("summary")
    if isinstance(summary_text, str):
        return summary_text

    return ""
