"""Cluster → kalıcı topic atama (Faz 2 PR-2b, #1505).

v1 = **entity-tabanlı** (saf SQL, vektör-aritmetiği yok): bir cluster'ın baskın
entity'si (person/org/event, en yüksek mention_count) aynı entity'ye çapalı mevcut
bir topic ile eşleşir → recur eden konu tek kimlikte birikir. Eşik yoksa yeni
topic seed edilir (entity-anchored öncelik; baskın entity yoksa cluster-anchored).

Tüm okuma/yazma RAW SQL: event_clusters/entities cross-domain (import-linter:
trends sibling import etmez); centroid_embedding cluster'dan **in-DB** kopyalanır
(INSERT...SELECT ec.embedding) → Python vektör round-trip yok. v1 eşleştirmede
centroid KULLANILMAZ (gelecekte cosine için saklanır).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

_TR_MAP = str.maketrans(
    {
        "ş": "s",
        "Ş": "s",
        "ı": "i",
        "İ": "i",
        "ç": "c",
        "Ç": "c",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
        "ğ": "g",
        "Ğ": "g",
    }
)


def slugify(text: str, max_len: int = 140) -> str:
    """Türkçe→ASCII + kebab-case (CLAUDE.md slug konvansiyonu)."""
    s = (text or "").translate(_TR_MAP).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len] or "topic"


def make_unique_slug(label: str, cluster_id: uuid.UUID) -> str:
    """slug + cluster_id kısa eki (UNIQUE constraint çakışmasını önler)."""
    return f"{slugify(label, max_len=140)}-{str(cluster_id)[:8]}"


async def find_dominant_entity(db: AsyncSession, cluster_id: uuid.UUID) -> tuple[str, str] | None:
    """Cluster'ın baskın entity'si (person/org/event, max Σmention_count)."""
    row = (
        await db.execute(
            sa_text(
                """
                SELECT e.entity_normalized AS norm, e.entity_type AS etype
                FROM event_articles ea
                JOIN entities e ON e.article_id = ea.article_id
                WHERE ea.event_id = :cid
                  AND e.entity_type IN ('person', 'org', 'event')
                GROUP BY e.entity_normalized, e.entity_type
                ORDER BY SUM(e.mention_count) DESC, e.entity_normalized
                LIMIT 1
                """
            ),
            {"cid": cluster_id},
        )
    ).first()
    return (row.norm, row.etype) if row is not None else None


async def assign_cluster_to_topic(db: AsyncSession, cluster_id: uuid.UUID, now: datetime) -> dict:
    """Bir live cluster'ı topic'e ata (idempotent, raw SQL)."""
    result: dict = {"cluster_id": str(cluster_id)}

    # Idempotent: zaten atanmışsa atla.
    if (
        await db.execute(
            sa_text("SELECT 1 FROM topic_clusters WHERE event_cluster_id = :cid LIMIT 1"),
            {"cid": cluster_id},
        )
    ).first() is not None:
        result["action"] = "already_assigned"
        return result

    cluster = (
        await db.execute(
            sa_text(
                """
                SELECT canonical_title, article_count, last_seen_at
                FROM event_clusters WHERE id = :cid
                """
            ),
            {"cid": cluster_id},
        )
    ).first()
    if cluster is None:
        result["action"] = "skipped"
        result["reason"] = "cluster_not_found"
        return result

    dominant = await find_dominant_entity(db, cluster_id)

    # Entity-anchored match: aynı baskın entity'ye çapalı mevcut topic.
    matched_topic_id = None
    if dominant is not None:
        norm, etype = dominant
        match = (
            await db.execute(
                sa_text(
                    """
                    SELECT id FROM topics
                    WHERE anchor_entity_normalized = :norm
                      AND anchor_entity_type = :etype
                      AND status <> 'merged'
                    ORDER BY last_seen_at DESC
                    LIMIT 1
                    """
                ),
                {"norm": norm, "etype": etype},
            )
        ).first()
        if match is not None:
            matched_topic_id = match.id

    if matched_topic_id is not None:
        await db.execute(
            sa_text(
                """
                INSERT INTO topic_clusters (topic_id, event_cluster_id, assigned_by)
                VALUES (:tid, :cid, 'auto')
                ON CONFLICT (topic_id, event_cluster_id) DO NOTHING
                """
            ),
            {"tid": matched_topic_id, "cid": cluster_id},
        )
        await db.execute(
            sa_text(
                """
                UPDATE topics SET
                    last_seen_at = GREATEST(last_seen_at, :last_seen),
                    cluster_count_total = cluster_count_total + 1,
                    article_count_total = article_count_total + :arts,
                    status = CASE WHEN status = 'dormant' THEN 'active' ELSE status END
                WHERE id = :tid
                """
            ),
            {
                "last_seen": cluster.last_seen_at,
                "arts": int(cluster.article_count or 0),
                "tid": matched_topic_id,
            },
        )
        result["action"] = "matched"
        result["topic_id"] = str(matched_topic_id)
        return result

    # Yeni topic seed — centroid_embedding cluster'dan in-DB kopyalanır.
    if dominant is not None:
        norm, etype = dominant
        slug = make_unique_slug(norm, cluster_id)
        kind = "entity"
    else:
        norm, etype = None, None
        slug = make_unique_slug(cluster.canonical_title, cluster_id)
        kind = "event"

    topic_row = (
        await db.execute(
            sa_text(
                """
                INSERT INTO topics (
                    slug, label, topic_kind, anchor_entity_normalized,
                    anchor_entity_type, centroid_embedding, status,
                    first_seen_at, last_seen_at, article_count_total, cluster_count_total
                )
                SELECT :slug, :label, :kind, :anorm, :atype, ec.embedding, 'active',
                       ec.first_seen_at, ec.last_seen_at, ec.article_count, 1
                FROM event_clusters ec WHERE ec.id = :cid
                RETURNING id
                """
            ),
            {
                "slug": slug,
                "label": cluster.canonical_title,
                "kind": kind,
                "anorm": norm,
                "atype": etype,
                "cid": cluster_id,
            },
        )
    ).first()
    new_topic_id = topic_row.id
    await db.execute(
        sa_text(
            """
            INSERT INTO topic_clusters (topic_id, event_cluster_id, assigned_by)
            VALUES (:tid, :cid, 'auto')
            ON CONFLICT (topic_id, event_cluster_id) DO NOTHING
            """
        ),
        {"tid": new_topic_id, "cid": cluster_id},
    )
    result["action"] = "seeded"
    result["topic_id"] = str(new_topic_id)
    result["topic_kind"] = kind
    return result
