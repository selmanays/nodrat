"""Trend worker wiring — Celery task/beat/route + maintenance_tracker (#1505 PR-2b).

DB-bağımsız: task'lar register mi, beat entry'leri var mı, route event_queue mi,
maintenance_tracker tracked + label/pipeline doğru mu.
"""

from __future__ import annotations


def test_trend_tasks_registered():
    from app.modules.trends.tasks import aggregate  # noqa: F401  (decoration → register)
    from app.workers.celery_app import celery_app

    for name in (
        "tasks.trends.aggregate_trends",
        "tasks.trends.backfill_snapshots",
        "tasks.trends.prune_snapshots",
    ):
        assert name in celery_app.tasks, f"{name} celery'de register değil"


def test_beat_entries_present():
    from app.workers.celery_app import celery_app

    beat = celery_app.conf.beat_schedule
    assert "aggregate-trends" in beat
    assert beat["aggregate-trends"]["task"] == "tasks.trends.aggregate_trends"
    assert beat["aggregate-trends"]["options"]["queue"] == "event_queue"
    assert "prune-trend-snapshots" in beat


def test_task_route_event_queue():
    from app.workers.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes["tasks.trends.*"]["queue"] == "event_queue"


def test_maintenance_tracker_registration():
    from app.shared.observability import maintenance_tracker as mt

    assert "tasks.trends.aggregate_trends" in mt.TRACKED_TASKS
    assert "tasks.trends.prune_snapshots" in mt.TRACKED_TASKS
    # backfill arg gerektirir → TRACKED değil
    assert "tasks.trends.backfill_snapshots" not in mt.TRACKED_TASKS
    assert mt.task_human_label("tasks.trends.aggregate_trends").startswith("Trend")
    assert mt.task_pipeline("tasks.trends.prune_snapshots") == "Trend Intelligence"


def test_admin_queue_map():
    from app.modules.ops.admin.queue import _MAINTENANCE_QUEUE

    assert _MAINTENANCE_QUEUE["tasks.trends.aggregate_trends"] == "event_queue"
    assert _MAINTENANCE_QUEUE["tasks.trends.prune_snapshots"] == "event_queue"
