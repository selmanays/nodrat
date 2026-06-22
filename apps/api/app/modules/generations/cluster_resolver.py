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
        -- #1697 casing: canonical_name yoksa lowercase entity_normalized yerine
        -- en SIK NER yüzey formu (mode(entity_text), doğru cased: 'Almanya',
        -- 'Filenin Sultanları'). MAX lexicographic 'almanya'>'Almanya' verirdi.
        COALESCE(
            MAX(ce.canonical_name),
            mode() WITHIN GROUP (ORDER BY e.entity_text)
        ) AS display_name,
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

# #1737 — ÇEKİM-BAĞIŞIK fallback: query-gram'lar Türkçe çekim yüzünden entity'yi
# kaçırınca (ör. "12. yargı paketinde" → gram "yargı paketinde" ≠ entity "12 yargı
# paketi"), cevabın ATIF YAPILAN kaynak makalelerinin entity'lerinden çapa çıkar.
# ENTITY_DF_SQL ile birebir kolon şekli (resolve_anchor reuse) — tek fark: gram-IN
# yerine cited article_id kümesi. df/src cited-set içinde sayılır (ortak konu kanıtı).
ARTICLE_ENTITY_DF_SQL = sa.text(
    """
    SELECT
        COALESCE(ce.canonical_normalized, e.entity_normalized) AS norm,
        COALESCE(ce.entity_type, e.entity_type) AS etype,
        COALESCE(
            MAX(ce.canonical_name),
            mode() WITHIN GROUP (ORDER BY e.entity_text)
        ) AS display_name,
        bool_or(ce.id IS NOT NULL) AS has_canonical,
        COUNT(DISTINCT e.article_id) AS df,
        COUNT(DISTINCT a.source_id) AS src
    FROM entities e
    JOIN articles a ON a.id = e.article_id
    LEFT JOIN entity_aliases ea
        ON ea.alias_normalized = e.entity_normalized AND ea.entity_type = e.entity_type
    LEFT JOIN canonical_entities ce ON ce.id = ea.canonical_id
    WHERE e.article_id::text = ANY(:aids)
      AND COALESCE(ce.entity_type, e.entity_type) IN ('person', 'org', 'place', 'event')
    GROUP BY 1, 2
    """
)


def _query_overlap(norm: str | None, qtoks: set[str]) -> bool:
    """Entity `norm`, sorguyla ÖRTÜŞÜYOR mu? (#1737 fallback filtresi.)

    YALNIZ Türkçe-ek yönü: entity-token, bir query-token'ın BAŞINDA yer alır
    (eşit ya da prefix: ``paketi`` ⊂ ``paketinde``, ``yargı`` == ``yargı``). Bu
    yön cited-makalelerin GENİŞ varlıklarını (parti/kurum: AKP, Adalet Bakanlığı)
    eler — sorgunun ÖZNESİ (yargı paketi) kalır. Ters yön (``yargı`` ⊂ ``yargıtay``)
    YANLIŞ-komşu canonical'ı içeri alır + has_canonical sıralamada önde olduğu için
    özneyi bastırırdı; bu yüzden kasıtlı tek-yön. ≥4 char → kısa-token gürültüsü yok.
    """
    nts = [t for t in (norm or "").split() if len(t) >= 4]
    return any(qt.startswith(nt) for nt in nts for qt in qtoks)


# #1705 — JENERİK-KATEGORİ sinyali (corpus-türevli): her norm'u BİLEŞEN olarak içeren
# FARKLI entity sayısı. Jenerik kategori ("belediye meclisi" → "X Belediye Meclisi") çok;
# spesifik özel-ad ("tuvalu"/"filenin sultanları") ~0. AYRI tek-round-trip unnest —
# ENTITY_DF_SQL'e correlated subquery koymak Postgres'te grouped-COALESCE'a izin vermez +
# kötü plan (~1.4s); bu form per-norm count(DISTINCT) trigram-index ile ~10-30ms (toplam
# ~30-120ms). LIKE tek '%' (asyncpg literal — escape YOK).
_ANCHOR_GENERIC_SQL = sa.text(
    """
    SELECT g.norm AS norm, count(DISTINCT e2.entity_normalized) AS gn
    FROM unnest(cast(:norms AS text[])) AS g(norm)
    LEFT JOIN entities e2
        ON e2.entity_normalized LIKE '%' || g.norm || '%'
       AND e2.entity_normalized <> g.norm
    GROUP BY g.norm
    """
)


async def _anchor_genericness(db: AsyncSession, norms: set[str]) -> dict[str, int]:
    """{norm → onu bileşen olarak içeren FARKLI entity sayısı} (#1705). Boş → {}."""
    clean = [n for n in norms if n and n.strip()]
    if not clean:
        return {}
    rows = (await db.execute(_ANCHOR_GENERIC_SQL, {"norms": clean})).all()
    return {r.norm: int(r.gn) for r in rows}


async def resolve_anchor(
    db: AsyncSession, cands: list[tuple[str, str, int, int, bool, str | None]]
) -> tuple[str, str, str | None] | None:
    """GATE + fragment-elim + corpus-türevli JENERİK-KATEGORİ reddi + spesifik-sıralama
    (#1705). cluster_resolver + cluster_assigner ORTAK çağırır → çapa kararı drift olmaz.
    Genericlik yalnız bu adaylar için tek-round-trip hesaplanır (post-answer yolu)."""
    gmap = await _anchor_genericness(db, {c[0] for c in cands if c[0]})
    return select_canonical_anchor(cands, genericness=gmap)


async def resolve_cluster_by_entity(
    db: AsyncSession,
    content: str,
    *,
    create: bool = True,
    article_ids: list[str] | None = None,
) -> ResearchCluster | None:
    """Sorgu metnini kanonik entity-kümesine çöz. Bulamazsa None.

    create=False → yalnız mevcut küme döner (yeni MİNTLEMEZ). create=True →
    yoksa kanonik küme yaratır (flush; commit caller'da). cluster_assigner
    entity-dalı ile birebir mantık (drift = ENTITY_DF_SQL tek kaynak + ortak core).

    article_ids (#1737): cevabın ATIF yaptığı kaynak makaleler. Query-gram yolu
    çapa bulamazsa (Türkçe çekim → "paketinde" ≠ entity "paketi") bu makalelerin
    SORGUYLA ÖRTÜŞEN entity'lerinden çapa çıkarılır (morfoloji-bağışık + özne-odaklı:
    geniş parti/kurum elenir). create-time yol; cluster_assigner'ı etkilemez.
    """
    grams = query_grams(content or "")
    if not grams:
        return None
    rows = (await db.execute(ENTITY_DF_SQL, {"grams": grams})).all()
    cands = [
        (r.norm, r.etype, int(r.df), int(r.src), bool(r.has_canonical), r.display_name)
        for r in rows
    ]
    anchor = await resolve_anchor(db, cands)
    if anchor is None and article_ids:
        # #1737 fallback — cited makale entity'leri, query-token PREFIX'i olanlarla
        # sınırlı (geniş varlığı ele). resolve_anchor zaten gate+jenerik-reddi uygular.
        qtoks = {g for g in grams if " " not in g and len(g) >= 4}
        a_rows = (
            await db.execute(ARTICLE_ENTITY_DF_SQL, {"aids": [str(x) for x in article_ids]})
        ).all()
        a_cands = [
            (r.norm, r.etype, int(r.df), int(r.src), bool(r.has_canonical), r.display_name)
            for r in a_rows
            if _query_overlap(r.norm, qtoks)
        ]
        anchor = await resolve_anchor(db, a_cands)
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
