"""Sources Celery tasks — Phase 3 PR 1b'de modules/sources altına taşındı.

Task names AYNEN (string-bound):
    tasks.sources.healthcheck_source
    tasks.sources.healthcheck_all
    tasks.sources.recompute_extract_health
    tasks.sources.crawl_active_sources
    tasks.sources.fetch_source_rss
    tasks.sources.fetch_source_category_page

Queue routing: tasks.sources.* → crawl_queue (celery_app.py task_routes).
Beat schedule: crawl_active_sources (15dk), healthcheck_all (6sa),
recompute_extract_health (periyodik).
"""
