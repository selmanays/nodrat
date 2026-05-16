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
from app.core.extractor import extract_listing_cards
from app.core.http_client import fetch_text
from app.core.robots import RobotsDisallowed, fetch_robots
from app.core.rss import fetch_feed
from app.models.source import Source, SourceConfig, SourceHealth
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


# ============================================================================
# DB session helper (Celery sync context — async DB session bridge)
# ============================================================================


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Her task çağrısı için fresh engine + factory.

    NEDEN PROCESS-WIDE CACHE YOK: Celery sync worker'ı her task için
    ayrı `asyncio.run()` çağırıyor → her seferinde yeni event loop.
    Eski loop'un asyncpg connection'ları stale olur ('Event loop is
    closed' hatası, #109).

    Caller `async with open_session() as db: ...` pattern'ini kullanmalı —
    engine dispose otomatik yapılır.
    """
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        pool_recycle=300,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    factory._engine = engine  # type: ignore[attr-defined]  # dispose için
    return factory


from contextlib import asynccontextmanager


@asynccontextmanager
async def open_session():
    """Async DB session — fresh engine + auto-dispose.

    Celery + asyncpg event loop bug'a karşı koruma (#109).
    Her task için fresh engine; çıkışta dispose.
    """
    factory = _get_session_factory()
    try:
        async with factory() as session:
            yield session
    finally:
        engine = getattr(factory, "_engine", None)
        if engine is not None:
            try:
                await engine.dispose()
            except Exception:  # pragma: no cover
                pass


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


# ---- #904 per-domain extraction-confidence telemetri (R-OPS-01 gate) -------

_EXTRACT_HEALTH_RED = 0.70   # R-OPS-01 gate — altında warning alarmı + red
_EXTRACT_HEALTH_YELLOW = 0.85


async def _recompute_extract_health_async() -> dict:
    """Kaynak başına 24h extraction başarı oranı → source_health.

    rate = cleaned_24h / (cleaned_24h + quarantine_24h + discarded_24h).
    Yalsız DOWNGRADE: robots/fetch kaynaklı 'red'i EZMEZ (yalnız 'green'/
    'yellow'/'unknown' iken düşürür). rate < 0.70 → 'red' + warning DLQ
    alarmı (default admin sorgusunda görünür; #904 görünürlük ilkesi).
    """
    from sqlalchemy import func

    from app.models.article import Article
    from app.models.job import FailedJob

    factory = _get_session_factory()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    summary = {"checked": 0, "red": 0, "yellow": 0, "green": 0, "alarms": 0}

    async with factory() as db:
        src_rows = (await db.execute(select(Source.id, Source.name))).all()
        for sid, sname in src_rows:
            cleaned = (
                await db.execute(
                    select(func.count(Article.id))
                    .where(Article.source_id == sid)
                    .where(Article.status == "cleaned")
                    .where(Article.cleaned_at >= cutoff)
                )
            ).scalar() or 0
            miss = (
                await db.execute(
                    select(func.count(Article.id))
                    .where(Article.source_id == sid)
                    .where(Article.status.in_(("quarantine", "discarded")))
                    .where(Article.updated_at >= cutoff)
                )
            ).scalar() or 0
            denom = cleaned + miss
            if denom == 0:
                continue  # sinyal yok — dokunma

            rate = round(cleaned / denom, 2)
            summary["checked"] += 1

            sh = (
                await db.execute(
                    select(SourceHealth).where(SourceHealth.source_id == sid)
                )
            ).scalar_one_or_none()
            if sh is None:
                sh = SourceHealth(source_id=sid, last_status="unknown")
                db.add(sh)
            sh.avg_extract_confidence = rate
            sh.updated_at = now

            if rate < _EXTRACT_HEALTH_RED:
                summary["red"] += 1
                # robots/fetch kaynaklı red'i ezme — yalnız downgrade.
                if sh.last_status in ("green", "yellow", "unknown"):
                    sh.last_status = "red"
                # Warning DLQ alarmı (görünür) — tekrar spam'ı önle: aynı
                # kaynak için 24h içinde açık extract_health alarmı yoksa.
                existing = (
                    await db.execute(
                        select(func.count(FailedJob.id))
                        .where(FailedJob.source_id == sid)
                        .where(FailedJob.job_type == "source.extract_health")
                        .where(FailedJob.resolved_at.is_(None))
                        .where(FailedJob.created_at >= cutoff)
                    )
                ).scalar() or 0
                if existing == 0:
                    db.add(
                        FailedJob(
                            job_type="source.extract_health",
                            payload_json={
                                "source_id": str(sid),
                                "rate": rate,
                                "cleaned_24h": cleaned,
                                "miss_24h": miss,
                            },
                            source_id=sid,
                            article_url=None,
                            error_message=(
                                f"extract-confidence düşük: {sname} "
                                f"rate={rate:.2f} (<{_EXTRACT_HEALTH_RED}) "
                                f"— cleaned={cleaned} miss={miss} / 24h "
                                f"(R-OPS-01 gate)"
                            ),
                            last_attempt_at=now,
                            severity="warning",  # GÖRÜNÜR (auto-resolve YOK)
                        )
                    )
                    summary["alarms"] += 1
            elif rate < _EXTRACT_HEALTH_YELLOW:
                summary["yellow"] += 1
                if sh.last_status in ("green", "unknown"):
                    sh.last_status = "yellow"
            else:
                summary["green"] += 1

        await db.commit()

    logger.info(
        "recompute_extract_health: checked=%d red=%d yellow=%d green=%d alarms=%d",
        summary["checked"],
        summary["red"],
        summary["yellow"],
        summary["green"],
        summary["alarms"],
    )
    return summary


@celery_app.task(name="tasks.sources.recompute_extract_health", bind=True)
def recompute_extract_health(self) -> dict:  # type: ignore[no-untyped-def]
    """#904 beat (6 saatte bir): per-domain extract-confidence + alarm."""
    return _run_async(_recompute_extract_health_async())


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
    """Aktif + due kaynaklar için fetch_source_rss veya
    fetch_source_category_page task'ını dispatch et (#71)."""
    factory = _get_session_factory()
    enqueued_rss = 0
    enqueued_category = 0
    skipped = 0
    async with factory() as db:
        sources = await _due_active_sources(db)
        for src in sources:
            try:
                if src.type == "rss":
                    fetch_source_rss.apply_async(args=[str(src.id)])
                    enqueued_rss += 1
                elif src.type == "category_page":
                    fetch_source_category_page.apply_async(args=[str(src.id)])
                    enqueued_category += 1
                else:
                    # 'manual' veya bilinmeyen tip — atla
                    skipped += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("dispatch error source=%s err=%s", src.slug, exc)

    return {
        "enqueued_rss": enqueued_rss,
        "enqueued_category": enqueued_category,
        "skipped": skipped,
    }


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

        # 2) Feed fetch — Conditional GET (#565): önceki ETag/Last-Modified
        # varsa header'lara gider; sunucu 304 dönerse bandwidth + dispatch
        # tasarrufu sağlanır.
        report = await fetch_feed(
            source.base_url,
            etag=source.etag,
            last_modified=source.last_modified,
        )
        now = datetime.now(timezone.utc)
        source.last_crawled_at = now

        # 2a) 304 Not Modified — feed değişmedi, dispatch yok, sayaç artır.
        if report.not_modified:
            source.consecutive_unchanged = (source.consecutive_unchanged or 0) + 1
            await db.commit()
            await _compute_and_persist_tier(db, source, now=now)
            return {
                "source_id": str(source_id),
                "fetched": True,
                "status_code": 304,
                "not_modified": True,
                "item_count": 0,
                "discover_dispatched": 0,
                "consecutive_unchanged": source.consecutive_unchanged,
                "polling_tier": source.polling_tier,
                "would_be_tier": source.would_be_tier,
            }

        # 2b) 200 OK — sunucudan yeni ETag/Last-Modified geldiyse persist et
        # ve sayacı sıfırla (içerik akışı var).
        if report.fetched:
            if report.etag is not None:
                source.etag = report.etag
            if report.last_modified is not None:
                source.last_modified = report.last_modified
            source.consecutive_unchanged = 0

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

        # 4) Adaptive tier shadow mode hesabı (#578).
        # Discover dispatch sonrası çağrılır — yeni article'lar henüz INSERT
        # edilmemiş olabilir (article_discover task ayrı queue'da), ama bir
        # sonraki crawl'da yansır. Kasıtlı: bu fetch'in tier hesabı bu cycle'da
        # zaten DB'ye yazılmış geçmiş veriye bakıyor.
        if report.fetched:
            await _compute_and_persist_tier(db, source, now=now)

        return {
            "source_id": str(source_id),
            "fetched": report.fetched,
            "status_code": report.status_code,
            "item_count": report.item_count,
            "discover_dispatched": dispatched,
            "feed_title": report.feed_title,
            "error": report.error,
            "polling_tier": source.polling_tier,
            "would_be_tier": source.would_be_tier,
        }


async def _compute_and_persist_tier(
    db: AsyncSession,
    source: Source,
    *,
    now: datetime,
) -> None:
    """Tier hesabını yapar + Source row'unu shadow/apply mode'a göre günceller (#578).

    `app_settings.rss.tier_shadow_mode` (default true): would_be_tier + metadata
    yazılır, polling_tier DOKUNULMAZ.
    `tier_apply_enabled=true` + `shadow_mode=false` (Faz 3): polling_tier =
    would_be_tier + tier_changed_at update edilir.

    Hata olursa logla + sessizce devam et — tier hesabı kritik path değil,
    fetch task'ının başarısını bozma.
    """
    from app.core.polling_tier import compute_tier
    from app.core.settings_store import settings_store

    try:
        computation = await compute_tier(source, db, now=now)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "compute_tier failed source=%s err=%s", source.slug, exc
        )
        return

    source.would_be_tier = computation.tier
    source.tier_metadata = computation.metadata

    # Shadow mode flag'lerini SettingsStore'dan oku — runtime tunable
    try:
        shadow_mode = await settings_store.get(
            db, "rss.tier_shadow_mode", default=True
        )
        apply_enabled = await settings_store.get(
            db, "rss.tier_apply_enabled", default=False
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "settings_store fail in tier persist source=%s err=%s; "
            "shadow mode'a fallback",
            source.slug,
            exc,
        )
        shadow_mode = True
        apply_enabled = False

    # Apply mode: polling_tier'ı transition kuralları geçtiyse senkronize et.
    if not shadow_mode and apply_enabled and computation.transitioned:
        old_tier = source.polling_tier
        source.polling_tier = computation.tier
        source.tier_changed_at = now
        logger.info(
            "tier transition source=%s old=%s new=%s metadata=%s",
            source.slug,
            old_tier,
            computation.tier,
            computation.metadata,
        )

    await db.commit()


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


# ============================================================================
# Category page fetch (#71)
# ============================================================================


def _build_paginated_urls(
    base_url: str,
    pagination_config: dict | None,
) -> list[str]:
    """Pagination config'e göre crawl edilecek URL listesi döner.

    Supported types:
        - 'none' veya None → [base_url]
        - 'page_param'     → [base_url?page=1, base_url?page=2, ...]
        - 'next_link'      → runtime'da DOM'dan ileride çıkarılır, ilk URL [base_url]

    pagination_config örnek:
        {"type": "page_param", "param_name": "page", "start": 1, "max_pages": 5}
        {"type": "next_link", "next_selector": "a.next", "max_pages": 5}
        {"type": "none"}
    """
    if not pagination_config:
        return [base_url]

    ptype = pagination_config.get("type", "none")
    if ptype == "none":
        return [base_url]

    if ptype == "page_param":
        param = pagination_config.get("param_name", "page")
        start = int(pagination_config.get("start", 1))
        max_pages = int(pagination_config.get("max_pages", 5))
        urls: list[str] = []
        from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

        for i in range(start, start + max_pages):
            parsed = urlparse(base_url)
            qs = dict(parse_qsl(parsed.query))
            qs[param] = str(i)
            urls.append(urlunparse(parsed._replace(query=urlencode(qs))))
        return urls

    if ptype == "next_link":
        # next_link case'i async crawl loop'unda DOM'dan çıkarılır;
        # burada sadece başlangıç URL'i döner, max_pages caller tarafında.
        return [base_url]

    # Bilinmeyen → fallback single page
    return [base_url]


async def _follow_next_link(
    html: str,
    current_url: str,
    next_selector: str,
) -> str | None:
    """next_link pagination — DOM'dan 'sonraki sayfa' linkini bul."""
    from urllib.parse import urljoin
    from bs4 import BeautifulSoup, Tag

    try:
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(next_selector)
        if not isinstance(node, Tag):
            return None
        href = node.get("href")
        if isinstance(href, str) and href.strip():
            return urljoin(current_url, href.strip())
    except Exception as exc:  # pragma: no cover
        logger.warning("follow_next_link parse err=%s", exc)
    return None


def _parse_card_date(value: str | None) -> datetime | None:
    """Card date metnini ISO datetime'a çevirmeye çalış.

    Sadece en yaygın patternler. Başarısız olursa None — article_discover
    daha sonra detail fetch'inde proper parse yapacak.
    """
    if not value:
        return None
    try:
        # ISO 8601 (yyyy-mm-ddThh:mm:ss veya datetime attr)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


async def _fetch_source_category_page_async(source_id: UUID) -> dict:
    """Source'un kategori sayfasını fetch et + her card için article_discover dispatch.

    Pattern paralel _fetch_source_rss_async ile:
      1. Robots check
      2. Page(s) fetch (pagination loop)
      3. extract_listing_cards
      4. article_discover dispatch
    """
    factory = _get_session_factory()
    async with factory() as db:
        source = await db.get(Source, source_id)
        if source is None or not source.is_active:
            return {"source_id": str(source_id), "skipped": True, "reason": "inactive"}

        # 1) Robots check
        try:
            from app.core.robots import enforce_or_raise

            await enforce_or_raise(source.base_url)
        except RobotsDisallowed as exc:
            logger.warning(
                "fetch_category_page blocked by robots source=%s reason=%s",
                source.slug,
                exc.reason,
            )
            source.is_active = False
            source.robots_txt_compliant = False
            source.robots_txt_check_at = datetime.now(timezone.utc)
            await db.commit()
            return {
                "source_id": str(source_id),
                "blocked": True,
                "reason": "robots_disallowed",
            }

        # 2) Aktif config'i çek (selectors + pagination)
        config_q = await db.execute(
            select(SourceConfig)
            .where(SourceConfig.source_id == source_id, SourceConfig.is_active.is_(True))
            .limit(1)
        )
        active_config = config_q.scalar_one_or_none()
        if active_config is None or not isinstance(active_config.config_json, dict):
            return {
                "source_id": str(source_id),
                "skipped": True,
                "reason": "no_active_config",
            }
        cfg = active_config.config_json
        # #71 — list_selectors yeni format; selectors backward compat
        selectors = cfg.get("list_selectors") or cfg.get("selectors") or {}
        pagination = cfg.get("pagination") or {"type": "none"}

        if not isinstance(selectors, dict) or "card" not in selectors:
            return {
                "source_id": str(source_id),
                "skipped": True,
                "reason": "selectors.card_missing",
            }

        # 3) Pagination loop — page_param URL listesi veya next_link runtime
        ptype = pagination.get("type", "none")
        max_pages = int(pagination.get("max_pages", 5))
        seen_urls: set[str] = set()
        total_cards = 0
        dispatched = 0

        if ptype == "next_link":
            next_selector = pagination.get("next_selector") or ""
            current_url: str | None = source.base_url
            page_idx = 0
            while current_url and page_idx < max_pages and current_url not in seen_urls:
                seen_urls.add(current_url)
                page_idx += 1
                status, body, _ = await fetch_text(current_url, timeout=20.0)
                if not body or status >= 400:
                    break
                cards, _warnings = extract_listing_cards(
                    body, url=current_url, selectors=selectors, max_cards=50
                )
                total_cards += len(cards)
                dispatched += await _dispatch_cards(source.id, cards)
                # Bir sonraki sayfa
                if next_selector:
                    next_url = await _follow_next_link(body, current_url, next_selector)
                    current_url = next_url
                else:
                    break
        else:
            urls = _build_paginated_urls(source.base_url, pagination)[:max_pages]
            for url in urls:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                status, body, _ = await fetch_text(url, timeout=20.0)
                if not body or status >= 400:
                    continue
                cards, _warnings = extract_listing_cards(
                    body, url=url, selectors=selectors, max_cards=50
                )
                total_cards += len(cards)
                dispatched += await _dispatch_cards(source.id, cards)

        now = datetime.now(timezone.utc)
        source.last_crawled_at = now
        await db.commit()

        return {
            "source_id": str(source_id),
            "pagination_type": ptype,
            "pages_crawled": len(seen_urls),
            "card_count": total_cards,
            "discover_dispatched": dispatched,
        }


async def _dispatch_cards(source_id: UUID, cards: list) -> int:
    """Card listesini article_discover task'ına dispatch et."""
    if not cards:
        return 0
    from app.workers.tasks.articles import article_discover

    dispatched = 0
    for card in cards:
        if not card.link or not card.title:
            continue  # link + title zorunlu
        published = _parse_card_date(card.date)
        payload = {
            "title": card.title,
            "link": card.link,
            "summary": "",
            "author": None,
            "published_at_iso": published.isoformat() if published else None,
            "image_url": card.image_url,
            "raw_id": None,  # category_page'de raw_id yok
        }
        try:
            article_discover.apply_async(args=[str(source_id), payload])
            dispatched += 1
        except Exception as exc:  # pragma: no cover
            logger.exception("category dispatch failed err=%s", exc)
    return dispatched


@celery_app.task(
    name="tasks.sources.fetch_source_category_page",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def fetch_source_category_page(self, source_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Tek kaynağın kategori sayfasını fetch et (pagination dahil)."""
    return _run_async(_fetch_source_category_page_async(UUID(source_id)))
