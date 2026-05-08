"""Unit tests for image_vlm retry mechanism (#304 fix).

Pure-Python tests — Celery task signature + transient exception listesi
+ retry/permanent decision boundaries. DB integration test'i ayrı yapılır.
"""

from __future__ import annotations

import httpx

from app.core.media import ImageDownloadError, ImageRejected
from app.providers.nim_vlm import (
    VLMError,
    VLMRateLimitError,
    VLMTimeoutError,
)
from app.workers.tasks.image_vlm import _TRANSIENT_EXCEPTIONS


# =============================================================================
# Transient exception classification
# =============================================================================


def test_transient_includes_rate_limit() -> None:
    """429 (rate limit) retry edilmeli."""
    assert VLMRateLimitError in _TRANSIENT_EXCEPTIONS


def test_transient_includes_vlm_timeout() -> None:
    """NIM timeout retry edilmeli."""
    assert VLMTimeoutError in _TRANSIENT_EXCEPTIONS


def test_transient_includes_image_download_error() -> None:
    """4xx/5xx network hataları retry edilmeli."""
    assert ImageDownloadError in _TRANSIENT_EXCEPTIONS


def test_transient_includes_httpx_timeout() -> None:
    """connect/read timeout retry edilmeli."""
    assert httpx.TimeoutException in _TRANSIENT_EXCEPTIONS


def test_transient_includes_httpx_request_error() -> None:
    """DNS, connection reset retry edilmeli."""
    assert httpx.RequestError in _TRANSIENT_EXCEPTIONS


def test_permanent_excluded_image_rejected() -> None:
    """Mime/size validation fail PERMANENT — retry edilmemeli."""
    assert ImageRejected not in _TRANSIENT_EXCEPTIONS


def test_permanent_excluded_vlm_error() -> None:
    """Parse fail / model error PERMANENT — retry edilmemeli."""
    assert VLMError not in _TRANSIENT_EXCEPTIONS


# =============================================================================
# Task signature verification
# =============================================================================


def test_process_task_has_autoretry() -> None:
    """process_article_image_vlm task'ında autoretry_for tanımlı olmalı."""
    from app.workers.tasks.image_vlm import process_article_image_vlm

    options = process_article_image_vlm.__wrapped__.__doc__ or ""
    # Task instance'ında autoretry config var mı
    task_obj = process_article_image_vlm
    # Celery autoretry_for task class attribute olarak set ediliyor
    assert hasattr(task_obj, "autoretry_for")
    autoretry = task_obj.autoretry_for
    assert VLMRateLimitError in autoretry
    assert VLMTimeoutError in autoretry
    assert ImageDownloadError in autoretry


def test_process_task_max_retries_3() -> None:
    """3 retry limiti."""
    from app.workers.tasks.image_vlm import process_article_image_vlm

    assert process_article_image_vlm.max_retries == 3


def test_process_task_uses_image_vlm_queue() -> None:
    """Task image_vlm_queue'ya routelanmalı."""
    from app.workers.tasks.image_vlm import process_article_image_vlm

    # Queue, decorator argümanı veya default routing'den geliyor
    queue = getattr(process_article_image_vlm, "queue", None)
    assert queue == "image_vlm_queue"


# =============================================================================
# Retry failed task signature
# =============================================================================


def test_retry_failed_task_exists() -> None:
    """tasks.image_vlm.retry_failed task export edilmiş olmalı."""
    from app.workers.tasks.image_vlm import retry_failed_images

    assert retry_failed_images.name == "tasks.image_vlm.retry_failed"


def test_backfill_task_exists() -> None:
    """tasks.image_vlm.backfill_pending task export edilmiş olmalı."""
    from app.workers.tasks.image_vlm import backfill_pending_images

    assert backfill_pending_images.name == "tasks.image_vlm.backfill_pending"


# =============================================================================
# Tracker.record kwargs regression (#424)
# =============================================================================


def test_tracker_record_accepts_image_vlm_kwargs() -> None:
    """`_process_image_async` `tracker.record(model=, cost_usd=)` çağırır.

    Regression #424: fd92475'te yanlışlıkla `cost_per_1m_input/_output` kwargs
    geçirilmiş (estimate_cost_usd helper'ına ait). TypeError her image
    işlemde patladı, 320+ pending stuck kaldı. Bu test signature mismatch'i
    deploy öncesi yakalar.
    """
    import inspect

    from app.core.cost_tracker import CallTracker

    sig = inspect.signature(CallTracker.record)
    params = sig.parameters

    # image_vlm.py'nin geçirdiği kwargs'lar accept ediliyor olmalı
    assert "model" in params, "tracker.record(model=) image_vlm.py'de kullanılıyor"
    assert "cost_usd" in params, "tracker.record(cost_usd=) image_vlm.py'de kullanılıyor"

    # Regression sentinel: bu kwargs'lar record()'a değil estimate_cost_usd'ye ait
    assert "cost_per_1m_input" not in params
    assert "cost_per_1m_output" not in params


def test_image_vlm_imports_decimal() -> None:
    """tracker.record(cost_usd=Decimal('0.0')) için Decimal import'u şart."""
    from app.workers.tasks import image_vlm

    assert hasattr(image_vlm, "Decimal"), (
        "image_vlm.py Decimal import etmiyor — tracker.record(cost_usd=Decimal(...)) "
        "NameError verir."
    )


# =============================================================================
# Beat schedule sanity
# =============================================================================


def test_beat_has_retry_failed_schedule() -> None:
    """Saatte bir retry_failed beat task'ı tanımlı."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "retry-failed-images" in schedule
    entry = schedule["retry-failed-images"]
    assert entry["task"] == "tasks.image_vlm.retry_failed"
    assert entry["kwargs"]["max_age_hours"] == 72


def test_beat_has_backfill_pending_schedule() -> None:
    """5 dk'da bir backfill beat task'ı tanımlı."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "backfill-pending-images" in schedule
