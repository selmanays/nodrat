"""Admin queue / DLQ endpoint smoke tests.

Auth ve DB integration testleri Faz 1 testcontainers (#43) ile gelecek;
burada router include + Pydantic model invariantları doğrulanır.
"""

from __future__ import annotations


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
