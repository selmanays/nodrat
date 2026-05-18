"""Agenda card generator Celery task (#21).

Trigger: Cluster oluştuğunda + her 6 saatte refresh (architecture.md §3.3).

Pipeline:
    cluster → 5-20 article fetch (related event_articles)
        → render_user_payload + system prompt
        → DeepSeek V4 Flash generate_text
        → parse_response → schema valid mi?
        → agenda_cards UPSERT (per cluster latest)

Errors:
    - DEEPSEEK_API_KEY yok → skip (registry returns no provider)
    - LLM error → autoretry
    - parse error → status='failed' generation, not persisted
    - insufficient_data → AgendaCard NOT created (event_count < 2)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cost_tracker import track_provider_call
from app.core.prompts_store import prompts_store
from app.models.agenda import AgendaCard
from app.models.event import EventCluster
from app.prompts.agenda_card import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    AgendaCardError,
    parse_response,
    render_user_payload,
)
from app.prompts.country_backfill import SYSTEM_PROMPT as _COUNTRY_PROMPT
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


async def _embed_and_store_agenda_card(
    *,
    db: AsyncSession,
    agenda_id: UUID,
    title: str,
    summary: str,
) -> None:
    """Agenda card için embedding hesapla + DB'ye yaz (#169).

    title + summary birleştirilip bge-m3'e gönderilir, vector(1024)
    agenda_cards.embedding column'una yazılır. RAG retrieval bu
    embedding üzerinde cosine similarity yapar.
    """
    _ensure_providers()
    provider = registry.route_for_tier(operation="embedding", tier="free")

    # title + summary birleşik metin (LLM zaten 100-2000 char özet üretti)
    combined = f"{title.strip()}\n\n{summary.strip()}"[:4000]

    result = await provider.create_embedding([combined])
    if not result.vectors or len(result.vectors[0]) != 1024:
        raise RuntimeError(
            f"agenda_card embedding unexpected dim: "
            f"got {len(result.vectors[0]) if result.vectors else 0}, expected 1024"
        )

    vec_str = "[" + ",".join(f"{v:.7f}" for v in result.vectors[0]) + "]"
    await db.execute(
        sa_text(
            """
            UPDATE agenda_cards
            SET embedding = (:vec)::vector
            WHERE id = :aid
            """
        ),
        {"vec": vec_str, "aid": str(agenda_id)},
    )
    await db.commit()
    logger.info(
        "agenda_card embedding stored agenda=%s model=%s",
        agenda_id,
        result.model,
    )


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
        # #270 PR-B — runtime prompt override + #272 PR-D — task params
        agenda_system = SYSTEM_PROMPT
        ag_max_tokens = 2800
        ag_temperature = 0.3
        try:
            from app.core.prompts_store import prompts_store
            from app.core.settings_store import settings_store

            agenda_system = await prompts_store.get(
                db, "agenda_card", SYSTEM_PROMPT
            )
            ag_max_tokens = await settings_store.get_int(
                db, "llm.agenda_max_tokens", 2800
            )
            ag_temperature = await settings_store.get_float(
                db, "llm.agenda_temperature", 0.3
            )
        except Exception:  # pragma: no cover
            pass

        try:
            async with track_provider_call(
                db=db,
                provider=provider.name,
                operation="chat",
            ) as tracker:
                generation = await provider.generate_text(
                    messages=[
                        Message(role="system", content=agenda_system),
                        Message(role="user", content=user_message_str),
                    ],
                    # #175 — 1500 token bazı 3+ article cluster'larda JSON truncate
                    # ediyordu ("Unterminated string"). 2800 emniyetli sınır.
                    max_tokens=ag_max_tokens,
                    temperature=ag_temperature,
                    json_mode=True,  # #171 PR-E — DeepSeek deterministic JSON
                )
                tracker.record(
                    input_tokens=generation.input_tokens,
                    output_tokens=generation.output_tokens,
                    cached_tokens=getattr(generation, "cached_input_tokens", 0),
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

        now = datetime.now(UTC)
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
            existing.country = parsed.country  # #210
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
                country=parsed.country,  # #210
                generated_by_model=generation.model,
            )
            db.add(new_card)
            await db.flush()
            agenda_id = new_card.id

        await db.commit()

        # #169 — Agenda card embedding (title + summary'den)
        # RAG retrieval için zorunlu: agenda_cards.embedding pgvector cosine search
        try:
            await _embed_and_store_agenda_card(
                db=db,
                agenda_id=agenda_id,
                title=parsed.title,
                summary=parsed.summary,
            )
        except Exception as emb_exc:
            # Embedding hatası agenda card'ı bozmasın (fallback: NULL kalır)
            logger.warning(
                "agenda_card embedding failed agenda=%s err=%s",
                agenda_id,
                emb_exc,
            )

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


# ============================================================================
# #228 — Country backfill task (NULL kartları toplu re-tag)
# ============================================================================


# #720: _COUNTRY_PROMPT app.prompts.country_backfill modülüne taşındı.
# Yukarıdaki import: SYSTEM_PROMPT as _COUNTRY_PROMPT (backward-compat name).


def _parse_country_response(text: str) -> str | None:
    """LLM '... TR' tarzı yanıtlardan ISO 2-char kod çıkar."""
    if not text:
        return None
    cleaned = text.strip().strip('"\'`').upper()
    if cleaned == "NULL":
        return None
    # İlk 2 ardışık harfli token
    import re

    match = re.search(r"\b([A-Z]{2})\b", cleaned)
    if match:
        code = match.group(1)
        if code in {
            "TR", "US", "DE", "FR", "GB", "IL", "PS", "LB", "RU",
            "UA", "SY", "IR", "GR", "CY", "AT", "CU", "JP", "CN",
            "IN", "EG", "SA", "AE", "NL", "BE", "ES", "IT", "PL",
            "SE", "NO", "DK", "FI", "BR", "MX", "AR", "CA", "AU",
            "KR", "TW", "TH", "VN", "ID", "PH", "MY", "SG",
        }:
            return code
    return None


async def _backfill_country_async(batch: int = 50) -> dict:
    """NULL country olan agenda card'lar için DeepSeek ile country tagging."""
    _ensure_providers()
    summary: dict = {"requested": batch, "tagged": 0, "skipped": 0, "errors": 0}

    try:
        provider = registry.route_for_tier(operation="chat", tier="free")
    except RuntimeError:
        summary["status"] = "no_chat_provider"
        return summary

    async with open_session() as db:
        rows = (
            await db.execute(
                sa_text(
                    """
                    SELECT id::text AS id, title, LEFT(summary, 600) AS summary
                    FROM agenda_cards
                    WHERE country IS NULL
                      AND level = 'daily'
                    ORDER BY updated_at DESC
                    LIMIT :batch
                    """
                ),
                {"batch": batch},
            )
        ).mappings().all()

        if not rows:
            summary["status"] = "no_null_cards"
            return summary

        # #720: prompts_store override (admin /prompts üzerinden editable)
        country_prompt = await prompts_store.get(
            db, "agenda_country_backfill", _COUNTRY_PROMPT
        )
        for row in rows:
            user_msg = (
                f"Başlık: {row['title']}\n\nÖzet: {row['summary']}\n\n"
                "Country (ISO2 ya da null):"
            )
            try:
                async with track_provider_call(
                    db=db,
                    provider=provider.name,
                    operation="chat",
                ) as tracker:
                    # #272 PR-D — runtime country backfill max_tokens
                    cb_max = 10
                    try:
                        from app.core.settings_store import settings_store

                        cb_max = await settings_store.get_int(
                            db, "llm.country_backfill_max_tokens", 10
                        )
                    except Exception:  # pragma: no cover
                        pass
                    gen = await provider.generate_text(
                        messages=[
                            Message(role="system", content=country_prompt),
                            Message(role="user", content=user_msg),
                        ],
                        max_tokens=cb_max,
                        temperature=0.0,
                    )
                    tracker.record(
                        input_tokens=gen.input_tokens,
                        output_tokens=gen.output_tokens,
                        cached_tokens=getattr(gen, "cached_input_tokens", 0),
                        model=gen.model,
                        cost_usd=gen.cost_usd,
                    )
            except ProviderError as exc:
                logger.warning("country backfill provider err: %s", exc)
                summary["errors"] += 1
                continue

            country = _parse_country_response(gen.text)
            if country is None:
                summary["skipped"] += 1
                # Yine de DB'ye dokun ki tekrar çekilmesin (sentinel "??")
                # Aslında: NULL kalsın, sonraki run tekrar denesin
                continue

            await db.execute(
                sa_text("UPDATE agenda_cards SET country = :c WHERE id = :id"),
                {"c": country, "id": row["id"]},
            )
            summary["tagged"] += 1

        await db.commit()

    summary["status"] = "ok"
    return summary


@celery_app.task(name="tasks.agenda.backfill_country", bind=True)
def backfill_country(self, batch: int = 50) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_backfill_country_async(batch))
