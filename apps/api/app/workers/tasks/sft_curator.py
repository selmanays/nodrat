"""SFT data curator — messages log → training_samples ETL (#800 S1E rewrite).

Chat-only mimari sonrası (generations DROP), curator artık `messages`
tablosundan beslenir. Hem SFT (eligible=true) hem DPO (rejected=true)
sample'ları üretir.

Beat schedule: günlük 02:45 UTC. Settings flag: sft.curator.enabled
(default false — kill switch).

Kanonik mimari: wiki/concepts/sft-data-pipeline.md
Locked karar: wiki/decisions/own-slm-strategy.md
S1E rewrite: wiki/decisions/sft-message-source.md

Adımlar:
  1. messages WHERE (sft_eligible=true OR dpo_rejected=true)
     AND role='assistant' AND NOT EXISTS training_samples(message_id,...)
  2. PII secondary scan (defense-in-depth) — hit varsa skip +
     sft_excluded_reason='pii_secondary_hit'
  3. ChatML serialize (input = previous user msg + sources, output = content)
  4. Sample types:
       sft_eligible=true   → INSERT sample_type='sft'
       dpo_rejected=true   → INSERT sample_type='dpo_rejected'
       dpo_chosen_content  → ek INSERT sample_type='dpo_chosen' (pair)
  5. Deterministic split: hash(message_id) % 100

Idempotent: UNIQUE(message_id, task_type, sample_type) — partial index.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.pii import redact
from app.core.settings_store import settings_store
from app.models.conversation import Conversation, Message
from app.models.training_sample import TrainingSample
from app.models.user import User
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _get_session_factory, _run_async

logger = logging.getLogger(__name__)


# Task type — chat-derived sample'lar
DEFAULT_TASK_TYPE = "chat_answer"
# #854 — provenance: bu sürümden sonra biriken training sample'lar
# agentic mimari (SYSTEM_PROMPT_NODRAT_AGENT, search_news+wikipedia
# tool orkestrasyonu, cited-only sources) ile üretildi. Gelecekteki
# SFT/DPO eğitimleri 1.x (eski chat_answer) vs 2.x ayrımını bilmeli.
DEFAULT_PROMPT_VERSION = "2.0.0"  # Nodrat agentic (#845→#854)

SPLIT_TRAIN_BUCKET = 80
SPLIT_VAL_BUCKET = 90


@celery_app.task(
    name="tasks.sft_curator.run",
    queue="embedding_queue",
)
def run_sft_curator(batch: int | None = None) -> dict[str, Any]:
    """SFT curator nightly run — messages tablosundan ETL."""
    return _run_async(_sft_curator_async(batch))


async def _sft_curator_async(batch_override: int | None) -> dict[str, Any]:
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "status": "ok",
        "scanned": 0,
        "ingested_sft": 0,
        "ingested_dpo_chosen": 0,
        "ingested_dpo_rejected": 0,
        "skipped_pii": 0,
        "skipped_duplicate": 0,
        "errors": 0,
    }

    async with factory() as db:
        # settings_store.get_* imzası (db, key, default) — db ZORUNLU.
        # Eski kod db'siz çağırıyordu → her gece task ilk satırda (try/except
        # dışında) çöküyor → curator hiç sample üretmiyordu.
        enabled = await settings_store.get_bool(
            db, "sft.curator.enabled", False
        )
        if not enabled:
            logger.info("sft_curator: disabled, skipping")
            return {"status": "disabled", "scanned": 0, "ingested": 0}

        daily_max = (
            batch_override
            if batch_override is not None
            else await settings_store.get_int(
                db, "sft.curator.daily_max_samples", 1000
            )
        )

        # NOT EXISTS filter — message_id zaten training_samples'ta varsa skip
        # SFT (sft_eligible) + DPO (dpo_rejected) message'ları çek
        rows_q = (
            select(Message, Conversation, User)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(User, User.id == Conversation.user_id)
            .where(
                Message.role == "assistant",
                (Message.sft_eligible.is_(True)) | (Message.dpo_rejected.is_(True)),
                ~Message.id.in_(
                    select(TrainingSample.message_id).where(
                        TrainingSample.message_id.is_not(None),
                        TrainingSample.task_type == DEFAULT_TASK_TYPE,
                    )
                ),
            )
            .order_by(Message.created_at.asc())
            .limit(daily_max)
        )
        rows = list((await db.execute(rows_q)).all())
        summary["scanned"] = len(rows)

        for msg, conv, msg_user in rows:
            try:
                # Önceki user message (input)
                user_msg = (
                    await db.execute(
                        select(Message).where(
                            Message.conversation_id == conv.id,
                            Message.created_at < msg.created_at,
                            Message.role == "user",
                        ).order_by(Message.created_at.desc()).limit(1)
                    )
                ).scalar_one_or_none()

                if user_msg is None:
                    logger.warning(
                        "sft_curator: orphan assistant msg=%s (no prev user)", msg.id,
                    )
                    summary["errors"] += 1
                    continue

                # PII secondary scan
                text_to_scan = (user_msg.content or "") + "\n" + (msg.content or "")
                if msg.edited_content:
                    text_to_scan += "\n" + msg.edited_content
                if msg.dpo_chosen_content:
                    text_to_scan += "\n" + msg.dpo_chosen_content

                redact_result = redact(text_to_scan)
                if redact_result.has_pii:
                    await db.execute(
                        update(Message)
                        .where(Message.id == msg.id)
                        .values(
                            sft_eligible=False,
                            sft_excluded_reason="pii_secondary_hit",
                        )
                    )
                    summary["skipped_pii"] += 1
                    continue

                # ChatML build
                input_payload = _build_input_payload(user_msg, msg)
                quality_signals = _compute_quality_signals(msg)
                sft_split = _assign_split(msg.id)

                # SFT sample (eligible olanlar)
                if msg.sft_eligible:
                    sample = TrainingSample(
                        message_id=msg.id,
                        user_id=msg_user.id,
                        task_type=DEFAULT_TASK_TYPE,
                        sample_type="sft",
                        prompt_version=DEFAULT_PROMPT_VERSION,
                        input_payload=input_payload,
                        output_payload={"content": msg.content},
                        edited_output=msg.edited_content,
                        quality_signals=quality_signals,
                        sft_split=sft_split,
                    )
                    db.add(sample)
                    try:
                        await db.flush()
                        summary["ingested_sft"] += 1
                    except IntegrityError:
                        await db.rollback()
                        summary["skipped_duplicate"] += 1

                # DPO rejected sample (halu_flagged → rejected)
                if msg.dpo_rejected:
                    rejected = TrainingSample(
                        message_id=msg.id,
                        user_id=msg_user.id,
                        task_type=DEFAULT_TASK_TYPE,
                        sample_type="dpo_rejected",
                        prompt_version=DEFAULT_PROMPT_VERSION,
                        input_payload=input_payload,
                        output_payload={"content": msg.content},
                        quality_signals=quality_signals,
                        sft_split=sft_split,
                    )
                    db.add(rejected)
                    try:
                        await db.flush()
                        summary["ingested_dpo_rejected"] += 1
                    except IntegrityError:
                        await db.rollback()
                        summary["skipped_duplicate"] += 1

                # DPO chosen sample (kullanıcının "doğru cevap" önerisi)
                if msg.dpo_rejected and msg.dpo_chosen_content:
                    chosen = TrainingSample(
                        message_id=msg.id,
                        user_id=msg_user.id,
                        task_type=DEFAULT_TASK_TYPE,
                        sample_type="dpo_chosen",
                        prompt_version=DEFAULT_PROMPT_VERSION,
                        input_payload=input_payload,
                        output_payload={"content": msg.dpo_chosen_content},
                        quality_signals={
                            **quality_signals,
                            "dpo_pair_with": str(msg.id),
                        },
                        sft_split=sft_split,
                    )
                    db.add(chosen)
                    try:
                        await db.flush()
                        summary["ingested_dpo_chosen"] += 1
                    except IntegrityError:
                        await db.rollback()
                        summary["skipped_duplicate"] += 1

            except Exception as exc:
                logger.exception(
                    "sft_curator row failed: msg=%s err=%s", msg.id, exc,
                )
                summary["errors"] += 1
                await db.rollback()

        await db.commit()

    logger.info("sft_curator run summary: %s", summary)
    return summary


# ============================================================================
# Helpers
# ============================================================================


def _assign_split(message_id: UUID) -> str:
    h = hashlib.sha256(str(message_id).encode()).hexdigest()[:8]
    bucket = int(h, 16) % 100
    if bucket < SPLIT_TRAIN_BUCKET:
        return "train"
    if bucket < SPLIT_VAL_BUCKET:
        return "val"
    return "test"


def _build_input_payload(user_msg: Message, assistant_msg: Message) -> dict[str, Any]:
    """ChatML format input: user query + sources context."""
    sources_block = ""
    if assistant_msg.sources_used:
        src_lines = []
        for i, s in enumerate(assistant_msg.sources_used[:10], start=1):
            if isinstance(s, dict):
                title = s.get("title") or ""
                source = s.get("source_name") or ""
                src_lines.append(f"[{i}] {source} — {title}")
        if src_lines:
            sources_block = "\n\nKaynaklar:\n" + "\n".join(src_lines)

    # #1013 (Faz 2a) — L1 görünmez bağlam gelince ham follow-up
    # ("Ankara'da ne yapacakmış?") tek başına eğitim INPUT'u olarak
    # KOPUK kalır; condense sonrası standalone effective_query cevabı
    # gerçekte ÜRETEN sorgudur → INPUT olarak onu kullan (self-contained).
    # effective_query yoksa (eski örnek / rewrite yok) ham content'e
    # düşülür — geriye-uyum, davranış değişmez.
    eq = (assistant_msg.effective_query or "").strip()
    effective = eq or user_msg.content
    rewritten = bool(eq and eq != (user_msg.content or "").strip())

    return {
        "messages": [
            {"role": "user", "content": effective + sources_block},
        ],
        # S8 — şema/provenance sürümü: effective_query'li örnekler
        # ham-input örneklerinden ayırt edilebilsin (heterojen dataset).
        "input_schema_version": "v2-effective_query",
        "raw_user_content": user_msg.content,
        "effective_query": assistant_msg.effective_query,
        "effective_query_rewritten": rewritten,
        # Metadata — train framework opsiyonel olarak okuyabilir
        "conversation_id": str(user_msg.conversation_id),
        "user_message_id": str(user_msg.id),
        "assistant_message_id": str(assistant_msg.id),
    }


def _compute_quality_signals(msg: Message) -> dict[str, Any]:
    """Quality signals — admin/sft dashboard'da gösterilir."""
    return {
        "char_count": len(msg.content or ""),
        "source_count": len(msg.sources_used or []) if msg.sources_used else 0,
        "user_action": msg.user_action,
        "edit_distance": float(msg.edit_distance) if msg.edit_distance is not None else None,
        "halu_flagged": msg.halu_flagged_at is not None,
        "dpo_rejected": msg.dpo_rejected,
        "has_dpo_chosen": bool(msg.dpo_chosen_content),
        "has_thinking_steps": bool(msg.thinking_steps),
    }
