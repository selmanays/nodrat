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

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cleaning import (
    STATUS_ARCHIVED,
    STATUS_CLEANED,
    STATUS_DISCOVERED,
    STATUS_FAILED,
    STATUS_FETCHED,
    canonicalize_url,
    clean_extracted,
    compute_content_hash,
    compute_title_hash,
    extract_external_article_id,
    should_skip_discovery,
)
from app.core.content_quality import (
    check_response_quality,
    validate_url,
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

        # #524 — URL validation: hostname/scheme yoksa fetch yapamayız.
        # Habertürk RSS bazen relative URL döner ('/video/haber/izle/...')
        # → fetch_text status=0 fail. Discovery aşamasında reddet.
        url_valid, url_reason = validate_url(canonical)
        if not url_valid:
            summary["status"] = "skipped_invalid_url"
            summary["reason"] = url_reason
            logger.info(
                "article_discover skipped invalid_url=%s reason=%s",
                canonical[:120], url_reason,
            )
            return summary

        # #504 — Discovery URL filter: canlı blog/video/veri sayfaları skip.
        # Bu URL'ler haber gibi görünür ama RAG için anlamsızdır (sürekli
        # güncellenen içerik, video player, finansal tablo). Discover'a
        # almamak gereksiz fetch + NIM token + queue meşguliyetini önler.
        skip, skip_reason = should_skip_discovery(canonical)
        if skip:
            summary["status"] = "skipped_url_pattern"
            summary["reason"] = skip_reason
            logger.info(
                "article_discover skipped url_pattern=%s url=%s",
                skip_reason, canonical[:120],
            )
            return summary

        # Dedupe katman 1: canonical_url exact match (DB-level UNIQUE).
        existing = (
            await db.execute(
                select(Article.id).where(Article.canonical_url == canonical)
            )
        ).scalar_one_or_none()
        if existing is not None:
            summary["status"] = "duplicate"
            summary["article_id"] = str(existing)
            return summary

        # Dedupe katman 2 (#496): external_article_id slug-agnostic match.
        # Slug değişikliği (Evrensel editöryel typo düzeltme) durumunda aynı
        # haber farklı URL'le iki kez INSERT edilmesin. Pattern eşleşmiyorsa
        # (None) bu katman skip — fallback canonical_url match yeterli.
        ext_id = extract_external_article_id(canonical)
        if ext_id:
            existing_by_ext_id = (
                await db.execute(
                    select(Article.id).where(
                        Article.source_id == source.id,
                        Article.external_article_id == ext_id,
                    )
                )
            ).scalar_one_or_none()
            if existing_by_ext_id is not None:
                summary["status"] = "duplicate_external_id"
                summary["article_id"] = str(existing_by_ext_id)
                summary["external_article_id"] = ext_id
                logger.info(
                    "article_discover slug-change dedup: ext_id=%s existing=%s "
                    "new_url=%s skip",
                    ext_id, existing_by_ext_id, canonical[:120],
                )
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
            external_article_id=ext_id,  # #496 — slug-change dedup
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


# Geçici hatalar — Celery autoretry tetikler (#433).
# IntegrityError BURADA YOK çünkü _article_fetch_detail_async içinde explicit
# handler'ı var (duplicate content_hash → article.duplicate_content). Diğer
# IntegrityError'lar gerçek bug — autoretry yapmasın, yüzeye çıksın.
_TRANSIENT_EXCEPTIONS = (
    httpx.TimeoutException,    # network timeout
    httpx.RequestError,         # DNS / connection reset / SSL handshake
    OperationalError,           # DB connection lost / pool timeout
    ConnectionError,            # generic connection
    TimeoutError,               # generic timeout
)


def _is_duplicate_content_hash_error(exc: IntegrityError) -> bool:
    """uq_articles_source_content_hash UNIQUE ihlali mi?

    asyncpg.UniqueViolationError detail message'ında constraint adı geçer.
    SQLAlchemy IntegrityError str() bunu sarmalayarak gösterir.
    """
    return "uq_articles_source_content_hash" in str(exc).lower()


async def _record_failure(
    db: AsyncSession,
    *,
    article: Article | None,
    job_type: str,
    error: str,
    payload: dict,
    severity: str = "error",
    article_status_override: str | None = None,
) -> None:
    """failed_jobs DLQ insert helper.

    severity (#445):
      - 'error' (default): gerçek hata — alarm sayımına dahil
      - 'warning': geçici/öngörülen, manuel müdahale gerekir
      - 'permanent_info': RSS re-emit gibi info-level olay — auto-resolve
        (resolved_at=now()), admin sayfasında default sorguda görünmez

    article_status_override (#488):
      Caller'ın kasıtlı olarak article.status'u belirli bir değere çekmesi
      için. Default davranış (None):
        - severity='error'/'warning' → STATUS_FAILED
        - severity='permanent_info' → DEĞİŞTİRMEZ
      Override örnekleri:
        - duplicate_content path → STATUS_ARCHIVED (terminal, retry yok)
    """
    now = datetime.now(timezone.utc)
    is_permanent_info = severity == "permanent_info"
    failed = FailedJob(
        job_type=job_type,
        payload_json=payload,
        source_id=article.source_id if article else None,
        article_url=article.source_url if article else payload.get("source_url"),
        error_message=error[:1000],
        last_attempt_at=now,
        severity=severity,
        resolved_at=now if is_permanent_info else None,
        resolution_note=(
            "auto-resolved permanent_info" if is_permanent_info else None
        ),
    )
    db.add(failed)

    if article is None:
        return

    # #488 — caller override > severity-tabanlı default
    if article_status_override is not None:
        article.status = article_status_override
        return

    # Default: error/warning → failed; permanent_info → değiştirme.
    # NOT: permanent_info caller'ı article'ı discovered'da bırakacaksa
    # mutlaka article_status_override kullansın — yoksa backfill_discovered
    # tarafından sonsuz dispatch loop'a girer.
    if not is_permanent_info:
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

        # 1.5) Content Quality Gate (#524) — fetch OK ama içerik geçersiz mi?
        # Soft 404 (Evrensel silinen haber: HTTP 200 + '<title>404 Sayfa
        # Bulunamadı</title>') veya thin content (AA SPA skeleton, AA
        # live-blog, video player) terminal archived'a alınır. Retry yok —
        # içerik yok demek, yeniden fetch'te değişmez.
        quality = check_response_quality(body, article.source_url)
        if not quality.passed:
            await _record_failure(
                db,
                article=article,
                job_type=f"article.{quality.failure_reason}",  # soft_404 / thin_content
                error=f"{quality.failure_reason}: {quality.detail or '(no detail)'}",
                payload={
                    "source_url": article.source_url,
                    "reason": quality.failure_reason,
                    "detail": quality.detail,
                },
                severity="permanent_info",  # auto-resolve DLQ — alarm değil
                article_status_override=STATUS_ARCHIVED,  # terminal, retry yok
            )
            await db.commit()
            summary["status"] = quality.failure_reason
            summary["detail"] = quality.detail
            return summary

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
        # #513 — cleaned_at sadece status='cleaned' geçişinde set edilir.
        # updated_at çok-amaçlı (migration UPDATE'leri, body_html drop,
        # dedup, vb. her UPDATE'te değişir). Admin chart 'Temizlenen
        # içerikler' yığılma önlemek için ayrı field.
        _now = datetime.now(timezone.utc)
        article.updated_at = _now
        article.cleaned_at = _now

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

        # IntegrityError handler — RSS re-emit / republish nedeniyle aynı kaynaktan
        # aynı content_hash başka bir article'da zaten 'cleaned' olarak var olabilir.
        # uq_articles_source_content_hash ihlali → article 'failed' + DLQ, stuck olmasın
        # (#433 — image_vlm "Bug sentinel" pattern'ı article için).
        # NOT: Rollback sonrası AYNI session kullanılır (yeni factory() açmak
        # outer async with'in __aexit__'inde MissingGreenlet tetikliyor).
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            if _is_duplicate_content_hash_error(exc):
                article_reload = await db.get(Article, article_id)
                if article_reload is not None and article_reload.status != STATUS_CLEANED:
                    await _record_failure(
                        db,
                        article=article_reload,
                        job_type="article.duplicate_content",
                        error=(
                            "content_hash already exists for source — "
                            "RSS re-emit / republish (uq_articles_source_content_hash)"
                        ),
                        payload={
                            "source_url": article_reload.source_url,
                            "content_hash": cleaned.content_hash,
                        },
                        # #445 — RSS re-emit info, hata değil; auto-resolve
                        severity="permanent_info",
                        # #488 — terminal state'e taşı; eski yorumda
                        # permanent_info article'ı 'değiştirme' deniyordu
                        # ama discovered'da kalınca backfill_discovered
                        # task her 5 dk yeniden dispatch ediyor → sonsuz loop.
                        # Archive content yok ve retry yok semantiğini
                        # taşır; bu duplicate için doğru semantik.
                        article_status_override=STATUS_ARCHIVED,
                    )
                    await db.commit()
                summary["status"] = "duplicate_content"
                summary["content_hash"] = cleaned.content_hash
                logger.info(
                    "article.duplicate_content art=%s url=%s — RSS re-emit",
                    article_id,
                    article.source_url[:120],
                )
                return summary
            # Başka bir IntegrityError → bug, yüzeye çıksın
            raise

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
                # #300 PR-3 — image_vlm_queue (NIM Llama 4 Maverick process & discard)
                from app.workers.tasks.image_vlm import process_article_image_vlm

                process_article_image_vlm.apply_async(args=[str(img_id)])
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("dispatch image_vlm failed img=%s err=%s", img_id, exc)

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
    autoretry_for=_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=2,
)
def article_fetch_detail(self, article_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Article detail fetch + extract + clean + persist.

    Transient (autoretry 2x, exp backoff): network timeout, DB connection lost.
    Permanent (DB 'failed' + DLQ): fetch HTTP 4xx/5xx, extraction conf<0.6,
    cleaning fail, duplicate content_hash (#433).

    autoretry_for=Exception (eski) "Bug sentinel" pattern riskliydi: IntegrityError
    autoretry'a girip 2× tüketiliyor, transaction rollback nedeniyle article
    'discovered' state'inde takılı kalıyordu. Şimdi sadece geçici hatalar
    autoretry edilir; IntegrityError explicit handler ile yakalanır.
    """
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


# ============================================================================
# #436 — Backfill discovered articles (image_vlm.backfill_pending pattern'i)
# ============================================================================


async def _backfill_discovered_async(batch: int, max_age_hours: int) -> dict:
    """En eski 'discovered' article'lardan batch kadarını dispatch et.

    Idempotent: sadece status='discovered' AND created_at >= NOW()-max_age_hours.
    Stale (>max_age_hours) article'lar bypass — kaynak haber muhtemelen artık
    erişilemez (yayıncı silmiş, URL değişmiş) veya freshness kayıp; sonsuz
    retry NIM kotasını ve worker yükünü boşa harcar.
    """
    from datetime import timedelta

    factory = _get_session_factory()
    summary: dict[str, object] = {
        "batch_requested": batch,
        "max_age_hours": max_age_hours,
        "dispatched": 0,
        "errors": 0,
    }

    async with factory() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        stmt = (
            select(Article.id)
            .where(Article.status == STATUS_DISCOVERED)
            .where(Article.created_at >= cutoff)
            .order_by(Article.created_at.asc())
            .limit(batch)
        )
        rows = list((await db.execute(stmt)).scalars().all())

    dispatched = 0
    errors = 0
    for article_id in rows:
        try:
            article_fetch_detail.apply_async(args=[str(article_id)])
            dispatched += 1
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "backfill_discovered dispatch failed id=%s err=%s", article_id, exc
            )
            errors += 1

    summary["dispatched"] = dispatched
    summary["errors"] = errors
    logger.info(
        "articles backfill_discovered: dispatched=%d errors=%d batch=%d age<=%dh",
        dispatched,
        errors,
        batch,
        max_age_hours,
    )
    return summary


@celery_app.task(name="tasks.articles.backfill_discovered", queue="crawl_queue")
def backfill_discovered_articles(batch: int = 100, max_age_hours: int = 72) -> dict:
    """Stuck 'discovered' article'ları batch olarak fetch_detail kuyruğuna al.

    Beat schedule: her 5 dakika, batch=100, max_age_hours=72.
    Discovery sırasında dispatch edilen fetch_detail Redis broker'da kaybolursa
    veya worker crash anında task uçtuysa, bu backfill stuck article'ı yakalar.
    Idempotent: sadece status='discovered'; processed/failed olanlar değişmez.
    """
    return _run_async(_backfill_discovered_async(batch, max_age_hours))


# ============================================================================
# #436 — Retry failed articles (image_vlm.retry_failed pattern'i)
# ============================================================================


async def _retry_failed_articles_async(batch: int, max_age_hours: int) -> dict:
    """Failed article'ları batch olarak yeniden dener (image retry_failed pattern).

    En eski 'failed' article'lardan batch kadarını 'discovered' yap +
    fetch_detail dispatch et. max_age_hours filtresi: çok eski failed'lar
    bypass (kaynak haber muhtemelen artık erişilemez).
    """
    from datetime import timedelta

    from sqlalchemy import update

    factory = _get_session_factory()
    summary: dict[str, object] = {
        "batch_requested": batch,
        "max_age_hours": max_age_hours,
        "reset_to_discovered": 0,
        "dispatched": 0,
        "errors": 0,
    }

    async with factory() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        stmt = (
            select(Article.id)
            .where(Article.status == STATUS_FAILED)
            .where(Article.created_at >= cutoff)
            .order_by(Article.created_at.asc())
            .limit(batch)
        )
        rows = list((await db.execute(stmt)).scalars().all())

        if not rows:
            return summary

        # Toplu UPDATE: failed → discovered (fetch_detail tekrar denesin)
        await db.execute(
            update(Article)
            .where(Article.id.in_(rows))
            .values(status=STATUS_DISCOVERED)
        )
        await db.commit()
        summary["reset_to_discovered"] = len(rows)

    dispatched = 0
    errors = 0
    for article_id in rows:
        try:
            article_fetch_detail.apply_async(args=[str(article_id)])
            dispatched += 1
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "retry_failed dispatch failed id=%s err=%s", article_id, exc
            )
            errors += 1

    summary["dispatched"] = dispatched
    summary["errors"] = errors
    logger.info(
        "articles retry_failed: reset=%d dispatched=%d errors=%d batch=%d age<=%dh",
        len(rows),
        dispatched,
        errors,
        batch,
        max_age_hours,
    )
    return summary


@celery_app.task(name="tasks.articles.retry_failed", queue="crawl_queue")
def retry_failed_articles(batch: int = 50, max_age_hours: int = 72) -> dict:
    """Failed article'ları batch olarak yeniden dener.

    Beat schedule: saatlik :25 (image retry_failed :20 ile çakışmasın),
    batch=50, max_age_hours=72.

    Akış: failed → discovered UPDATE → article_fetch_detail dispatch.
    Permanent fail kayıtları (duplicate_content, fetch HTTP 4xx, extraction
    conf<0.6) tekrar fail olur ama:
      - autoretry yok (Faz B sayesinde IntegrityError + ImageRejected hızlı reject)
      - max 72h penceresi sonsuz retry'ı önler

    Geçici hatalar (DNS outage, 5xx, timeout) bu retry ile recover olur.
    """
    return _run_async(_retry_failed_articles_async(batch, max_age_hours))
