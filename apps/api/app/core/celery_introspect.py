"""Celery broker introspection — gerçek queue depth + active task sayımı.

#444 (Epic #443) — admin queue overview eskiden `crawler_jobs` tablosundan sayım
yapıyordu, ama bu tabloya hiçbir worker yazmadığı için 16 hücrenin 12'si yapısal
olarak yanlıştı. Bu modül Redis broker'a (LLEN) ve Celery `control.inspect()`
API'sine gidip canlı veri çeker.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import redis.asyncio as aioredis

from app.config import get_settings
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def get_queue_depths(queue_names: Iterable[str]) -> dict[str, int]:
    """Redis broker'dan kuyruk başına bekleyen task sayımı.

    Celery default kuyruk Redis'te liste olarak tutulur; key adı queue adının
    aynısıdır (`crawl_queue`, `embedding_queue`, vb.). LLEN O(1).

    Hata durumunda queue depth 0 döner — admin sayfası çökmesin.
    """
    r = _get_redis()
    out: dict[str, int] = {}
    for q in queue_names:
        try:
            out[q] = int(await r.llen(q))
        except Exception as exc:
            logger.warning("queue_depth_failed queue=%s err=%s", q, exc)
            out[q] = 0
    return out


def _inspect_blocking(method: str) -> dict[str, list[dict]] | None:
    """Celery control.inspect blocking çağrı — async wrapper'dan çağrılır.

    `inspect()` worker bazlı dict döner: {worker_name: [task_dict, ...]}.
    Worker yoksa None — broker'a bağlanamadı veya hiçbir worker subscribe değil.
    """
    inspector = celery_app.control.inspect(timeout=2.0)
    fn = getattr(inspector, method, None)
    if fn is None:
        return None
    try:
        return fn()
    except Exception as exc:
        logger.warning("celery_inspect_%s_failed err=%s", method, exc)
        return None


async def get_active_counts_by_queue(queue_names: Iterable[str]) -> dict[str, int]:
    """Aktif (worker'da çalışan) task sayımı — kuyruk bazlı.

    `inspect().active()` blocking — `asyncio.to_thread` ile sarılır.
    Task dict'inde `delivery_info.routing_key` queue adıdır (Celery routing
    convention). routing_key uyumluluk için fallback olarak task `name`
    prefix'i ile de eşleştirilir (task_routes config ile birebir).
    """
    qnames = set(queue_names)
    counts: dict[str, int] = {q: 0 for q in qnames}

    active = await asyncio.to_thread(_inspect_blocking, "active")
    if not active:
        return counts

    for worker_tasks in active.values():
        for task in worker_tasks or []:
            queue = (
                (task.get("delivery_info") or {}).get("routing_key")
                or _queue_from_task_name(task.get("name", ""))
            )
            if queue in counts:
                counts[queue] += 1
    return counts


def _queue_from_task_name(name: str) -> str | None:
    """task_routes ile birebir — fallback eşleme.

    `tasks.sources.X` veya `tasks.articles.X` → `crawl_queue` vb.
    """
    if name.startswith(("tasks.sources.", "tasks.articles.")):
        return "crawl_queue"
    if name.startswith("tasks.image_vlm."):
        return "image_vlm_queue"
    if name.startswith("tasks.embedding.") or name.startswith("tasks.maintenance."):
        return "embedding_queue"
    if name.startswith(("tasks.clustering.", "tasks.agenda.", "tasks.raptor.")):
        return "event_queue"
    if name.startswith("tasks.media."):
        return "media_queue"
    return None


async def get_worker_count() -> int:
    """Aktif worker sayısı — `inspect().ping()` worker isimleri döner."""
    pong = await asyncio.to_thread(_inspect_blocking, "ping")
    return len(pong) if pong else 0


# Task name registry — admin retry endpoint'i FailedJob.job_type'tan
# Celery task adına geçiş yapar. articles.py içinde `_record_failure`
# kullanılan tüm job_type'lar burada eşlemiş olmalı.
JOB_TYPE_TO_TASK: dict[str, str] = {
    "article.fetch_detail": "tasks.articles.fetch_detail",
    "article.extract": "tasks.articles.fetch_detail",  # extract fail → tüm fetch_detail tekrar
    "article.clean": "tasks.articles.fetch_detail",  # clean fail → tüm fetch_detail tekrar
    "article.duplicate_content": "tasks.articles.fetch_detail",  # info-level, retry mantıklı değil ama dispatcher kabul eder
    "article.discovered_timeout": "tasks.articles.fetch_detail",
    "image.download": "tasks.image_vlm.process_article_image_vlm",
    "image_vlm.process": "tasks.image_vlm.process_article_image_vlm",
    "media.download": "tasks.media.download_article_image",
}


def task_for_job_type(job_type: str) -> str | None:
    """FailedJob.job_type'tan Celery task name'i çöz. None → bilinmeyen tip."""
    return JOB_TYPE_TO_TASK.get(job_type)
