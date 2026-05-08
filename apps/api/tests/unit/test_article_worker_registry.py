"""Article worker pipeline registry smoke tests (#94).

DB integration testleri testcontainers ile gelecek (#43 ✓ + bu task'ın
gerçek senaryoları); burada Celery task registry + routing doğrulanır.
"""

from __future__ import annotations


def test_article_tasks_registered():
    from app.workers import celery_app as celery_module
    from app.workers.tasks import articles  # noqa: F401

    registry = celery_module.celery_app.tasks
    assert "tasks.articles.discover" in registry
    assert "tasks.articles.fetch_detail" in registry


def test_article_routes_to_crawl_queue():
    from app.workers.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes["tasks.articles.*"]["queue"] == "crawl_queue"


def test_article_fetch_detail_retry_policy():
    from app.workers.tasks.articles import article_fetch_detail

    assert article_fetch_detail.max_retries == 2
    assert article_fetch_detail.retry_backoff is True


def test_article_discover_idempotent_signature():
    """Discover task signature: source_id + item_data dict."""
    from app.workers.tasks.articles import article_discover

    # Celery task'ları .name attr'ı ile registered olmalı
    assert article_discover.name == "tasks.articles.discover"


# =============================================================================
# Transient/permanent exception classification (#433 — Faz B)
# =============================================================================


def test_transient_includes_httpx_timeout():
    """fetch_text içinde sarmalanmamış httpx hataları autoretry edilebilmeli."""
    import httpx

    from app.workers.tasks.articles import _TRANSIENT_EXCEPTIONS

    assert httpx.TimeoutException in _TRANSIENT_EXCEPTIONS
    assert httpx.RequestError in _TRANSIENT_EXCEPTIONS


def test_transient_includes_db_operational_error():
    """DB connection lost / pool timeout → autoretry işe yarayabilir."""
    from sqlalchemy.exc import OperationalError

    from app.workers.tasks.articles import _TRANSIENT_EXCEPTIONS

    assert OperationalError in _TRANSIENT_EXCEPTIONS


def test_transient_excludes_integrity_error():
    """IntegrityError explicit handler ile yakalanır; autoretry yapılmamalı.

    Regression: eski autoretry_for=Exception IntegrityError'ı 2x retry'a
    sokuyordu, her seferinde aynı hata, sonunda article 'discovered' stuck
    kalıyordu (#433).
    """
    from sqlalchemy.exc import IntegrityError

    from app.workers.tasks.articles import _TRANSIENT_EXCEPTIONS

    assert IntegrityError not in _TRANSIENT_EXCEPTIONS


def test_transient_excludes_value_error():
    """Programming bug (ValueError, KeyError) autoretry yapmasın — hızlı yüzeye."""
    from app.workers.tasks.articles import _TRANSIENT_EXCEPTIONS

    assert ValueError not in _TRANSIENT_EXCEPTIONS
    assert KeyError not in _TRANSIENT_EXCEPTIONS


def test_fetch_detail_autoretry_uses_transient_only():
    """article_fetch_detail Celery task autoretry_for sadece transient list."""
    from app.workers.tasks.articles import _TRANSIENT_EXCEPTIONS, article_fetch_detail

    assert article_fetch_detail.autoretry_for == _TRANSIENT_EXCEPTIONS
    # Eski yanlış davranış kontrolü
    assert article_fetch_detail.autoretry_for != (Exception,)


# =============================================================================
# IntegrityError duplicate content_hash detection (#433)
# =============================================================================


def test_is_duplicate_content_hash_error_match():
    """uq_articles_source_content_hash constraint adı geçen IntegrityError true döner."""
    from sqlalchemy.exc import IntegrityError

    from app.workers.tasks.articles import _is_duplicate_content_hash_error

    # Production'dan gerçek hata mesajı pattern'i
    fake = IntegrityError(
        statement=None,
        params=None,
        orig=Exception(
            'duplicate key value violates unique constraint '
            '"uq_articles_source_content_hash"\nDETAIL: Key (source_id, content_hash)=...'
        ),
    )
    assert _is_duplicate_content_hash_error(fake) is True


def test_is_duplicate_content_hash_error_no_match():
    """Başka bir UNIQUE ihlali (örn: canonical_url) false döner."""
    from sqlalchemy.exc import IntegrityError

    from app.workers.tasks.articles import _is_duplicate_content_hash_error

    fake = IntegrityError(
        statement=None,
        params=None,
        orig=Exception(
            'duplicate key value violates unique constraint '
            '"uq_articles_canonical_url"'
        ),
    )
    assert _is_duplicate_content_hash_error(fake) is False


def test_is_duplicate_content_hash_error_case_insensitive():
    """Constraint adı match'i case-insensitive olmalı (PG bazen büyük harf döner)."""
    from sqlalchemy.exc import IntegrityError

    from app.workers.tasks.articles import _is_duplicate_content_hash_error

    fake = IntegrityError(
        statement=None,
        params=None,
        orig=Exception('UQ_ARTICLES_SOURCE_CONTENT_HASH violation'),
    )
    assert _is_duplicate_content_hash_error(fake) is True


# =============================================================================
# Backfill discovered + Retry failed (#436 — Faz C)
# =============================================================================


def test_backfill_discovered_task_registered():
    """tasks.articles.backfill_discovered registered + crawl_queue'ya routed."""
    from app.workers.tasks.articles import backfill_discovered_articles

    assert backfill_discovered_articles.name == "tasks.articles.backfill_discovered"
    assert getattr(backfill_discovered_articles, "queue", None) == "crawl_queue"


def test_retry_failed_articles_task_registered():
    """tasks.articles.retry_failed registered + crawl_queue'ya routed."""
    from app.workers.tasks.articles import retry_failed_articles

    assert retry_failed_articles.name == "tasks.articles.retry_failed"
    assert getattr(retry_failed_articles, "queue", None) == "crawl_queue"


def test_beat_has_backfill_discovered_articles():
    """Beat schedule'a backfill-discovered-articles eklendi (5 dk, batch=100, 72h)."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "backfill-discovered-articles" in schedule
    entry = schedule["backfill-discovered-articles"]
    assert entry["task"] == "tasks.articles.backfill_discovered"
    assert entry["kwargs"]["batch"] == 100
    assert entry["kwargs"]["max_age_hours"] == 72
    assert entry["options"]["queue"] == "crawl_queue"


def test_beat_has_retry_failed_articles():
    """Beat schedule'a retry-failed-articles eklendi (saatlik :25, batch=50, 72h)."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "retry-failed-articles" in schedule
    entry = schedule["retry-failed-articles"]
    assert entry["task"] == "tasks.articles.retry_failed"
    assert entry["kwargs"]["batch"] == 50
    assert entry["kwargs"]["max_age_hours"] == 72
    assert entry["options"]["queue"] == "crawl_queue"


def test_backfill_discovered_default_kwargs():
    """Manuel call için default kwargs reasonable: batch=100, max_age_hours=72."""
    import inspect

    from app.workers.tasks.articles import backfill_discovered_articles

    # Celery task __wrapped__'dan signature alınır
    sig = inspect.signature(backfill_discovered_articles.__wrapped__)
    params = sig.parameters
    assert params["batch"].default == 100
    assert params["max_age_hours"].default == 72


def test_retry_failed_articles_default_kwargs():
    """Manuel call için default kwargs: batch=50, max_age_hours=72."""
    import inspect

    from app.workers.tasks.articles import retry_failed_articles

    sig = inspect.signature(retry_failed_articles.__wrapped__)
    params = sig.parameters
    assert params["batch"].default == 50
    assert params["max_age_hours"].default == 72


def test_article_beat_schedules_dont_clash_with_image():
    """Article retry-failed (:25) image retry-failed (:20)'den farklı dakika.

    Hourly çakışma worker'ı boğmamalı. Article + image aynı saat
    içinde farklı dakikalarda fire etmeli.
    """
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    art_minute = schedule["retry-failed-articles"]["schedule"].minute
    img_minute = schedule["retry-failed-images"]["schedule"].minute
    assert art_minute != img_minute, (
        f"Article retry ({art_minute}) and image retry ({img_minute}) çakışıyor; "
        "her iki saatlik task aynı anda fire ederse worker yükü pikleşir."
    )
