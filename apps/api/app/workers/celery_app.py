"""Celery application — worker entry point.

docs/engineering/architecture.md §3 (Worker mimarisi)
docs/engineering/architecture.md §3.3 (Beat schedule)

Faz 0: minimal config, task'lar Faz 1+'da eklenecek.
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings


settings = get_settings()


celery_app = Celery(
    "nodrat",
    broker=settings.redis_url,
    backend=settings.redis_url,
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
    # Routing — queue başına task assignment Faz 1'de eklenecek
    task_default_queue="default",
    task_routes={
        # 'tasks.scraper.*': {'queue': 'crawl_queue'},
        # 'tasks.cleaner.*': {'queue': 'cleaning_queue'},
        # 'tasks.embedding.*': {'queue': 'embedding_queue'},
        # 'tasks.rag.*': {'queue': 'event_queue'},
    },
)


# Beat schedule — periyodik task'lar (Architecture §3.3)
# Faz 1'de aktif edilecek; şimdilik placeholder
celery_app.conf.beat_schedule = {
    # 'crawl-all-sources': {
    #     'task': 'tasks.scheduler.crawl_active_sources',
    #     'schedule': crontab(minute='*/15'),
    # },
}


# Task auto-discovery — Faz 1+'da:
# celery_app.autodiscover_tasks(["app.workers.tasks"])


if __name__ == "__main__":
    celery_app.start()
