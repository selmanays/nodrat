"""Integration — #1566 korpus-normalize trend_state end-to-end (testcontainers).

`_read_entity_trends`: korpus-geneli hacim büyürken (ramp) korpusla birlikte
büyüyen entity 'breaking' OLMAZ (rel≈0); yalnız korpusu belirgin geçen + pencere-
içi yükselen entity breaking olur. Ham momentum'un 'her şey patlıyor' hatasını
(her ikisi de +%100/+%600 ham momentum → eski mantıkta ikisi de breaking) önler.

tests/migration/ → CI testcontainers job (alembic upgrade head ile tam şema) koşar.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.api.admin_trends import SPARKLINE_BUCKETS, _read_entity_trends
from sqlalchemy import text

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
_WIN_START = _NOW - timedelta(hours=24)
_PREV_START = _NOW - timedelta(hours=48)


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


async def _art(db, sid: uuid.UUID, pub: datetime, norm: str) -> None:
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
            "VALUES (:a, :t, :n, 'place')"
        ),
        {"a": aid, "t": norm, "n": norm},
    )


async def test_corpus_rider_not_breaking_only_true_spike_breaks(test_db_session):
    db = test_db_session
    s1 = await _src(db)
    s2 = await _src(db)

    # rider: korpusla birlikte büyür (prev=4, cur=16, 24s'e yayılı = düz grafik)
    for i in range(4):  # prev pencere
        await _art(db, s1 if i % 2 else s2, _PREV_START + timedelta(hours=2 + i), "rider")
    for i in range(16):  # cur pencere — tüm 24s'e yayılı (flat)
        await _art(db, s1 if i % 2 else s2, _WIN_START + timedelta(hours=1.4 * i), "rider")

    # spike: korpusu belirgin geçer (prev=2, cur=14) + cur son 6 saatte (yükselen grafik)
    for i in range(2):
        await _art(db, s1 if i % 2 else s2, _PREV_START + timedelta(hours=3 + i), "spike")
    for i in range(14):
        await _art(db, s1 if i % 2 else s2, _NOW - timedelta(hours=0.4 * (i % 6) + 0.3), "spike")

    bucket_count, bucket_seconds = SPARKLINE_BUCKETS["24h"]
    data, _total = await _read_entity_trends(
        db,
        _WIN_START,
        _PREV_START,
        _NOW,
        "score",
        bucket_count,
        bucket_seconds,
        50,
        0,
        2,  # min_articles
        2,  # min_sources
        False,
    )
    by_key = {d.cluster_id: d for d in data}
    rider = by_key["place:rider"]
    spike = by_key["place:spike"]

    # Ham momentum İKİSİNİ de breaking yapardı (rider +%300, spike +%600 ham).
    # Korpus-normalize: rider korpusla aynı hızda (rel≈0/negatif) → breaking DEĞİL;
    # spike korpusu geçer + pencere-içi yükselir → breaking.
    assert spike.trend_state == "breaking"
    assert rider.trend_state != "breaking"
    assert spike.relative_momentum is not None and rider.relative_momentum is not None
    assert spike.relative_momentum > rider.relative_momentum
    # spike pencere-içi yükseliyor (son dilim baseline-üstü) → burst pozitif
    assert spike.burst_z is not None and spike.burst_z > 0
