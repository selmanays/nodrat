"""Integration — #1570 Kümeler↔Trendler köprüsü (testcontainers).

KRİTİK: `cluster_link._KEBAB` SQL ifadesi `core.research_clustering.tr_ascii_kebab`
ile BİREBİR eşleşmeli. Küme anahtarı Python tr_ascii_kebab ile basılır; trend tarafı
SQL kebab ile eşler → ayrışırsa join SESSİZCE boş döner. Bu test parity'yi kilitler.

Ayrıca end-to-end: seed entity → Python cluster_key → trend_metrics_for_clusters
o anahtar için doğru pencere metriği döndürür.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.research_clustering import canonical_cluster_key, tr_ascii_kebab
from app.modules.trends.cluster_link import (
    _KEBAB,
    rising_entities,
    trend_metrics_for_clusters,
)
from sqlalchemy import text

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

_KEBAB_SAMPLES = [
    "Özgür Özel",
    "Recep Tayyip Erdoğan",
    "CHP",
    "Cumhuriyet Halk Partisi",
    "İran",  # dotless/dotted I
    "i̇ran",  # combining-dot (entities korpusunda gerçek biçim)
    "2026 FIFA Dünya Kupası",
    "Şişli'de çöküş",
    "ABD & İsrail",
    "  boşluklu  kenar  ",
]


async def test_kebab_parity_sql_matches_python(test_db_session):
    """SQL _KEBAB == Python tr_ascii_kebab (her sample için)."""
    db = test_db_session
    sql = text(f"SELECT {_KEBAB.format(col=':inp')} AS k")
    for s in _KEBAB_SAMPLES:
        got = (await db.execute(sql, {"inp": s})).scalar()
        assert got == tr_ascii_kebab(s), (
            f"parity kırıldı: {s!r} → SQL={got!r} PY={tr_ascii_kebab(s)!r}"
        )


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


async def _art(db, sid: uuid.UUID, pub: datetime, norm: str, etype: str) -> None:
    aid = uuid.uuid4()
    h = aid.hex
    await db.execute(
        text(
            "INSERT INTO articles (id, source_id, canonical_url, source_url, title, "
            "content_hash, title_hash, published_at) VALUES (:id, :sid, :u, :u, 't', :h, :h, :p)"
        ),
        {"id": aid, "sid": sid, "u": f"https://x/{h}", "h": h, "p": pub},
    )
    await db.execute(
        text(
            "INSERT INTO entities (article_id, entity_text, entity_normalized, entity_type) "
            "VALUES (:a, :t, :n, :et)"
        ),
        {"a": aid, "t": norm, "n": norm, "et": etype},
    )


async def test_trend_metrics_for_clusters_e2e(test_db_session):
    db = test_db_session
    s1 = await _src(db)
    s2 = await _src(db)
    win_start = _NOW - timedelta(hours=24)
    prev_start = _NOW - timedelta(hours=48)

    # "özgür özel" (person): cur=6 (2 kaynak), prev=2 → küme anahtarı "person:ozgur-ozel"
    for i in range(6):
        await _art(
            db, s1 if i % 2 else s2, win_start + timedelta(hours=2 + i), "özgür özel", "person"
        )
    for i in range(2):
        await _art(
            db, s1 if i % 2 else s2, prev_start + timedelta(hours=3 + i), "özgür özel", "person"
        )
    # gürültü: başka entity (eşleşmemeli)
    await _art(db, s1, _NOW - timedelta(hours=1), "başka konu", "event")

    key = canonical_cluster_key("person", "özgür özel")  # "person:ozgur-ozel"
    out = await trend_metrics_for_clusters(db, [key], window_seconds=86_400, now=_NOW)

    assert key in out, f"küme anahtarı eşleşmedi: {key}; dönen: {list(out)}"
    m = out[key]
    assert m.article_count == 6
    assert m.previous_article_count == 2
    assert m.unique_sources == 2
    assert m.relative_momentum is not None
    assert m.trend_state in {"breaking", "developing", "stable", "fading"}
    # eşleşmeyen anahtar dict'te olmamalı
    assert canonical_cluster_key("person", "olmayan kisi") not in out


async def _canon(db, name: str, norm: str, etype: str) -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO canonical_entities (id, canonical_name, entity_type, "
            "canonical_normalized, source) VALUES (:id, :n, :et, :cn, 'wikidata')"
        ),
        {"id": cid, "n": name, "et": etype, "cn": norm},
    )
    return cid


async def _alias(db, alias_norm: str, etype: str, cid: uuid.UUID) -> None:
    await db.execute(
        text(
            "INSERT INTO entity_aliases (alias_normalized, entity_type, canonical_id, source) "
            "VALUES (:a, :et, :cid, 'wikidata')"
        ),
        {"a": alias_norm, "et": etype, "cid": cid},
    )


async def test_trend_metrics_canonical_alias_grouping(test_db_session):
    """#1712 — alias→canonical: trend metriği CANONICAL cluster_key'e hizalanır.

    'filenin sultanları' entity'si Wikidata canonical'a ('Türkiye kadın millî voleybol
    takımı') maplenince, trend metriği ham 'org:filenin-sultanlari' yerine CANONICAL
    anahtarla eşleşir → küme (resolver da canonical) ile SENKRON.
    """
    db = test_db_session
    s1 = await _src(db)
    s2 = await _src(db)
    win_start = _NOW - timedelta(hours=24)
    prev_start = _NOW - timedelta(hours=48)
    cid = await _canon(
        db, "Türkiye kadın millî voleybol takımı", "türkiye kadın millî voleybol takımı", "org"
    )
    await _alias(db, "filenin sultanları", "org", cid)
    for i in range(6):
        await _art(
            db, s1 if i % 2 else s2, win_start + timedelta(hours=2 + i), "filenin sultanları", "org"
        )
    for i in range(2):
        await _art(
            db,
            s1 if i % 2 else s2,
            prev_start + timedelta(hours=3 + i),
            "filenin sultanları",
            "org",
        )

    canon_key = canonical_cluster_key("org", "türkiye kadın millî voleybol takımı")
    raw_key = canonical_cluster_key("org", "filenin sultanları")
    out = await trend_metrics_for_clusters(
        db, [canon_key, raw_key], window_seconds=86_400, now=_NOW
    )
    # CANONICAL anahtar eşleşir (entity canonical'a maplenmiş)
    assert canon_key in out, f"canonical key eşleşmedi: {canon_key}; dönen: {list(out)}"
    assert out[canon_key].article_count == 6
    # ham anahtar artık eşleşmez (canonical'a yönlendi → SENKRON)
    assert raw_key not in out


async def test_trend_metrics_empty_keys_noop(test_db_session):
    out = await trend_metrics_for_clusters(test_db_session, [], window_seconds=86_400, now=_NOW)
    assert out == {}


async def test_rising_entities_filters_to_breaking_developing(test_db_session):
    """G — rising_entities yalnız yükselen (breaking/developing) entity'leri döndürür.

    'patlayan' (prev az + cur son-6saatte yoğun, korpus-üstü) yükselir; 'sakin'
    (korpusla aynı/altı, düz) yükselmez → listede olmamalı.
    """
    db = test_db_session
    s1 = await _src(db)
    s2 = await _src(db)
    win_start = _NOW - timedelta(hours=24)
    prev_start = _NOW - timedelta(hours=48)

    # patlayan (place): prev=2, cur=20 son 6 saatte yoğun
    for i in range(2):
        await _art(
            db, s1 if i % 2 else s2, prev_start + timedelta(hours=3 + i), "patlayan", "place"
        )
    for i in range(20):
        await _art(
            db,
            s1 if i % 2 else s2,
            _NOW - timedelta(hours=0.25 * (i % 6) + 0.2),
            "patlayan",
            "place",
        )
    # sakin (place): prev=18, cur=20 (24s'e düz yayılı) → korpus-altı, düz
    for i in range(18):
        await _art(
            db, s1 if i % 2 else s2, prev_start + timedelta(minutes=40 * i), "sakin", "place"
        )
    for i in range(20):
        await _art(db, s1 if i % 2 else s2, win_start + timedelta(hours=1.1 * i), "sakin", "place")

    out = await rising_entities(db, window_seconds=86_400, now=_NOW, limit=10)
    keys = {r.cluster_key for r in out}
    assert canonical_cluster_key("place", "patlayan") in keys
    assert canonical_cluster_key("place", "sakin") not in keys
    for r in out:
        assert r.trend_state in {"breaking", "developing"}


async def test_cluster_supply_detail_articles_and_timeline(test_db_session):
    """F — cluster_supply_detail kebab-match ile haber/sparkline/metrik döndürür."""
    from app.modules.trends.cluster_link import cluster_supply_detail

    db = test_db_session
    s1 = await _src(db)
    s2 = await _src(db)
    win_start = _NOW - timedelta(hours=24)
    for i in range(5):
        await _art(
            db, s1 if i % 2 else s2, win_start + timedelta(hours=3 + i), "özgür özel", "person"
        )
    await _art(db, s1, _NOW - timedelta(hours=1), "alakasiz", "event")  # eşleşmemeli

    key = canonical_cluster_key("person", "özgür özel")
    det = await cluster_supply_detail(db, key, window_seconds=86_400, now=_NOW, limit=10)
    assert det.article_count == 5
    assert len(det.articles) == 5
    assert len(det.sparkline) == 12  # 24h → 12 bucket
    assert sum(p.article_count for p in det.sparkline) == 5
    assert det.unique_sources == 2


async def test_coverage_sources_for_clusters(test_db_session):
    """E-lite — tarihsel kapsayan kaynaklar (azalan sayım) + eşleşmeyen boş."""
    from app.modules.trends.cluster_link import coverage_sources_for_clusters

    db = test_db_session
    s1 = await _src(db)
    s2 = await _src(db)
    # s1 → 3 makale, s2 → 1 makale (son 30g içinde)
    for i in range(3):
        await _art(db, s1, _NOW - timedelta(days=2 + i), "özgür özel", "person")
    await _art(db, s2, _NOW - timedelta(days=1), "özgür özel", "person")

    key = canonical_cluster_key("person", "özgür özel")
    cov = await coverage_sources_for_clusters(db, [key], now=_NOW)
    assert key in cov
    counts = dict(cov[key])
    assert counts and max(counts.values()) == 3  # s1 baskın
    assert sum(counts.values()) == 4
    # s1 ilk (azalan sıralı)
    assert cov[key][0][1] == 3
    # eşleşmeyen anahtar yok
    assert canonical_cluster_key("person", "yok kisi") not in cov
