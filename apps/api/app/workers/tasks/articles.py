"""Article worker pipeline (#94) — RSS item → DB → extract → clean → persist.

Tasks:
    article_discover(source_id, item_dict)
        - Feed item'i articles tablosuna INSERT (status='discovered')
        - Dedupe check (canonical_url unique)
        - article_fetch_detail Celery task dispatch

    article_fetch_detail(article_id)
        - articles row'unun source_url'sinden HTML fetch
        - 3-kademeli extractor (selectors > trafilatura > fallback)
        - clean_extracted (boilerplate + PII + canonicalize + hash + lang)
        - articles UPDATE (status='cleaned')
        - Hata → failed_jobs DLQ
        - Görsel varsa article_images + media task

docs/engineering/architecture.md §3
docs/engineering/data-model.md §3.4 (state machine)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cleaning import (
    STATUS_CLEANED,
    STATUS_DISCOVERED,
    STATUS_FAILED,
    STATUS_FETCHED,
    canonicalize_url,
    clean_extracted,
    compute_content_hash,
    compute_title_hash,
)
from app.core.extractor import extract_article
from app.core.http_client import fetch_text
from app.core.rss import FeedItem
from app.models.article import Article, ArticleImage
from app.models.job import FailedJob
from app.models.source import Source
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _get_session_factory, _run_async


logger = logging.getLogger(__name__)


# ============================================================================
# article_discover — RSS item → articles row (status=discovered)
# ============================================================================


async def _article_discover_async(source_id: UUID, item_data: dict[str, Any]) -> dict:
    """Feed item'i articles tablosuna INSERT eder.

    item_data: {title, link, summary, author, published_at_iso, image_url, raw_id}
    """
    factory = _get_session_factory()
    summary: dict[str, object] = {
        "source_id": str(source_id),
        "status": "unknown",
    }

    async with factory() as db:
        source = await db.get(Source, source_id)
        if source is None:
            summary["status"] = "skipped"
            summary["reason"] = "source_not_found"
            return summary

        link = (item_data.get("link") or "").strip()
        title = (item_data.get("title") or "").strip()
        if not link or not title:
            summary["status"] = "skipped"
            summary["reason"] = "missing_link_or_title"
            return summary

        canonical = canonicalize_url(link)

        # Dedupe: canonical_url UNIQUE (DB-level)
        existing = (
            await db.execute(
                select(Article.id).where(Article.canonical_url == canonical)
            )
        ).scalar_one_or_none()
        if existing is not None:
            summary["status"] = "duplicate"
            summary["article_id"] = str(existing)
            return summary

        # ISO published_at
        published_at: datetime | None = None
        if iso := item_data.get("published_at_iso"):
            try:
                published_at = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
            except ValueError:
                published_at = None

        # Discover sırasında summary'den geçici hash (cleaning sonrası güncellenecek)
        provisional_text = (item_data.get("summary") or title).strip()

        article = Article(
            source_id=source.id,
            canonical_url=canonical,
            source_url=link,
            title=title[:1000],
            subtitle=None,
            author=item_data.get("author") or None,
            published_at=published_at,
            language=source.language or "tr",
            content_hash=compute_content_hash(provisional_text),
            title_hash=compute_title_hash(title),
            status=STATUS_DISCOVERED,
        )
        db.add(article)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            summary["status"] = "duplicate"
            return summary

        # #300 PR-2 — RSS thumbnail SKIP. Body images detail-fetch aşamasında
        # extract_body_images ile parse edilir (article_fetch_detail task).

        await db.commit()
        summary["status"] = "discovered"
        summary["article_id"] = str(article.id)

        # 2nd-stage detail task — dispatch (sync Celery)
        try:
            article_fetch_detail.apply_async(args=[str(article.id)])
            summary["dispatched_detail"] = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("dispatch fetch_detail failed art=%s err=%s", article.id, exc)

        return summary


@celery_app.task(name="tasks.articles.discover", bind=True, max_retries=2)
def article_discover(self, source_id: str, item_data: dict) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_article_discover_async(UUID(source_id), item_data))


# ============================================================================
# article_fetch_detail — full extraction + cleaning + persist
# ============================================================================


async def _record_failure(
    db: AsyncSession,
    *,
    article: Article | None,
    job_type: str,
    error: str,
    payload: dict,
) -> None:
    """failed_jobs DLQ insert helper."""
    failed = FailedJob(
        job_type=job_type,
        payload_json=payload,
        source_id=article.source_id if article else None,
        article_url=article.source_url if article else payload.get("source_url"),
        error_message=error[:1000],
        last_attempt_at=datetime.now(timezone.utc),
    )
    db.add(failed)
    if article is not None:
        article.status = STATUS_FAILED


async def _article_fetch_detail_async(article_id: UUID) -> dict:
    """articles row'una bağlı detay sayfayı fetch+extract+clean+persist."""
    factory = _get_session_factory()
    summary: dict[str, object] = {"article_id": str(article_id), "status": "unknown"}

    async with factory() as db:
        article = await db.get(Article, article_id)
        if article is None:
            summary["status"] = "not_found"
            return summary

        # State guard
        if article.status == STATUS_CLEANED:
            summary["status"] = "already_cleaned"
            return summary

        # 1) HTML fetch — #270 runtime timeout override
        try:
            from app.core.settings_store import settings_store

            timeout = await settings_store.get_float(
                db, "scraping.article_detail_timeout", 20.0
            )
        except Exception:  # pragma: no cover
            timeout = 20.0
        status_code, body, _ = await fetch_text(article.source_url, timeout=timeout)
        if status_code == 0 or status_code >= 400 or not body:
            await _record_failure(
                db,
                article=article,
                job_type="article.fetch_detail",
                error=f"fetch failed status={status_code}",
                payload={"source_url": article.source_url},
            )
            await db.commit()
            summary["status"] = "fetch_failed"
            summary["http_status"] = status_code
            return summary

        article.status = STATUS_FETCHED

        # 2) Extract (kaynağa özel selectors yoksa trafilatura+fallback)
        extracted = extract_article(body, url=article.source_url, language=article.language)
        if not extracted.successful:
            await _record_failure(
                db,
                article=article,
                job_type="article.extract",
                error=(
                    f"extraction failed strategy={extracted.strategy_used} "
                    f"conf={extracted.extraction_confidence}"
                ),
                payload={"source_url": article.source_url, "strategy": extracted.strategy_used},
            )
            await db.commit()
            summary["status"] = "extract_failed"
            return summary

        # 3) Clean (PII redaction default açık)
        cleaned = clean_extracted(extracted)
        if not cleaned.successful:
            await _record_failure(
                db,
                article=article,
                job_type="article.clean",
                error=cleaned.error or "cleaning_failed",
                payload={"source_url": article.source_url},
            )
            await db.commit()
            summary["status"] = "clean_failed"
            return summary

        # 4) Persist
        article.title = cleaned.title or article.title
        if cleaned.subtitle:
            article.subtitle = cleaned.subtitle
        if cleaned.author:
            article.author = cleaned.author
        if cleaned.published_at and not article.published_at:
            article.published_at = cleaned.published_at
        article.body_html = cleaned.body_html
        article.clean_text = cleaned.clean_text
        article.content_hash = cleaned.content_hash
        article.title_hash = cleaned.title_hash
        article.language = cleaned.language
        article.extraction_confidence = cleaned.extraction_confidence
        article.status = STATUS_CLEANED
        article.updated_at = datetime.now(timezone.utc)

        # 5) Görsel — #300 PR-2: body içindeki TÜM img tag'leri (multi-image)
        # Önceki RSS thumbnail / og:image eksklusif. Sadece body_images kullanılır.
        for body_img in cleaned.body_images:
            db.add(
                ArticleImage(
                    article_id=article.id,
                    source_id=article.source_id,
                    original_url=body_img.url[:2000],
                    alt_text=body_img.alt or None,
                    caption=body_img.caption or None,
                    position=body_img.position,
                    discovered_from="body",
                    status="pending",
                )
            )

        await db.commit()

        # 6) Media task dispatch (görsel pending'se)
        pending_imgs = list(
            (
                await db.execute(
                    select(ArticleImage.id)
                    .where(ArticleImage.article_id == article.id)
                    .where(ArticleImage.status == "pending")
                )
            ).scalars().all()
        )
        for img_id in pending_imgs:
            try:
                from app.workers.tasks.media import download_article_image

                download_article_image.apply_async(args=[str(img_id)])
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("dispatch media failed img=%s err=%s", img_id, exc)

        # 7) Embedding chain dispatch (Faz 2)
        chunk_dispatched = False
        try:
            from app.workers.tasks.embedding import chunk_article

            chunk_article.apply_async(args=[str(article.id)])
            chunk_dispatched = True
        except Exception as exc:  # pragma: no cover
            logger.exception("dispatch chunk_article failed art=%s err=%s", article.id, exc)

        summary.update(
            {
                "status": "cleaned",
                "title": article.title[:80],
                "language": article.language,
                "lang_conf": cleaned.language_confidence,
                "boilerplate_ratio": cleaned.boilerplate_ratio,
                "pii_redactions": cleaned.pii_redactions,
                "text_len": len(cleaned.clean_text),
                "media_dispatched": len(pending_imgs),
                "chunk_dispatched": chunk_dispatched,
            }
        )
        return summary


@celery_app.task(
    name="tasks.articles.fetch_detail",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=2,
)
def article_fetch_detail(self, article_id: str) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_article_fetch_detail_async(UUID(article_id)))


# ============================================================================
# #166 — Backfill chunk_article for cleaned articles missing chunks
# ============================================================================


async def _backfill_missing_chunks_async(batch: int = 50) -> dict:
    """Cleaned ama chunks oluşmamış article'lar için chunk_article dispatch.

    Eski article'lar (chain dispatch eklenmeden önce cleaned olmuş) veya
    embedding provider transient hata sırasında kaybedilen task'lar bu
    backfill ile tekrar kuyruğa alınır. Idempotent.
    """
    from sqlalchemy import text as sa_text

    from app.workers.tasks.embedding import chunk_article
    from app.workers.tasks.sources import open_session

    summary: dict = {"requested": batch, "dispatched": 0, "errors": 0}

    async with open_session() as db:
        rows = (
            await db.execute(
                sa_text(
                    """
                    SELECT a.id::text AS id
                    FROM articles a
                    WHERE a.status = 'cleaned'
                      AND NOT EXISTS (
                          SELECT 1 FROM article_chunks
                          WHERE article_id = a.id
                      )
                    ORDER BY a.created_at DESC
                    LIMIT :batch
                    """
                ),
                {"batch": batch},
            )
        ).mappings().all()

    if not rows:
        summary["status"] = "no_missing"
        return summary

    for r in rows:
        try:
            chunk_article.apply_async(args=[r["id"]])
            summary["dispatched"] += 1
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "backfill chunk dispatch failed art=%s err=%s", r["id"], exc
            )
            summary["errors"] += 1

    summary["status"] = "ok"
    return summary


@celery_app.task(name="tasks.articles.backfill_missing_chunks", bind=True)
def backfill_missing_chunks(self, batch: int = 50) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_backfill_missing_chunks_async(batch))
