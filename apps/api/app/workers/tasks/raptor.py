"""RAPTOR-Lite — hierarchical agenda clustering (#182).

Mevcut tek-seviye agenda_cards (level='daily') sistemine ikinci seviye
ekler: günlük cluster'ları haftalık tema kart'lara birleştirir.

Beat: günlük 02:00 UTC çalışır.

Akış:
    1. Son 7 gün daily agenda card'ları çek (status active/developing/cooling)
    2. Embedding cosine clustering (threshold 0.75)
    3. Min 2 daily card'lık cluster'lar için DeepSeek özet üret
    4. UPSERT level='weekly' card → parent yok (üst seviye)
    5. Her daily card'ın parent_card_id'sini set et (cluster'a aitse)

RAGFlow rag/raptor.py esinlenmesi (basitleştirilmiş — UMAP/GMM yok).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cost_tracker import track_provider_call
from app.models.agenda import AgendaCard
from app.providers.base import Message, ProviderError
from app.providers.registry import bootstrap_default_providers, registry
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _run_async, open_session


logger = logging.getLogger(__name__)


# Hyperparameters
WEEKLY_WINDOW_DAYS = 7
WEEKLY_SIM_THRESHOLD = 0.75
WEEKLY_MIN_CLUSTER_SIZE = 2
WEEKLY_MAX_CLUSTERS_PER_RUN = 8


WEEKLY_SUMMARY_PROMPT = """Sen Nodrat'ın haftalık tema özetleyicisisin. Verilen
günlük agenda kartlarını tek bir haftalık tema altında birleştirip Türkçe
özet üretirsin.

ÇIKTI SADECE JSON OLMALIDIR:

{
  "title": "<haftalık tema başlığı, 50-120 char>",
  "summary": "<200-600 char özet, anahtar gelişmeleri kronolojik olarak>",
  "key_points": ["<3-5 önemli madde>"],
  "importance": <0.0-1.0>
}

KURALLAR:
- "Bu hafta ..." gibi başlangıçlar tercih edilmez; tema doğrudan ifade edilmeli
- Bilgi yoksa uydurma — sadece verilen kartlardaki içerikten yaz
- Başlık günlük kartlardan en kapsayıcı olanı yansıtmalı
- key_points sıralı (önem-desc), her madde 1 cümle
- importance: günlük kartların article_count toplamı log-scale (0..1)
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fetch_daily_cards(db: AsyncSession) -> list[dict]:
    """Son 7 gün daily agenda card'ları (embedding dolu)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=WEEKLY_WINDOW_DAYS)
    rows = (
        await db.execute(
            sa_text(
                """
                SELECT ac.id::text AS id,
                       ac.title,
                       ac.summary,
                       ac.embedding::text AS emb_text,
                       ac.importance_score,
                       ac.event_id::text AS event_id,
                       ac.updated_at,
                       ec.article_count
                FROM agenda_cards ac
                JOIN event_clusters ec ON ec.id = ac.event_id
                WHERE ac.level = 'daily'
                  AND ac.embedding IS NOT NULL
                  AND ec.status IN ('developing', 'active', 'cooling')
                  AND ac.updated_at >= :cutoff
                ORDER BY ec.article_count DESC, ac.updated_at DESC
                """
            ),
            {"cutoff": cutoff},
        )
    ).mappings().all()

    out: list[dict] = []
    for r in rows:
        emb = _parse_vector(r["emb_text"])
        if emb is None:
            continue
        out.append(
            {
                "id": r["id"],
                "title": r["title"],
                "summary": r["summary"] or "",
                "embedding": emb,
                "importance": float(r["importance_score"] or 0.5),
                "event_id": r["event_id"],
                "article_count": int(r["article_count"] or 1),
            }
        )
    return out


def _parse_vector(s: str | None) -> list[float] | None:
    if not s:
        return None
    try:
        inner = s.strip("[] \n")
        return [float(x) for x in inner.split(",") if x.strip()]
    except (ValueError, AttributeError):
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    import math

    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _cluster_daily_cards(cards: list[dict]) -> list[list[dict]]:
    """Greedy single-link clustering with cosine threshold."""
    clusters: list[list[dict]] = []
    used: set[str] = set()

    for i, c in enumerate(cards):
        if c["id"] in used:
            continue
        cluster = [c]
        used.add(c["id"])
        for j in range(i + 1, len(cards)):
            other = cards[j]
            if other["id"] in used:
                continue
            sim = _cosine(c["embedding"], other["embedding"])
            if sim >= WEEKLY_SIM_THRESHOLD:
                cluster.append(other)
                used.add(other["id"])
        if len(cluster) >= WEEKLY_MIN_CLUSTER_SIZE:
            clusters.append(cluster)

    # En önemli ilk
    clusters.sort(
        key=lambda cl: sum(c["article_count"] for c in cl), reverse=True
    )
    return clusters[:WEEKLY_MAX_CLUSTERS_PER_RUN]


def _render_cluster_payload(cluster: list[dict]) -> str:
    """Cluster içeriğini DeepSeek için yapılandır."""
    import json

    docs = [
        {
            "title": c["title"][:200],
            "summary": c["summary"][:500],
            "article_count": c["article_count"],
        }
        for c in cluster
    ]
    return json.dumps(
        {
            "daily_cards_count": len(cluster),
            "daily_cards": docs,
            "instruction": "Tek bir haftalık tema özeti üret (yukarıdaki JSON şemasına uygun).",
        },
        ensure_ascii=False,
    )


def _parse_summary_response(text: str) -> dict | None:
    """LLM JSON output → dict."""
    import json

    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```", 2)
        if len(parts) >= 2:
            content = parts[1]
            if content.startswith("json\n"):
                content = content[5:]
            elif content.startswith("\n"):
                content = content[1:]
            cleaned = content.rstrip("`").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("weekly summary parse failed: %s", exc)
        return None
    if not isinstance(data, dict):
        return None

    title = str(data.get("title") or "")[:500]
    summary = str(data.get("summary") or "")
    if not title or not summary:
        return None

    key_points = data.get("key_points") or []
    if not isinstance(key_points, list):
        key_points = []
    key_points = [str(k)[:200] for k in key_points if k][:6]

    try:
        importance = float(data.get("importance") or 0.5)
    except (ValueError, TypeError):
        importance = 0.5
    importance = max(0.0, min(1.0, importance))

    return {
        "title": title,
        "summary": summary[:2000],
        "key_points": key_points,
        "importance": importance,
    }


# ---------------------------------------------------------------------------
# Build weekly card
# ---------------------------------------------------------------------------


async def _build_weekly_card_async(
    db: AsyncSession, cluster: list[dict]
) -> dict:
    """Tek bir günlük cluster için haftalık card UPSERT."""
    bootstrap_default_providers()

    summary: dict = {"size": len(cluster), "status": "unknown"}

    # En önemli daily card'ı temsilci seç (article_count desc)
    representative = max(cluster, key=lambda c: c["article_count"])
    daily_ids = [c["id"] for c in cluster]

    # LLM çağrısı
    try:
        provider = registry.route_for_tier(operation="chat", tier="free")
    except RuntimeError:
        summary["status"] = "skipped"
        summary["reason"] = "no_chat_provider"
        return summary

    user_msg = _render_cluster_payload(cluster)

    try:
        async with track_provider_call(
            db=db,
            provider=provider.name,
            operation="chat",
        ) as tracker:
            generation = await provider.generate_text(
                messages=[
                    Message(role="system", content=WEEKLY_SUMMARY_PROMPT),
                    Message(role="user", content=user_msg),
                ],
                max_tokens=1800,
                temperature=0.3,
                json_mode=True,
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
        summary["error"] = str(exc)[:200]
        await db.commit()
        return summary

    parsed = _parse_summary_response(generation.text)
    if parsed is None:
        summary["status"] = "parse_error"
        return summary

    # Embedding (title + summary)
    try:
        emb_provider = registry.route_for_tier(
            operation="embedding", tier="free"
        )
        combined = f"{parsed['title']}\n\n{parsed['summary']}"[:4000]
        emb_result = await emb_provider.create_embedding([combined])
        emb_vec = (
            emb_result.vectors[0]
            if emb_result.vectors and len(emb_result.vectors[0]) == 1024
            else None
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("weekly embedding failed: %s", exc)
        emb_vec = None

    # UPSERT — same event_id ile mevcut weekly card var mı?
    existing_id = (
        await db.execute(
            sa_text(
                """
                SELECT id::text
                FROM agenda_cards
                WHERE level = 'weekly'
                  AND event_id = (SELECT event_id FROM agenda_cards WHERE id = :rep_id)
                  AND updated_at >= NOW() - INTERVAL '8 days'
                LIMIT 1
                """
            ),
            {"rep_id": representative["id"]},
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing_id:
        await db.execute(
            sa_text(
                """
                UPDATE agenda_cards
                SET title = :title,
                    summary = :summary,
                    key_points = CAST(:kp AS jsonb),
                    importance_score = :imp,
                    generated_by_model = :model,
                    updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "title": parsed["title"][:500],
                "summary": parsed["summary"],
                "kp": __import__("json").dumps(parsed["key_points"]),
                "imp": Decimal(str(parsed["importance"])),
                "model": generation.model,
                "now": now,
                "id": existing_id,
            },
        )
        weekly_id = existing_id
        summary["action"] = "updated"
    else:
        new_card = AgendaCard(
            event_id=UUID(representative["event_id"]),
            title=parsed["title"][:500],
            summary=parsed["summary"],
            key_points=parsed["key_points"],
            content_angles=[],
            timeline=[],
            source_refs=[
                {"daily_card_id": did} for did in daily_ids
            ],
            status="active",
            importance_score=Decimal(str(parsed["importance"])),
            freshness_score=Decimal("1.00"),
            generated_by_model=generation.model,
            level="weekly",
        )
        db.add(new_card)
        await db.flush()
        weekly_id = str(new_card.id)
        summary["action"] = "created"

    # Embedding yaz
    if emb_vec:
        vec_str = "[" + ",".join(f"{v:.7f}" for v in emb_vec) + "]"
        await db.execute(
            sa_text(
                "UPDATE agenda_cards SET embedding = (:vec)::vector WHERE id = :id"
            ),
            {"vec": vec_str, "id": weekly_id},
        )

    # Daily card'ların parent'ını set et
    for daily_id in daily_ids:
        await db.execute(
            sa_text(
                "UPDATE agenda_cards SET parent_card_id = :pid WHERE id = :id"
            ),
            {"pid": weekly_id, "id": daily_id},
        )

    await db.commit()

    summary["status"] = "ok"
    summary["weekly_id"] = weekly_id
    summary["title"] = parsed["title"][:80]
    summary["daily_count"] = len(cluster)
    return summary


# ---------------------------------------------------------------------------
# Beat task
# ---------------------------------------------------------------------------


async def _build_weekly_summary_cards_async() -> dict:
    """RAPTOR-Lite günlük 02:00 UTC: haftalık tema kart'ları üret."""
    async with open_session() as db:
        cards = await _fetch_daily_cards(db)
        logger.info("raptor: daily_cards=%d", len(cards))

        clusters = _cluster_daily_cards(cards)
        logger.info("raptor: clusters=%d", len(clusters))

        results: list[dict] = []
        for cluster in clusters:
            try:
                res = await _build_weekly_card_async(db, cluster)
                results.append(res)
            except Exception as exc:  # pragma: no cover
                logger.exception("weekly card failed: %s", exc)
                results.append({"status": "exception", "error": str(exc)[:200]})

    summary_out = {
        "daily_count": len(cards),
        "cluster_count": len(clusters),
        "weekly_results": results,
        "ok_count": sum(1 for r in results if r.get("status") == "ok"),
    }
    return summary_out


@celery_app.task(name="tasks.raptor.build_weekly_summary_cards", bind=True)
def build_weekly_summary_cards(self) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_build_weekly_summary_cards_async())
