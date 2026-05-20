"""Module: articles

Layer: kernel (master plan §1.3 — sources/articles kernel modülleri)
Status: Phase 3 PR 2b'de aktif (admin route + Celery tasks taşıması).

Public API:
    router  — Admin route (mount prefix /admin/articles)
              GET / POST endpoint'ler (3 GET + 1 POST)
    tasks   — Celery task module (string-bound: tasks.articles.*)

Storage dependency:
    `app.shared.workers.db_session` (Phase 3 PR 1a'da taşındı)
    `app.models.article` — Article, ArticleImage (flat, Faz N+1'e kadar)
    `app.models.source` — Source (flat, FK source_id)
    `app.models.job` — FailedJob, AdminAuditLog (flat)

Legacy crawler/cleaning dependencies (Phase 4'e kadar tasks/articles.py'da kalır):
    `app.core.cleaning`        — STATUS_DISCOVERED, normalize_text
    `app.core.content_quality` — quality gating
    `app.core.extractor`       — Article body extraction
    `app.core.http_client`     — HTTP fetch utility

Cross-module lazy imports (string-bound where possible; Python import where required):
    `app.modules.media.tasks.image_vlm.process_article_image_vlm` (allowed direction)
    `app.workers.tasks.embedding` (legacy worker — to be decoupled when embedding migrates)

See:
- wiki/plans/modular-monolith-transition-master-plan.md §1.3
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/admin-route-domain-ownership.md
"""

from app.modules.articles.admin.routes import router

__all__ = ["router"]
