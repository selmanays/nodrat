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
        "app.workers.tasks.media",
        "app.workers.tasks.articles",
        "app.workers.tasks.embedding",
        "app.workers.tasks.clustering",
        "app.workers.tasks.agenda",
        # Faz 1+:
        # "app.workers.tasks.maintenance",
        # Faz 2+:
        # "app.workers.tasks.rag",
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
        "tasks.media.*": {"queue": "media_queue"},
        "tasks.embedding.*": {"queue": "embedding_queue"},
        "tasks.clustering.*": {"queue": "event_queue"},
        "tasks.agenda.*": {"queue": "event_queue"},
        # Faz 1+:
        # 'tasks.cleaner.*': {'queue': 'cleaning_queue'},
        # 'tasks.embedding.*': {'queue': 'embedding_queue'},
        # 'tasks.rag.*': {'queue': 'event_queue'},
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
        "schedule": crontab(minute=30, hour="*/6"),  # 6 saatte bir
        "options": {"queue": "event_queue"},
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
