"""Module: sources

Layer: kernel (master plan §1.3 — sources/articles kernel modülleri)
Status: Phase 3 PR 1b'de aktif (admin route + Celery tasks taşıması).

Public API (T8-PRE-1 sonrası — submodule path):
    `app.modules.sources.admin.routes.router` — admin router (/admin/sources)
    `app.modules.sources.tasks`               — Celery task module (string-bound)

Storage dependency:
    `app.shared.workers.db_session` (Phase 3 PR 1a'da taşındı)
    `app.modules.sources.models` — Source, SourceConfig, SourceHealth (T8-11: 2026-05-28 buraya taşındı)

Legacy crawler dependencies (Phase 4'e kadar admin/routes.py'da kalır):
    `app.core.extractor`     — Listing card extraction
    `app.core.rss`           — RSS feed fetch
    `app.shared.http.client`   — HTTP fetch utility
    `app.core.robots`        — robots.txt fetch

See:
- wiki/plans/modular-monolith-transition-master-plan.md §1.3
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/admin-route-domain-ownership.md
- wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop 11 (lazy `__init__.py`)
"""

# T8-PRE-1 (v68): route eager re-export kaldırıldı (collect-time circular
# import koruması).

__all__: list[str] = []
