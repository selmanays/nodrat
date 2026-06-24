"""Integration — #1590 küme çapası canonical-aware + tip-filtre (testcontainers).

`_ENTITY_DF_SQL` (cluster_assigner): query-gram'ları entities ile eşler, alias→
canonical map (COALESCE) + person/org/place/event tip-filtresi. "trump"/"donald trump"
→ tek canonical "donald trump" (display "Donald Trump"); "bir"(number) elenir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.research_clustering import canonical_cluster_key
from app.modules.generations.cluster_resolver import (
    ENTITY_DF_SQL,
    attach_artifact_clusters,
    resolve_cluster_by_entity,
    resolve_or_create_cluster,
    resolve_secondary_clusters,
)
from sqlalchemy import text

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


async def _canon(db, name: str, norm: str, etype: str, aliases: list[str]) -> str:
    """canonical_entities + entity_aliases ekle; canonical_id (str) döndür."""
    cid = (
        await db.execute(
            text(
                "INSERT INTO canonical_entities (canonical_name, entity_type, "
                "canonical_normalized, source) VALUES (:n,:t,:cn,'wikidata') RETURNING id"
            ),
            {"n": name, "t": etype, "cn": norm},
        )
    ).scalar()
    for a in aliases:
        await db.execute(
            text(
                "INSERT INTO entity_aliases (alias_normalized, entity_type, canonical_id, "
                "confidence, source) VALUES (:a,:t,:c,1.000,'wikidata')"
            ),
            {"a": a, "t": etype, "c": cid},
        )
    return str(cid)


async def _cluster(db, key: str, etype: str, name: str, cid: str | None = None) -> str:
    """research_clusters satırı ekle; cluster id (str) döndür."""
    rid = (
        await db.execute(
            text(
                "INSERT INTO research_clusters (cluster_key, cluster_type, canonical_name, "
                "canonical_entity_id) VALUES (:k,:t,:n,:c) RETURNING id"
            ),
            {"k": key, "t": etype, "n": name, "c": cid},
        )
    ).scalar()
    return str(rid)


async def _article(db, sid: uuid.UUID, ents: list[tuple[str, str]]) -> uuid.UUID:
    """1 makale + verilen (normalized, type) entity'leri ekle; article_id döndür."""
    aid = uuid.uuid4()
    h = aid.hex
    await db.execute(
        text(
            "INSERT INTO articles (id, source_id, canonical_url, source_url, title, "
            "content_hash, title_hash, published_at) VALUES (:id,:s,:u,:u,'t',:h,:h,:p)"
        ),
        {"id": aid, "s": sid, "u": f"https://x/{h}", "h": h, "p": _NOW},
    )
    for norm, etype in ents:
        await db.execute(
            text(
                "INSERT INTO entities (article_id, entity_text, entity_normalized, entity_type) "
                "VALUES (:a,:t,:n,:et)"
            ),
            {"a": aid, "t": norm, "n": norm, "et": etype},
        )
    return aid


async def _src(db) -> uuid.UUID:
    sid = uuid.uuid4()
    slug = f"s-{sid.hex[:8]}"
    await db.execute(
        text(
            "INSERT INTO sources (id, name, slug, domain, type, base_url, reliability_score) "
            "VALUES (:id, :n, :s, :d, 'rss', :u, 0.8)"
        ),
        {"id": sid, "n": slug, "s": slug, "d": f"{slug}.x", "u": f"https://{slug}.x"},
    )
    return sid


async def _ent(db, sid: uuid.UUID, norm: str, etype: str, n: int) -> None:
    for i in range(n):
        aid = uuid.uuid4()
        h = aid.hex
        await db.execute(
            text(
                "INSERT INTO articles (id, source_id, canonical_url, source_url, title, "
                "content_hash, title_hash, published_at) VALUES (:id,:s,:u,:u,'t',:h,:h,:p)"
            ),
            {"id": aid, "s": sid, "u": f"https://x/{h}", "h": h, "p": _NOW - timedelta(hours=i)},
        )
        await db.execute(
            text(
                "INSERT INTO entities (article_id, entity_text, entity_normalized, entity_type) "
                "VALUES (:a,:t,:n,:et)"
            ),
            {"a": aid, "t": norm, "n": norm, "et": etype},
        )


async def test_anchor_query_canonical_map_and_type_filter(test_db_session):
    db = test_db_session
    s = await _src(db)
    await _ent(db, s, "trump", "person", 5)  # kısa form
    await _ent(db, s, "donald trump", "person", 12)  # tam form
    await _ent(db, s, "bir", "number", 3)  # gürültü (tip-filtre eler)

    # canonical "Donald Trump" + alias map (trump + donald trump)
    cid = (
        await db.execute(
            text(
                "INSERT INTO canonical_entities (canonical_name, entity_type, canonical_normalized, "
                "source) VALUES ('Donald Trump','person','donald trump','seed') RETURNING id"
            )
        )
    ).scalar()
    for a in ("trump", "donald trump"):
        await db.execute(
            text(
                "INSERT INTO entity_aliases (alias_normalized, entity_type, canonical_id, "
                "confidence, source) VALUES (:a,'person',:c,1.000,'seed')"
            ),
            {"a": a, "c": cid},
        )

    rows = (await db.execute(ENTITY_DF_SQL, {"grams": ["trump", "donald trump", "bir"]})).all()
    by_norm = {r.norm: r for r in rows}

    # "bir" (number) → tip-filtre eledi
    assert "bir" not in by_norm
    # trump + donald trump → tek canonical "donald trump" (display "Donald Trump")
    assert "donald trump" in by_norm
    assert "trump" not in by_norm  # ayrı kalmadı, canonical'a maplendi
    row = by_norm["donald trump"]
    assert row.etype == "person"
    assert row.has_canonical is True
    assert row.display_name == "Donald Trump"
    assert int(row.df) == 17  # 5 + 12 birleşti


async def test_resolve_cluster_fallback_anchors_on_cited_subject(test_db_session):
    """#1737 — Türkçe çekimli sorgu ("12. yargı paketinde...") query-gram'la entity'yi
    kaçırır; cited makale entity'lerinden ÖZNEYE (12. yargı paketi) çapalanmalı,
    canonical'lı GENİŞ varlığa (parti) DEĞİL."""
    db = test_db_session
    s1, s2 = await _src(db), await _src(db)
    # canonical "Adalet ve Kalkınma Partisi" (geniş varlık; has_canonical=True →
    # overlap-filtre OLMASA sıralamada özneyi bastırırdı).
    cid = (
        await db.execute(
            text(
                "INSERT INTO canonical_entities (canonical_name, entity_type, "
                "canonical_normalized, source) VALUES "
                "('Adalet ve Kalkınma Partisi','org','adalet ve kalkınma partisi','seed') "
                "RETURNING id"
            )
        )
    ).scalar()
    await db.execute(
        text(
            "INSERT INTO entity_aliases (alias_normalized, entity_type, canonical_id, "
            "confidence, source) VALUES ('adalet ve kalkınma partisi','org',:c,1.000,'seed')"
        ),
        {"c": cid},
    )
    # 4 cited makale, 2 kaynağa yayılı; her biri KONU + PARTİ içerir.
    ents = [("12. yargı paketi", "event"), ("adalet ve kalkınma partisi", "org")]
    aids = [await _article(db, sid, ents) for sid in (s1, s1, s2, s2)]

    query = "12. yargı paketinde neler var"
    # Primary (article_ids YOK): çekimli sorgu gram'la eşleşmez → küme YOK (hata sınıfı).
    assert await resolve_cluster_by_entity(db, query, create=False) is None

    # Fallback (cited article_ids): özneye çapalanır — parti DEĞİL.
    cluster = await resolve_cluster_by_entity(db, query, article_ids=[str(a) for a in aids])
    assert cluster is not None
    assert cluster.cluster_type == "event"
    assert "yargı paketi" in (cluster.canonical_name or "").lower()
    assert "parti" not in (cluster.canonical_name or "").lower()


# ---------------------------------------------------------------------------
# #1740 — kanonik-demirli çözüm/yaratım (drift-bağışıklık)
# ---------------------------------------------------------------------------


async def test_anchor_reuses_stranded_cluster_via_alias_key(test_db_session):
    """Drift-bağışıklık: canonical bağlanmadan ÖNCE 'akp' key'iyle açılmış stranded
    küme, sonradan canonical norm'la çözülünce YENİDEN KULLANILIR (yeni küme MİNTLENMEZ)
    + canonical_entity_id fırsatçı backfill edilir."""
    db = test_db_session
    cid = await _canon(
        db,
        "Adalet ve Kalkınma Partisi",
        "adalet ve kalkınma partisi",
        "org",
        ["akp", "adalet ve kalkınma partisi"],
    )
    # stranded: eski alias-key, canonical_entity_id NULL
    stranded = await _cluster(db, "org:akp", "org", "AKP", cid=None)

    cluster, created = await resolve_or_create_cluster(
        db, "org", "adalet ve kalkınma partisi", "Adalet ve Kalkınma Partisi"
    )
    assert created is False  # yeni MİNTLENMEDİ
    assert str(cluster.id) == stranded  # AYNI stranded küme
    assert str(cluster.canonical_entity_id) == cid  # backfill edildi
    assert cluster.cluster_key == "org:akp"  # key DEĞİŞMEDİ (sürpriz yok)
    # canonical-key ile ikinci bir aktif küme olmamalı
    n = (
        await db.execute(
            text(
                "SELECT count(*) FROM research_clusters "
                "WHERE deprecated_at IS NULL AND cluster_type='org' "
                "AND cluster_key='org:adalet-ve-kalkinma-partisi'"
            )
        )
    ).scalar()
    assert n == 0


async def test_anchor_resolves_by_canonical_id_when_key_differs(test_db_session):
    """canonical_entity_id'ye demirli mevcut küme, key farklı olsa da bulunur."""
    db = test_db_session
    cid = await _canon(db, "Madagaskar", "madagaskar", "place", ["büyük ada"])
    anchored = await _cluster(db, "place:eski-ad", "place", "Madagaskar", cid=cid)

    cluster, created = await resolve_or_create_cluster(db, "place", "madagaskar", "Madagaskar")
    assert created is False
    assert str(cluster.id) == anchored


async def test_anchor_creates_with_canonical_id(test_db_session):
    """Mevcut küme yokken canonical norm → yeni küme canonical_entity_id DOLU yaratılır."""
    db = test_db_session
    cid = await _canon(db, "G7 zirvesi", "g7 zirvesi", "event", ["g7 zirvesi"])
    cluster, created = await resolve_or_create_cluster(db, "event", "g7 zirvesi", "G7 zirvesi")
    assert created is True
    assert cluster.cluster_key == canonical_cluster_key("event", "g7 zirvesi")
    assert str(cluster.canonical_entity_id) == cid


async def test_anchor_canonical_less_keeps_key_only(test_db_session):
    """Canonical yoksa eski key-only davranış: canonical_entity_id NULL kalır."""
    db = test_db_session
    cluster, created = await resolve_or_create_cluster(db, "person", "bazı kişi", "Bazı Kişi")
    assert created is True
    assert cluster.cluster_key == canonical_cluster_key("person", "bazı kişi")
    assert cluster.canonical_entity_id is None
    # create=False + mevcut yok → (None, False)
    again, created2 = await resolve_or_create_cluster(
        db, "person", "başka kişi", "Başka Kişi", create=False
    )
    assert again is None and created2 is False


# ---------------------------------------------------------------------------
# #1751 — küme CEVABIN konusundan (sorgudan değil); genç-collision before/after
# ---------------------------------------------------------------------------


async def test_cluster_from_answer_not_query_subject(test_db_session):
    """Sorgu kelimesi yer-adıyla çakışsa bile ("genç"→yer entity) küme, CEVAP
    öznesinden (deniz kaya) çözülür. Bağlam entity'si (tayland, df-baskın) cevapta
    geçmediği için elenir."""
    db = test_db_session
    s1, s2 = await _src(db), await _src(db)
    # "genç" = sorgu kelimesiyle çakışan YER entity'si (gate-pass, jenerik-muaf)
    await _ent(db, s1, "genç", "place", 2)
    await _ent(db, s2, "genç", "place", 2)
    # cevabın kaynak makaleleri: özne (deniz kaya) + bağlam (tayland), 3 makale/2 kaynak
    cited = [
        await _article(db, sid, [("deniz kaya", "person"), ("tayland", "place")])
        for sid in (s1, s2, s1)
    ]
    query = "geçen hafta ölen genç oyuncu kimdi"  # özneyi ADLANDIRMAZ
    answer = "Deniz Kaya, 35 yaşında bir oyuncu, kalp krizi sonucu hayatını kaybetti."

    # BUG (eski query-driven): answer_content yok → "genç" yer entity'sine çapalanır
    # (create=True → küme mintlenir; create=False olsaydı mevcut-yok → None yanıltırdı).
    buggy = await resolve_cluster_by_entity(db, query)
    assert buggy is not None and buggy.cluster_type == "place"
    assert "genç" in (buggy.canonical_name or "").lower()

    # FIX (#1751 cevap-tarafı): cited + answer → özne deniz kaya, genç/tayland DEĞİL
    fixed = await resolve_cluster_by_entity(
        db, query, article_ids=[str(a) for a in cited], answer_content=answer
    )
    assert fixed is not None
    assert fixed.cluster_type == "person"
    assert "deniz kaya" in (fixed.canonical_name or "").lower()
    assert "genç" not in (fixed.canonical_name or "").lower()
    assert "tayland" not in (fixed.canonical_name or "").lower()


async def test_answer_anchor_alias_and_df_dominant(test_db_session):
    """#1759 — asıl özne canonical adı uzun + cevap KISALTMAYI yazıyor (alias yüzey)
    + df-baskın → küme özneye (parti) çözülür; cevapta geçen canonical'lı İKİNCİL
    (df-az kişi) bastırmaz. (DEM Parti vakası analoğu.)"""
    db = test_db_session
    # asıl özne: canonical uzun ad + 'kısa parti' alias yüzey-formu
    cid_p = await _canon(db, "Uzun Resmi Parti Adı", "uzun resmi parti adı", "org", ["kısa parti"])
    # ikincil: canonical'lı kişi (cevapta geçer ama df-az)
    await _canon(db, "Ahmet Veli", "ahmet veli", "person", ["ahmet veli"])
    s1, s2 = await _src(db), await _src(db)
    # 4 makale: parti hepsinde (df4/src2), kişi 2'sinde (df2/src2)
    cited = []
    for i, sid in enumerate((s1, s2, s1, s2)):
        ents = [("kısa parti", "org")] + ([("ahmet veli", "person")] if i < 2 else [])
        cited.append(await _article(db, sid, ents))

    query = "o parti neden gündemde"  # özneyi adlandırmaz
    answer = "Kısa Parti bugün gündemde; Ahmet Veli bir açıklama yaptı."
    cluster = await resolve_cluster_by_entity(
        db, query, article_ids=[str(a) for a in cited], answer_content=answer
    )
    assert cluster is not None
    assert cluster.cluster_type == "org"  # parti (kişi değil)
    assert "parti" in (cluster.canonical_name or "").lower()
    assert "ahmet" not in (cluster.canonical_name or "").lower()  # canonical ikincil bastırılmadı
    # küme canonical-demirli (asıl özne canonical'ına)
    assert str(cluster.canonical_entity_id) == cid_p


async def test_resolve_secondary_clusters_excludes_primary_df_ranked_capped(test_db_session):
    """#1762 — ikincil kümeler: cevapta adı geçen, gate geçen, df-sıralı, BİRİNCİL
    hariç entity'ler; cap uygulanır. (DEM Parti → Tülay/asgari ücret analoğu.)"""
    db = test_db_session
    s1, s2 = await _src(db), await _src(db)
    # 4 makale/2 kaynak: parti hepsinde (df4), tülay 3'ünde (df3), asgari ücret 2'sinde (df2),
    # düşük-kanıt 'gürültü' 1'inde (df1 → gate eler)
    cited = []
    for i, sid in enumerate((s1, s2, s1, s2)):
        ents = [("dem parti", "org")]
        if i < 3:
            ents.append(("tülay hatimoğulları", "person"))
        if i < 2:
            ents.append(("asgari ücret", "org"))
        if i < 1:
            ents.append(("gürültü kişi", "person"))
        cited.append(await _article(db, sid, ents))
    answer = (
        "DEM Parti gündemde; Tülay Hatimoğulları asgari ücret çağrısı yaptı. "
        "Gürültü Kişi de katıldı."
    )
    aids = [str(a) for a in cited]
    # birincil = dem parti
    primary = await resolve_cluster_by_entity(
        db, "dem parti neden gündemde", article_ids=aids, answer_content=answer
    )
    assert primary is not None and "dem parti" in (primary.canonical_name or "").lower()

    secs = await resolve_secondary_clusters(
        db, aids, answer, exclude_cluster_ids={str(primary.id)}, limit=3
    )
    names = [c.canonical_name.lower() for c, _df in secs]
    # birincil (dem parti) HARİÇ; df-sıralı: tülay(3) → asgari ücret(2); gürültü(df1) gate eler
    assert "dem parti" not in names
    assert names == ["tülay hatimoğulları", "asgari ücret"]
    assert [df for _c, df in secs] == [3, 2]  # relevance = df, sıralı
    # cap: limit=1 → yalnız en yüksek df
    secs1 = await resolve_secondary_clusters(
        db, aids, answer, exclude_cluster_ids={str(primary.id)}, limit=1
    )
    assert [c.canonical_name.lower() for c, _df in secs1] == ["tülay hatimoğulları"]


async def test_attach_artifact_clusters_writes_primary_and_secondary(test_db_session):
    """#1762 — attach_artifact_clusters birincil (role=primary) + ikincil (role=secondary,
    relevance=df) junction satırları yazar; tekrar çağrı idempotent (ON CONFLICT)."""
    db = test_db_session
    # küme + kullanıcı + artefakt iskeleti
    pc = await _cluster(db, "org:dem-parti", "org", "DEM Parti")
    sc = await _cluster(db, "person:tulay", "person", "Tülay Hatimoğulları")
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:i, :e, 'x')"),
        {"i": uid, "e": f"u-{uid.hex[:8]}@x.com"},
    )
    aid = (
        await db.execute(
            text(
                "INSERT INTO artifacts (cluster_id, user_id, artifact_type) "
                "VALUES (:c,:u,'post') RETURNING id"
            ),
            {"c": pc, "u": uid},
        )
    ).scalar()

    sc_cluster = (
        await db.execute(text("SELECT * FROM research_clusters WHERE id = :i"), {"i": sc})
    ).first()

    class _C:
        pass

    sec_obj = _C()
    sec_obj.id = sc_cluster.id
    sec_obj.canonical_name = "Tülay Hatimoğulları"

    await attach_artifact_clusters(db, aid, primary_cluster_id=pc, secondaries=[(sec_obj, 3)])
    # idempotent: tekrar çağrı çakışma yaratmaz
    await attach_artifact_clusters(db, aid, primary_cluster_id=pc, secondaries=[(sec_obj, 3)])

    rows = (
        await db.execute(
            text(
                "SELECT cluster_id, role, relevance FROM artifact_clusters "
                "WHERE artifact_id = :a ORDER BY role"
            ),
            {"a": aid},
        )
    ).all()
    by_cluster = {str(r.cluster_id): (r.role, r.relevance) for r in rows}
    assert len(rows) == 2  # dup yazılmadı
    assert by_cluster[str(pc)] == ("primary", 0)
    assert by_cluster[str(sc)] == ("secondary", 3)
