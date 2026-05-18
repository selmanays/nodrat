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
    from app.workers.tasks.articles import _TRANSIENT_EXCEPTIONS
    from sqlalchemy.exc import OperationalError

    assert OperationalError in _TRANSIENT_EXCEPTIONS


def test_transient_excludes_integrity_error():
    """IntegrityError explicit handler ile yakalanır; autoretry yapılmamalı.

    Regression: eski autoretry_for=Exception IntegrityError'ı 2x retry'a
    sokuyordu, her seferinde aynı hata, sonunda article 'discovered' stuck
    kalıyordu (#433).
    """
    from app.workers.tasks.articles import _TRANSIENT_EXCEPTIONS
    from sqlalchemy.exc import IntegrityError

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
    from app.workers.tasks.articles import _is_duplicate_content_hash_error
    from sqlalchemy.exc import IntegrityError

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
    from app.workers.tasks.articles import _is_duplicate_content_hash_error
    from sqlalchemy.exc import IntegrityError

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
    from app.workers.tasks.articles import _is_duplicate_content_hash_error
    from sqlalchemy.exc import IntegrityError

    fake = IntegrityError(
        statement=None,
        params=None,
        orig=Exception('UQ_ARTICLES_SOURCE_CONTENT_HASH violation'),
    )
    assert _is_duplicate_content_hash_error(fake) is True


# =============================================================================
# Backfill discovered + Retry failed (#436 — Faz C)
# =============================================================================


# #488 — _record_failure article_status_override testleri


def test_record_failure_signature_has_override():
    """_record_failure article_status_override parametresi kabul etmeli."""
    import inspect as _inspect

    from app.workers.tasks import articles

    sig = _inspect.signature(articles._record_failure)
    assert "article_status_override" in sig.parameters
    assert sig.parameters["article_status_override"].default is None


def test_record_failure_default_error_sets_failed():
    """Severity error/warning + override yok → article.status = failed (eski davranış)."""
    import asyncio
    import types

    from app.core.cleaning import STATUS_DISCOVERED, STATUS_FAILED
    from app.workers.tasks import articles as articles_module

    article = types.SimpleNamespace(
        source_id=None,
        source_url="http://example.com/x",
        status=STATUS_DISCOVERED,
    )
    db = types.SimpleNamespace(add=lambda _: None)

    asyncio.run(
        articles_module._record_failure(
            db=db,  # type: ignore[arg-type]
            article=article,  # type: ignore[arg-type]
            job_type="article.fetch_detail",
            error="HTTP 500",
            payload={},
        )
    )
    assert article.status == STATUS_FAILED


def test_record_failure_permanent_info_no_override_keeps_status():
    """Severity permanent_info + override yok → article.status değişmez (legacy semantik).

    NOT (#488): bu davranış sonsuz loop'a sebep olabilir; caller her zaman
    article_status_override geçmelidir. Test sadece backward compat'ı doğrular.
    """
    import asyncio
    import types

    from app.core.cleaning import STATUS_DISCOVERED
    from app.workers.tasks import articles as articles_module

    article = types.SimpleNamespace(
        source_id=None,
        source_url="http://example.com/x",
        status=STATUS_DISCOVERED,
    )
    db = types.SimpleNamespace(add=lambda _: None)

    asyncio.run(
        articles_module._record_failure(
            db=db,  # type: ignore[arg-type]
            article=article,  # type: ignore[arg-type]
            job_type="article.duplicate_content",
            error="dup",
            payload={},
            severity="permanent_info",
        )
    )
    assert article.status == STATUS_DISCOVERED  # değişmedi


def test_record_failure_override_archives_discovered():
    """#488 — override=ARCHIVED + severity=permanent_info → article.status = archived
    (terminal, sonsuz loop kırıldı)."""
    import asyncio
    import types

    from app.core.cleaning import STATUS_ARCHIVED, STATUS_DISCOVERED
    from app.workers.tasks import articles as articles_module

    article = types.SimpleNamespace(
        source_id=None,
        source_url="http://example.com/x",
        status=STATUS_DISCOVERED,
    )
    # #488 — terminal status geçişinde _record_failure kardeş FailedJob
    # row'larını `await db.execute(update(FailedJob)...)` ile auto-resolve
    # eder (sonsuz loop kırıldı, articles.py:288). Mock'a async execute
    # stub'ı şart; eski mock yalnız `add` taşıyordu (test bu davranıştan
    # önce yazılmış — stale).
    async def _noop_execute(*_a, **_kw):
        return None

    db = types.SimpleNamespace(add=lambda _: None, execute=_noop_execute)

    asyncio.run(
        articles_module._record_failure(
            db=db,  # type: ignore[arg-type]
            article=article,  # type: ignore[arg-type]
            job_type="article.duplicate_content",
            error="dup",
            payload={},
            severity="permanent_info",
            article_status_override=STATUS_ARCHIVED,
        )
    )
    assert article.status == STATUS_ARCHIVED


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
    """#917 — backfill-discovered DENEME-tabanlı (5 dk, batch=100,
    max_attempts=5; yaş-tabanlı max_age_hours KALDIRILDI — #904 ile tutarlı)."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "backfill-discovered-articles" in schedule
    entry = schedule["backfill-discovered-articles"]
    assert entry["task"] == "tasks.articles.backfill_discovered"
    assert entry["kwargs"]["batch"] == 100
    assert entry["kwargs"]["max_attempts"] == 5
    assert "max_age_hours" not in entry["kwargs"]
    assert entry["options"]["queue"] == "crawl_queue"


def test_beat_has_retry_failed_articles():
    """#904 — retry-failed-articles deneme-tabanlı (saatlik :25, batch=50,
    max_attempts=5; yaş-tabanlı max_age_hours KALDIRILDI)."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "retry-failed-articles" in schedule
    entry = schedule["retry-failed-articles"]
    assert entry["task"] == "tasks.articles.retry_failed"
    assert entry["kwargs"]["batch"] == 50
    assert entry["kwargs"]["max_attempts"] == 5
    assert "max_age_hours" not in entry["kwargs"]
    assert entry["options"]["queue"] == "crawl_queue"


def test_beat_has_recompute_extract_health():
    """#904 — per-domain extract-confidence telemetri beat (6 saatte bir)."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "recompute-extract-health" in schedule
    entry = schedule["recompute-extract-health"]
    assert entry["task"] == "tasks.sources.recompute_extract_health"
    assert entry["options"]["queue"] == "crawl_queue"


def test_is_low_volume_gate():
    """Teslimat 1 — düşük-hacim gate'i: küçük örneklem VEYA frekans sinyali
    (cold/hibernate) → True (red/alarm bastırılır); aktif/yoğun → False."""
    from app.workers.tasks.sources import _is_low_volume

    # Küçük örneklem → güvenilmez (Arkitera tipi: denom 1)
    assert _is_low_volume(1, 8, "normal") is True
    assert _is_low_volume(7, 8, None) is True
    # Frekans sinyali sessiz işaretliyor → düşük-hacim (tier önceliği)
    assert _is_low_volume(50, 8, "cold") is True
    assert _is_low_volume(50, 8, "hibernate") is True
    # Aktif/yoğun + yeterli örneklem → gate KAPALI (red davranışı korunur)
    assert _is_low_volume(20, 8, "normal") is False
    assert _is_low_volume(20, 8, "hot") is False
    # would_be_tier NULL + yeterli örneklem → yalnız örneklem karar verir
    assert _is_low_volume(8, 8, None) is False
    assert _is_low_volume(8, 8, "normal") is False
    # NOT: scraping.extract_health_min_sample setting kaydı admin import
    # zinciri (pyotp) lokal venv'de yok → live VPS'te doğrulanır (#911 gibi).


def test_backfill_discovered_default_kwargs():
    """#917 — deneme-tabanlı default kwargs: batch=100, max_attempts=5
    (yaş-tabanlı max_age_hours KALDIRILDI; #904 retry_failed ile tutarlı)."""
    import inspect

    from app.workers.tasks.articles import backfill_discovered_articles

    # Celery task __wrapped__'dan signature alınır
    sig = inspect.signature(backfill_discovered_articles.__wrapped__)
    params = sig.parameters
    assert params["batch"].default == 100
    assert params["max_attempts"].default == 5
    assert "max_age_hours" not in params


def test_retry_failed_articles_default_kwargs():
    """#904 — deneme-tabanlı default kwargs: batch=50, max_attempts=5
    (max_age_hours KALDIRILDI)."""
    import inspect

    from app.workers.tasks.articles import retry_failed_articles

    sig = inspect.signature(retry_failed_articles.__wrapped__)
    params = sig.parameters
    assert params["batch"].default == 50
    assert params["max_attempts"].default == 5
    assert "max_age_hours" not in params


def test_recover_quarantined_registered():
    """#904 — recover_quarantined task + crawl_queue + default batch."""
    import inspect

    from app.workers.tasks.articles import recover_quarantined

    assert recover_quarantined.name == "tasks.articles.recover_quarantined"
    assert getattr(recover_quarantined, "queue", None) == "crawl_queue"
    params = inspect.signature(recover_quarantined.__wrapped__).parameters
    assert params["batch"].default == 200


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
