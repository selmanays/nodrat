"""Celery broker introspection — gerçek queue depth + active task sayımı.

#444 (Epic #443) — admin queue overview eskiden `crawler_jobs` tablosundan sayım
yapıyordu, ama bu tabloya hiçbir worker yazmadığı için 16 hücrenin 12'si yapısal
olarak yanlıştı. Bu modül Redis broker'a (LLEN) ve Celery `control.inspect()`
API'sine gidip canlı veri çeker.

Performance (#475):
  - inspect timeout 2.0s → 0.5s (worker'lar localhost broker üzerinde 50-150ms
    cevap verir, 2sn fazla güvenli marj)
  - Tek inspect call ile worker_count + active_counts birlikte alınır
    (eskiden ayrı `inspect.active()` + `inspect.ping()` 2 çağrı = 4 saniye)
  - Snapshot 5s Redis cache (nodrat:broker:overview) — auto-refresh 10s ile
    her 2 yenilemenin 1'i cache hit
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


# #475 — inspect timeout: localhost broker'da worker'lar hızlı cevap verir
_INSPECT_TIMEOUT_S = 0.5

# #475 — broker snapshot cache TTL (queue depths + active counts + worker count)
_SNAPSHOT_CACHE_KEY = "nodrat:broker:overview"
_SNAPSHOT_CACHE_TTL_S = 5

# #1621 — Celery/kombu Redis priority kör noktası. priority>0 ile gönderilen
# task'lar base key'de DEĞİL `<queue>\x06\x16<step>` alt-key'lerinde tutulur
# (kombu default priority_steps 0/3/6/9; 0=base, 3/6/9=alt-key). Örn.
# chunk_article `priority=9` → `embedding_fast_queue\x06\x169`. Salt base-key
# LLEN bu backlog'u GÖRMEZ (564 bekleyen task base'de 0 görünür → admin UI
# yanıltıcı "boş"). Gerçek derinlik = base + tüm priority alt-key'leri toplamı.
_KOMBU_PRIORITY_SEP = "\x06\x16"
_KOMBU_PRIORITY_STEPS = (3, 6, 9)


def _queue_keys(queue: str) -> list[str]:
    """Bir kuyruğun tüm Redis liste-key'leri: base + priority alt-key'leri."""
    return [queue, *(f"{queue}{_KOMBU_PRIORITY_SEP}{p}" for p in _KOMBU_PRIORITY_STEPS)]


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
            # #1621 — base + priority alt-key'leri topla (priority backlog dahil)
            out[q] = sum(int(await r.llen(key)) for key in _queue_keys(q))
        except Exception as exc:
            logger.warning("queue_depth_failed queue=%s err=%s", q, exc)
            out[q] = 0
    return out


def _inspect_blocking(method: str) -> dict[str, list[dict]] | None:
    """Celery control.inspect blocking çağrı — async wrapper'dan çağrılır.

    `inspect()` worker bazlı dict döner: {worker_name: [task_dict, ...]}.
    Worker yoksa None — broker'a bağlanamadı veya hiçbir worker subscribe değil.
    """
    inspector = celery_app.control.inspect(timeout=_INSPECT_TIMEOUT_S)
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
    counts: dict[str, int] = dict.fromkeys(qnames, 0)

    active = await asyncio.to_thread(_inspect_blocking, "active")
    if not active:
        return counts

    for worker_tasks in active.values():
        for task in worker_tasks or []:
            queue = (task.get("delivery_info") or {}).get("routing_key") or _queue_from_task_name(
                task.get("name", "")
            )
            if queue in counts:
                counts[queue] += 1
    return counts


async def get_broker_snapshot(
    queue_names: Iterable[str],
) -> dict[str, Any]:
    """Tek seferde queue depths + active counts + worker count + cache (#475).

    Eski API: `get_queue_depths` + `get_active_counts_by_queue` + `get_worker_count`
    = 3 ayrı round-trip, 2 ayrı inspect call (~4 saniye).
    Yeni: tek inspect.active() çağrısı (worker_name keys = worker_count + tasks
    listesi = active_counts) + paralel Redis LLEN + 5s snapshot cache.

    Cache hit: ~5ms (Redis GET).
    Cache miss: ~500ms (inspect timeout + LLEN'ler paralel).
    """
    qnames = list(queue_names)

    # 1) Cache check
    r = _get_redis()
    try:
        cached = await r.get(_SNAPSHOT_CACHE_KEY)
    except Exception as exc:
        logger.warning("broker_snapshot_cache_get_failed err=%s", exc)
        cached = None
    if cached:
        try:
            payload = json.loads(cached)
            # Cache içeriği queue listesi ile uyuyor mu? (yeni queue eklenmiş olabilir)
            if set(payload.get("queue_depths", {}).keys()) == set(qnames):
                return payload
        except (ValueError, TypeError):
            pass  # corrupt cache → invalidate

    # 2) Cache miss — broker'a paralel sorgu
    depths_task = asyncio.create_task(_fetch_depths(qnames))
    inspect_task = asyncio.create_task(asyncio.to_thread(_inspect_blocking, "active"))
    depths, active = await asyncio.gather(depths_task, inspect_task)

    counts: dict[str, int] = dict.fromkeys(qnames, 0)
    worker_count = 0
    if active:
        worker_count = len(active)
        for worker_tasks in active.values():
            for task in worker_tasks or []:
                queue = (task.get("delivery_info") or {}).get(
                    "routing_key"
                ) or _queue_from_task_name(task.get("name", ""))
                if queue in counts:
                    counts[queue] += 1

    payload = {
        "queue_depths": depths,
        "active_counts": counts,
        "worker_count": worker_count,
    }

    # 3) Cache write (best effort)
    try:
        await r.set(
            _SNAPSHOT_CACHE_KEY,
            json.dumps(payload),
            ex=_SNAPSHOT_CACHE_TTL_S,
        )
    except Exception as exc:
        logger.warning("broker_snapshot_cache_set_failed err=%s", exc)

    return payload


async def _fetch_depths(queue_names: list[str]) -> dict[str, int]:
    """Redis LLEN paralel — pipeline'le tek round-trip."""
    r = _get_redis()
    out: dict[str, int] = {}
    try:
        # #1621 — her kuyruk için base + priority alt-key'leri pipeline'la çek,
        # kuyruk başına topla (priority backlog görünür olsun).
        pipe = r.pipeline()
        key_spans: list[tuple[str, int]] = []
        for q in queue_names:
            keys = _queue_keys(q)
            key_spans.append((q, len(keys)))
            for key in keys:
                pipe.llen(key)
        results = await pipe.execute()
        idx = 0
        for q, span in key_spans:
            out[q] = sum(int(results[idx + j] or 0) for j in range(span))
            idx += span
    except Exception as exc:
        logger.warning("broker_snapshot_depths_failed err=%s", exc)
        for q in queue_names:
            out[q] = 0
    return out


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
    # #904 — generic cascade / gate-as-router job_type'ları (manuel DLQ-retry).
    "article.thin_content": "tasks.articles.fetch_detail",
    "article.soft_404": "tasks.articles.fetch_detail",
    "article.invalid_url": "tasks.articles.fetch_detail",
    "source.extract_health": "tasks.sources.recompute_extract_health",
    "image.download": "tasks.image_vlm.process_article_image_vlm",
    "image_vlm.process": "tasks.image_vlm.process_article_image_vlm",
    "media.download": "tasks.media.download_article_image",
}


def task_for_job_type(job_type: str) -> str | None:
    """FailedJob.job_type'tan Celery task name'i çöz. None → bilinmeyen tip."""
    return JOB_TYPE_TO_TASK.get(job_type)
