"""Event clustering algoritması (#20).

PRD §2.5: aynı olaya ait farklı kaynaklı haberleri grup'la.

Strateji (semantic + temporal):
  1. Her cleaned article için:
     - article_chunks[0].embedding (chunk 0 = title + lead) al
     - Son 72h içindeki aktif clusters'da en benzer olanı ara
       (cosine_similarity > SEMANTIC_THRESHOLD)
     - Title trigram similarity > TITLE_THRESHOLD ek filtre
     - Eşleşme varsa article'ı cluster'a ekle (event_articles INSERT)
     - Yoksa yeni cluster oluştur (article'ın embedding'iyle)
  2. Cluster status auto-update:
     - last_seen_at < 72h: active (article_count >= 2) | developing
     - 72h-7d: cooling
     - >7d: stale
     - >30d: archived
  3. Importance score:
     importance = log10(source_count) * 0.5 + log10(article_count) * 0.5
     (clamped 0..1)

Output: ClusteringReport (added/created cluster sayıları + skipped reasons)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


# Eşikler — admin override edilebilir (Faz 2 sonu config tab'ı)
# #247 — eşikler 0.78/0.30 → 0.85/0.40 (farklı spor maçları aynı cluster'a
# alınıyordu; embedding "Süper Lig 32. hafta" bağlamında çok yakın çıkıyor).
SEMANTIC_THRESHOLD = 0.85  # cosine similarity (1 - cosine_distance/2)
TITLE_TRIGRAM_THRESHOLD = 0.40  # pg_trgm similarity (0..1)
WINDOW_HOURS = 72  # cluster matching window


@dataclass
class ClusteringResult:
    """Tek article'ın cluster'a eklenme sonucu."""

    article_id: UUID
    action: str
    """'matched' | 'created' | 'skipped'"""

    event_id: UUID | None = None
    similarity: float | None = None
    reason: str | None = None


@dataclass
class ClusteringReport:
    """Clustering batch sonucu."""

    processed: int = 0
    matched: int = 0
    created: int = 0
    skipped: int = 0
    errors: int = 0
    details: list[ClusteringResult] = field(default_factory=list)


# ============================================================================
# Score helpers
# ============================================================================


def compute_importance_score(*, source_count: int, article_count: int) -> float:
    """log-scale importance: 1 source/1 article → 0, 10/10 → ~1."""
    if source_count <= 0 and article_count <= 0:
        return 0.0
    src_log = math.log10(max(source_count, 1) + 1)
    art_log = math.log10(max(article_count, 1) + 1)
    raw = (src_log * 0.5 + art_log * 0.5) / math.log10(11)  # normalize to ~1 at 10
    return max(0.0, min(1.0, raw))


def compute_status(
    *, last_seen_at: datetime, article_count: int, now: datetime | None = None
) -> str:
    """Status state machine — auto-update."""
    now = now or datetime.now(timezone.utc)
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    age = now - last_seen_at

    if age > timedelta(days=30):
        return "archived"
    if age > timedelta(days=7):
        return "stale"
    if age > timedelta(hours=72):
        return "cooling"
    # Son 72h içinde
    if article_count >= 2:
        return "active"
    return "developing"


# ============================================================================
# Vector serialization (retrieval'le aynı pattern)
# ============================================================================


def _vec_lit(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"


# ============================================================================
# Cluster matching
# ============================================================================


async def find_matching_cluster(
    db: AsyncSession,
    *,
    article_embedding: list[float],
    article_title: str,
    semantic_threshold: float = SEMANTIC_THRESHOLD,
    title_threshold: float = TITLE_TRIGRAM_THRESHOLD,
    window_hours: int = WINDOW_HOURS,
) -> tuple[UUID, float] | None:
    """Aktif window içindeki en benzer cluster'ı bul.

    İki şart birden:
      - cosine_similarity(embedding, cluster.embedding) > semantic_threshold
      - pg_trgm.similarity(title, cluster.canonical_title) > title_threshold

    Returns: (cluster_id, semantic_similarity) or None
    """
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    vec_lit = _vec_lit(article_embedding)

    # ORDER BY: en yakın embedding (cosine_distance ASC = similarity DESC)
    sql = sa_text(
        """
        SELECT
            ec.id,
            ec.canonical_title,
            (1 - (ec.embedding <=> (:vec)::vector) / 2.0) AS semantic_sim,
            similarity(ec.canonical_title, :title) AS title_sim
        FROM event_clusters ec
        WHERE ec.last_seen_at >= :since
          AND ec.embedding IS NOT NULL
          AND ec.status IN ('developing', 'active', 'cooling')
        ORDER BY ec.embedding <=> (:vec)::vector
        LIMIT 5
        """
    )
    rows = (
        await db.execute(
            sql, {"vec": vec_lit, "title": article_title, "since": since}
        )
    ).all()

    for row in rows:
        sem_sim = float(row.semantic_sim or 0)
        title_sim = float(row.title_sim or 0)
        if sem_sim >= semantic_threshold and title_sim >= title_threshold:
            return (row.id, sem_sim)
    return None


async def add_article_to_cluster(
    db: AsyncSession,
    *,
    event_id: UUID,
    article_id: UUID,
    source_id: UUID,
    published_at: datetime | None,
    relationship_score: float,
) -> bool:
    """event_articles INSERT + counters update.

    Returns True if INSERTed, False if duplicate (already in cluster).
    """
    insert_sql = sa_text(
        """
        INSERT INTO event_articles
            (event_id, article_id, source_id, published_at, relationship_score)
        VALUES (:eid, :aid, :sid, :pat, :rel)
        ON CONFLICT (event_id, article_id) DO NOTHING
        RETURNING id
        """
    )
    result = await db.execute(
        insert_sql,
        {
            "eid": str(event_id),
            "aid": str(article_id),
            "sid": str(source_id),
            "pat": published_at,
            "rel": relationship_score,
        },
    )
    inserted = result.scalar_one_or_none()
    if inserted is None:
        return False

    # Cluster counters (article_count + source_count rebuild from event_articles)
    await db.execute(
        sa_text(
            """
            UPDATE event_clusters ec
            SET
                article_count = sub.art_count,
                source_count = sub.src_count,
                last_seen_at = GREATEST(ec.last_seen_at, COALESCE(:pat, ec.last_seen_at)),
                last_updated_at = NOW()
            FROM (
                SELECT
                    COUNT(*) AS art_count,
                    COUNT(DISTINCT source_id) AS src_count
                FROM event_articles
                WHERE event_id = :eid
            ) AS sub
            WHERE ec.id = :eid
            """
        ),
        {"eid": str(event_id), "pat": published_at},
    )
    return True


async def create_cluster(
    db: AsyncSession,
    *,
    canonical_title: str,
    embedding: list[float],
    article_id: UUID,
    source_id: UUID,
    published_at: datetime | None,
) -> UUID:
    """Yeni event_cluster oluştur + ilk article'ı ekle.

    Returns: cluster_id
    """
    seen_at = published_at or datetime.now(timezone.utc)
    vec_lit = _vec_lit(embedding)

    cluster_id_row = await db.execute(
        sa_text(
            """
            INSERT INTO event_clusters
                (canonical_title, embedding, first_seen_at, last_seen_at,
                 status, article_count, source_count)
            VALUES (:title, (:vec)::vector, :seen, :seen, 'developing', 1, 1)
            RETURNING id
            """
        ),
        {"title": canonical_title[:500], "vec": vec_lit, "seen": seen_at},
    )
    cluster_id = cluster_id_row.scalar_one()

    await db.execute(
        sa_text(
            """
            INSERT INTO event_articles
                (event_id, article_id, source_id, published_at, relationship_score)
            VALUES (:eid, :aid, :sid, :pat, 1.0)
            """
        ),
        {
            "eid": str(cluster_id),
            "aid": str(article_id),
            "sid": str(source_id),
            "pat": published_at,
        },
    )
    return cluster_id


# ============================================================================
# Status updater (periyodik task)
# ============================================================================


async def refresh_cluster_statuses(db: AsyncSession) -> dict[str, int]:
    """Tüm cluster'lar için status + importance + freshness update.

    Returns: status başına güncellenen sayaç.
    """
    rows = (
        await db.execute(
            sa_text(
                """
                SELECT id, last_seen_at, article_count, source_count, status
                FROM event_clusters
                WHERE status IN ('developing', 'active', 'cooling', 'stale')
                """
            )
        )
    ).all()

    counts: dict[str, int] = {
        "developing": 0,
        "active": 0,
        "cooling": 0,
        "stale": 0,
        "archived": 0,
        "unchanged": 0,
    }

    now = datetime.now(timezone.utc)

    for row in rows:
        last_seen = row.last_seen_at
        new_status = compute_status(
            last_seen_at=last_seen, article_count=row.article_count, now=now
        )
        importance = compute_importance_score(
            source_count=row.source_count, article_count=row.article_count
        )

        # Freshness: hours since last_seen, half-life 24h
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        delta_hours = max(0.0, (now - last_seen).total_seconds() / 3600.0)
        freshness = max(0.0, min(1.0, math.pow(0.5, delta_hours / 24.0)))

        if new_status == row.status:
            # Yine de score'ları update et
            await db.execute(
                sa_text(
                    "UPDATE event_clusters SET importance_score = :imp, "
                    "freshness_score = :fresh WHERE id = :cid"
                ),
                {"imp": importance, "fresh": freshness, "cid": str(row.id)},
            )
            counts["unchanged"] += 1
            continue

        await db.execute(
            sa_text(
                "UPDATE event_clusters SET status = :st, importance_score = :imp, "
                "freshness_score = :fresh, last_updated_at = NOW() WHERE id = :cid"
            ),
            {
                "st": new_status,
                "imp": importance,
                "fresh": freshness,
                "cid": str(row.id),
            },
        )
        counts[new_status] = counts.get(new_status, 0) + 1

    return counts
