"""Image VLM processing — NIM Llama 4 Maverick (#300 MVP-1.4 PR-3).

Process & discard pattern:
    1. ArticleImage row'dan original_url al
    2. HEAD check (404 → fail + skip)
    3. Geçici download (RAM, max 5 MB)
    4. NIM VLM API call (caption + OCR + depicts JSON)
    5. DB update (vlm_caption, ocr_text, depicts, processed_at, status='processed')
    6. Image bytes discard (no persistent storage)

Queue: image_vlm_queue
Concurrency: 1-2 (NIM rate limit 40 RPM, conservative)

docs/engineering/architecture.md §3.1 (image_vlm_queue)
docs/engineering/data-model.md §3.5 (article_images)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.core.media import (
    DOWNLOAD_TIMEOUT,
    ImageDownloadError,
    ImageRejected,
    download_image_url,
)
from app.core.settings_store import settings_store
from app.models.article import Article, ArticleImage
from app.providers.nim_vlm import (
    NIM_VLM_DEFAULT_MODEL,
    VLMError,
    VLMRateLimitError,
    VLMTimeoutError,
    build_nim_vlm_provider,
)
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _get_session_factory, _run_async


logger = logging.getLogger(__name__)


async def _process_image_async(article_image_id: UUID) -> dict:
    """Tek ArticleImage'ı NIM VLM ile işle — process & discard."""
    factory = _get_session_factory()
    summary: dict[str, object] = {
        "article_image_id": str(article_image_id),
        "status": "unknown",
        "error": None,
    }

    async with factory() as db:
        # Settings flag
        try:
            enabled = await settings_store.get_bool(
                db, "media.processing_enabled", False
            )
            vlm_model = await settings_store.get(
                db, "media.vlm_model", NIM_VLM_DEFAULT_MODEL
            )
            max_image_bytes = await settings_store.get_int(
                db, "media.max_image_bytes", 5 * 1024 * 1024
            )
            download_timeout = await settings_store.get_float(
                db, "media.download_timeout", 10.0
            )
        except Exception:  # pragma: no cover
            enabled = False
            vlm_model = NIM_VLM_DEFAULT_MODEL
            max_image_bytes = 5 * 1024 * 1024
            download_timeout = 10.0

        if not enabled:
            summary["status"] = "skipped"
            summary["error"] = "media.processing_enabled=false"
            return summary

        img = await db.get(ArticleImage, article_image_id)
        if img is None:
            summary["error"] = "article_image_not_found"
            return summary

        # Idempotent
        if img.status == "processed":
            summary["status"] = "already_processed"
            return summary

        # Article context (caption prompt için)
        article = await db.get(Article, img.article_id)
        article_title = article.title if article else ""

        # 1) HEAD check + geçici download
        try:
            downloaded = await download_image_url(
                img.original_url,
                timeout=download_timeout,
                max_bytes=max_image_bytes,
            )
        except ImageRejected as exc:
            img.status = "failed"
            await db.commit()
            summary["status"] = "rejected"
            summary["error"] = str(exc)
            return summary
        except ImageDownloadError as exc:
            img.status = "failed"
            await db.commit()
            summary["status"] = "failed"
            summary["error"] = f"download: {exc}"
            return summary
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            img.status = "failed"
            await db.commit()
            summary["status"] = "failed"
            summary["error"] = f"network: {exc}"
            return summary

        # 2) NIM VLM call
        provider = build_nim_vlm_provider()
        if provider is None:
            summary["status"] = "failed"
            summary["error"] = "NIM_API_KEY missing"
            return summary

        try:
            result = await provider.analyze_image(
                image_bytes=downloaded.data,
                mime_type=downloaded.mime_type,
                alt_text=img.alt_text or "",
                article_title=article_title or "",
                model=vlm_model,
            )
        except VLMRateLimitError as exc:
            # 429 — retry kuyrukta (Celery autoretry)
            logger.warning("NIM VLM rate limit img=%s", article_image_id)
            raise
        except VLMTimeoutError as exc:
            img.status = "failed"
            await db.commit()
            summary["status"] = "failed"
            summary["error"] = f"vlm timeout: {exc}"
            return summary
        except VLMError as exc:
            img.status = "failed"
            await db.commit()
            summary["status"] = "failed"
            summary["error"] = f"vlm: {exc}"
            return summary
        finally:
            # 3) Bytes discard (Python GC, ek explicit del)
            del downloaded

        # 4) DB update — VLM metadata
        img.vlm_caption = result.caption[:5000] if result.caption else None
        img.ocr_text = result.ocr_text[:10000] if result.ocr_text else None
        img.depicts = result.depicts if result.depicts else None
        img.processed_at = datetime.now(timezone.utc)
        img.status = "processed"
        await db.commit()

        summary["status"] = "processed"
        summary["caption_len"] = len(result.caption)
        summary["ocr_len"] = len(result.ocr_text)
        summary["depicts_count"] = len(result.depicts)
        summary["model"] = result.model_used
        summary["latency_ms"] = round(result.latency_ms, 1)
        return summary


@celery_app.task(
    name="tasks.image_vlm.process",
    bind=True,
    autoretry_for=(VLMRateLimitError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,  # Rate limit ile cooldown için 3 deneme
    queue="image_vlm_queue",
)
def process_article_image_vlm(self, article_image_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Article image NIM VLM ile işle (process & discard).

    Queue: image_vlm_queue (worker_image_vlm consumer)
    Retry: 3x for VLMRateLimitError (429 cooldown)
    """
    return _run_async(_process_image_async(UUID(article_image_id)))


# =============================================================================
# Backfill task — pending görselleri batch olarak queue'ya dispatch eder.
# Beat schedule (her 5 dk) + manuel admin trigger (deploy sonrası one-shot).
# =============================================================================


async def _backfill_pending_async(batch: int) -> dict:
    """DB'den batch kadar pending ArticleImage al, her biri için
    `process_article_image_vlm` task'ı dispatch et.

    Worker rate limit kendisi yönetir (autoretry + backoff). Queue size
    kontrolü gereksiz — Celery zaten dağıtık.
    """
    from sqlalchemy import select

    from app.models.article import ArticleImage

    factory = _get_session_factory()
    summary: dict[str, object] = {
        "batch_requested": batch,
        "dispatched": 0,
        "errors": 0,
    }

    async with factory() as db:
        # En eski pending'lerden başla — eşit dağılım için sıra önemli
        stmt = (
            select(ArticleImage.id)
            .where(ArticleImage.status == "pending")
            .order_by(ArticleImage.created_at.asc())
            .limit(batch)
        )
        rows = (await db.execute(stmt)).scalars().all()

    dispatched = 0
    errors = 0
    for image_id in rows:
        try:
            process_article_image_vlm.apply_async(args=[str(image_id)])
            dispatched += 1
        except Exception as exc:
            logger.warning(
                "backfill dispatch failed image_id=%s err=%s", image_id, exc
            )
            errors += 1

    summary["dispatched"] = dispatched
    summary["errors"] = errors
    logger.info(
        "image_vlm backfill: dispatched=%d errors=%d batch=%d",
        dispatched,
        errors,
        batch,
    )
    return summary


@celery_app.task(
    name="tasks.image_vlm.backfill_pending",
    queue="image_vlm_queue",
)
def backfill_pending_images(batch: int = 200) -> dict:
    """Pending ArticleImage'ları batch olarak queue'ya dispatch eder.

    Beat schedule: her 5 dakikada bir, batch=200.
    NIM rate limit 40 RPM, worker concurrency 2 → 5 dk'da pratikte
    300-400 görsel işlenir. Batch 200 ile worker beslenmesi garanti.

    Idempotent: status='pending' olanları seçer; processed/failed/skipped
    olanlar değişmez.
    """
    return _run_async(_backfill_pending_async(batch))
