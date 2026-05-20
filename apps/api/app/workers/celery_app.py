"""Celery application — worker entry point.

docs/engineering/architecture.md §3 (Worker mimarisi)
docs/engineering/architecture.md §3.3 (Beat schedule)

Faz 1: source crawl + healthcheck task'ları aktif.
"""

from __future__ import annotations

from datetime import UTC, datetime

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_postrun, task_prerun

from app.config import get_settings

settings = get_settings()


celery_app = Celery(
    "nodrat",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks.sources",
        "app.modules.media.tasks.media",  # legacy stub (#300 PR-1) — Phase 2 modular
        "app.modules.media.tasks.image_vlm",  # #300 PR-3 NIM VLM — Phase 2 modular
        "app.workers.tasks.articles",
        "app.workers.tasks.embedding",
        "app.modules.entities.tasks.entities",  # #667 Faz 6 NER pipeline (Phase 2 modular)
        "app.modules.clusters.tasks.clustering",  # event clustering — Phase 2 modular
        "app.workers.tasks.agenda",
        "app.workers.tasks.raptor",  # #182 RAPTOR-Lite hierarchical
        "app.workers.tasks.maintenance",  # #219 MVP-1.5 cold tier
        "app.modules.style_profiles.tasks.style_profile",  # #52 Faz 5 style analyzer (Phase 2 modular)
        "app.modules.sft.tasks.sft_curator",  # #567 MVP-1.7 SFT data ETL (Phase 2 modular)
        "app.workers.tasks.cluster_assigner",  # #1015 Pivot Faz 3 araştırma kümeleme
    ],
)


celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Tracking
    task_track_started=True,
    task_send_sent_event=True,
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Result expiry (1 day)
    result_expires=86400,
    # Routing — queue başına task assignment
    task_default_queue="default",
    task_routes={
        "tasks.sources.*": {"queue": "crawl_queue"},
        "tasks.articles.*": {"queue": "crawl_queue"},
        "tasks.media.*": {"queue": "media_queue"},  # legacy (deprecated #300)
        "tasks.image_vlm.*": {"queue": "image_vlm_queue"},  # #300 NIM VLM
        "tasks.embedding.*": {"queue": "embedding_queue"},
        "tasks.clustering.*": {"queue": "event_queue"},
        "tasks.agenda.*": {"queue": "event_queue"},
        "tasks.raptor.*": {"queue": "event_queue"},
        # #345 MVP-1.5 — re-embed + cold tier maintenance worker_embedding'de
        "tasks.maintenance.*": {"queue": "embedding_queue"},
        # #52 Faz 5 — style analyzer (DeepSeek tek seferlik) — agenda ile aynı queue
        "tasks.style_profile.*": {"queue": "event_queue"},
        # #567 MVP-1.7 — SFT data curator (PII secondary scan + ChatML serialize)
        "tasks.sft_curator.*": {"queue": "embedding_queue"},
        # #1015 Pivot Faz 3 — araştırma kümeleme (haber-OLAY clustering'den AYRI)
        "tasks.research_clustering.*": {"queue": "embedding_queue"},
        # #667 Faz 6 — NER entity extraction (DeepSeek LLM call) — agenda queue
        "tasks.entities.*": {"queue": "event_queue"},
    },
)


# ============================================================================
# Beat schedule (Architecture §3.3)
# ============================================================================
# Faz 1 aktif:
#   crawl-active-sources    → her 15 dk
#   source-healthcheck-all  → her 6 saat
#   cleanup-old-snapshots   → gece 03:00 (Faz 1 maintenance task'ı geldiğinde)
#   database-backup         → gece 04:00 (Faz 1 maintenance task'ı geldiğinde)
#
# Faz 2'de aktif olacak:
#   event-clustering        → saatlik
#   agenda-card-refresh     → 2 saatte bir
celery_app.conf.beat_schedule = {
    "crawl-active-sources": {
        "task": "tasks.sources.crawl_active_sources",
        "schedule": crontab(minute="*/15"),  # her 15 dk
        "options": {"queue": "crawl_queue"},
    },
    "source-healthcheck-all": {
        "task": "tasks.sources.healthcheck_all",
        "schedule": crontab(minute=0, hour="*/6"),  # 6 saatte bir
        "options": {"queue": "crawl_queue"},
    },
    "refresh-clusters": {
        "task": "tasks.clustering.refresh_clusters",
        "schedule": crontab(minute=0, hour="*"),  # saatlik
        "options": {"queue": "event_queue"},
    },
    "refresh-agenda-cards": {
        "task": "tasks.agenda.refresh_active_cards",
        # #175 — saatlik refresh: yeni cluster'lar 6 saate kadar agenda'sız beklemesin
        "schedule": crontab(minute=15, hour="*"),
        "options": {"queue": "event_queue"},
    },
    "build-weekly-summary-cards": {
        # #182 RAPTOR-Lite — günlük 02:00 UTC'de haftalık tema kart üretir
        "task": "tasks.raptor.build_weekly_summary_cards",
        "schedule": crontab(minute=0, hour=2),
        "options": {"queue": "event_queue"},
    },
    "backfill-country": {
        # #228 — NULL country kartları günlük 04:00 UTC'de batch=50 re-tag
        "task": "tasks.agenda.backfill_country",
        "schedule": crontab(minute=0, hour=4),
        "kwargs": {"batch": 50},
        "options": {"queue": "event_queue"},
    },
    "backfill-missing-chunks": {
        # #166 — cleaned ama chunks olmayan article'lar için chain backfill
        "task": "tasks.articles.backfill_missing_chunks",
        "schedule": crontab(minute=30, hour="*/2"),  # 2 saatte bir
        "kwargs": {"batch": 50},
        "options": {"queue": "embedding_queue"},
    },
    "backfill-discovered-articles": {
        # #917 — discovered article'ları DENEME-tabanlı fetch_detail'e al
        # (#904 retry_failed ile tutarlı; yaş-tabanlı max_age_hours KALDIRILDI
        # — o "deneme tükendi" değil "makale eski" ölçüyordu, dispatch-kaybı
        # eski orphan'ları 72h sonra kalıcı bypass ediyordu = 75 orphan kök).
        # Idempotent: status='discovered' AND extract_attempts < max_attempts;
        # dispatch kaybı (extract_attempts=0) yaştan bağımsız DAİMA yakalanır.
        "task": "tasks.articles.backfill_discovered",
        "schedule": crontab(minute="*/5"),  # her 5 dk
        "kwargs": {"batch": 100, "max_attempts": 5},
        "options": {"queue": "crawl_queue"},
    },
    "retry-failed-articles": {
        # #904 — failed + quarantine'i DENEME-tabanlı tekrar dene
        # (eski yaş-tabanlı max_age_hours kaldırıldı; o "deneme tükendi"
        # değil "makale eski" ölçüyordu → 1182 stranded kök neden).
        # max_attempts=5: bütçeli failed/quarantine → discovered; tükenmiş
        # quarantine → discarded. dk:25 (image retry_failed dk:20 ile çakışmaz).
        "task": "tasks.articles.retry_failed",
        "schedule": crontab(minute=25, hour="*"),  # saatte bir, dk:25
        "kwargs": {"batch": 50, "max_attempts": 5},
        "options": {"queue": "crawl_queue"},
    },
    "recompute-extract-health": {
        # #904 — per-domain extract-confidence telemetri (R-OPS-01 gate).
        # 6 saatte bir dk:40 (source-healthcheck dk:0 ile çakışmaz).
        "task": "tasks.sources.recompute_extract_health",
        "schedule": crontab(minute=40, hour="*/6"),
        "options": {"queue": "crawl_queue"},
    },
    "backfill-pending-images": {
        # #304 fix — pending ArticleImage'lar için VLM batch dispatch
        # NIM 40 RPM + worker concurrency 2 → 5 dk'da pratikte 300-400 işlenir.
        # Beat her 5 dk batch=300 atar; worker zaten meşgulse Celery sıraya
        # ekler. Idempotent (sadece status='pending' seçer).
        "task": "tasks.image_vlm.backfill_pending",
        "schedule": crontab(minute="*/5"),  # her 5 dk
        "kwargs": {"batch": 300},
        "options": {"queue": "image_vlm_queue"},
    },
    "retry-failed-images": {
        # #304 fix — failed ArticleImage'ları saatte bir tekrar dene
        # max_age_hours=72 (3 gün) — daha eski failed'lar bypass edilir,
        # manuel reprocess gerekir (kaynak haber muhtemelen artık erişilemez).
        # Geçici hatalar (DNS, 5xx, timeout) genelde 1-2 saat sonra düzelir.
        "task": "tasks.image_vlm.retry_failed",
        "schedule": crontab(minute=20, hour="*"),  # saatte bir, dk:20
        "kwargs": {"batch": 100, "max_age_hours": 72},
        "options": {"queue": "image_vlm_queue"},
    },
    "body-html-drop": {
        # #220 MVP-1.5 PR-5 — 24h sonrası body_html NULL'a çek
        # Settings flag: body_html_drop.enabled (default False)
        # Cold tier'dan ÖNCE çalışır (03:00 < 03:30) — body_html drop edilen
        # article'ın raw_html cold tier candidate olabilir (sıralı pipeline).
        "task": "tasks.maintenance.body_html_drop",
        "schedule": crontab(minute=0, hour=3),  # günlük 03:00
        "kwargs": {"batch": 500, "max_age_hours": 24},
    },
    "cold-tier-archive": {
        # #219 MVP-1.5 PR-4 — 30+ gün eski raw_html → Contabo OS
        # Settings flag: cold_tier.enabled (default False — manuel enable)
        # Backup'tan önce çalıştır (03:30 < 04:00 backup) → tutarlı state
        "task": "tasks.maintenance.cold_tier_archive",
        "schedule": crontab(minute=30, hour=3),  # günlük 03:30
        "kwargs": {"batch": 100, "max_age_days": 30},
    },
    "sft-curator-nightly": {
        # #567 MVP-1.7 — generations.sft_eligible=true → training_samples ETL.
        # Settings flag: sft.curator.enabled (default False — kill switch).
        # 02:45 UTC: RAPTOR (02:00) + body_html_drop (03:00) arası boş slot;
        # backup (04:00) öncesi state tutarlı.
        # Idempotent (UNIQUE(generation_id, task_type)).
        "task": "tasks.sft_curator.run",
        "schedule": crontab(minute=45, hour=2),  # günlük 02:45 UTC
        "options": {"queue": "embedding_queue"},
    },
    "research-cluster-assign": {
        # #1015 Pivot Faz 3 — kullanıcı sorgularını GLOBAL araştırma
        # kümelerine ata (haber-OLAY clustering'den AYRI namespace).
        # Settings flag: research.clustering.enabled (default False —
        # kill switch; #854: DB override yoksa no-op, deploy güvenli).
        # 03:50 UTC: cold-tier (03:30) sonrası, backup (04:00) öncesi
        # boş slot. Idempotent (UNIQUE(message_id, cluster_id)).
        "task": "tasks.research_clustering.assign",
        "schedule": crontab(minute=50, hour=3),  # günlük 03:50 UTC
        "options": {"queue": "embedding_queue"},
    },
    "research-hierarchy-refine": {
        # #1020 Pivot Faz 6 — GLOBAL hiyerarşi rafine (aggregate
        # co-occurrence + df-asimetri). Settings flag:
        # research.hierarchy_refine_enabled (default False — kill switch).
        # 03:55 UTC: assign (03:50) SONRASI, backup (04:00) öncesi.
        # Idempotent + reversible (düz-küme-önce; flag kapalı = no-op).
        "task": "tasks.research_clustering.refine_hierarchy",
        "schedule": crontab(minute=55, hour=3),  # günlük 03:55 UTC
        "options": {"queue": "embedding_queue"},
    },
    # Faz 1 maintenance (henüz task yok):
    # 'cleanup-old-snapshots': {
    #     'task': 'tasks.maintenance.cleanup_old_html_snapshots',
    #     'schedule': crontab(minute=0, hour=3),
    # },
    # 'database-backup': {
    #     'task': 'tasks.maintenance.backup_database',
    #     'schedule': crontab(minute=0, hour=4),
    # },
}


# ============================================================================
# #468 — Maintenance task last-run tracker (Celery signal hooks)
# ============================================================================
# 5 backfill/retry task'ı için her run'ın started_at + summary'sini Redis'e
# kaydeder; admin queue UI bunları gösterir + manuel tetikleme yapar.

# In-memory store: task_id -> started_at (worker process içi, signal handler'lar
# senkron olduğu için thread-safe değildir ama Celery default prefork model'inde
# her process tek aktif task hariç sorun yok)
_maintenance_prerun_starts: dict[str, datetime] = {}


@task_prerun.connect
def _maintenance_prerun_handler(task_id=None, task=None, **_):  # type: ignore[no-untyped-def]
    if not task or not task_id:
        return
    try:
        from app.core.maintenance_tracker import is_tracked

        if is_tracked(task.name):
            _maintenance_prerun_starts[task_id] = datetime.now(UTC)
    except Exception:  # pragma: no cover — signal hook never raise  # noqa: S110
        pass


@task_postrun.connect
def _maintenance_postrun_handler(  # type: ignore[no-untyped-def]
    task_id=None,
    task=None,
    retval=None,
    state=None,
    **_,
):
    if not task or not task_id:
        return
    try:
        from app.core.maintenance_tracker import is_tracked, record_run_sync

        if not is_tracked(task.name):
            return
        started = _maintenance_prerun_starts.pop(task_id, datetime.now(UTC))
        status = "succeeded" if state == "SUCCESS" else "failed"
        record_run_sync(
            task.name,
            summary=retval,
            started_at=started,
            status=status,
        )
    except Exception:  # pragma: no cover  # noqa: S110
        pass


if __name__ == "__main__":
    celery_app.start()
