"""Source crawl + healthcheck Celery tasks (#16).

Tasks:
    crawl_active_sources()       — Beat: her 15dk, due olan kaynakları enqueue
    healthcheck_all()            — Beat: her 6sa, source_health güncelle
    fetch_source_rss(source_id)  — RSS feed fetch + article discover
    healthcheck_source(source_id) — robots + reachability + DB update

docs/engineering/architecture.md §3.3
docs/engineering/data-model.md §3.3 (source_health)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.robots import RobotsDisallowed, fetch_robots
from app.core.rss import fetch_feed
from app.models.source import Source, SourceHealth
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


# ============================================================================
# DB session helper (Celery sync context — async DB session bridge)
# ============================================================================


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Lazy engine init. Celery worker process başına bir kez."""
    global _engine, _session_factory
    if _session_factory is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


def _run_async(coro):
    """Sync Celery task içinden async DB akışını çalıştır."""
    return asyncio.run(coro)


# ============================================================================
# Healthcheck
# ============================================================================


async def _healthcheck_source_async(source_id: UUID) -> dict:
    """Tek kaynak için robots.txt + temel reachability kontrolü.

    Sonuç DB'ye yazılır (source_health upsert), dict olarak da döner.
    """
    factory = _get_session_factory()
    result_summary: dict[str, object] = {
        "source_id": str(source_id),
        "status": "unknown",
        "error": None,
    }

    async with factory() as db:
        source = await db.get(Source, source_id)
        if source is None:
            result_summary["error"] = "source_not_found"
            return result_summary

        # 1) Robots.txt
        report = await fetch_robots(source.base_url)
        now = datetime.now(timezone.utc)

        # 2) Source kayıtları güncelle
        source.robots_txt_check_at = now
        source.robots_txt_compliant = bool(
            report.fetched and report.base_url_allowed
        )

        # Robots değiştiyse aktif kaynak deaktive
        if source.is_active and not source.robots_txt_compliant:
            source.is_active = False
            logger.warning(
                "source auto-deactivated by robots id=%s domain=%s",
                source.id,
                source.domain,
            )
            result_summary["auto_deactivated"] = True

        # 3) source_health upsert (1:1)
        sh_stmt = select(SourceHealth).where(SourceHealth.source_id == source.id)
        sh_result = await db.execute(sh_stmt)
        health = sh_result.scalar_one_or_none()

        # Status hesapla
        if not source.robots_txt_compliant:
            status = "red"
            err = report.error or "robots disallowed"
        elif report.fetched:
            status = "green"
            err = None
        else:
            status = "yellow"
            err = report.error or "unreachable"

        if health is None:
            health = SourceHealth(
                source_id=source.id,
                last_status=status,
                last_success_at=now if status == "green" else None,
                last_failure_at=now if status != "green" else None,
                failure_count_24h=0 if status == "green" else 1,
                last_error=err,
            )
            db.add(health)
        else:
            health.last_status = status
            if status == "green":
                health.last_success_at = now
                # 24h pencerede başarılı → counter reset (basit yaklaşım)
                if (
                    health.last_failure_at is None
                    or (now - health.last_failure_at) > timedelta(hours=24)
                ):
                    health.failure_count_24h = 0
            else:
                health.last_failure_at = now
                health.failure_count_24h = (health.failure_count_24h or 0) + 1
                health.last_error = err
            health.updated_at = now

        await db.commit()

        result_summary["status"] = status
        result_summary["error"] = err
        result_summary["robots_compliant"] = source.robots_txt_compliant
        result_summary["failure_count_24h"] = health.failure_count_24h
        return result_summary


async def _healthcheck_all_async() -> dict:
    """Aktif olmayan ama varlığı sürmüş kaynaklar dahil — tümünü kontrol et."""
    factory = _get_session_factory()
    async with factory() as db:
        result = await db.execute(select(Source.id))
        ids = [row[0] for row in result.fetchall()]

    summary = {"checked": 0, "green": 0, "yellow": 0, "red": 0, "errors": 0}
    for sid in ids:
        try:
            res = await _healthcheck_source_async(sid)
            summary["checked"] += 1
            status = res.get("status", "unknown")
            if status in summary:
                summary[status] += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("healthcheck error source_id=%s err=%s", sid, exc)
            summary["errors"] += 1

    return summary


@celery_app.task(name="tasks.sources.healthcheck_source", bind=True)
def healthcheck_source(self, source_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Tek kaynak için healthcheck (manuel tetik)."""
    return _run_async(_healthcheck_source_async(UUID(source_id)))


@celery_app.task(name="tasks.sources.healthcheck_all", bind=True)
def healthcheck_all(self) -> dict:  # type: ignore[no-untyped-def]
    """Beat task: tüm kaynaklar (her 6 saat)."""
    return _run_async(_healthcheck_all_async())


# ============================================================================
# Crawl scheduling
# ============================================================================


async def _due_active_sources(db: AsyncSession) -> list[Source]:
    """Crawl interval'i dolmuş aktif kaynaklar.

    last_crawled_at NULL veya last_crawled_at + interval < now() → due.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(Source)
        .where(Source.is_active.is_(True))
        .where(
            (Source.last_crawled_at.is_(None))
            | (
                Source.last_crawled_at
                + (Source.crawl_interval_minutes * timedelta(minutes=1))
                <= now
            )
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _crawl_active_async() -> dict:
    """Aktif + due kaynaklar için fetch_source_rss task'ını dispatch et."""
    factory = _get_session_factory()
    enqueued = 0
    skipped = 0
    async with factory() as db:
        sources = await _due_active_sources(db)
        for src in sources:
            if src.type != "rss":
                # MVP-1: sadece RSS — category_page Faz 2+
                skipped += 1
                continue
            try:
                # Celery dispatch — sync çağrı
                fetch_source_rss.apply_async(args=[str(src.id)])
                enqueued += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("dispatch error source=%s err=%s", src.slug, exc)

    return {"enqueued": enqueued, "skipped": skipped}


async def _fetch_source_rss_async(source_id: UUID) -> dict:
    """Source RSS feed'ini fetch + her item için article.discover task'ı.

    MVP-1'de article.discover task henüz yok; şimdilik sadece feed item count
    döndürür ve last_crawled_at güncellenir.
    """
    factory = _get_session_factory()
    async with factory() as db:
        source = await db.get(Source, source_id)
        if source is None or not source.is_active:
            return {"source_id": str(source_id), "skipped": True, "reason": "inactive"}

        # 1) Robots check (her crawl öncesi)
        try:
            from app.core.robots import enforce_or_raise

            await enforce_or_raise(source.base_url)
        except RobotsDisallowed as exc:
            logger.warning(
                "fetch_source_rss blocked by robots source=%s reason=%s",
                source.slug,
                exc.reason,
            )
            # Auto-deactivate
            source.is_active = False
            source.robots_txt_compliant = False
            source.robots_txt_check_at = datetime.now(timezone.utc)
            await db.commit()
            return {
                "source_id": str(source_id),
                "blocked": True,
                "reason": "robots_disallowed",
            }

        # 2) Feed fetch
        report = await fetch_feed(source.base_url)
        now = datetime.now(timezone.utc)
        source.last_crawled_at = now
        await db.commit()

        # 3) Her item için article_discover task'ı dispatch
        dispatched = 0
        if report.fetched and report.items:
            from app.workers.tasks.articles import article_discover

            for item in report.items:
                payload = {
                    "title": item.title,
                    "link": item.link,
                    "summary": item.summary,
                    "author": item.author,
                    "published_at_iso": (
                        item.published_at.isoformat() if item.published_at else None
                    ),
                    "image_url": item.image_url,
                    "raw_id": item.raw_id,
                }
                try:
                    article_discover.apply_async(args=[str(source.id), payload])
                    dispatched += 1
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("dispatch discover failed err=%s", exc)

        return {
            "source_id": str(source_id),
            "fetched": report.fetched,
            "status_code": report.status_code,
            "item_count": report.item_count,
            "discover_dispatched": dispatched,
            "feed_title": report.feed_title,
            "error": report.error,
        }


@celery_app.task(name="tasks.sources.crawl_active_sources", bind=True)
def crawl_active_sources(self) -> dict:  # type: ignore[no-untyped-def]
    """Beat task: aktif + due kaynaklar için fetch_source_rss enqueue."""
    return _run_async(_crawl_active_async())


@celery_app.task(
    name="tasks.sources.fetch_source_rss",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def fetch_source_rss(self, source_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Tek kaynağın RSS feed'ini fetch et."""
    return _run_async(_fetch_source_rss_async(UUID(source_id)))
