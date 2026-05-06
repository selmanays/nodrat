"""Maintenance tasks (#219 MVP-1.5 PR-4 + #220 PR-5).

Cold tier retention:
    - 30+ gün eski article'ların raw_html'ini MinIO (hot, VPS lokal) →
      Contabo OS (cold, uzak S3) taşı
    - DB'de archived_at + cold_storage_key set
    - MinIO'dan sil (hot disk free up)

Saatlik beat: günlük 03:30 UTC. Idempotent.

docs/engineering/architecture.md §5 (storage hot/cold tier)
docs/strategy/unit-economics.md §2.4.1 (storage projeksiyonu)
"""

from __future__ import annotations

import gzip
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select, update

from app.config import get_settings
from app.core.settings_store import settings_store
from app.core.storage import (
    build_cold_storage_key,
    get_cold_storage_client,
    get_s3_client,
)
from app.models.article import Article
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _get_session_factory, _run_async


logger = logging.getLogger(__name__)


# =============================================================================
# Cold tier archive — hot (MinIO) → cold (Contabo OS)
# =============================================================================


async def _archive_one(article_id: UUID) -> dict[str, Any]:
    """Tek article'ın raw_html'ini cold storage'a taşı."""
    settings = get_settings()
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "article_id": str(article_id),
        "status": "unknown",
        "bytes_moved": 0,
    }

    async with factory() as db:
        article = await db.get(Article, article_id)
        if article is None:
            summary["status"] = "not_found"
            return summary
        if article.archived_at is not None:
            summary["status"] = "already_archived"
            return summary
        if not article.raw_html_storage_path:
            summary["status"] = "no_raw_html"
            return summary

    # 1) MinIO'dan oku (sync — boto3 client)
    minio = get_s3_client()
    minio_bucket = settings.minio_bucket_snapshots
    # raw_html_storage_path "s3://bucket/key" formatında veya direkt key
    src_path = article.raw_html_storage_path
    if src_path.startswith("s3://"):
        # s3://bucket/key parse
        without_prefix = src_path[5:]
        bucket_in_path, _, key_in_path = without_prefix.partition("/")
        minio_bucket = bucket_in_path
        minio_key = key_in_path
    else:
        minio_key = src_path

    try:
        obj = minio.get_object(Bucket=minio_bucket, Key=minio_key)
        raw_bytes = obj["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        # MinIO'da yok — DB'de path var ama obje silinmiş (tutarsızlık).
        # archived_at set etme; admin manuel inceleme yapsın.
        logger.warning(
            "cold_tier: minio object missing id=%s key=%s err=%s",
            article_id,
            minio_key,
            exc,
        )
        summary["status"] = "minio_missing"
        return summary

    # 2) Gzip compress (raw HTML genelde 30-60 KB → ~5-10 KB)
    compressed = gzip.compress(raw_bytes)
    bytes_in = len(raw_bytes)
    bytes_out = len(compressed)

    # 3) Cold storage'a yaz (Contabo OS)
    cold = get_cold_storage_client()
    cold_bucket = settings.s3_bucket
    now = datetime.now(timezone.utc)
    cold_key = build_cold_storage_key(
        article_id=str(article_id), year=now.year, month=now.month
    )
    try:
        cold.put_object(
            Bucket=cold_bucket,
            Key=cold_key,
            Body=compressed,
            ContentType="application/gzip",
            ContentEncoding="gzip",
            Metadata={
                "article-id": str(article_id),
                "original-size": str(bytes_in),
                "archived-at": now.isoformat(),
            },
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "cold_tier: contabo put failed id=%s key=%s err=%s",
            article_id,
            cold_key,
            exc,
        )
        summary["status"] = "cold_put_failed"
        summary["error"] = str(exc)
        return summary

    # 4) DB update (archived_at + cold_storage_key)
    async with factory() as db:
        await db.execute(
            update(Article)
            .where(Article.id == article_id)
            .values(archived_at=now, cold_storage_key=cold_key)
        )
        await db.commit()

    # 5) MinIO'dan sil (hot disk free up)
    try:
        minio.delete_object(Bucket=minio_bucket, Key=minio_key)
    except (ClientError, BotoCoreError) as exc:
        # Cold copy başarılı, MinIO delete başarısız — uyarı ver, geri dönme
        # (DB zaten archived_at set; tekrar dispatch edilirse already_archived döner)
        logger.warning(
            "cold_tier: minio delete failed (cold copy OK) id=%s err=%s",
            article_id,
            exc,
        )

    summary["status"] = "archived"
    summary["bytes_in"] = bytes_in
    summary["bytes_out"] = bytes_out
    summary["compression_ratio"] = round(bytes_in / max(bytes_out, 1), 2)
    summary["cold_key"] = cold_key
    return summary


async def _cold_tier_archive_async(batch: int, max_age_days: int) -> dict[str, Any]:
    """30+ gün eski article'ları batch ile cold tier'a taşı."""
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "batch_requested": batch,
        "max_age_days": max_age_days,
        "candidates": 0,
        "archived": 0,
        "skipped": 0,
        "failed": 0,
        "total_bytes_moved": 0,
    }

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    async with factory() as db:
        # Settings flag check
        try:
            enabled = await settings_store.get_bool(
                db, "cold_tier.enabled", False
            )
        except Exception:  # pragma: no cover
            enabled = False

        if not enabled:
            summary["status"] = "disabled"
            return summary

        stmt = (
            select(Article.id)
            .where(
                Article.archived_at.is_(None),
                Article.raw_html_storage_path.is_not(None),
                Article.created_at < cutoff,
            )
            .order_by(Article.created_at.asc())
            .limit(batch)
        )
        rows = list((await db.execute(stmt)).scalars().all())

    summary["candidates"] = len(rows)

    for article_id in rows:
        result = await _archive_one(article_id)
        if result["status"] == "archived":
            summary["archived"] += 1
            summary["total_bytes_moved"] += result.get("bytes_in", 0)
        elif result["status"] in ("already_archived", "no_raw_html", "minio_missing"):
            summary["skipped"] += 1
        else:
            summary["failed"] += 1

    summary["status"] = "ok"
    logger.info(
        "cold_tier_archive: candidates=%d archived=%d skipped=%d failed=%d "
        "bytes_moved=%d batch=%d age>=%dd",
        summary["candidates"],
        summary["archived"],
        summary["skipped"],
        summary["failed"],
        summary["total_bytes_moved"],
        batch,
        max_age_days,
    )
    return summary


@celery_app.task(
    name="tasks.maintenance.cold_tier_archive",
    queue="default",
)
def cold_tier_archive(batch: int = 100, max_age_days: int = 30) -> dict:
    """30+ gün eski article'ların raw_html'ini cold tier'a (Contabo OS) taşı.

    Beat schedule: günlük 03:30 UTC (backup 04:00'tan önce → backup'ta archived
    state tutarlı görünür).

    Settings flag: cold_tier.enabled (default False — manuel enable).
    Batch: 100 (NIM/Postgres yükünü dengelemek için ihtiyatlı; runtime tunable).

    Idempotent: archived_at NOT NULL olanlar atlanır.
    """
    return _run_async(_cold_tier_archive_async(batch, max_age_days))


# =============================================================================
# Cold tier restore (manuel, admin endpoint için)
# =============================================================================


async def _restore_one(article_id: UUID) -> dict[str, Any]:
    """Article'ın cold storage'taki raw_html'ini MinIO'ya geri getir."""
    settings = get_settings()
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "article_id": str(article_id),
        "status": "unknown",
    }

    async with factory() as db:
        article = await db.get(Article, article_id)
        if article is None:
            summary["status"] = "not_found"
            return summary
        if article.archived_at is None:
            summary["status"] = "not_archived"
            return summary
        if not article.cold_storage_key:
            summary["status"] = "no_cold_key"
            return summary

    # 1) Cold storage'tan oku (gzip)
    cold = get_cold_storage_client()
    try:
        obj = cold.get_object(Bucket=settings.s3_bucket, Key=article.cold_storage_key)
        compressed = obj["Body"].read()
        raw_bytes = gzip.decompress(compressed)
    except (ClientError, BotoCoreError) as exc:
        summary["status"] = "cold_get_failed"
        summary["error"] = str(exc)
        return summary

    # 2) MinIO'ya yaz (hot tier'a geri)
    minio = get_s3_client()
    minio_bucket = settings.minio_bucket_snapshots
    minio_key = article.raw_html_storage_path or f"raw-restored/{article_id}.html"
    if minio_key.startswith("s3://"):
        without_prefix = minio_key[5:]
        bucket_in_path, _, key_in_path = without_prefix.partition("/")
        minio_bucket = bucket_in_path
        minio_key = key_in_path

    try:
        minio.put_object(
            Bucket=minio_bucket,
            Key=minio_key,
            Body=raw_bytes,
            ContentType="text/html",
        )
    except (ClientError, BotoCoreError) as exc:
        summary["status"] = "minio_put_failed"
        summary["error"] = str(exc)
        return summary

    # 3) DB: archived_at = NULL (geri hot'a geldi)
    async with factory() as db:
        await db.execute(
            update(Article)
            .where(Article.id == article_id)
            .values(archived_at=None, cold_storage_key=None)
        )
        await db.commit()

    summary["status"] = "restored"
    summary["bytes"] = len(raw_bytes)
    return summary


@celery_app.task(
    name="tasks.maintenance.cold_tier_restore",
    queue="default",
)
def cold_tier_restore(article_id: str) -> dict:
    """Cold storage'tan single article'ı MinIO'ya geri yükle (admin manuel).

    Genelde reprocess veya investigation amaçlı. Bulk restore için batch task
    yazılabilir (gerek olunca).
    """
    return _run_async(_restore_one(UUID(article_id)))


# =============================================================================
# Body HTML drop — 24h sonrası NULL (#220 MVP-1.5 PR-5)
# =============================================================================
#
# Akış:
#   articles.body_html → 24h sonra NULL (DB row size azalır)
#   clean_text + chunks zaten saklı → RAG çalışmaya devam eder
#   raw_html_storage_path (MinIO) veya cold_storage_key (Contabo OS) korunur
#     → reprocess gerekirse extractor.py raw HTML'den body_html'i tekrar üretir
#
# Storage etki (1400 source / 1000 user senaryosunda):
#   body_html ortalama 30-60 KB/article
#   24h sonrası 28K article → 1-2 GB/gün NULL'a çekilir
#   Yıllık DB tasarruf: ~200-400 GB (unit-economics.md §2.4.1 ile uyumlu)


async def _body_html_drop_async(batch: int, max_age_hours: int) -> dict[str, Any]:
    """24+ saat eski cleaned article'ların body_html'ini NULL'a çek."""
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "batch_requested": batch,
        "max_age_hours": max_age_hours,
        "candidates": 0,
        "dropped": 0,
        "bytes_freed_estimate": 0,
    }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    async with factory() as db:
        # Settings flag check
        try:
            enabled = await settings_store.get_bool(
                db, "body_html_drop.enabled", False
            )
        except Exception:  # pragma: no cover
            enabled = False

        if not enabled:
            summary["status"] = "disabled"
            return summary

        # Aday seçim: body_html dolu, status='cleaned', updated_at eski
        # NOT: status='cleaned' filter — fetched/discovered article'ların
        # body_html'i hala extraction pipeline'ında gerekli olabilir.
        stmt = (
            select(Article.id, sa_func_octet_length_safe(Article.body_html))
            .where(
                Article.body_html.is_not(None),
                Article.status == "cleaned",
                Article.updated_at < cutoff,
            )
            .order_by(Article.updated_at.asc())
            .limit(batch)
        )
        rows = list((await db.execute(stmt)).all())

        summary["candidates"] = len(rows)
        if not rows:
            summary["status"] = "no_candidates"
            return summary

        ids = [r[0] for r in rows]
        bytes_estimate = sum((r[1] or 0) for r in rows)
        summary["bytes_freed_estimate"] = bytes_estimate

        # Toplu UPDATE: body_html → NULL (clean_text dokunulmaz)
        result = await db.execute(
            update(Article)
            .where(Article.id.in_(ids))
            .values(body_html=None)
        )
        await db.commit()
        summary["dropped"] = result.rowcount or 0

    summary["status"] = "ok"
    logger.info(
        "body_html_drop: candidates=%d dropped=%d bytes_freed=%d batch=%d age>=%dh",
        summary["candidates"],
        summary["dropped"],
        summary["bytes_freed_estimate"],
        batch,
        max_age_hours,
    )
    return summary


def sa_func_octet_length_safe(col):
    """SQLAlchemy octet_length helper — NULL-safe için func.coalesce."""
    from sqlalchemy import func as _f

    return _f.coalesce(_f.octet_length(col), 0)


@celery_app.task(
    name="tasks.maintenance.body_html_drop",
    queue="default",
)
def body_html_drop(batch: int = 500, max_age_hours: int = 24) -> dict:
    """24+ saat eski cleaned article'ların body_html'ini NULL'a çek.

    clean_text + article_chunks (embeddings) zaten saklı → RAG çalışır.
    body_html sadece reprocess senaryosunda gerek; extractor.py raw_html
    (MinIO veya cold storage) → re-extract ile yeniden üretebilir.

    Settings flag: body_html_drop.enabled (default False — manuel enable).
    Beat schedule: günlük 03:00 UTC (cold tier 03:30'dan ÖNCE — body_html
    drop edilen article cold tier candidate olabilir).

    Idempotent: body_html IS NULL olanlar atlanır (zaten DROP edilmiş).
    """
    return _run_async(_body_html_drop_async(batch, max_age_hours))
