"""Admin queue / DLQ endpoint smoke tests.

Auth ve DB integration testleri Faz 1 testcontainers (#43) ile gelecek;
burada router include + Pydantic model invariantları doğrulanır.

#444: Celery broker introspection + retry dispatch helper testleri eklendi.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


def test_admin_queue_router_registered():
    """Router main.app'a eklenmiş mi?"""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/queue/overview" in paths
    assert "/admin/queue/failed" in paths


def test_pydantic_failed_job_public_fields():
    """FailedJobPublic stack_trace + payload + resolution alanlarını taşımalı."""
    from app.api.admin_queue import FailedJobPublic

    fields = FailedJobPublic.model_fields
    assert "stack_trace" in fields
    assert "payload" in fields
    assert "resolved_at" in fields
    assert "resolved_by" in fields
    assert "resolution_note" in fields


def test_pydantic_queue_overview_shape():
    from app.api.admin_queue import QueueOverviewResponse, QueueStat

    sample = QueueOverviewResponse(
        queues=[
            QueueStat(
                name="crawl_queue",
                queued_count=5,
                running_count=1,
                succeeded_count_24h=200,
                failed_count_24h=2,
            )
        ],
        failed_jobs_unresolved=3,
    )
    assert sample.queues[0].name == "crawl_queue"
    assert sample.failed_jobs_unresolved == 3


def test_resolve_request_max_note_len():
    from pydantic import ValidationError

    from app.api.admin_queue import ResolveRequest

    # Boş + kısa → OK
    ResolveRequest(note=None)
    ResolveRequest(note="kısa not")
    # 501 char → reddedilmeli
    long_note = "x" * 501
    try:
        ResolveRequest(note=long_note)
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError for >500 char note")


def test_retry_response_shape():
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.api.admin_queue import RetryResponse

    r = RetryResponse(new_job_id=uuid4(), scheduled_at=datetime.now(timezone.utc))
    assert r.new_job_id is not None
    # #444 — celery_task_id default empty, geriye dönük uyumlu
    assert r.celery_task_id == ""


# ---------------------------------------------------------------------------
# #444 — Celery broker introspection + retry dispatch helper tests
# ---------------------------------------------------------------------------


def test_tracked_queues_match_celery_routing():
    """Admin overview'in izlediği kuyruklar celery_app task_routes ile birebir.

    Test broker'la haberleşmeyen 'crawl_queue', 'embedding_queue', 'event_queue',
    'image_vlm_queue' isimlerinin celery_app config ile uyumlu olduğunu
    doğrular — config'de değişiklik admin sayfasını sessizce kırarsa burada
    yakalansın.
    """
    from app.api.admin_queue import _TRACKED_QUEUES
    from app.workers.celery_app import celery_app

    routes = celery_app.conf.task_routes or {}
    routed_queues = {v.get("queue") for v in routes.values() if v}
    for q in _TRACKED_QUEUES:
        assert q in routed_queues, f"{q} celery task_routes'ta yok"


def test_task_for_job_type_known_mappings():
    from app.core.celery_introspect import task_for_job_type

    # Article tarafı — fetch_detail tüm article.* için entry point
    assert task_for_job_type("article.fetch_detail") == "tasks.articles.fetch_detail"
    assert task_for_job_type("article.extract") == "tasks.articles.fetch_detail"
    assert task_for_job_type("article.clean") == "tasks.articles.fetch_detail"
    assert (
        task_for_job_type("article.duplicate_content")
        == "tasks.articles.fetch_detail"
    )

    # Image tarafı
    assert (
        task_for_job_type("image_vlm.process")
        == "tasks.image_vlm.process_article_image_vlm"
    )

    # Bilinmeyen → None
    assert task_for_job_type("unknown.thing") is None
    assert task_for_job_type("") is None


def test_payload_arg_for_task_extraction():
    from app.api.admin_queue import _payload_arg_for_task

    aid = "11111111-1111-1111-1111-111111111111"
    iid = "22222222-2222-2222-2222-222222222222"

    # Article task → article_id
    assert _payload_arg_for_task("article.fetch_detail", {"article_id": aid}) == aid
    assert _payload_arg_for_task("article.extract", {"article_id": aid}) == aid

    # Image task → article_image_id (öncelik) ya da image_id
    assert (
        _payload_arg_for_task("image_vlm.process", {"article_image_id": iid}) == iid
    )
    assert _payload_arg_for_task("image_vlm.process", {"image_id": iid}) == iid

    # Eksik payload → None (dispatcher 422 dönmeli)
    assert _payload_arg_for_task("article.fetch_detail", {}) is None
    assert _payload_arg_for_task("image_vlm.process", {}) is None

    # Bilinmeyen prefix → None
    assert _payload_arg_for_task("totally.unknown", {"x": 1}) is None


def test_celery_introspect_queue_name_fallback():
    """Task name'inden queue resolve fallback — task_routes ile birebir."""
    from app.core.celery_introspect import _queue_from_task_name

    assert _queue_from_task_name("tasks.sources.crawl_active_sources") == "crawl_queue"
    assert _queue_from_task_name("tasks.articles.fetch_detail") == "crawl_queue"
    assert _queue_from_task_name("tasks.image_vlm.process_article_image_vlm") == "image_vlm_queue"
    assert _queue_from_task_name("tasks.embedding.chunk_article") == "embedding_queue"
    assert _queue_from_task_name("tasks.maintenance.cold_tier_archive") == "embedding_queue"
    assert _queue_from_task_name("tasks.clustering.cluster_article") == "event_queue"
    assert _queue_from_task_name("tasks.agenda.refresh_active_cards") == "event_queue"
    assert _queue_from_task_name("tasks.raptor.build_weekly_summary_cards") == "event_queue"
    assert _queue_from_task_name("tasks.media.download_article_image") == "media_queue"
    assert _queue_from_task_name("unknown.task") is None


def test_get_active_counts_fallback_when_inspect_returns_none():
    """celery inspect None dönerse (broker kapalı) tüm queue'lar 0."""
    import asyncio

    from app.core.celery_introspect import get_active_counts_by_queue

    with patch("app.core.celery_introspect._inspect_blocking", return_value=None):
        counts = asyncio.run(
            get_active_counts_by_queue(["crawl_queue", "embedding_queue"])
        )
    assert counts == {"crawl_queue": 0, "embedding_queue": 0}


def test_get_active_counts_aggregates_workers():
    """Birden çok worker'da aktif task'lar toplanır, queue bazlı."""
    import asyncio

    from app.core.celery_introspect import get_active_counts_by_queue

    fake_active: dict[str, list[dict[str, Any]]] = {
        "worker1@host": [
            {
                "name": "tasks.articles.fetch_detail",
                "delivery_info": {"routing_key": "crawl_queue"},
            },
            {
                "name": "tasks.image_vlm.process_article_image_vlm",
                "delivery_info": {"routing_key": "image_vlm_queue"},
            },
        ],
        "worker2@host": [
            {
                "name": "tasks.articles.fetch_detail",
                # routing_key yok → name fallback
                "delivery_info": {},
            },
        ],
    }

    with patch(
        "app.core.celery_introspect._inspect_blocking", return_value=fake_active
    ):
        counts = asyncio.run(
            get_active_counts_by_queue(
                ["crawl_queue", "embedding_queue", "image_vlm_queue"]
            )
        )
    assert counts == {
        "crawl_queue": 2,  # 1'i routing_key, 1'i name fallback
        "embedding_queue": 0,
        "image_vlm_queue": 1,
    }


def test_failed_job_public_has_severity_field():
    """#445 — severity field FailedJobPublic'e eklenmeli."""
    from app.api.admin_queue import FailedJobPublic

    fields = FailedJobPublic.model_fields
    assert "severity" in fields
    # Default 'error' (geriye dönük uyumlu — eski rows severity yoksa)
    sample = FailedJobPublic(
        id="11111111-1111-1111-1111-111111111111",
        original_job_id=None,
        job_type="article.fetch_detail",
        source_id=None,
        article_url=None,
        error_message="x",
        stack_trace=None,
        retry_count=0,
        last_attempt_at="2026-05-08T12:00:00Z",
        resolved_at=None,
        resolved_by=None,
        resolution_note=None,
        payload={},
    )
    assert sample.severity == "error"


def test_failed_job_model_has_severity():
    """SQLAlchemy ORM model'ında severity kolonu var."""
    from app.models.job import FailedJob

    assert hasattr(FailedJob, "severity")


def test_record_failure_supports_permanent_info():
    """articles.py:_record_failure permanent_info severity'i kabul eder."""
    import inspect as _inspect

    from app.workers.tasks import articles as articles_module

    sig = _inspect.signature(articles_module._record_failure)
    assert "severity" in sig.parameters
    assert sig.parameters["severity"].default == "error"


def test_bulk_endpoints_registered():
    """#462 — bulk-retry + bulk-resolve route'ları eklenmiş olmalı."""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/queue/failed/bulk-retry" in paths
    assert "/admin/queue/failed/bulk-resolve" in paths


def test_bulk_request_validation():
    """#462 — BulkRequest min_length=1, max_length=200 ids."""
    from pydantic import ValidationError

    from app.api.admin_queue import BulkRequest

    # Boş id listesi reddedilmeli
    try:
        BulkRequest(ids=[])
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError for empty ids")

    # 200'den fazla id reddedilmeli
    try:
        from uuid import uuid4

        BulkRequest(ids=[uuid4() for _ in range(201)])
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError for >200 ids")


def test_bulk_response_shape():
    from uuid import uuid4

    from app.api.admin_queue import BulkResponse, BulkResultItem

    sample = BulkResponse(
        succeeded=2,
        failed=1,
        results=[
            BulkResultItem(id=uuid4(), ok=True, celery_task_id="abc-1"),
            BulkResultItem(id=uuid4(), ok=True, celery_task_id="abc-2"),
            BulkResultItem(id=uuid4(), ok=False, code="JOB_TYPE_NOT_DISPATCHABLE"),
        ],
    )
    assert sample.succeeded == 2
    assert sample.failed == 1
    assert len(sample.results) == 3
    assert sample.results[0].ok is True
    assert sample.results[2].code == "JOB_TYPE_NOT_DISPATCHABLE"


def test_maintenance_endpoints_registered():
    """#468 — bakım endpoint'leri kayıtlı."""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/queue/maintenance" in paths
    assert "/admin/queue/maintenance/{task_name}/run-now" in paths


def test_maintenance_tracker_tracked_tasks():
    """#468 — TRACKED_TASKS 5 öğe içermeli, beat schedule ile uyumlu."""
    from app.core.maintenance_tracker import TRACKED_TASKS
    from app.workers.celery_app import celery_app

    assert len(TRACKED_TASKS) == 5
    expected = {
        "tasks.articles.backfill_discovered",
        "tasks.articles.retry_failed",
        "tasks.image_vlm.backfill_pending",
        "tasks.image_vlm.retry_failed",
        "tasks.articles.backfill_missing_chunks",
    }
    assert set(TRACKED_TASKS) == expected

    # Beat schedule'da hepsi tanımlı mı? Schedule entry'leri task name'le
    # eşleştirilir (entry["task"]).
    scheduled = {
        entry.get("task")
        for entry in (celery_app.conf.beat_schedule or {}).values()
    }
    for t in TRACKED_TASKS:
        assert t in scheduled, f"{t} celery beat_schedule'da yok"


def test_maintenance_tracker_human_labels():
    from app.core.maintenance_tracker import (
        TRACKED_TASKS,
        is_tracked,
        task_human_label,
        task_pipeline,
    )

    for t in TRACKED_TASKS:
        assert is_tracked(t)
        # Label = ham isim DEĞİL — dictionary kapsamlı olmalı
        assert task_human_label(t) != t
        assert task_pipeline(t) in {"Kazıyıcı", "Görsel VLM", "Vektörleştirici"}

    # Bilinmeyen → False
    assert not is_tracked("tasks.unknown.foo")


def test_failed_prefix_map_covers_known_job_types():
    """Üretilen failed_jobs.job_type değerleri en az bir kuyruk prefix'iyle eşleşmeli."""
    from app.api.admin_queue import _QUEUE_FAILED_PREFIXES

    # articles.py'de yazılan tüm job_type değerleri
    known_job_types = [
        "article.fetch_detail",
        "article.extract",
        "article.clean",
        "article.duplicate_content",
        "article.discovered_timeout",
    ]

    all_prefixes: list[str] = []
    for prefixes in _QUEUE_FAILED_PREFIXES.values():
        all_prefixes.extend(prefixes)

    for jt in known_job_types:
        assert any(
            jt.startswith(p) for p in all_prefixes
        ), f"{jt} hiçbir _QUEUE_FAILED_PREFIXES entry'siyle eşleşmiyor"
