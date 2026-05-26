"""Module: media

Domain: görsel medya boru hattı (#300 — NIM VLM) + media suggest + VLM
postprocess + admin moderation.

Public API (T8-PRE-1 sonrası — submodule path):
    `app.modules.media.admin.routes.router` — admin router (/admin/media)
    `app.modules.media.media`               — image download / storage glue
    `app.modules.media.media_suggest`       — Jaccard-based suggestion scoring
    `app.modules.media.vlm_postprocess`     — caption enrichment

Celery tasks (registered via shared/workers/celery_app):
    tasks.media.*        — legacy stub (#300 PR-1)
    tasks.image_vlm.*    — NIM VLM pipeline (backfill_pending, retry_failed,
                           process_article_image_vlm)

NOT a destination for `shared/storage` or `shared/providers` — those refactors
are deferred to later phases. This module only owns the *media domain* surface.

See:
    docs/engineering/modular-monolith-architecture.md §3.2
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
    wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop 11 (lazy `__init__.py`)
"""

# T8-PRE-1 (v68): route eager re-export kaldırıldı (collect-time circular
# import koruması).

__all__: list[str] = []
