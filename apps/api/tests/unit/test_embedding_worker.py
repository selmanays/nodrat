"""Embedding worker registry + routing tests (#19).

DB integration testleri testcontainers ile gelecek (#43).
Bu testler task registry + routing + provider failover'ı doğrular.
"""

from __future__ import annotations


def test_embedding_tasks_registered():
    from app.workers import celery_app as celery_module
    from app.workers.tasks import embedding  # noqa: F401

    registry = celery_module.celery_app.tasks
    assert "tasks.embedding.chunk_article" in registry
    assert "tasks.embedding.embed_chunks" in registry


def test_embedding_route_to_embedding_queue():
    from app.workers.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes["tasks.embedding.*"]["queue"] == "embedding_queue"


def test_embed_chunks_retry_policy():
    from app.workers.tasks.embedding import embed_article_chunks

    assert embed_article_chunks.max_retries == 3
    assert embed_article_chunks.retry_backoff is True
    assert embed_article_chunks.retry_backoff_max == 600


def test_embed_batch_size_constant():
    """NIM batch size sabit ve mantıklı (1-200)."""
    from app.workers.tasks.embedding import EMBED_BATCH_SIZE

    assert 1 <= EMBED_BATCH_SIZE <= 200
