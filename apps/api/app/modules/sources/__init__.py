"""Module: sources

Layer: kernel (master plan §1.3 — sources/articles kernel modülleri)
Status: Phase 3 PR 1b'de aktif (admin route + Celery tasks taşıması).

Public API:
    router  — Admin route (mount prefix /admin/sources)
              GET / POST / PUT / PATCH / DELETE endpoint'ler
    tasks   — Celery task module (string-bound: tasks.sources.*)

Storage dependency:
    `app.shared.workers.db_session` (Phase 3 PR 1a'da taşındı)
    `app.models.source` — Source, SourceConfig, SourceHealth (flat)

Legacy crawler dependencies (Phase 4'e kadar admin/routes.py'da kalır):
    `app.core.extractor`     — Listing card extraction
    `app.core.rss`           — RSS feed fetch
    `app.core.http_client`   — HTTP fetch utility
    `app.core.robots`        — robots.txt fetch

See:
- wiki/plans/modular-monolith-transition-master-plan.md §1.3
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/admin-route-domain-ownership.md
"""

from app.modules.sources.admin.routes import router

__all__ = ["router"]
