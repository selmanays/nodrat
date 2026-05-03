"""Media download Celery tasks (#15).

Tasks:
    download_article_image(article_image_id)
        — article_images row'una bağlı görseli indir + MinIO'ya yükle + DB güncelle

docs/engineering/data-model.md §3.5 (article_images)
docs/engineering/architecture.md §3.1 (media_queue)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.media import (
    DOWNLOAD_TIMEOUT,
    DownloadedImage,
    ImageDownloadError,
    ImageRejected,
    download_image_url,
)
from app.core.storage import (
    UploadResult,
    build_image_key,
    ensure_bucket,
    upload_bytes,
)
from app.models.article import ArticleImage
from app.models.source import Source
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _get_session_factory, _run_async


logger = logging.getLogger(__name__)


async def _find_existing_by_hash(
    db: AsyncSession, sha256_hash: str
) -> ArticleImage | None:
    """Aynı sha256 hash + status='downloaded' olan ArticleImage var mı?

    DB'de partial unique index (uniq_article_images_hash) zaten var; bu sorgu
    duplicate olduğunda mevcut storage_url'ı reuse etmek için.
    """
    stmt = (
        select(ArticleImage)
        .where(ArticleImage.sha256_hash == sha256_hash)
        .where(ArticleImage.status == "downloaded")
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _download_article_image_async(article_image_id: UUID) -> dict:
    """ArticleImage row'una bağlı görseli indir + MinIO upload + DB update."""
    factory = _get_session_factory()
    settings = get_settings()
    bucket = settings.minio_bucket_images
    summary: dict[str, object] = {
        "article_image_id": str(article_image_id),
        "status": "unknown",
        "error": None,
    }

    async with factory() as db:
        img = await db.get(ArticleImage, article_image_id)
        if img is None:
            summary["error"] = "article_image_not_found"
            return summary

        # Idempotent: zaten indirilmişse skip
        if img.status == "downloaded":
            summary["status"] = "already_downloaded"
            summary["storage_url"] = img.storage_url
            return summary

        source = await db.get(Source, img.source_id)
        source_slug = source.slug if source else "unknown"
        original_url = img.original_url

        # 1) Download + validate — #271 runtime override
        try:
            from app.core.settings_store import settings_store

            dl_timeout = await settings_store.get_float(
                db, "media.download_timeout", DOWNLOAD_TIMEOUT
            )
            dl_max_bytes = await settings_store.get_int(
                db, "media.max_image_bytes", 10 * 1024 * 1024
            )
            dl_max_redirects = await settings_store.get_int(
                db, "media.max_redirects", 5
            )
        except Exception:  # pragma: no cover
            dl_timeout = DOWNLOAD_TIMEOUT
            dl_max_bytes = 10 * 1024 * 1024
            dl_max_redirects = 5

        try:
            downloaded = await download_image_url(
                original_url,
                timeout=dl_timeout,
                max_bytes=dl_max_bytes,
                max_redirects=dl_max_redirects,
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
            summary["error"] = str(exc)
            return summary

        # 2) DB-level dedupe (aynı sha → reuse storage_url)
        existing = await _find_existing_by_hash(db, downloaded.sha256_hash)
        if existing is not None and existing.id != img.id:
            img.sha256_hash = downloaded.sha256_hash
            img.mime_type = downloaded.mime_type
            img.file_size = downloaded.size_bytes
            img.storage_url = existing.storage_url
            img.status = "duplicate"
            await db.commit()
            summary["status"] = "duplicate"
            summary["storage_url"] = existing.storage_url
            return summary

        # 3) MinIO upload
        if not ensure_bucket(bucket):
            summary["status"] = "failed"
            summary["error"] = "bucket_unavailable"
            img.status = "failed"
            await db.commit()
            return summary

        now = datetime.now(timezone.utc)
        key = build_image_key(
            source_slug=source_slug,
            image_id=str(img.id),
            extension=downloaded.extension,
            year=now.year,
            month=now.month,
            day=now.day,
        )

        try:
            result: UploadResult = await asyncio.to_thread(
                upload_bytes,
                bucket=bucket,
                key=key,
                data=downloaded.data,
                content_type=downloaded.mime_type,
                metadata={
                    "source_slug": source_slug,
                    "article_image_id": str(img.id),
                    "original_url": original_url[:200],
                },
            )
        except Exception as exc:  # pragma: no cover - external
            logger.exception("MinIO upload failed key=%s err=%s", key, exc)
            img.status = "failed"
            await db.commit()
            summary["status"] = "failed"
            summary["error"] = f"upload error: {exc}"
            return summary

        # 4) Persist
        img.sha256_hash = downloaded.sha256_hash
        img.mime_type = downloaded.mime_type
        img.file_size = downloaded.size_bytes
        img.storage_url = result.storage_url
        img.status = "downloaded"
        await db.commit()

        summary["status"] = "downloaded"
        summary["storage_url"] = result.storage_url
        summary["mime"] = downloaded.mime_type
        summary["size_bytes"] = downloaded.size_bytes
        summary["sha256"] = downloaded.sha256_hash[:16] + "..."
        return summary


@celery_app.task(
    name="tasks.media.download_article_image",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=2,  # PRD §1.8: max 2 retry
)
def download_article_image(self, article_image_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Tek görsel için download + upload + DB update."""
    return _run_async(_download_article_image_async(UUID(article_image_id)))
