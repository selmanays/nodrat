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

import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sources.models import Source, SourceConfig, SourceHealth
from app.shared.crawl.robots import can_fetch, fetch_robots
from app.shared.crawl.rss import fetch_feed
from app.shared.crawl.sitemap import SitemapEntry, parse_sitemap
from app.shared.extraction import extract_listing_cards
from app.shared.http.client import fetch_text
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _record_auto_deactivation(
    db: AsyncSession,
    *,
    source: Source,
    now: datetime,
    reason: str,
    detail: str,
) -> None:
    """Kaynak otomatik deaktive edildiğinde admin-görünür kalıcı iz bırakır (#1498).

    ``admin_audit_log.actor_id`` NOT NULL (users FK) olduğu için sistem-aktörlü
    olay oraya yazılamaz → ``FailedJob`` (DLQ / ops gözlemlenebilirlik, source_id
    nullable, actor gerektirmez, admin panelde görünür) kullanılır. Aynı kaynak
    için 24h içinde açık kayıt varsa tekrar yazılmaz (alarm spam'ı önleme).
    """
    from sqlalchemy import func

    from app.models.job import FailedJob

    cutoff = now - timedelta(hours=24)
    existing = (
        await db.execute(
            select(func.count(FailedJob.id))
            .where(FailedJob.source_id == source.id)
            .where(FailedJob.job_type == "source.auto_deactivated")
            .where(FailedJob.resolved_at.is_(None))
            .where(FailedJob.created_at >= cutoff)
        )
    ).scalar() or 0
    if existing:
        return
    db.add(
        FailedJob(
            job_type="source.auto_deactivated",
            payload_json={
                "source_id": str(source.id),
                "slug": source.slug,
                "domain": source.domain,
                "reason": reason,
                "detail": detail,
            },
            source_id=source.id,
            article_url=None,
            error_message=(
                f"Kaynak otomatik deaktive edildi: {source.name} "
                f"({source.domain}) — {reason}: {detail}"
            ),
            last_attempt_at=now,
            severity="warning",  # GÖRÜNÜR (auto-resolve YOK)
        )
    )


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
        now = datetime.now(UTC)
        source.robots_txt_check_at = now

        # 2) Karar — GEÇİCİ fetch hatası vs GERÇEK disallow (#1498).
        # report.fetched=False → robots.txt o an çekilemedi (network/timeout/
        # 5xx/4xx-forbidden). Bu GEÇİCİ bir durumdur ve daha önce doğrulanmış
        # canlı bir kaynağı kapatmak için yeterli DEĞİL — aksi halde anlık ağ
        # takılması kaynağı sessizce öldürür. Yalnız KESİN disallow
        # (fetched=True ama base_url_allowed=False) deactivate eder.
        if report.fetched:
            source.robots_txt_compliant = report.base_url_allowed
            if report.base_url_allowed:
                status = "green"
                err = None
            else:
                status = "red"
                err = report.error or "robots disallowed"
                if source.is_active:
                    source.is_active = False
                    result_summary["auto_deactivated"] = True
                    logger.warning(
                        "source auto-deactivated by robots DISALLOW id=%s domain=%s",
                        source.id,
                        source.domain,
                    )
                    await _record_auto_deactivation(
                        db,
                        source=source,
                        now=now,
                        reason="robots_disallow",
                        detail=f"robots.txt base_url disallow (status={report.status_code})",
                    )
        else:
            # GEÇİCİ hata: is_active + robots_txt_compliant DOKUNULMAZ
            # (önceki iyi değer korunur), yalnız sağlık 'yellow' işaretlenir.
            status = "yellow"
            err = report.error or "robots fetch failed (transient)"
            result_summary["robots_transient_error"] = True

        # 3) source_health upsert (1:1)
        sh_stmt = select(SourceHealth).where(SourceHealth.source_id == source.id)
        sh_result = await db.execute(sh_stmt)
        health = sh_result.scalar_one_or_none()

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
                if health.last_failure_at is None or (now - health.last_failure_at) > timedelta(
                    hours=24
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

# #904 — runtime-tunable: admin `scraping.extract_health_{red,yellow}_threshold`.
# Aşağıdakiler yalnız fallback/seed default'u (settings_store erişilemezse).
_EXTRACT_HEALTH_RED = 0.70  # R-OPS-01 gate — altında warning alarmı + red
_EXTRACT_HEALTH_YELLOW = 0.85


def _is_low_volume(denom: int, min_sample: int, would_be_tier: str | None) -> bool:
    """Teslimat 1 — bu kaynağın 24h oranı istatistiksel olarak güvenilmez mi?

    True ise red/alarm BASTIRILIR (yanlış panik fix'i). İki bağımsız sinyal:
      - denom < min_sample: pencerede yargılamaya yetecek makale yok.
      - would_be_tier ∈ {cold, hibernate}: #578 shadow frekans sinyali bu
        kaynağı 'sessiz/düşük-hacim' işaretliyor (zaten her fetch'te yazılır).
    would_be_tier NULL ise yalnız örneklem karar verir (güvenli varsayılan).
    """
    if denom < min_sample:
        return True
    return would_be_tier in ("cold", "hibernate")


async def _recompute_extract_health_async() -> dict:
    """Kaynak başına 24h extraction başarı oranı → source_health.

    rate = cleaned_24h / (cleaned_24h + quarantine_24h + discarded_24h).
    Yalnız DOWNGRADE: robots/fetch kaynaklı 'red'i EZMEZ (yalnız 'green'/
    'yellow'/'unknown' iken düşürür). rate < red_th → 'red' + warning DLQ
    alarmı (#904 görünürlük ilkesi).

    Teslimat 1 — düşük-hacim gate'i: `_is_low_volume` True ise (küçük
    örneklem VEYA frekans sinyali 'cold'/'hibernate') red+alarm BASTIRILIR;
    confidence yine yazılır, yellow (alarmsız) ve aktif kaynaklar etkilenmez.
    """
    from sqlalchemy import func, text

    from app.models.job import FailedJob

    # T8-12a: Article ORM import KALDIRILDI (sources → articles import-linter
    # `sources/ must not import any other domain` ihlalini, T8-12b article →
    # modules/articles relocation öncesi önler). Article'a yalnız count query
    # için ihtiyaç vardı → raw SQL (tablo adı `articles` sabit; davranış AYNEN).
    from app.shared.runtime_config.settings_store import settings_store

    factory = _get_session_factory()
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=24)
    summary = {
        "checked": 0,
        "red": 0,
        "yellow": 0,
        "green": 0,
        "alarms": 0,
        "low_volume_skipped": 0,
    }

    async with factory() as db:
        # #904 — runtime-tunable R-OPS-01 gate (fallback: modül sabitleri).
        try:
            red_th = await settings_store.get_float(
                db, "scraping.extract_health_red_threshold", _EXTRACT_HEALTH_RED
            )
            yellow_th = await settings_store.get_float(
                db,
                "scraping.extract_health_yellow_threshold",
                _EXTRACT_HEALTH_YELLOW,
            )
            # Teslimat 1 — düşük-hacim yanlış-alarm eşiği (frekans sinyaline bağlı).
            min_sample = await settings_store.get_int(db, "scraping.extract_health_min_sample", 8)
        except Exception:  # pragma: no cover — settings_store erişilemezse sabit
            red_th, yellow_th, min_sample = (
                _EXTRACT_HEALTH_RED,
                _EXTRACT_HEALTH_YELLOW,
                8,
            )

        # Frekans sinyali (#578 shadow tier) gate girdisi: would_be_tier +
        # tier_metadata zaten her fetch'te yazılıyor — sıfır yeni altyapı.
        src_rows = (
            await db.execute(
                select(
                    Source.id,
                    Source.name,
                    Source.would_be_tier,
                )
            )
        ).all()
        for sid, sname, wbt in src_rows:
            # T8-12a: raw SQL (Article ORM decouple — sources→articles önlenir).
            # Tablo/kolon adları sabit; count davranışı ORM ile birebir aynı.
            cleaned = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM articles "
                        "WHERE source_id = :sid AND status = 'cleaned' "
                        "AND cleaned_at >= :cutoff"
                    ),
                    {"sid": sid, "cutoff": cutoff},
                )
            ).scalar() or 0
            miss = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM articles "
                        "WHERE source_id = :sid "
                        "AND status IN ('quarantine', 'discarded') "
                        "AND updated_at >= :cutoff"
                    ),
                    {"sid": sid, "cutoff": cutoff},
                )
            ).scalar() or 0
            denom = cleaned + miss
            if denom == 0:
                continue  # sinyal yok — dokunma

            rate = round(cleaned / denom, 2)
            summary["checked"] += 1

            sh = (
                await db.execute(select(SourceHealth).where(SourceHealth.source_id == sid))
            ).scalar_one_or_none()
            if sh is None:
                sh = SourceHealth(source_id=sid, last_status="unknown")
                db.add(sh)
            sh.avg_extract_confidence = rate  # telemetri DAİMA yazılır
            sh.updated_at = now

            # Teslimat 1 — düşük-hacim gate'i (frekans sinyaline bağlı):
            # 24h örneklem küçükse VEYA shadow tier kaynağı 'cold'/'hibernate'
            # (sessiz) işaretliyorsa oran istatistiksel gürültüdür → red/alarm
            # BASTIRILIR (Arkitera/IGN tipi boş panik fix'i). would_be_tier
            # NULL ise yalnız örneklem karar verir (güvenli). Aktif/yoğun
            # kaynakta davranış DEĞİŞMEZ; yellow (alarmsız) da dokunulmaz.
            low_volume = _is_low_volume(denom, min_sample, wbt)

            if low_volume and rate < red_th:
                summary["low_volume_skipped"] += 1
                # Yeni red/alarm üretme + ESKİ spurious durumu EMEKLİYE AYIR:
                # bu kaynağın açık `source.extract_health` alarmlarını resolve
                # et; varsa (= red bu telemetriden gelmiş, robots/fetch DEĞİL)
                # last_status 'red' → 'unknown' (nötr; hacim dönünce yeniden
                # değerlendirilir, sahte 'green' YAPMA). Yeşil Gazete tipi
                # robots/fetch-red'in extract_health alarmı YOK → dokunulmaz.
                res = await db.execute(
                    update(FailedJob)
                    .where(FailedJob.source_id == sid)
                    .where(FailedJob.job_type == "source.extract_health")
                    .where(FailedJob.resolved_at.is_(None))
                    .values(
                        resolved_at=now,
                        resolution_note=(
                            "Teslimat 1 — düşük-hacim, yetersiz veri; "
                            "spurious extract_health alarmı auto-resolve"
                        ),
                    )
                )
                if (res.rowcount or 0) > 0 and sh.last_status == "red":
                    sh.last_status = "unknown"
                logger.info(
                    "extract_health düşük-hacim BASTIRILDI: %s rate=%.2f "
                    "denom=%d (<%d) wbt=%s — red/alarm YOK, %d eski alarm resolve",
                    sname,
                    rate,
                    denom,
                    min_sample,
                    wbt,
                    res.rowcount or 0,
                )
            elif rate < red_th:
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
                                f"rate={rate:.2f} (<{red_th:.2f}) "
                                f"— cleaned={cleaned} miss={miss} / 24h "
                                f"(R-OPS-01 gate)"
                            ),
                            last_attempt_at=now,
                            severity="warning",  # GÖRÜNÜR (auto-resolve YOK)
                        )
                    )
                    summary["alarms"] += 1
            elif rate < yellow_th:
                summary["yellow"] += 1
                if sh.last_status in ("green", "unknown"):
                    sh.last_status = "yellow"
            else:
                summary["green"] += 1

        await db.commit()

    logger.info(
        "recompute_extract_health: checked=%d red=%d yellow=%d green=%d "
        "alarms=%d low_volume_skipped=%d",
        summary["checked"],
        summary["red"],
        summary["yellow"],
        summary["green"],
        summary["alarms"],
        summary["low_volume_skipped"],
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
    now = datetime.now(UTC)
    stmt = (
        select(Source)
        .where(Source.is_active.is_(True))
        .where(
            (Source.last_crawled_at.is_(None))
            | (
                Source.last_crawled_at + (Source.crawl_interval_minutes * timedelta(minutes=1))
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

        # 1) Robots check (her crawl öncesi) — GEÇİCİ fetch hatası ile GERÇEK
        # disallow ayrımı (#1498). Geçici hata (robots.txt çekilemedi) canlı
        # kaynağı KAPATMAZ; yalnız bu crawl turu güvenli şekilde atlanır.
        allowed, robots_report = await can_fetch(source.base_url)
        now_robots = datetime.now(UTC)
        source.robots_txt_check_at = now_robots
        if not allowed:
            if not robots_report.fetched:
                logger.warning(
                    "fetch_source_rss robots fetch failed (transient) source=%s err=%s",
                    source.slug,
                    robots_report.error,
                )
                await db.commit()
                return {
                    "source_id": str(source_id),
                    "skipped": True,
                    "reason": "robots_fetch_transient",
                }
            # GERÇEK disallow → deactivate + görünür iz.
            logger.warning(
                "fetch_source_rss blocked by robots DISALLOW source=%s",
                source.slug,
            )
            source.is_active = False
            source.robots_txt_compliant = False
            await _record_auto_deactivation(
                db,
                source=source,
                now=now_robots,
                reason="robots_disallow",
                detail=f"crawl-time robots disallow (status={robots_report.status_code})",
            )
            await db.commit()
            return {
                "source_id": str(source_id),
                "blocked": True,
                "reason": "robots_disallowed",
            }
        source.robots_txt_compliant = True

        # 2) Feed fetch — Conditional GET (#565): önceki ETag/Last-Modified
        # varsa header'lara gider; sunucu 304 dönerse bandwidth + dispatch
        # tasarrufu sağlanır.
        report = await fetch_feed(
            source.base_url,
            etag=source.etag,
            last_modified=source.last_modified,
        )
        now = datetime.now(UTC)
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
        # PR 2a (#1085 T6): string-bound send_task — sources Python seviyesinde
        # articles modülüne bağlı değil; muafiyetsiz import-linter pass.
        dispatched = 0
        if report.fetched and report.items:
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
                    celery_app.send_task(
                        "tasks.articles.discover",
                        args=[str(source.id), payload],
                    )
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
    from app.modules.sources.services.polling_tier import compute_tier
    from app.shared.runtime_config.settings_store import settings_store

    try:
        computation = await compute_tier(source, db, now=now)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("compute_tier failed source=%s err=%s", source.slug, exc)
        return

    source.would_be_tier = computation.tier
    source.tier_metadata = computation.metadata

    # Shadow mode flag'lerini SettingsStore'dan oku — runtime tunable
    try:
        shadow_mode = await settings_store.get(db, "rss.tier_shadow_mode", default=True)
        apply_enabled = await settings_store.get(db, "rss.tier_apply_enabled", default=False)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "settings_store fail in tier persist source=%s err=%s; shadow mode'a fallback",
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
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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

        # 1) Robots check — GEÇİCİ fetch hatası ile GERÇEK disallow ayrımı
        # (#1498). Geçici hata canlı kaynağı KAPATMAZ; tur güvenle atlanır.
        allowed, robots_report = await can_fetch(source.base_url)
        now_robots = datetime.now(UTC)
        source.robots_txt_check_at = now_robots
        if not allowed:
            if not robots_report.fetched:
                logger.warning(
                    "fetch_category_page robots fetch failed (transient) source=%s err=%s",
                    source.slug,
                    robots_report.error,
                )
                await db.commit()
                return {
                    "source_id": str(source_id),
                    "skipped": True,
                    "reason": "robots_fetch_transient",
                }
            logger.warning(
                "fetch_category_page blocked by robots DISALLOW source=%s",
                source.slug,
            )
            source.is_active = False
            source.robots_txt_compliant = False
            await _record_auto_deactivation(
                db,
                source=source,
                now=now_robots,
                reason="robots_disallow",
                detail=f"crawl-time robots disallow (status={robots_report.status_code})",
            )
            await db.commit()
            return {
                "source_id": str(source_id),
                "blocked": True,
                "reason": "robots_disallowed",
            }
        source.robots_txt_compliant = True

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
        # #1527 — sitemap-ingestion mode: config'de sitemap_url varsa JS-render'lı
        # liste sayfası yerine sitemap'ten makale URL'leri keşfedilir (card-scraping
        # bypass). robots zaten yukarıda kontrol edildi (source.robots_txt_compliant).
        if isinstance(cfg, dict) and cfg.get("sitemap_url"):
            return await _discover_from_sitemap(db, source, cfg)
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

        now = datetime.now(UTC)
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
    """Card listesini article_discover task'ına dispatch et.

    PR 2a (#1085 T6): string-bound send_task — Python import yok.
    """
    if not cards:
        return 0

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
            celery_app.send_task(
                "tasks.articles.discover",
                args=[str(source_id), payload],
            )
            dispatched += 1
        except Exception as exc:  # pragma: no cover
            logger.exception("category dispatch failed err=%s", exc)
    return dispatched


def _provisional_title_from_url(loc: str) -> str:
    """URL slug'ından geçici başlık türet (#1527).

    Sitemap <loc> başlık taşımaz; `discover` ise title zorunlu ister. Burada
    slug'dan geçici bir başlık üretilir — `article_fetch_detail` sayfayı çekince
    `article.title = cleaned.title or article.title` ile gerçek başlık yazılır.
    """
    path = urlparse(loc).path.rstrip("/")
    seg = path.rsplit("/", 1)[-1] if path else ""
    # Trailing makale-id'sini at: T24 ",132" + ANKA "-d7e7279d" (8-hex). #1640.
    # {8}+hex precise: gerçek son-kelimeler (farklı uzunluk/charset) kırpılmaz.
    seg = re.sub(r"(?:,\d+|-[0-9a-f]{8})$", "", seg, flags=re.IGNORECASE)
    seg = seg.replace("-", " ").replace("_", " ").strip()
    return seg[:200]


async def _discover_from_sitemap(db: AsyncSession, source: Source, cfg: dict) -> dict:
    """Sitemap'ten makale URL'lerini keşfet + article.discover dispatch (#1527).

    Config (config_json):
      sitemap_url        zorunlu — modu tetikler
      subsitemap_pattern opsiyonel regex — index ise alt-sitemap loc filtresi
                         (örn. ``sitemap-\\d{8}`` → tarih-isimli)
      subsitemap_latest  index ise açılacak en yeni alt-sitemap sayısı (default 1)
      url_include        opsiyonel substring — yalnız bu deseni içeren loc'lar
      max_age_days       opsiyonel — lastmod bu kadar günden eskiyse atla
      max_items          dispatch cap (default 50)

    Idempotent: discover canonical-URL dedup yapar → tekrar no-op.
    """
    sitemap_url = str(cfg.get("sitemap_url") or "").strip()
    if not sitemap_url:
        return {"source_id": str(source.id), "skipped": True, "reason": "no_sitemap_url"}

    status, body, _ = await fetch_text(sitemap_url, timeout=20.0)
    if not body or status >= 400:
        await db.commit()
        return {
            "source_id": str(source.id),
            "skipped": True,
            "reason": f"sitemap_fetch_failed:{status}",
        }

    entries, is_index = parse_sitemap(body)

    if is_index:
        sub_pattern = cfg.get("subsitemap_pattern")
        subs = entries
        if sub_pattern:
            try:
                rx = re.compile(str(sub_pattern))
                subs = [e for e in entries if rx.search(e.loc)]
            except re.error:
                logger.warning("invalid subsitemap_pattern source=%s", source.slug)
        # En yeni: lastmod varsa ona, yoksa loc string'e göre (tarih-isimli dosya
        # adları lexicographic = kronolojik sıralanır).
        subs.sort(
            key=lambda e: (e.lastmod or datetime.min.replace(tzinfo=UTC), e.loc),
            reverse=True,
        )
        latest = max(1, int(cfg.get("subsitemap_latest", 1) or 1))
        url_entries: list[SitemapEntry] = []
        for sub in subs[:latest]:
            s2, b2, _ = await fetch_text(sub.loc, timeout=20.0)
            if b2 and s2 < 400:
                sub_entries, sub_is_index = parse_sitemap(b2)
                if not sub_is_index:
                    url_entries.extend(sub_entries)
        entries = url_entries

    inc = str(cfg.get("url_include") or "").strip()
    if inc:
        entries = [e for e in entries if inc in e.loc]

    max_age = cfg.get("max_age_days")
    if max_age:
        try:
            cutoff = datetime.now(UTC) - timedelta(days=float(max_age))
            entries = [e for e in entries if e.lastmod is None or e.lastmod >= cutoff]
        except (TypeError, ValueError):
            pass

    entries.sort(key=lambda e: e.lastmod or datetime.min.replace(tzinfo=UTC), reverse=True)
    max_items = max(1, int(cfg.get("max_items", 50) or 50))
    entries = entries[:max_items]

    dispatched = 0
    for entry in entries:
        title = _provisional_title_from_url(entry.loc)
        if not title:
            continue
        payload = {
            "title": title,
            "link": entry.loc,
            "summary": "",
            "author": None,
            "published_at_iso": entry.lastmod.isoformat() if entry.lastmod else None,
            "image_url": None,
            "raw_id": None,
        }
        try:
            celery_app.send_task("tasks.articles.discover", args=[str(source.id), payload])
            dispatched += 1
        except Exception as exc:  # pragma: no cover
            logger.exception("sitemap dispatch failed source=%s err=%s", source.slug, exc)

    await db.commit()
    logger.info(
        "sitemap discover source=%s entries=%d dispatched=%d",
        source.slug,
        len(entries),
        dispatched,
    )
    return {
        "source_id": str(source.id),
        "mode": "sitemap",
        "total_entries": len(entries),
        "dispatched": dispatched,
    }


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


# ============================================================================
# Recovery — sessizce pasife düşmüş kaynakları güvenli reaktive et (#1498)
# ============================================================================


async def _reactivate_dormant_sources_async(*, dry_run: bool) -> dict:
    """Geçici robots hatası nedeniyle pasife düşmüş kaynakları robots re-check
    ile güvenli reaktive eder. Bkz. ``reactivate_dormant_sources``.
    """
    from app.models.job import FailedJob

    factory = _get_session_factory()
    summary: dict[str, object] = {
        "evaluated": 0,
        "reactivated": [],
        "skipped_disallow": [],
        "skipped_transient": [],
        "skipped_no_tos": [],
        "dry_run": dry_run,
    }

    # Network I/O sırasında DB session tutmamak için önce alanları topla.
    async with factory() as db:
        result = await db.execute(select(Source).where(Source.is_active.is_(False)))
        rows = [
            (s.id, s.slug, s.base_url, bool(s.tos_acknowledged)) for s in result.scalars().all()
        ]

    for sid, slug, base_url, tos_ok in rows:
        # tos_acknowledged olmayan kaynaklar hiç onboard edilmemiş → atla.
        if not tos_ok:
            summary["skipped_no_tos"].append(slug)  # type: ignore[union-attr]
            continue

        summary["evaluated"] += 1  # type: ignore[operator]
        allowed, report = await can_fetch(base_url)
        now = datetime.now(UTC)

        if not report.fetched:
            # Robots hâlâ çekilemiyor → güvenli tarafta kal, açma.
            summary["skipped_transient"].append(slug)  # type: ignore[union-attr]
            continue

        if not allowed:
            # GERÇEK disallow → kalıcı, açma; bayrağı doğru tut.
            summary["skipped_disallow"].append(slug)  # type: ignore[union-attr]
            if not dry_run:
                async with factory() as db:
                    s = await db.get(Source, sid)
                    if s is not None:
                        s.robots_txt_compliant = False
                        s.robots_txt_check_at = now
                        await db.commit()
            continue

        # Güvenli reaktivasyon (robots KESİN allow).
        summary["reactivated"].append(slug)  # type: ignore[union-attr]
        if dry_run:
            continue
        async with factory() as db:
            s = await db.get(Source, sid)
            if s is None:
                continue
            s.is_active = True
            s.robots_txt_compliant = True
            s.robots_txt_check_at = now
            # Açık auto-deactivation izlerini çöz (artık geçersiz).
            await db.execute(
                update(FailedJob)
                .where(FailedJob.source_id == sid)
                .where(FailedJob.job_type == "source.auto_deactivated")
                .where(FailedJob.resolved_at.is_(None))
                .values(
                    resolved_at=now,
                    resolution_note="reactivate_dormant_sources ile yeniden aktive (#1498)",
                )
            )
            await db.commit()

    return summary


@celery_app.task(name="tasks.sources.reactivate_dormant_sources", bind=True)
def reactivate_dormant_sources(self, dry_run: bool = False) -> dict:  # type: ignore[no-untyped-def]
    """Sessizce pasife düşmüş kaynakları güvenli (robots re-check'li) reaktive eder.

    Yalnız ``tos_acknowledged=True`` kaynaklar değerlendirilir. Her biri için
    robots.txt taze çekilir; KESİN allow ise (``fetched=True`` + ``base_url_allowed``)
    ``is_active=True`` yapılır ve açık ``FailedJob('source.auto_deactivated')``
    kayıtları resolved işaretlenir. Gerçekten disallow olan veya robots'u hâlâ
    çekilemeyen kaynaklar AÇILMAZ, raporda sebebiyle döner. Idempotent.

    ``dry_run=True`` ile hiçbir yazma yapılmadan ne yapılacağı raporlanır (#1498).
    """
    return _run_async(_reactivate_dormant_sources_async(dry_run=dry_run))
