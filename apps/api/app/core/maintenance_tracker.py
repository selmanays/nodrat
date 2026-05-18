"""Maintenance task last-run tracking — Redis backed.

#468 (Epic #443 follow-up) — admin queue sayfasındaki "Bakım görevleri"
kartının veri kaynağı. Beat schedule'da çalışan ve manuel tetiklenebilen 5
backfill/retry task'ı için son çalışma zamanı + sonuç özeti tutulur.

Mimari:
  - Celery task_prerun signal: started_at memory store
  - Celery task_postrun signal: started + retval birlikte Redis'e yazılır
  - Endpoint /admin/queue/maintenance: Redis'ten okur

Anahtar: nodrat:maintenance:last:{task_name}
TTL: 24h (eski sonuçlar otomatik düşer; UI "—" gösterir)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import redis as sync_redis
import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)


# Görünür hale getirilen task'lar — beat schedule'da tanımlı + admin
# manuel tetikleyebilir. Yeni task ekleyince buraya ekle.
TRACKED_TASKS: tuple[str, ...] = (
    "tasks.articles.backfill_discovered",
    "tasks.articles.retry_failed",
    "tasks.image_vlm.backfill_pending",
    "tasks.image_vlm.retry_failed",
    "tasks.articles.backfill_missing_chunks",
    # #904 — quarantine toplu kurtarma (operatör) + per-domain telemetri.
    "tasks.articles.recover_quarantined",
    "tasks.sources.recompute_extract_health",
)

_KEY_PREFIX = "nodrat:maintenance:last:"
_TTL_SECONDS = 86400


def _key(task_name: str) -> str:
    return f"{_KEY_PREFIX}{task_name}"


# Sync client — Celery signal handler içinde kullanılır
_sync_client: sync_redis.Redis | None = None


def _client_sync() -> sync_redis.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = sync_redis.Redis.from_url(
            get_settings().redis_url, decode_responses=True
        )
    return _sync_client


# Async client — FastAPI endpoint içinde kullanılır
_async_client: aioredis.Redis | None = None


def _client_async() -> aioredis.Redis:
    global _async_client
    if _async_client is None:
        _async_client = aioredis.from_url(
            get_settings().redis_url, decode_responses=True
        )
    return _async_client


def is_tracked(task_name: str) -> bool:
    return task_name in TRACKED_TASKS


def record_run_sync(
    task_name: str,
    *,
    summary: Any,
    started_at: datetime,
    status: str = "succeeded",
    triggered_by: str = "beat",
    error: str | None = None,
) -> None:
    """Celery signal handler tarafından çağrılır — son çalışma sonucunu yazar.

    summary genelde dict döner ama None veya başka tip olabilir; sadece dict
    JSON-serialize edilir, diğerleri repr'ı saklanır.
    """
    if not is_tracked(task_name):
        return
    try:
        normalized_summary: Any
        if isinstance(summary, dict):
            normalized_summary = summary
        elif summary is None:
            normalized_summary = None
        else:
            normalized_summary = {"_repr": repr(summary)[:500]}

        payload = {
            "task_name": task_name,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "duration_seconds": (
                datetime.now(UTC) - started_at
            ).total_seconds(),
            "status": status,
            "summary": normalized_summary,
            "triggered_by": triggered_by,
            "error": error,
        }
        _client_sync().set(
            _key(task_name),
            json.dumps(payload, default=str),
            ex=_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "maintenance_tracker_record_failed task=%s err=%s",
            task_name,
            exc,
        )


async def get_last_runs(
    task_names: list[str] | tuple[str, ...] = TRACKED_TASKS,
) -> dict[str, dict[str, Any] | None]:
    """Endpoint için: TRACKED_TASKS için son çalışma payload'larını çek.

    Yoksa None — task hiç çalışmamış veya TTL'den düşmüş.
    """
    keys = [_key(n) for n in task_names]
    try:
        vals = await _client_async().mget(keys)
    except Exception as exc:
        logger.warning("maintenance_tracker_mget_failed err=%s", exc)
        return dict.fromkeys(task_names)

    out: dict[str, dict[str, Any] | None] = {}
    for n, v in zip(task_names, vals, strict=False):
        if not v:
            out[n] = None
            continue
        try:
            out[n] = json.loads(v)
        except (ValueError, TypeError):
            out[n] = None
    return out


def task_human_label(task_name: str) -> str:
    """Admin UI için insancıllaştırılmış ad."""
    return {
        "tasks.articles.backfill_discovered": "Stuck haber yakalama",
        "tasks.articles.retry_failed": "Başarısız haber tekrar dene",
        "tasks.image_vlm.backfill_pending": "Bekleyen görsel VLM kuyruğa al",
        "tasks.image_vlm.retry_failed": "Başarısız görsel tekrar dene",
        "tasks.articles.backfill_missing_chunks": "Eksik chunk yakalama",
        "tasks.articles.recover_quarantined": "Karantina toplu kurtarma (#904)",
        "tasks.sources.recompute_extract_health": "Kaynak çıkarım sağlığı (#904)",
    }.get(task_name, task_name)


def task_pipeline(task_name: str) -> str:
    """Hangi pipeline'a aittir."""
    if "image_vlm" in task_name:
        return "Görsel VLM"
    if "missing_chunks" in task_name:
        return "Vektörleştirici"
    if "articles" in task_name:
        return "Kazıyıcı"
    return "—"
