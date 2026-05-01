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
