"""Sorgu→küme SENKRON çözücü — Faz 3 (artefakt için, sorgu anında).

Artefakt `cluster_id` NOT NULL → artefakt oluşturmak için küme sorgu anında
çözülmeli (gece batch'i beklenemez). Bu modül `cluster_assigner._assign_one`'ın
entity-çapa mantığını paylaşımlı kılar: `ENTITY_DF_SQL` (tek kaynak) + core
`query_grams`/`select_canonical_anchor`/`canonical_cluster_key` reuse.

Yalnız ENTITY çapa (yüksek-güven, haber-korpusu); embedding-fallback YOK —
entity'siz sorgu artefakt-küme'ye bağlanmaz (jenerik sorgu → artefakt yok).
S11: çapa yalnız korpus entity'si → özel-sorgu adı global küme MİNTLEMEZ.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.research_clustering import (
    canonical_cluster_key,
    query_grams,
    select_canonical_anchor,
)
from app.modules.generations.models import ResearchCluster

# #1590 — canonical-farkında çapa: alias→canonical map + tip-filtre (person/org/
# place/event). number/money/misc gürültü ELE. Tek kaynak (cluster_assigner
# buradan import eder) — SQL drift olmaz.
ENTITY_DF_SQL = sa.text(
    """
    SELECT
        COALESCE(ce.canonical_normalized, e.entity_normalized) AS norm,
        COALESCE(ce.entity_type, e.entity_type) AS etype,
        MAX(ce.canonical_name) AS display_name,
        bool_or(ce.id IS NOT NULL) AS has_canonical,
        COUNT(DISTINCT e.article_id) AS df,
        COUNT(DISTINCT a.source_id) AS src
    FROM entities e
    JOIN articles a ON a.id = e.article_id
    LEFT JOIN entity_aliases ea
        ON ea.alias_normalized = e.entity_normalized AND ea.entity_type = e.entity_type
    LEFT JOIN canonical_entities ce ON ce.id = ea.canonical_id
    WHERE lower(e.entity_normalized) IN :grams
      AND COALESCE(ce.entity_type, e.entity_type) IN ('person', 'org', 'place', 'event')
    GROUP BY 1, 2
    """
).bindparams(sa.bindparam("grams", expanding=True))


async def resolve_cluster_by_entity(
    db: AsyncSession, content: str, *, create: bool = True
) -> ResearchCluster | None:
    """Sorgu metnini kanonik entity-kümesine çöz. Bulamazsa None.

    create=False → yalnız mevcut küme döner (yeni MİNTLEMEZ). create=True →
    yoksa kanonik küme yaratır (flush; commit caller'da). cluster_assigner
    entity-dalı ile birebir mantık (drift = ENTITY_DF_SQL tek kaynak + ortak core).
    """
    grams = query_grams(content or "")
    if not grams:
        return None
    rows = (await db.execute(ENTITY_DF_SQL, {"grams": grams})).all()
    cands = [
        (r.norm, r.etype, int(r.df), int(r.src), bool(r.has_canonical), r.display_name)
        for r in rows
    ]
    anchor = select_canonical_anchor(cands)
    if anchor is None:
        return None
    ent_norm, ent_type, display_name = anchor
    key = canonical_cluster_key(ent_type, ent_norm)
    cluster = (
        await db.execute(
            select(ResearchCluster).where(
                ResearchCluster.cluster_key == key,
                ResearchCluster.deprecated_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if cluster is None and create:
        # Eşzamanlı aynı cluster_key create yarışı: INSERT ... ON CONFLICT DO
        # NOTHING (begin_nested/savepoint DEĞİL — SQLAlchemy 2.0'da flush-
        # IntegrityError savepoint İÇİNDE bile kök transaction'ı zehirler →
        # caller commit'i + except re-query PendingRollbackError fırlatır).
        # ON CONFLICT atomik + race-safe (artifact_curator _upsert_sample deseni).
        await db.execute(
            pg_insert(ResearchCluster)
            .values(
                cluster_key=key,
                cluster_type=ent_type,
                canonical_name=display_name or ent_norm,
            )
            .on_conflict_do_nothing(
                index_elements=["cluster_key"],
                index_where=sa.text("deprecated_at IS NULL"),
            )
        )
        # Insert ettiysek de yarış kaybettiysek de tek kaynak re-query (ORM
        # objesi olarak döner; pending-obje takılması yok).
        cluster = (
            await db.execute(
                select(ResearchCluster).where(
                    ResearchCluster.cluster_key == key,
                    ResearchCluster.deprecated_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    return cluster
