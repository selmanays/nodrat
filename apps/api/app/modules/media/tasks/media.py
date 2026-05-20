"""Media Celery tasks (#15, #300 MVP-1.4 PR-1 cleanup).

Eski 'download → MinIO upload' pattern kaldırıldı. PR-3 (#303) NIM VLM
'process & discard' pipeline ile değiştirilecek.

Tasks:
    download_article_image(article_image_id)
        — Şu an: media.processing_enabled flag kontrolü, false ise skip.
          PR-3'te: NIM VLM call + metadata save (bytes saklamaz).

docs/engineering/data-model.md §3.5 (article_images)
docs/engineering/architecture.md §3.1 (image_vlm_queue)
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.models.article import ArticleImage
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _download_article_image_async(article_image_id: UUID) -> dict:
    """ArticleImage row'una bağlı görseli indir + MinIO upload + DB update.

    #300 MVP-1.4 PR-1 — DEPRECATED. media.processing_enabled flag'i ile
    disable edilebilir (default: false). PR-3'te NIM VLM pipeline ile
    tamamen değiştirilecek (process & discard pattern, MinIO upload yok).
    """
    factory = _get_session_factory()
    summary: dict[str, object] = {
        "article_image_id": str(article_image_id),
        "status": "unknown",
        "error": None,
    }

    async with factory() as db:
        # #300 — global media processing flag (default false PR-1 cleanup)
        from app.shared.runtime_config.settings_store import settings_store

        try:
            processing_enabled = await settings_store.get_bool(
                db, "media.processing_enabled", False
            )
        except Exception:  # pragma: no cover
            processing_enabled = False

        if not processing_enabled:
            img_skip = await db.get(ArticleImage, article_image_id)
            if img_skip is not None and img_skip.status == "pending":
                img_skip.status = "skipped"
                await db.commit()
            summary["status"] = "skipped"
            summary["error"] = "media.processing_enabled=false (PR-1 cleanup)"
            return summary

        img = await db.get(ArticleImage, article_image_id)
        if img is None:
            summary["error"] = "article_image_not_found"
            return summary

        # Idempotent: zaten işlenmişse skip
        if img.status == "processed":
            summary["status"] = "already_processed"
            return summary

        # PR-3 (#303) — NIM VLM pipeline burada implement edilecek
        # (process & discard: bytes geçici download → VLM call → metadata save)
        # Şu an stub: flag açıkken bile işlemiyor (PR-3'te yeni implementation)
        img.status = "skipped"
        await db.commit()
        summary["status"] = "skipped"
        summary["error"] = "VLM pipeline not yet implemented (waiting PR-3 #303)"
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
