"""Module: media

Domain: görsel medya boru hattı (#300 — NIM VLM) + media suggest + VLM
postprocess + admin moderation.

Public API:
    admin_router    — FastAPI router (URL prefix `/admin/media`)
    media           — image download / storage glue (re-exported from .media)
    media_suggest   — Jaccard-based suggestion scoring
    vlm_postprocess — caption enrichment

Celery tasks (registered via shared/workers/celery_app):
    tasks.media.*        — legacy stub (#300 PR-1)
    tasks.image_vlm.*    — NIM VLM pipeline (backfill_pending, retry_failed,
                           process_article_image_vlm)

NOT a destination for `shared/storage` or `shared/providers` — those refactors
are deferred to later phases. This module only owns the *media domain* surface.

See:
    docs/engineering/modular-monolith-architecture.md §3.2
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
"""

from app.modules.media.admin.routes import router as admin_router

__all__ = ["admin_router"]
