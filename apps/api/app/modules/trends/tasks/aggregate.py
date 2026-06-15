"""Trend aggregation Celery tasks (Faz 2 PR-2b, #1505).

Tasks (event_queue, hepsi flag-gated default OFF):
    aggregate_trends()           — beat :20. assign (trends.assignment.enabled) →
                                   snapshot kapanmış saat bucket'ı (trends.snapshots.enabled).
    backfill_snapshots(s, e)     — verilen tarih aralığı için snapshot (idempotent).
    prune_snapshots()            — beat günlük. 180g'den eski snapshot sil
                                   (trends.retention.enabled).

İdempotency: snapshot upsert ON CONFLICT (subject_type,subject_id,bucket_start,
algo_version) DO UPDATE + yalnız KAPANMIŞ bucket (önceki tam saat) → re-run =
identical. Cross-domain okuma RAW SQL (import-linter: trends sibling import etmez).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trends.aggregation import (
    BUCKET_SECONDS,
    BURST_BASELINE_BUCKETS,
    BURST_SIGNAL_THRESHOLD,
    TRENDS_ALGO_VERSION,
    compute_burst_score,
    compute_momentum,
    compute_novelty,
    compute_source_diversity,
    compute_trend_state,
    compute_velocity,
)
from app.modules.trends.topic_assignment import assign_cluster_to_topic
from app.shared.runtime_config.settings_store import settings_store
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

RETENTION_DAYS = 180
_ASSIGN_BATCH = 100
_SNAPSHOT_BATCH = 200
_LIVE_TOPIC_WINDOW_DAYS = 7


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


# =============================================================================
# Topic assignment (live cluster → topic)
# =============================================================================


async def _assign_live_clusters(db: AsyncSession, now: datetime) -> dict:
    """Atanmamış live cluster'ları topic'lere ata (idempotent)."""
    cutoff = now - timedelta(days=_LIVE_TOPIC_WINDOW_DAYS)
    rows = (
        await db.execute(
            sa_text(
                """
                SELECT ec.id
                FROM event_clusters ec
                WHERE ec.status IN ('developing', 'active', 'cooling')
                  AND ec.last_seen_at >= :cutoff
                  AND NOT EXISTS (
                      SELECT 1 FROM topic_clusters tc WHERE tc.event_cluster_id = ec.id
                  )
                ORDER BY ec.last_seen_at DESC
                LIMIT :lim
                """
            ),
            {"cutoff": cutoff, "lim": _ASSIGN_BATCH},
        )
    ).all()
    counts = {"seeded": 0, "matched": 0, "skipped": 0}
    for r in rows:
        res = await assign_cluster_to_topic(db, r.id, now)
        action = res.get("action", "skipped")
        counts[action if action in counts else "skipped"] += 1
    return {"processed": len(rows), **counts}


# =============================================================================
# Snapshot yazımı (topic başına, kapanmış bucket)
# =============================================================================


async def _write_topic_snapshot(
    db: AsyncSession, topic_id, topic_first_seen: datetime, bucket_start: datetime
) -> bool:
    """Bir topic için bucket snapshot'ını upsert et. Burst sinyali atıldıysa True."""
    bucket_end = bucket_start + timedelta(seconds=BUCKET_SECONDS)

    agg = (
        await db.execute(
            sa_text(
                """
                SELECT COUNT(*) AS ac,
                       COUNT(DISTINCT ea.source_id) AS usc,
                       AVG(s.reliability_score) AS avgrel
                FROM event_articles ea
                JOIN topic_clusters tc ON tc.event_cluster_id = ea.event_id
                LEFT JOIN sources s ON s.id = ea.source_id
                WHERE tc.topic_id = :tid
                  AND ea.published_at >= :bs AND ea.published_at < :be
                """
            ),
            {"tid": topic_id, "bs": bucket_start, "be": bucket_end},
        )
    ).first()
    cur = int(agg.ac or 0)
    unique_sources = int(agg.usc or 0)
    credibility = round(float(agg.avgrel), 4) if agg.avgrel is not None else None

    cumulative = int(
        (
            await db.execute(
                sa_text(
                    """
                    SELECT COUNT(*) FROM event_articles ea
                    JOIN topic_clusters tc ON tc.event_cluster_id = ea.event_id
                    WHERE tc.topic_id = :tid AND ea.published_at < :be
                    """
                ),
                {"tid": topic_id, "be": bucket_end},
            )
        ).scalar()
        or 0
    )

    trailing = (
        await db.execute(
            sa_text(
                """
                SELECT bucket_start, article_count, velocity_1h
                FROM trend_snapshots
                WHERE subject_type = 'topic' AND subject_id = :tid
                  AND algo_version = :av AND bucket_start < :bs
                ORDER BY bucket_start DESC
                LIMIT :lim
                """
            ),
            {
                "tid": topic_id,
                "av": TRENDS_ALGO_VERSION,
                "bs": bucket_start,
                "lim": BURST_BASELINE_BUCKETS,
            },
        )
    ).all()
    counts_by_bs = {r.bucket_start: int(r.article_count) for r in trailing}
    prev_1h = counts_by_bs.get(bucket_start - timedelta(hours=1))
    prev_6h = counts_by_bs.get(bucket_start - timedelta(hours=6))
    prev_24h = counts_by_bs.get(bucket_start - timedelta(hours=24))
    prev_vel_1h = (
        float(trailing[0].velocity_1h) if trailing and trailing[0].velocity_1h is not None else None
    )

    velocity_1h = compute_velocity(cur, prev_1h)
    velocity_6h = compute_velocity(cur, prev_6h)
    velocity_24h = compute_velocity(cur, prev_24h)
    acceleration = (
        round(velocity_1h - prev_vel_1h, 4)
        if velocity_1h is not None and prev_vel_1h is not None
        else None
    )
    burst = compute_burst_score(cur, [int(r.article_count) for r in trailing])
    novelty = compute_novelty(topic_first_seen, bucket_start)
    source_diversity = compute_source_diversity(unique_sources, cur)
    prev_for_state = prev_1h if prev_1h is not None else 0
    momentum = compute_momentum(cur, prev_for_state)
    trend_state = compute_trend_state(cur, prev_for_state, momentum)

    await db.execute(
        sa_text(
            """
            INSERT INTO trend_snapshots (
                subject_type, subject_id, bucket_start, bucket_seconds, algo_version,
                article_count, cumulative_article_count, unique_source_count,
                source_diversity, velocity_1h, velocity_6h, velocity_24h, acceleration,
                burst_score, novelty_score, credibility_score, trend_state
            ) VALUES (
                'topic', :tid, :bs, :bsec, :av,
                :ac, :cum, :usc,
                :div, :v1, :v6, :v24, :acc,
                :burst, :nov, :cred, :state
            )
            ON CONFLICT (subject_type, subject_id, bucket_start, algo_version)
            DO UPDATE SET
                article_count = EXCLUDED.article_count,
                cumulative_article_count = EXCLUDED.cumulative_article_count,
                unique_source_count = EXCLUDED.unique_source_count,
                source_diversity = EXCLUDED.source_diversity,
                velocity_1h = EXCLUDED.velocity_1h,
                velocity_6h = EXCLUDED.velocity_6h,
                velocity_24h = EXCLUDED.velocity_24h,
                acceleration = EXCLUDED.acceleration,
                burst_score = EXCLUDED.burst_score,
                novelty_score = EXCLUDED.novelty_score,
                credibility_score = EXCLUDED.credibility_score,
                trend_state = EXCLUDED.trend_state
            """
        ),
        {
            "tid": topic_id,
            "bs": bucket_start,
            "bsec": BUCKET_SECONDS,
            "av": TRENDS_ALGO_VERSION,
            "ac": cur,
            "cum": cumulative,
            "usc": unique_sources,
            "div": source_diversity,
            "v1": velocity_1h,
            "v6": velocity_6h,
            "v24": velocity_24h,
            "acc": acceleration,
            "burst": burst,
            "nov": novelty,
            "cred": credibility,
            "state": trend_state,
        },
    )

    if burst >= BURST_SIGNAL_THRESHOLD and cur > 0:
        await db.execute(
            sa_text(
                """
                INSERT INTO trend_signals (
                    subject_type, subject_id, signal_type, detected_at,
                    bucket_seconds, algo_version, magnitude, status, payload
                ) VALUES (
                    'topic', :tid, 'burst', :bs, :bsec, :av, :mag, 'new',
                    CAST(:payload AS jsonb)
                )
                ON CONFLICT (subject_type, subject_id, signal_type, detected_at, algo_version)
                DO UPDATE SET magnitude = EXCLUDED.magnitude, payload = EXCLUDED.payload
                """
            ),
            {
                "tid": topic_id,
                "bs": bucket_start,
                "bsec": BUCKET_SECONDS,
                "av": TRENDS_ALGO_VERSION,
                "mag": burst,
                "payload": json.dumps({"article_count": cur, "burst_score": burst}),
            },
        )
        return True
    return False


async def _snapshot_live_topics(db: AsyncSession, bucket_start: datetime) -> dict:
    """Tüm live topic'ler için bucket snapshot'ı yaz."""
    cutoff = bucket_start - timedelta(days=_LIVE_TOPIC_WINDOW_DAYS)
    topics = (
        await db.execute(
            sa_text(
                """
                SELECT id, first_seen_at FROM topics
                WHERE status IN ('active', 'dormant') AND last_seen_at >= :cutoff
                ORDER BY last_seen_at DESC
                LIMIT :lim
                """
            ),
            {"cutoff": cutoff, "lim": _SNAPSHOT_BATCH},
        )
    ).all()
    signals = 0
    errors = 0
    for t in topics:
        # Per-topic SAVEPOINT izolasyonu: bir topic'in yazımı hata verirse
        # (aborted transaction) tüm batch çökmesin → savepoint'e rollback +
        # log + sonraki topic'e devam. Outer transaction sağlam kalır.
        try:
            async with db.begin_nested():
                if await _write_topic_snapshot(db, t.id, t.first_seen_at, bucket_start):
                    signals += 1
        except Exception:
            logger.exception("trend snapshot failed topic_id=%s bucket=%s", t.id, bucket_start)
            errors += 1
    return {"topics": len(topics), "signals": signals, "errors": errors}


# =============================================================================
# Celery tasks
# =============================================================================


async def _aggregate_trends_async() -> dict:
    factory = _get_session_factory()
    async with factory() as db:
        assign_on = await settings_store.get_bool(db, "trends.assignment.enabled", False)
        snap_on = await settings_store.get_bool(db, "trends.snapshots.enabled", False)
        if not assign_on and not snap_on:
            return {"skipped": "disabled"}

        now = datetime.now(UTC)
        bucket_start = _floor_hour(now) - timedelta(hours=1)  # kapanmış tam saat
        summary: dict = {
            "bucket_start": bucket_start.isoformat(),
            "algo_version": TRENDS_ALGO_VERSION,
        }

        if assign_on:
            summary["assignment"] = await _assign_live_clusters(db, now)
            await db.commit()
        if snap_on:
            summary["snapshot"] = await _snapshot_live_topics(db, bucket_start)
            await db.commit()
        return summary


@celery_app.task(name="tasks.trends.aggregate_trends", bind=True)
def aggregate_trends(self) -> dict:  # type: ignore[no-untyped-def]
    """Beat :20 — topic assignment + kapanmış bucket snapshot (flag-gated)."""
    return _run_async(_aggregate_trends_async())


async def _backfill_snapshots_async(start_iso: str, end_iso: str) -> dict:
    factory = _get_session_factory()
    async with factory() as db:
        if not await settings_store.get_bool(db, "trends.snapshots.enabled", False):
            return {"skipped": "disabled"}
        start = _floor_hour(datetime.fromisoformat(start_iso))
        end = _floor_hour(datetime.fromisoformat(end_iso))
        buckets = 0
        total_signals = 0
        cursor = start
        while cursor < end:
            res = await _snapshot_live_topics(db, cursor)
            total_signals += res["signals"]
            buckets += 1
            await db.commit()
            cursor += timedelta(seconds=BUCKET_SECONDS)
        return {
            "buckets": buckets,
            "signals": total_signals,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }


@celery_app.task(name="tasks.trends.backfill_snapshots", bind=True)
def backfill_snapshots(self, start_iso: str, end_iso: str) -> dict:  # type: ignore[no-untyped-def]
    """Tarih aralığı için snapshot backfill (idempotent upsert)."""
    return _run_async(_backfill_snapshots_async(start_iso, end_iso))


async def _prune_snapshots_async() -> dict:
    factory = _get_session_factory()
    async with factory() as db:
        if not await settings_store.get_bool(db, "trends.retention.enabled", False):
            return {"skipped": "disabled"}
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        deleted = (
            await db.execute(
                sa_text("DELETE FROM trend_snapshots WHERE bucket_start < :cut"),
                {"cut": cutoff},
            )
        ).rowcount
        await db.commit()
        return {"deleted": int(deleted or 0), "cutoff": cutoff.isoformat()}


@celery_app.task(name="tasks.trends.prune_snapshots", bind=True)
def prune_snapshots(self) -> dict:  # type: ignore[no-untyped-def]
    """Beat günlük — retention (180g) eski snapshot sil (flag-gated)."""
    return _run_async(_prune_snapshots_async())
