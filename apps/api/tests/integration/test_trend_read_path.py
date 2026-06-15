"""PR-2c (#1505) — snapshot-öncelikli read path (Docker-gated).

_read_topic_trends: snapshot yoksa None (caller canlı fallback); seeded snapshot →
topic-tabanlı TrendListItem. db param ile test_db_session (endpoint dependency).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.api.admin_trends import _read_topic_trends
from sqlalchemy import text

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
_WIN_START = _NOW - timedelta(hours=24)


async def test_read_topic_trends_empty_returns_none(test_db_session):
    """Snapshot yok → None (caller canlı path'e düşer)."""
    res = await _read_topic_trends(
        test_db_session, _WIN_START, _NOW, "momentum", 12, 7200, 50, 0, 2, 2
    )
    assert res is None


async def test_read_topic_trends_seeded(test_db_session):
    db = test_db_session
    tid = uuid.uuid4()
    bucket = _NOW - timedelta(hours=1)  # pencere içinde

    await db.execute(
        text(
            "INSERT INTO topics (id, slug, label, topic_kind, first_seen_at, last_seen_at) "
            "VALUES (:id, :slug, 'Merkez Bankası faiz kararı', 'event', :fs, :ls)"
        ),
        {"id": tid, "slug": f"mb-faiz-{tid.hex[:8]}", "fs": _WIN_START, "ls": bucket},
    )
    await db.execute(
        text(
            "INSERT INTO trend_snapshots (subject_type, subject_id, bucket_start, "
            "bucket_seconds, algo_version, article_count, unique_source_count, "
            "source_diversity, credibility_score, novelty_score, trend_state, velocity_1h) "
            "VALUES ('topic', :tid, :bs, 3600, 1, 5, 3, 0.600, 0.700, 0.500, 'developing', 2.000)"
        ),
        {"tid": tid, "bs": bucket},
    )

    res = await _read_topic_trends(db, _WIN_START, _NOW, "momentum", 12, 7200, 50, 0, 2, 2)
    assert res is not None
    data, total = res
    assert total == 1
    assert len(data) == 1
    item = data[0]
    assert item.cluster_id == str(tid)  # subject = topic id
    assert item.title == "Merkez Bankası faiz kararı"
    assert item.article_count == 5
    assert item.unique_source_count == 3
    assert item.trend_state == "developing"
    assert item.previous_article_count == 3  # cur(5) - velocity_1h(2)
    assert item.momentum == pytest.approx((5 - 3) / 3, abs=1e-4)
    # sparkline: bucket pencere içinde → ilgili index'te 5
    assert any(p.article_count == 5 for p in item.sparkline)


async def test_read_topic_trends_evidence_gate_filters_below_threshold(test_db_session):
    """#1516: snapshot var ama son bucket gate'in altında (1 haber / 1 kaynak) →
    boş liste döner (None DEĞİL — canlı path'e düşmez)."""
    db = test_db_session
    tid = uuid.uuid4()
    bucket = _NOW - timedelta(hours=1)
    await db.execute(
        text(
            "INSERT INTO topics (id, slug, label, topic_kind, first_seen_at, last_seen_at) "
            "VALUES (:id, :slug, 'Tekil haber başlığı', 'event', :fs, :ls)"
        ),
        {"id": tid, "slug": f"tekil-{tid.hex[:8]}", "fs": _WIN_START, "ls": bucket},
    )
    await db.execute(
        text(
            "INSERT INTO trend_snapshots (subject_type, subject_id, bucket_start, "
            "bucket_seconds, algo_version, article_count, unique_source_count, "
            "source_diversity, credibility_score, novelty_score, trend_state, velocity_1h) "
            "VALUES ('topic', :tid, :bs, 3600, 1, 1, 1, 0.000, 0.700, 0.900, 'developing', 1.000)"
        ),
        {"tid": tid, "bs": bucket},
    )

    res = await _read_topic_trends(db, _WIN_START, _NOW, "momentum", 12, 7200, 50, 0, 2, 2)
    assert res is not None  # snapshot var → canlı fallback'e DÜŞMEZ
    data, total = res
    assert total == 0
    assert data == []

    # gate kapalı (0/0) → aynı satır görünür (reversible)
    res_open = await _read_topic_trends(db, _WIN_START, _NOW, "momentum", 12, 7200, 50, 0, 0, 0)
    assert res_open is not None
    data_open, total_open = res_open
    assert total_open == 1
    assert len(data_open) == 1
