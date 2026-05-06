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
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx

from app.core.media import (
    DOWNLOAD_TIMEOUT,
    ImageDownloadError,
    ImageRejected,
    download_image_url,
)
from app.core.settings_store import settings_store
from app.core.vlm_postprocess import enrich_caption_with_depicts
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
        # Geçici hatalar (timeout/network/5xx/rate limit) re-raise → Celery autoretry
        # Permanent hatalar (mime hatası, çok büyük dosya) DB 'failed' yaz, summary dön
        try:
            downloaded = await download_image_url(
                img.original_url,
                timeout=download_timeout,
                max_bytes=max_image_bytes,
            )
        except ImageRejected as exc:
            # Permanent — mime/size validation fail
            img.status = "failed"
            await db.commit()
            summary["status"] = "rejected"
            summary["error"] = str(exc)
            return summary
        # ImageDownloadError + httpx errors → re-raise (autoretry)
        # NOT: 4xx/5xx ayrımı download_image_url içinde yok; 4xx genelde
        # 1 retry'da düzelmez ama 1-2 deneme zarar etmez. retry_failed_images
        # task'ı saatte bir 'failed' kayıtları tekrar dispatch eder.

        # 2) NIM VLM call
        provider = build_nim_vlm_provider()
        if provider is None:
            # Settings hatası — permanent
            del downloaded
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
        except VLMRateLimitError:
            # 429 — re-raise → Celery autoretry (mevcut)
            logger.warning("NIM VLM rate limit img=%s", article_image_id)
            del downloaded
            raise
        except VLMTimeoutError:
            # Geçici — re-raise → Celery autoretry (yeni)
            logger.warning("NIM VLM timeout img=%s", article_image_id)
            del downloaded
            raise
        except VLMError as exc:
            # Permanent (parse fail, model hatası) — DB failed
            img.status = "failed"
            await db.commit()
            summary["status"] = "failed"
            summary["error"] = f"vlm: {exc}"
            del downloaded
            return summary

        # 3) Bytes discard (Python GC, ek explicit del)
        del downloaded

        # 4) Post-processing — caption + depicts uyumsuzluğu (#304 fix)
        # VLM bazen depicts'te isim verir ama caption'da kullanmaz; helper
        # otomatik birleştirir (pure Python, ek API call YOK).
        enriched_caption = enrich_caption_with_depicts(
            result.caption or "", result.depicts or []
        )

        # 5) DB update — VLM metadata
        img.vlm_caption = enriched_caption[:5000] if enriched_caption else None
        img.ocr_text = result.ocr_text[:10000] if result.ocr_text else None
        img.depicts = result.depicts if result.depicts else None
        img.processed_at = datetime.now(timezone.utc)
        img.status = "processed"
        await db.commit()

        summary["status"] = "processed"
        summary["caption_len"] = len(enriched_caption)
        summary["caption_enriched"] = enriched_caption != (result.caption or "")
        summary["ocr_len"] = len(result.ocr_text)
        summary["depicts_count"] = len(result.depicts)
        summary["model"] = result.model_used
        summary["latency_ms"] = round(result.latency_ms, 1)
        return summary


# Geçici hatalar — Celery autoretry tetikler (#304 fix)
_TRANSIENT_EXCEPTIONS = (
    VLMRateLimitError,        # NIM 429
    VLMTimeoutError,          # NIM timeout
    ImageDownloadError,       # 4xx/5xx network — 1-2 deneme genelde yeter
    httpx.TimeoutException,   # connect/read timeout
    httpx.RequestError,       # DNS, connection reset
)


async def _mark_failed_async(image_id: UUID, error: str) -> None:
    """Retry tükendiğinde DB'ye 'failed' yaz."""
    factory = _get_session_factory()
    async with factory() as db:
        img = await db.get(ArticleImage, image_id)
        if img and img.status != "processed":
            img.status = "failed"
            await db.commit()
            logger.warning(
                "image_vlm: marked failed after retries id=%s err=%s",
                image_id,
                error[:200],
            )


@celery_app.task(
    name="tasks.image_vlm.process",
    bind=True,
    autoretry_for=_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    queue="image_vlm_queue",
)
def process_article_image_vlm(self, article_image_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Article image NIM VLM ile işle (process & discard).

    Queue: image_vlm_queue (worker_image_vlm consumer)
    Retry: 3x for transient errors (rate limit, timeout, network, 5xx).
    Retry tükendiğinde DB'ye status='failed' yazar.
    """
    try:
        return _run_async(_process_image_async(UUID(article_image_id)))
    except _TRANSIENT_EXCEPTIONS as exc:
        # autoretry mekanizması tetikleyecek — son denemeyse DB failed yaz
        if self.request.retries >= self.max_retries:
            _run_async(_mark_failed_async(UUID(article_image_id), str(exc)))
            return {
                "article_image_id": article_image_id,
                "status": "failed_after_retries",
                "error": str(exc),
            }
        # Aksi halde Celery autoretry_for ile re-raise edilir
        raise


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


# =============================================================================
# Retry failed task — failed kayıtları periyodik olarak yeniden dener (#304 fix).
# Beat schedule: saatte bir batch=100. Geçici nedenlerle (DNS outage, NIM
# server hatası, vb.) failed olan görseller ortalama 1-2 retry sonrası başarılı
# olur. Permanent hatalar (mime/size validation, parse fail) zaten zaten
# 1 retry sonrası tekrar başarısız olur — sonsuz döngü riski yok.
# =============================================================================


async def _retry_failed_async(batch: int, max_age_hours: int) -> dict:
    """En eski 'failed' ArticleImage'lardan batch kadarını 'pending' yap +
    process task'ı dispatch et. max_age_hours filtresi: çok eski failed'ları
    bypass et (bunlar kaynak haber zaten silinmiş olabilir).
    """
    from sqlalchemy import select, update

    from app.models.article import ArticleImage

    factory = _get_session_factory()
    summary: dict[str, object] = {
        "batch_requested": batch,
        "max_age_hours": max_age_hours,
        "reset_to_pending": 0,
        "dispatched": 0,
        "errors": 0,
    }

    async with factory() as db:
        # Failed + max_age_hours filtreli (eski hata, kaynak hala accessible olabilir)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        stmt = (
            select(ArticleImage.id)
            .where(
                ArticleImage.status == "failed",
                ArticleImage.created_at >= cutoff,
            )
            .order_by(ArticleImage.created_at.asc())
            .limit(batch)
        )
        rows = list((await db.execute(stmt)).scalars().all())

        if not rows:
            return summary

        # Toplu UPDATE: failed → pending
        await db.execute(
            update(ArticleImage)
            .where(ArticleImage.id.in_(rows))
            .values(status="pending", processed_at=None)
        )
        await db.commit()
        summary["reset_to_pending"] = len(rows)

    # Dispatch
    dispatched = 0
    errors = 0
    for image_id in rows:
        try:
            process_article_image_vlm.apply_async(args=[str(image_id)])
            dispatched += 1
        except Exception as exc:
            logger.warning(
                "retry_failed dispatch failed id=%s err=%s", image_id, exc
            )
            errors += 1

    summary["dispatched"] = dispatched
    summary["errors"] = errors
    logger.info(
        "image_vlm retry_failed: reset=%d dispatched=%d errors=%d batch=%d age<=%dh",
        len(rows),
        dispatched,
        errors,
        batch,
        max_age_hours,
    )
    return summary


@celery_app.task(
    name="tasks.image_vlm.retry_failed",
    queue="image_vlm_queue",
)
def retry_failed_images(batch: int = 100, max_age_hours: int = 72) -> dict:
    """Failed ArticleImage'ları batch olarak yeniden dener.

    Beat schedule: saatte bir, batch=100, max_age_hours=72 (3 gün).
    72 saatten eski failed kayıtlar bypass edilir (kaynak haber muhtemelen
    artık erişilemez veya yeni nedenler birikmiş — manuel inceleme gerek).

    Akış: failed → pending UPDATE → process_article_image_vlm dispatch.
    Permanent fail kayıtları (parse fail, mime validation) tekrar failed
    olur ama bir sonraki saat tekrar denenir; max 72h penceresi sonsuz
    döngüyü önler.
    """
    return _run_async(_retry_failed_async(batch, max_age_hours))
