"""Trend worker — SQL-validity + idempotency + seeded end-to-end (#1505 PR-2b).

Docker-gated (testcontainers). Helper'lar db param alır → test_db_session ile
test edilir (task wrapper'ları _get_session_factory kullanır, burada test edilmez).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.trends.tasks.aggregate import _write_topic_snapshot
from app.modules.trends.topic_assignment import assign_cluster_to_topic
from sqlalchemy import text

pytestmark = pytest.mark.integration

_BS = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
_FS = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
_H64 = "a" * 64


async def test_snapshot_idempotent_empty(test_db_session):
    """subject_id FK'siz → rastgele topic; boş event_articles → 0-snapshot + idempotent."""
    tid = uuid.uuid4()
    burst1 = await _write_topic_snapshot(test_db_session, tid, _FS, _BS)
    burst2 = await _write_topic_snapshot(test_db_session, tid, _FS, _BS)
    rows = (
        await test_db_session.execute(
            text("SELECT article_count, trend_state FROM trend_snapshots WHERE subject_id = :t"),
            {"t": tid},
        )
    ).all()
    assert len(rows) == 1  # ON CONFLICT upsert → tek satır (idempotent)
    assert rows[0].article_count == 0
    assert burst1 is False and burst2 is False  # 0 article → burst yok


async def test_assign_nonexistent_cluster(test_db_session):
    res = await assign_cluster_to_topic(test_db_session, uuid.uuid4(), datetime.now(UTC))
    assert res["action"] == "skipped"
    assert res["reason"] == "cluster_not_found"


async def test_seeded_assign_and_snapshot(test_db_session):
    """source→article→cluster→event_article → assign seeds topic → snapshot count=1."""
    db = test_db_session
    sid, aid, ecid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    pub = _BS + timedelta(minutes=30)  # bucket [10:00, 11:00) içinde

    await db.execute(
        text(
            "INSERT INTO sources (id, name, slug, domain, type, base_url) "
            "VALUES (:id, 'Test Kaynak', :slug, 'test.example', 'rss', 'https://test.example')"
        ),
        {"id": sid, "slug": f"test-{sid.hex[:10]}"},
    )
    await db.execute(
        text(
            "INSERT INTO articles (id, source_id, canonical_url, source_url, title, "
            "content_hash, title_hash, published_at) "
            "VALUES (:id, :sid, :url, :url, 'Test Haber', :h, :h, :pub)"
        ),
        {"id": aid, "sid": sid, "url": f"https://test.example/{aid.hex}", "h": _H64, "pub": pub},
    )
    await db.execute(
        text(
            "INSERT INTO event_clusters (id, canonical_title, first_seen_at, last_seen_at, article_count) "
            "VALUES (:id, 'Merkez Bankası faiz kararı', :fs, :ls, 1)"
        ),
        {"id": ecid, "fs": _FS, "ls": pub},
    )
    await db.execute(
        text(
            "INSERT INTO event_articles (event_id, article_id, source_id, published_at) "
            "VALUES (:ec, :a, :s, :pub)"
        ),
        {"ec": ecid, "a": aid, "s": sid, "pub": pub},
    )

    # Assign → topic seed (entity yok → cluster-anchored).
    res = await assign_cluster_to_topic(db, ecid, datetime.now(UTC))
    assert res["action"] == "seeded"
    topic_id = uuid.UUID(res["topic_id"])

    # topic + topic_clusters oluştu mu.
    assert (
        await db.execute(text("SELECT count(*) FROM topics WHERE id = :t"), {"t": topic_id})
    ).scalar() == 1
    assert (
        await db.execute(
            text(
                "SELECT count(*) FROM topic_clusters WHERE topic_id = :t AND event_cluster_id = :c"
            ),
            {"t": topic_id, "c": ecid},
        )
    ).scalar() == 1

    # Idempotent assign: ikinci kez already_assigned.
    res2 = await assign_cluster_to_topic(db, ecid, datetime.now(UTC))
    assert res2["action"] == "already_assigned"

    # Snapshot: bucket içinde 1 haber, 1 kaynak, credibility=0.70 (default).
    await _write_topic_snapshot(db, topic_id, _FS, _BS)
    snap = (
        await db.execute(
            text(
                "SELECT article_count, unique_source_count, credibility_score, source_diversity "
                "FROM trend_snapshots WHERE subject_id = :t AND bucket_start = :bs"
            ),
            {"t": topic_id, "bs": _BS},
        )
    ).first()
    assert snap.article_count == 1
    assert snap.unique_source_count == 1
    assert float(snap.credibility_score) == pytest.approx(0.70, abs=0.001)
    assert float(snap.source_diversity) == pytest.approx(1.0, abs=0.001)  # 1 kaynak / 1 haber

    # Snapshot idempotent: re-run → tek satır.
    await _write_topic_snapshot(db, topic_id, _FS, _BS)
    assert (
        await db.execute(
            text("SELECT count(*) FROM trend_snapshots WHERE subject_id = :t"), {"t": topic_id}
        )
    ).scalar() == 1


async def test_burst_signal_written(test_db_session):
    """burst≥2.0 → trend_signals INSERT (CAST(:payload AS jsonb)) hatasız (#1514).

    trailing baseline [0,0,0] + current bucket'ta 2 haber → burst=(2-0)/max(0,1)=2.0
    → signal yazılır. PR-2b'de :payload::jsonb bind/cast çakışması syntax error
    veriyordu; bu test o yolu kapsar.
    """
    db = test_db_session
    sid, ecid, tid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    pub = _BS + timedelta(minutes=20)

    await db.execute(
        text(
            "INSERT INTO sources (id, name, slug, domain, type, base_url) "
            "VALUES (:id, 'K', :slug, 'b.example', 'rss', 'https://b.example')"
        ),
        {"id": sid, "slug": f"burst-{sid.hex[:10]}"},
    )
    for _ in range(2):  # current bucket'ta 2 haber
        aid = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO articles (id, source_id, canonical_url, source_url, title, "
                "content_hash, title_hash, published_at) "
                "VALUES (:id, :sid, :u, :u, 'H', :h, :h, :pub)"
            ),
            {"id": aid, "sid": sid, "u": f"https://b.example/{aid.hex}", "h": _H64, "pub": pub},
        )
        await db.execute(
            text(
                "INSERT INTO event_articles (event_id, article_id, source_id, published_at) "
                "VALUES (:ec, :a, :s, :pub)"
            ),
            {"ec": ecid, "a": aid, "s": sid, "pub": pub},
        )
    await db.execute(
        text(
            "INSERT INTO event_clusters (id, canonical_title, first_seen_at, last_seen_at, article_count) "
            "VALUES (:id, 'Burst konu', :fs, :ls, 2)"
        ),
        {"id": ecid, "fs": _FS, "ls": pub},
    )
    await db.execute(
        text(
            "INSERT INTO topics (id, slug, label, topic_kind, first_seen_at, last_seen_at) "
            "VALUES (:id, :slug, 'Burst konu', 'event', :fs, :ls)"
        ),
        {"id": tid, "slug": f"burst-konu-{tid.hex[:8]}", "fs": _FS, "ls": pub},
    )
    await db.execute(
        text(
            "INSERT INTO topic_clusters (topic_id, event_cluster_id, assigned_by) "
            "VALUES (:t, :c, 'auto')"
        ),
        {"t": tid, "c": ecid},
    )
    # trailing baseline: 3 önceki bucket, article_count=0
    for h in (1, 2, 3):
        await db.execute(
            text(
                "INSERT INTO trend_snapshots (subject_type, subject_id, bucket_start, "
                "bucket_seconds, algo_version, article_count) "
                "VALUES ('topic', :t, :bs, 3600, 1, 0)"
            ),
            {"t": tid, "bs": _BS - timedelta(hours=h)},
        )

    burst = await _write_topic_snapshot(db, tid, _FS, _BS)
    assert burst is True  # burst≥2.0 → sinyal atıldı
    sig = (
        await db.execute(
            text(
                "SELECT magnitude, payload->>'article_count' AS ac "
                "FROM trend_signals WHERE subject_id = :t AND signal_type = 'burst'"
            ),
            {"t": tid},
        )
    ).first()
    assert sig is not None
    assert float(sig.magnitude) >= 2.0
    assert sig.ac == "2"  # payload jsonb doğru yazıldı (CAST fix)
