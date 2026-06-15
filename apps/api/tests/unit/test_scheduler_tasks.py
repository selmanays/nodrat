"""Beat schedule + Celery task integration smoke tests.

DB integration testleri Faz 1 testcontainers setup ile gelecek (#43).
Burada sadece Celery config + task registry + Beat schedule mantığı test edilir.
"""

from __future__ import annotations


def test_celery_app_includes_source_tasks():
    from app.workers.celery_app import celery_app

    # Celery config 'include' ile source modülünü registerlamış mı?
    assert "app.modules.sources.tasks.sources" in celery_app.conf.include


def test_beat_schedule_has_crawl_and_healthcheck():
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "crawl-active-sources" in schedule
    assert "source-healthcheck-all" in schedule

    crawl = schedule["crawl-active-sources"]
    assert crawl["task"] == "tasks.sources.crawl_active_sources"
    assert crawl["options"]["queue"] == "crawl_queue"

    health = schedule["source-healthcheck-all"]
    assert health["task"] == "tasks.sources.healthcheck_all"


def test_task_routes_for_sources():
    from app.workers.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert "tasks.sources.*" in routes
    assert routes["tasks.sources.*"]["queue"] == "crawl_queue"


def test_source_tasks_registered():
    """Task'lar Celery registry'de görünmeli (autodiscover)."""
    from app.modules.sources.tasks import sources  # noqa: F401 (import side-effect)
    from app.workers import celery_app as celery_module

    registry = celery_module.celery_app.tasks
    assert "tasks.sources.crawl_active_sources" in registry
    assert "tasks.sources.healthcheck_all" in registry
    assert "tasks.sources.fetch_source_rss" in registry
    assert "tasks.sources.healthcheck_source" in registry


def test_fetch_source_rss_has_retry_policy():
    """Network task'ları retry'lı olmalı."""
    from app.modules.sources.tasks.sources import fetch_source_rss

    # Celery shared decorator config'i
    assert fetch_source_rss.max_retries == 3
    assert fetch_source_rss.retry_backoff is True
    assert fetch_source_rss.retry_backoff_max == 300


# ---------------------------------------------------------------------------
# #1531 — NER'i embedding'den ayır: adanmış ner_queue + worker + backfill beat
# ---------------------------------------------------------------------------


def test_entities_routed_to_dedicated_ner_queue():
    """tasks.entities.* artık ADANMIŞ ner_queue'ya yönlenir (event_queue değil)."""
    from app.workers.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes["tasks.entities.*"]["queue"] == "ner_queue"


def test_backfill_entities_beat_registered():
    """NER güvenlik-ağı beat'i: cleaned-ama-entity'siz article'ları yakalar."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "backfill-entities" in schedule
    entry = schedule["backfill-entities"]
    assert entry["task"] == "tasks.entities.backfill"
    assert entry["options"]["queue"] == "ner_queue"


def test_entity_tasks_registered():
    """NER task'ları registry'de (autodiscover) — dispatch hedefleri."""
    from app.modules.entities.tasks import entities  # noqa: F401 (import side-effect)
    from app.workers.celery_app import celery_app

    registry = celery_app.tasks
    assert "tasks.entities.extract_article_entities" in registry
    assert "tasks.entities.backfill" in registry
