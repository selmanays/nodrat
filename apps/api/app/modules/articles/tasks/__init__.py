"""Articles Celery tasks — Phase 3 PR 2b'de modules/articles altına taşındı.

Task names AYNEN (string-bound):
    tasks.articles.discover
    tasks.articles.fetch_detail
    tasks.articles.backfill_missing_chunks
    tasks.articles.backfill_discovered
    tasks.articles.retry_failed
    tasks.articles.recover_quarantined

Queue routing: tasks.articles.* → crawl_queue (celery_app.py task_routes).
Beat schedule:
    backfill-missing-chunks    — chain backfill (#166)
    backfill-discovered-articles — denemeli fetch (#917)
    retry-failed-articles      — saatlik :25
"""
