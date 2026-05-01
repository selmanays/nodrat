"""Agenda card generator Celery task (#21).

Trigger: Cluster oluştuğunda + her 6 saatte refresh (architecture.md §3.3).

Pipeline:
    cluster → 5-20 article fetch (related event_articles)
        → render_user_payload + system prompt
        → DeepSeek V3 generate_text
        → parse_response → schema valid mi?
        → agenda_cards UPSERT (per cluster latest)

Errors:
    - DEEPSEEK_API_KEY yok → skip (registry returns no provider)
    - LLM error → autoretry
    - parse error → status='failed' generation, not persisted
    - insufficient_data → AgendaCard NOT created (event_count < 2)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cost_tracker import track_provider_call
from app.models.agenda import AgendaCard
from app.models.article import Article
from app.models.event import EventArticle, EventCluster
from app.models.source import Source
from app.prompts.agenda_card import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    AgendaCardError,
    AgendaCardOutput,
    parse_response,
    render_user_payload,
)
from app.providers.base import Message, ProviderError
from app.providers.registry import bootstrap_default_providers, registry
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _run_async, open_session


logger = logging.getLogger(__name__)


_BOOTSTRAPPED = False


def _ensure_providers() -> None:
    global _BOOTSTRAPPED
    if not _BOOTSTRAPPED:
        bootstrap_default_providers()
        _BOOTSTRAPPED = True


# Min cluster article_count for agenda card generation
MIN_ARTICLES_FOR_AGENDA = 1  # MVP-1: 1 article'lı bile generate (Faz 2 sonrası 2 yapılır)
MAX_ARTICLES_PER_CARD = 20


async def _fetch_cluster_data(
    db: AsyncSession, event_id: UUID
) -> tuple[EventCluster | None, list[dict]]:
    """Cluster + bağlı article'ları (sources.name ile) çek."""
    cluster = await db.get(EventCluster, event_id)
    if cluster is None:
        return None, []

    rows = (
        await db.execute(
            sa_text(
                """
                SELECT
                    a.id, a.title, a.subtitle, a.published_at,
                    a.canonical_url, a.clean_text,
                    s.name AS source_name, s.reliability_score AS source_reliability
                FROM event_articles ea
                JOIN articles a ON a.id = ea.article_id
                JOIN sources s ON s.id = a.source_id
                WHERE ea.event_id = :eid
                ORDER BY a.published_at DESC NULLS LAST
                LIMIT :max
                """
            ),
            {"eid": str(event_id), "max": MAX_ARTICLES_PER_CARD},
        )
    ).mappings().all()

    return cluster, [dict(r) for r in rows]


async def _generate_agenda_card_async(event_id: UUID) -> dict:
    """Cluster'dan agenda card üret + DB'ye persist."""
    _ensure_providers()
    summary: dict = {"event_id": str(event_id), "status": "unknown"}

    # Provider seç
    try:
        provider = registry.route_for_tier(operation="chat", tier="free")
    except RuntimeError:
        summary["status"] = "skipped"
        summary["reason"] = "no_chat_provider"
        return summary

    if not provider.supports_chat:
        summary["status"] = "skipped"
        summary["reason"] = "provider_no_chat"
        return summary

    async with open_session() as db:
        cluster, articles = await _fetch_cluster_data(db, event_id)
        if cluster is None:
            summary["status"] = "not_found"
            return summary

        if len(articles) < MIN_ARTICLES_FOR_AGENDA:
            summary["status"] = "skipped"
            summary["reason"] = f"insufficient_articles ({len(articles)})"
            return summary

        # Render payload
        user_message_str = render_user_payload(
            event_cluster={
                "id": str(cluster.id),
                "canonical_title": cluster.canonical_title,
                "first_seen_at": cluster.first_seen_at,
                "last_seen_at": cluster.last_seen_at,
                "article_count": cluster.article_count,
                "source_count": cluster.source_count,
            },
            articles=articles,
        )

        # Provider call (cost tracker ile)
        try:
            async with track_provider_call(
                db=db,
                provider=provider.name,
                operation="chat",
            ) as tracker:
                generation = await provider.generate_text(
                    messages=[
                        Message(role="system", content=SYSTEM_PROMPT),
                        Message(role="user", content=user_message_str),
                    ],
                    max_tokens=1500,
                    temperature=0.3,  # düşük — halüsinasyonu azalt
                )
                tracker.record(
                    input_tokens=generation.input_tokens,
                    output_tokens=generation.output_tokens,
                    model=generation.model,
                    cost_usd=generation.cost_usd,
                )
        except ProviderError as exc:
            summary["status"] = "provider_error"
            summary["error"] = str(exc)[:300]
            await db.commit()  # cost log
            return summary

        # Parse response
        parsed = parse_response(generation.text)

        if isinstance(parsed, AgendaCardError):
            summary["status"] = "parse_error"
            summary["error_type"] = parsed.error
            summary["reason"] = parsed.reason
            await db.commit()
            return summary

        # UPSERT (per cluster latest agenda card — yeni record)
        # Eski agenda_card varsa update et; yoksa insert.
        existing = (
            await db.execute(
                select(AgendaCard).where(AgendaCard.event_id == cluster.id)
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if existing is not None:
            existing.title = parsed.title[:500]
            existing.summary = parsed.summary
            existing.key_points = parsed.key_points
            existing.content_angles = parsed.content_angles
            existing.timeline = parsed.timeline
            existing.source_refs = parsed.source_refs
            existing.status = parsed.status
            existing.importance_score = Decimal(str(parsed.importance_score))
            existing.freshness_score = Decimal(str(parsed.freshness_score))
            existing.generated_by_model = generation.model
            existing.updated_at = now
            agenda_id = existing.id
        else:
            new_card = AgendaCard(
                event_id=cluster.id,
                title=parsed.title[:500],
                summary=parsed.summary,
                key_points=parsed.key_points,
                content_angles=parsed.content_angles,
                timeline=parsed.timeline,
                source_refs=parsed.source_refs,
                status=parsed.status,
                importance_score=Decimal(str(parsed.importance_score)),
                freshness_score=Decimal(str(parsed.freshness_score)),
                generated_by_model=generation.model,
            )
            db.add(new_card)
            await db.flush()
            agenda_id = new_card.id

        await db.commit()

        summary.update(
            {
                "status": "generated",
                "agenda_id": str(agenda_id),
                "title": parsed.title[:80],
                "model": generation.model,
                "input_tokens": generation.input_tokens,
                "output_tokens": generation.output_tokens,
                "cost_usd": generation.cost_usd,
                "warnings": parsed.warnings,
                "prompt_version": PROMPT_VERSION,
            }
        )
        return summary


@celery_app.task(
    name="tasks.agenda.generate_agenda_card",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=2,
)
def generate_agenda_card(self, event_id: str) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_generate_agenda_card_async(UUID(event_id)))


# ============================================================================
# Refresh task — Beat 6 saatte bir
# ============================================================================


async def _refresh_active_cards_async() -> dict:
    """Active + cooling cluster'lar için agenda card refresh."""
    async with open_session() as db:
        rows = (
            await db.execute(
                sa_text(
                    """
                    SELECT id FROM event_clusters
                    WHERE status IN ('developing', 'active', 'cooling')
                    ORDER BY last_updated_at DESC
                    LIMIT 50
                    """
                )
            )
        ).all()

    dispatched = 0
    for row in rows:
        try:
            generate_agenda_card.apply_async(args=[str(row[0])])
            dispatched += 1
        except Exception as exc:  # pragma: no cover
            logger.exception("dispatch agenda failed eid=%s err=%s", row[0], exc)

    return {"dispatched": dispatched}


@celery_app.task(name="tasks.agenda.refresh_active_cards", bind=True)
def refresh_active_cards(self) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_refresh_active_cards_async())
