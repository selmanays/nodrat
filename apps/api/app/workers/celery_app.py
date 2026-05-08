"""Celery application — worker entry point.

docs/engineering/architecture.md §3 (Worker mimarisi)
docs/engineering/architecture.md §3.3 (Beat schedule)

Faz 1: source crawl + healthcheck task'ları aktif.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings


settings = get_settings()


celery_app = Celery(
    "nodrat",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks.sources",
        "app.workers.tasks.media",  # legacy stub (#300 PR-1)
        "app.workers.tasks.image_vlm",  # #300 PR-3 NIM VLM
        "app.workers.tasks.articles",
        "app.workers.tasks.embedding",
        "app.workers.tasks.clustering",
        "app.workers.tasks.agenda",
        "app.workers.tasks.raptor",  # #182 RAPTOR-Lite hierarchical
        "app.workers.tasks.maintenance",  # #219 MVP-1.5 cold tier
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
        # #436 — discovered article'ları fetch_detail kuyruğuna al.
        # Discovery sırasında dispatch edilen fetch_detail Redis broker'da
        # kaybolursa (worker crash, OOM, restart) bu backfill yakalar.
        # Idempotent (sadece status='discovered' AND created_at >= NOW()-72h).
        "task": "tasks.articles.backfill_discovered",
        "schedule": crontab(minute="*/5"),  # her 5 dk
        "kwargs": {"batch": 100, "max_age_hours": 72},
        "options": {"queue": "crawl_queue"},
    },
    "retry-failed-articles": {
        # #436 — failed article'ları saatte bir tekrar dene.
        # max_age_hours=72 — daha eski failed'lar bypass (kaynak muhtemelen
        # artık erişilemez veya freshness kayıp). dakika=25 → image
        # retry_failed (dakika=20) ile çakışmasın, worker yükü dengeli.
        "task": "tasks.articles.retry_failed",
        "schedule": crontab(minute=25, hour="*"),  # saatte bir, dk:25
        "kwargs": {"batch": 50, "max_age_hours": 72},
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


if __name__ == "__main__":
    celery_app.start()
