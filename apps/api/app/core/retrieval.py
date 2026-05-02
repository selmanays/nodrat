"""Vector retrieval (#22) — pgvector + freshness + reliability scoring.

PRD §2.7 (final retrieval score)
docs/engineering/data-model.md §4.1 (article_chunks)

Algoritma:
  1. Query embedding üret (NIM)
  2. Top-K candidate'i pgvector cosine_similarity ile çek (3-5x of needed)
  3. Final score:
     final_score = semantic*0.50 + freshness*0.25 + importance*0.15 + reliability*0.10
     (current mod: semantic*0.45 + freshness*0.35 + importance*0.10 + reliability*0.10)
  4. Sort by final_score desc, top-K döndür

Retrieval modes:
  - current  : son 24h → 48h → 72h fallback (PRD §2.9)
  - weekly   : Faz 2 (out of scope MVP-1 cut-list)
  - archive  : Faz 2

Kabul: latency hedef <200ms p50 (DB + embed call dahil değil — sadece SQL).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


RetrievalMode = Literal["current", "weekly", "archive"]


# Score weight presets
WEIGHTS_DEFAULT = {
    "semantic": 0.50,
    "freshness": 0.25,
    "importance": 0.15,
    "reliability": 0.10,
}
WEIGHTS_CURRENT = {
    "semantic": 0.45,
    "freshness": 0.35,
    "importance": 0.10,
    "reliability": 0.10,
}

# Current mode time fallback levels (saat)
CURRENT_MODE_FALLBACKS_HOURS = (24, 48, 72)


@dataclass
class RetrievedChunk:
    """Tek arama sonucu — caller bu listeyle agenda card / generation yapar."""

    chunk_id: UUID
    article_id: UUID
    source_id: UUID
    chunk_index: int
    chunk_text: str
    article_title: str
    article_canonical_url: str
    source_name: str | None
    source_slug: str | None
    source_reliability: float
    published_at: datetime | None

    semantic_score: float
    """Cosine similarity (0..1) — pgvector 1 - cosine_distance"""

    freshness_score: float
    """Time-decay score (0..1)"""

    importance_score: float
    """Article-level importance — MVP-1: 0.5 placeholder, Faz 2 sonu calc"""

    reliability_score: float
    """Source reliability (0..1)"""

    final_score: float


@dataclass
class RetrievalReport:
    """Tüm arama sonucu + telemetri."""

    chunks: list[RetrievedChunk]
    mode_used: str
    """current_24h / current_48h / current_72h / weekly / archive"""

    candidate_count: int
    """SQL'den dönen aday sayısı (rerank öncesi)"""

    weights_used: dict[str, float]


# ============================================================================
# Score helpers
# ============================================================================


def freshness_decay(published_at: datetime | None, *, half_life_hours: float = 24.0) -> float:
    """Time-decay score: yeni → 1, eski → 0.

    Half-life modeli: half_life_hours geçtikçe skor /2.
    None published_at → 0.5 (orta).
    """
    if published_at is None:
        return 0.5
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    delta_hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
    if half_life_hours <= 0:
        return 1.0
    decay = math.pow(0.5, delta_hours / half_life_hours)
    return max(0.0, min(1.0, decay))


def compute_final_score(
    *,
    semantic: float,
    freshness: float,
    importance: float,
    reliability: float,
    weights: dict[str, float],
) -> float:
    return (
        semantic * weights["semantic"]
        + freshness * weights["freshness"]
        + importance * weights["importance"]
        + reliability * weights["reliability"]
    )


# ============================================================================
# Vector serialization
# ============================================================================


def _vector_to_pg_literal(vector: list[float]) -> str:
    """pgvector literal: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"


# ============================================================================
# SQL retrieval
# ============================================================================


async def _fetch_candidates(
    db: AsyncSession,
    *,
    query_vector: list[float],
    since: datetime | None,
    candidate_limit: int,
    source_id: UUID | None = None,
) -> list[dict]:
    """pgvector cosine similarity + JOIN sources.

    cosine_distance: 0 (identical) → 2 (opposite); semantic_score = 1 - cosine_distance/2
    pgvector <=> operator returns cosine distance (0 to 2).

    Note: hidden in raw SQL since article_chunks ORM model not defined yet.
    """
    vec_lit = _vector_to_pg_literal(query_vector)
    params: dict = {"vec": vec_lit, "limit": candidate_limit}
    where_clauses = ["c.embedding IS NOT NULL"]

    if since is not None:
        where_clauses.append(
            "(c.published_at IS NULL OR c.published_at >= :since)"
        )
        params["since"] = since

    if source_id is not None:
        where_clauses.append("c.source_id = :source_id")
        params["source_id"] = str(source_id)

    where_sql = " AND ".join(where_clauses)

    sql = sa_text(
        f"""
        SELECT
            c.id AS chunk_id,
            c.article_id,
            c.source_id,
            c.chunk_index,
            c.chunk_text,
            c.published_at,
            a.title AS article_title,
            a.canonical_url AS article_canonical_url,
            s.name AS source_name,
            s.slug AS source_slug,
            s.reliability_score AS source_reliability,
            (c.embedding <=> (:vec)::vector) AS distance
        FROM article_chunks c
        JOIN articles a ON a.id = c.article_id
        JOIN sources s ON s.id = c.source_id
        WHERE {where_sql}
        ORDER BY c.embedding <=> (:vec)::vector
        LIMIT :limit
        """
    )

    rows = (await db.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


# ============================================================================
# Public API
# ============================================================================


async def search(
    db: AsyncSession,
    *,
    query_vector: list[float],
    mode: RetrievalMode = "current",
    top_k: int = 10,
    candidate_multiplier: int = 5,
    source_id: UUID | None = None,
    custom_since: datetime | None = None,
    min_semantic_score: float = 0.45,
) -> RetrievalReport:
    """Top-K chunks için search.

    Args:
        query_vector: embedded user query (NIM çıktısı)
        mode: 'current' (default), 'weekly', 'archive'
        top_k: nihai döndürülecek sayı (default 10)
        candidate_multiplier: SQL'den top_k * mult kadar aday çekilir, sonra rerank
        source_id: opsiyonel kaynak filtresi
        custom_since: opsiyonel time filter override

    Returns:
        RetrievalReport (chunks + mode_used + candidate_count + weights)
    """
    if not query_vector:
        return RetrievalReport(
            chunks=[],
            mode_used=mode,
            candidate_count=0,
            weights_used=WEIGHTS_DEFAULT,
        )

    weights = WEIGHTS_CURRENT if mode == "current" else WEIGHTS_DEFAULT
    candidate_limit = max(top_k * candidate_multiplier, top_k)

    # Mode-specific time filter + fallback
    fallback_used: str = mode

    if mode == "current":
        # 24h → 48h → 72h fallback
        for hours in CURRENT_MODE_FALLBACKS_HOURS:
            since = (
                custom_since
                if custom_since is not None
                else datetime.now(timezone.utc) - timedelta(hours=hours)
            )
            rows = await _fetch_candidates(
                db,
                query_vector=query_vector,
                since=since,
                candidate_limit=candidate_limit,
                source_id=source_id,
            )
            if rows:
                fallback_used = f"current_{hours}h"
                break
        else:
            rows = []
    elif mode == "weekly":
        since = (
            custom_since
            if custom_since is not None
            else datetime.now(timezone.utc) - timedelta(days=7)
        )
        rows = await _fetch_candidates(
            db,
            query_vector=query_vector,
            since=since,
            candidate_limit=candidate_limit,
            source_id=source_id,
        )
    else:  # archive
        rows = await _fetch_candidates(
            db,
            query_vector=query_vector,
            since=custom_since,
            candidate_limit=candidate_limit,
            source_id=source_id,
        )

    # Score + rerank
    enriched: list[RetrievedChunk] = []
    for row in rows:
        # cosine_distance 0..2 → semantic 0..1 (cos distance / 2 reversed)
        cos_dist = float(row.get("distance") or 0)
        semantic = max(0.0, min(1.0, 1.0 - (cos_dist / 2.0)))

        published_at = row.get("published_at")
        freshness = freshness_decay(published_at)

        # importance MVP-1 placeholder — Faz 2 sonu source reliability * recency benzeri
        importance = 0.5

        reliability = float(row.get("source_reliability") or 0.7)

        final = compute_final_score(
            semantic=semantic,
            freshness=freshness,
            importance=importance,
            reliability=reliability,
            weights=weights,
        )

        enriched.append(
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                article_id=row["article_id"],
                source_id=row["source_id"],
                chunk_index=row["chunk_index"],
                chunk_text=row["chunk_text"],
                article_title=row["article_title"],
                article_canonical_url=row["article_canonical_url"],
                source_name=row["source_name"],
                source_slug=row["source_slug"],
                source_reliability=reliability,
                published_at=published_at,
                semantic_score=round(semantic, 4),
                freshness_score=round(freshness, 4),
                importance_score=round(importance, 4),
                reliability_score=round(reliability, 4),
                final_score=round(final, 4),
            )
        )

    # #157 — Halüsinasyon koruması: alakasız sonuçları filtrele.
    # Cosine sim < min_semantic_score → query ile gerçekten alakasız demek.
    # Empty result halinde insufficiency'e gider (PRD §3.4).
    if min_semantic_score > 0:
        before_count = len(enriched)
        enriched = [c for c in enriched if c.semantic_score >= min_semantic_score]
        filtered_out = before_count - len(enriched)
        if filtered_out > 0:
            import logging
            logging.getLogger(__name__).info(
                "retrieval.filtered_low_relevance count=%d threshold=%.2f",
                filtered_out,
                min_semantic_score,
            )

    enriched.sort(key=lambda c: c.final_score, reverse=True)
    top = enriched[:top_k]

    return RetrievalReport(
        chunks=top,
        mode_used=fallback_used,
        candidate_count=len(rows),
        weights_used=weights,
    )
