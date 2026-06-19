"""refresh_cluster_statuses — N+1 batch refactor davranış testi (Bulgu 8).

Per-row UPDATE → iki batch (executemany) refactor'u davranış-koruyucu olmalı:
  - status DEĞİŞMEYEN cluster → importance+freshness güncellenir,
    last_updated_at DOKUNULMAZ.
  - status DEĞİŞEN cluster → status + last_updated_at = NOW() güncellenir.
  - counts dict doğru sayar (unchanged + yeni-status sayaçları).

Docker-gated (testcontainers); helper db param alır → test_db_session.
event_clusters.last_updated_at'in onupdate'i YOK (server_default=now() only),
bu yüzden "unchanged korur" assertion'ı güvenilir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.clusters.clustering import refresh_cluster_statuses
from sqlalchemy import text

pytestmark = pytest.mark.integration

# Bilinen-eski last_updated_at (refresh sonrası "değişti mi" kıyası için sabit).
_OLD = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


async def _insert_cluster(
    db,
    *,
    status: str,
    last_seen_at: datetime,
    article_count: int,
    source_count: int,
) -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO event_clusters "
            "(id, canonical_title, first_seen_at, last_seen_at, last_updated_at, "
            " status, article_count, source_count) "
            "VALUES (:id, 'Test Cluster', :fs, :ls, :upd, :st, :ac, :sc)"
        ),
        {
            "id": cid,
            "fs": _OLD,
            "ls": last_seen_at,
            "upd": _OLD,
            "st": status,
            "ac": article_count,
            "sc": source_count,
        },
    )
    return cid


async def test_refresh_unchanged_writes_scores_preserves_timestamp(test_db_session):
    """Status değişmiyor → score yazılır, last_updated_at korunur."""
    db = test_db_session
    now = datetime.now(UTC)
    # recent + 1 article + status='developing' → compute_status='developing' (unchanged)
    cid = await _insert_cluster(
        db,
        status="developing",
        last_seen_at=now - timedelta(hours=1),
        article_count=1,
        source_count=1,
    )

    counts = await refresh_cluster_statuses(db)

    assert counts["unchanged"] >= 1
    row = (
        await db.execute(
            text(
                "SELECT status, importance_score, freshness_score, last_updated_at "
                "FROM event_clusters WHERE id = :id"
            ),
            {"id": cid},
        )
    ).one()
    assert row.status == "developing"
    assert row.importance_score is not None  # score batch'te yazıldı
    assert row.freshness_score is not None
    assert row.last_updated_at == _OLD  # unchanged → dokunulmadı


async def test_refresh_changed_sets_status_and_timestamp(test_db_session):
    """Status değişiyor → yeni status + last_updated_at=NOW()."""
    db = test_db_session
    now = datetime.now(UTC)
    # last_seen 80h önce + status='developing' → compute_status='cooling' (changed)
    cid = await _insert_cluster(
        db,
        status="developing",
        last_seen_at=now - timedelta(hours=80),
        article_count=5,
        source_count=3,
    )

    counts = await refresh_cluster_statuses(db)

    assert counts["cooling"] >= 1
    row = (
        await db.execute(
            text(
                "SELECT status, importance_score, last_updated_at "
                "FROM event_clusters WHERE id = :id"
            ),
            {"id": cid},
        )
    ).one()
    assert row.status == "cooling"
    assert row.importance_score is not None
    assert row.last_updated_at > _OLD  # changed → NOW()'a güncellendi


async def test_refresh_mixed_batch_all_correct(test_db_session):
    """Karışık çok-cluster (3 unchanged + 2 changed) tek batch'te doğru işlenir."""
    db = test_db_session
    now = datetime.now(UTC)
    unchanged_ids = [
        await _insert_cluster(
            db,
            status="developing",
            last_seen_at=now - timedelta(hours=2),
            article_count=1,
            source_count=1,
        )
        for _ in range(3)
    ]
    changed_ids = [
        await _insert_cluster(
            db,
            status="active",  # ama last_seen 10g önce → compute_status='stale'
            last_seen_at=now - timedelta(days=10),
            article_count=10,
            source_count=5,
        )
        for _ in range(2)
    ]

    counts = await refresh_cluster_statuses(db)

    assert counts["unchanged"] >= 3
    assert counts["stale"] >= 2

    for cid in changed_ids:
        row = (
            await db.execute(
                text(
                    "SELECT status, importance_score, last_updated_at "
                    "FROM event_clusters WHERE id = :id"
                ),
                {"id": cid},
            )
        ).one()
        assert row.status == "stale"
        assert row.importance_score is not None
        assert row.last_updated_at > _OLD  # changed → NOW()'a güncellendi

    for cid in unchanged_ids:
        row = (
            await db.execute(
                text(
                    "SELECT status, freshness_score, last_updated_at "
                    "FROM event_clusters WHERE id = :id"
                ),
                {"id": cid},
            )
        ).one()
        assert row.status == "developing"
        assert row.freshness_score is not None
        assert row.last_updated_at == _OLD  # unchanged → korundu
