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
