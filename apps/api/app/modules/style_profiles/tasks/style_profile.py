"""Style profile analyzer Celery task (#52, Faz 5).

docs/engineering/prompt-contracts.md §5.1
PRD §5.3

Trigger:
    /app/style-profiles POST sonrası (manuel)
    /app/style-profiles/{id}/samples POST sonrası (sample sayısı eşiği aşınca)

Pipeline:
    style_profile_id → samples fetch (status='pending'|'analyzing')
        → render_user_payload + system prompt
        → DeepSeek V4 Flash generate_text (json_mode)
        → parse_response → JSON sanity
        → style_profiles UPDATE (status='ready', rules_json doldurulur)

Errors:
    - DEEPSEEK_API_KEY yok → status='failed' (manuel retry)
    - sample_count < MIN_SAMPLES → status='failed' (kullanıcı daha örnek eklesin)
    - LLM transient → autoretry (max 2x)
    - parse error → status='failed' + error_message
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.cost_tracker import track_provider_call
from app.modules.style_profiles.models import StyleProfile, StyleSample
from app.prompts.style_analyzer import (
    MIN_SAMPLES,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    parse_response,
    render_user_payload,
)
from app.providers.base import Message
from app.providers.registry import bootstrap_default_providers, registry
from app.shared.runtime_config.prompts_store import prompts_store
from app.shared.workers.db_session import _run_async, open_session
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _ensure_providers() -> None:
    try:
        bootstrap_default_providers()
    except Exception as exc:  # pragma: no cover
        logger.warning("Style analyzer provider bootstrap failed: %s", exc)


async def _analyze_style_profile_async(profile_id: UUID) -> dict:
    summary: dict = {"profile_id": str(profile_id), "status": "unknown"}
    _ensure_providers()

    try:
        provider = registry.route_for_tier(operation="chat", tier="free")
    except RuntimeError:
        async with open_session() as db:
            await _mark_failed(db, profile_id, "no_chat_provider")
        summary["status"] = "skipped"
        summary["reason"] = "no_chat_provider"
        return summary

    if not getattr(provider, "supports_chat", False):
        async with open_session() as db:
            await _mark_failed(db, profile_id, "provider_no_chat")
        summary["status"] = "skipped"
        summary["reason"] = "provider_no_chat"
        return summary

    async with open_session() as db:
        profile = await db.get(StyleProfile, profile_id)
        if profile is None:
            summary["status"] = "not_found"
            return summary

        # Sample fetch
        samples_rows = (
            (
                await db.execute(
                    select(StyleSample)
                    .where(StyleSample.style_profile_id == profile_id)
                    .order_by(StyleSample.created_at)
                )
            )
            .scalars()
            .all()
        )

        if len(samples_rows) < MIN_SAMPLES:
            await _mark_failed(
                db,
                profile_id,
                f"insufficient_samples ({len(samples_rows)}<{MIN_SAMPLES})",
            )
            summary["status"] = "failed"
            summary["reason"] = "insufficient_samples"
            return summary

        # status='analyzing'
        profile.status = "analyzing"
        profile.error_message = None
        profile.updated_at = datetime.now(UTC)
        await db.commit()

        # Render
        user_payload = render_user_payload(
            [{"text": s.text, "source_url": s.source_url} for s in samples_rows]
        )

        # #720: prompts_store override (admin /prompts üzerinden editable)
        style_prompt = await prompts_store.get(db, "style_analyzer", SYSTEM_PROMPT)
        try:
            async with track_provider_call(
                db=db,
                provider=provider.name,
                operation="chat",
            ) as tracker:
                generation = await provider.generate_text(
                    messages=[
                        Message(role="system", content=style_prompt),
                        Message(role="user", content=user_payload),
                    ],
                    max_tokens=2000,
                    temperature=0.2,
                    json_mode=True,
                )
                tracker.record(
                    input_tokens=generation.input_tokens,
                    output_tokens=generation.output_tokens,
                    cached_tokens=getattr(generation, "cached_input_tokens", None),
                    model=generation.model,
                )
        except Exception as exc:
            logger.exception("style_analyzer LLM failed pid=%s", profile_id)
            await _mark_failed(db, profile_id, f"llm_error: {type(exc).__name__}")
            summary["status"] = "failed"
            summary["reason"] = "llm_error"
            return summary

        # Parse
        try:
            rules = parse_response(generation.text)
        except Exception as exc:
            logger.warning(
                "style_analyzer parse failed pid=%s err=%s raw=%s",
                profile_id,
                exc,
                generation.text[:300],
            )
            await _mark_failed(db, profile_id, f"parse_error: {exc}")
            summary["status"] = "failed"
            summary["reason"] = "parse_error"
            return summary

        # Persist
        profile.style_summary = (rules.get("style_summary") or "")[:2000]
        profile.rules_json = rules
        profile.sample_count = len(samples_rows)
        profile.status = "ready"
        profile.error_message = None
        profile.analyzed_at = datetime.now(UTC)
        profile.updated_at = profile.analyzed_at
        await db.commit()

        summary["status"] = "ready"
        summary["sample_count"] = len(samples_rows)
        summary["prompt_version"] = PROMPT_VERSION
        return summary


async def _mark_failed(db, profile_id: UUID, reason: str) -> None:
    profile = await db.get(StyleProfile, profile_id)
    if profile is None:
        return
    profile.status = "failed"
    profile.error_message = reason[:2000]
    profile.updated_at = datetime.now(UTC)
    await db.commit()


@celery_app.task(
    name="tasks.style_profile.analyze",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=2,
)
def analyze_style_profile(self, profile_id: str) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_analyze_style_profile_async(UUID(profile_id)))
