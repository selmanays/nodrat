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

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import select, text
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
        COUNT(DISTINCT a.source_id) AS src,
        -- #1759: ham NER yüzey-formları (alias/kısaltma). norm canonical'a COALESCE'lı
        -- olduğundan cevap kısaltmayı yazsa bile ("DEM Parti" ≠ canonical "Halkların...")
        -- cevap-eşleşmesi bu formlardan yakalanır.
        array_agg(DISTINCT e.entity_normalized) AS surface_forms
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
    db: AsyncSession,
    cands: list[tuple[str, str, int, int, bool, str | None]],
    *,
    prefer: str = "canonical",
) -> tuple[str, str, str | None] | None:
    """GATE + fragment-elim + corpus-türevli JENERİK-KATEGORİ reddi + spesifik-sıralama
    (#1705). cluster_resolver + cluster_assigner ORTAK çağırır → çapa kararı drift olmaz.
    Genericlik yalnız bu adaylar için tek-round-trip hesaplanır (post-answer yolu).
    prefer="df" (#1759): cevap-tarafı yol için df-baskın sıralama (canonical-first yerine)."""
    gmap = await _anchor_genericness(db, {c[0] for c in cands if c[0]})
    return select_canonical_anchor(cands, genericness=gmap, prefer=prefer)


def _answer_mentions(
    norm: str | None,
    display: str | None,
    answer_lower: str,
    surface_forms: list[str] | None = None,
) -> bool:
    """Entity CEVAP metninde geçiyor mu? (#1751 + #1759 alias-farkında.)

    norm/display + ham NER yüzey-formları (surface_forms — alias/kısaltma) cevapta
    aranır. #1759: canonical adı uzun ("Halkların Eşitlik ve Demokrasi Partisi") ama
    cevap kısaltmayı ("DEM Parti") yazsa bile yüzey-formundan yakalanır → asıl özne
    aday olur. ≥4 char → kısa-ad gürültüsü yok. Cevap özneyi adıyla söyler, bağlamı
    (Tayland) söylemeyebilir.
    """
    for cand in (norm, display, *(surface_forms or [])):
        if cand:
            c = cand.lower()
            if len(c) >= 4 and c in answer_lower:
                return True
    return False


async def _resolve_answer_anchor(
    db: AsyncSession, article_ids: list[str], answer_content: str
) -> tuple[str, str, str | None] | None:
    """#1751 — CEVAP-TARAFI çapa: cited kaynakların, CEVAP metninde adı geçen baskın
    entity'si. Sorgu kelimelerinden BAĞIMSIZ — sorgu özneyi adlandırmasa da çalışır
    ("genç oyuncu kimdi" → cevap "Ece İrtem" → çapa Ece İrtem). Cevapta GEÇMEYEN
    bağlam entity'leri (df'de baskın olsa bile, ör. "Tayland") elenir. resolve_anchor
    gate + jenerik-reddi + df-sıralama uygular (drift-bağışık tek kaynak)."""
    a_rows = (
        await db.execute(ARTICLE_ENTITY_DF_SQL, {"aids": [str(x) for x in article_ids]})
    ).all()
    ans = (answer_content or "").lower()
    cands = [
        (r.norm, r.etype, int(r.df), int(r.src), bool(r.has_canonical), r.display_name)
        for r in a_rows
        if _answer_mentions(r.norm, r.display_name, ans, list(r.surface_forms or []))
    ]
    # #1759: df-baskın sıralama — cevapta en çok geçen ÖZNE kazanır (canonical'lı
    # ikincil bastırmaz: DEM Parti df7 > Numan Kurtulmuş df2). Gate/jenerik-reddi aynı.
    return await resolve_anchor(db, cands, prefer="df")


async def resolve_cluster_by_entity(
    db: AsyncSession,
    content: str,
    *,
    create: bool = True,
    article_ids: list[str] | None = None,
    answer_content: str | None = None,
) -> ResearchCluster | None:
    """Sorguyu/cevabı kanonik entity-kümesine çöz. Bulamazsa None.

    Çözüm sırası (#1751 — küme = CEVABIN konusu, sorgunun ifadesi DEĞİL):
      1. **CEVAP-TARAFI (primary):** answer_content + article_ids verilirse, cited
         kaynakların CEVAPTA adı geçen baskın entity'si. Sorgu kelimesi yer/özel-ad
         ile çakışsa bile ("genç" → Bingöl Genç ilçesi place) etkilenmez.
      2. **Query-gram (fallback):** cevap-tarafı çapa vermezse (cited yok / cevap
         corpus-entity adamadı) eski sorgu-tabanlı yol.
      3. **#1737 cited∩sorgu:** query-gram da bulamazsa, cited entity ∩ sorgu-token
         (Türkçe çekim morfoloji-bağışıklığı).

    create=False → yalnız mevcut küme döner. create=True → yoksa kanonik küme yaratır
    (resolve_or_create_cluster; commit caller'da). cluster_assigner'ı etkilemez.
    """
    anchor: tuple[str, str, str | None] | None = None

    # 1) CEVAP-TARAFI primary (#1751)
    if answer_content and article_ids:
        anchor = await _resolve_answer_anchor(db, article_ids, answer_content)

    # 2+3) Fallback — query-gram + #1737 cited∩sorgu
    if anchor is None:
        grams = query_grams(content or "")
        if grams:
            rows = (await db.execute(ENTITY_DF_SQL, {"grams": grams})).all()
            cands = [
                (r.norm, r.etype, int(r.df), int(r.src), bool(r.has_canonical), r.display_name)
                for r in rows
            ]
            anchor = await resolve_anchor(db, cands)
            if anchor is None and article_ids:
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
    cluster, _created = await resolve_or_create_cluster(
        db, ent_type, ent_norm, display_name, create=create
    )
    return cluster


# ============================================================================
# #1740 — KANONİK-DEMİRLİ küme çözümle/yarat (drift-bağışık tek kaynak).
# resolve_cluster_by_entity (sorgu-anı) + cluster_assigner (gece batch) ORTAK
# çağırır → ikisi de aynı kimlik mantığını paylaşır (key-only find/create drift
# ederdi). Çapa entity'sinin canonical'ı varsa küme `canonical_entity_id`'ye
# demirlenir: alias yüzey-formu değişse de (ör. "akp" → "Adalet ve Kalkınma
# Partisi") AYNI düğüme bağlanır, ikinci küme MİNTLENMEZ.
# ============================================================================


async def _lookup_canonical_id(
    db: AsyncSession, ent_type: str, ent_norm: str
) -> tuple[str | None, str | None]:
    """Çapa norm'unun canonical kaydı (id, canonical_name) — yoksa (None, None).

    Çapa norm'u ENTITY_DF_SQL'de COALESCE(canonical_normalized, entity_normalized);
    canonical varsa norm == canonical_normalized → birebir eşleşir.
    """
    row = (
        await db.execute(
            text(
                "SELECT id, canonical_name FROM canonical_entities "
                "WHERE canonical_normalized = :n AND entity_type = :t"
            ),
            {"n": ent_norm, "t": ent_type},
        )
    ).first()
    return (str(row[0]), row[1]) if row else (None, None)


async def _candidate_keys(db: AsyncSession, ent_type: str, key: str, cid: str | None) -> set[str]:
    """Bu canonical'ı temsil edebilecek tüm cluster_key'ler: canonical-key +
    canonical'ın TÜM alias yüzey-formlarının key'i. Stranded eski küme (canonical
    bağlanmadan önce "akp" key'iyle açılmış) bu sayede yakalanır (#1740)."""
    keys = {key}
    if cid is None:
        return keys
    rows = (
        await db.execute(
            text(
                "SELECT alias_normalized FROM entity_aliases "
                "WHERE canonical_id = :cid AND entity_type = :t"
            ),
            {"cid": cid, "t": ent_type},
        )
    ).all()
    for r in rows:
        try:
            keys.add(canonical_cluster_key(ent_type, r[0]))
        except ValueError:  # pragma: no cover — boş alias atlanır
            continue
    return keys


async def _find_existing_cluster(
    db: AsyncSession, key: str, cid: str | None, cand_keys: set[str]
) -> ResearchCluster | None:
    """Aktif kümeyi canonical_entity_id VEYA aday-key'lerle bul; deterministik
    seç: önce canonical_id eşleşmesi, sonra tam canonical-key, sonra en eski."""
    conds = [ResearchCluster.cluster_key.in_(cand_keys)]
    if cid is not None:
        conds.append(ResearchCluster.canonical_entity_id == cid)
    rows = (
        (
            await db.execute(
                select(ResearchCluster).where(
                    ResearchCluster.deprecated_at.is_(None), sa.or_(*conds)
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    rows.sort(
        key=lambda c: (
            0 if (cid is not None and str(c.canonical_entity_id) == cid) else 1,
            0 if c.cluster_key == key else 1,
            c.created_at,
        )
    )
    return rows[0]


async def resolve_or_create_cluster(
    db: AsyncSession,
    ent_type: str,
    ent_norm: str,
    display_name: str | None,
    *,
    create: bool = True,
    centroid: bytes | None = None,
) -> tuple[ResearchCluster | None, bool]:
    """Çapa (tip, norm) → kanonik küme. Dönüş: (cluster|None, created_bool).

    Kimlik canonical_entity_id'ye DEMİRLİ (#1740): canonical varsa küme onunla
    çözülür/yaratılır → alias yüzey-formu değişse de drift olmaz. Mevcut NULL
    canonical_id fırsatçı backfill edilir (additive, geri alınabilir; key/ad
    DEĞİŞMEZ). Canonical yoksa eski key-only davranış birebir korunur.
    """
    key = canonical_cluster_key(ent_type, ent_norm)
    cid, canon_name = await _lookup_canonical_id(db, ent_type, ent_norm)
    cand_keys = await _candidate_keys(db, ent_type, key, cid)

    cluster = await _find_existing_cluster(db, key, cid, cand_keys)
    if cluster is not None:
        if cid is not None and cluster.canonical_entity_id is None:
            # Fırsatçı demirleme: yalnız NULL canonical_id doldurulur (reversible);
            # cluster_key + canonical_name DOKUNULMAZ (sürpriz/UNIQUE riski yok).
            cluster.canonical_entity_id = cid
            cluster.updated_at = datetime.now(UTC)
        return cluster, False

    if not create:
        return None, False

    # Race-safe create (ON CONFLICT DO NOTHING — savepoint kök-tx zehirler).
    values: dict = {
        "cluster_key": key,
        "cluster_type": ent_type,
        "canonical_name": display_name or canon_name or ent_norm,
    }
    if cid is not None:
        values["canonical_entity_id"] = cid
    if centroid is not None:
        values["centroid_embedding"] = centroid
    await db.execute(
        pg_insert(ResearchCluster)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=["cluster_key"],
            index_where=sa.text("deprecated_at IS NULL"),
        )
    )
    cluster = await _find_existing_cluster(db, key, cid, cand_keys)
    return cluster, True
