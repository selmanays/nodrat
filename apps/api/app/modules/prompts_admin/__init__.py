"""Module: prompts_admin

Layer: parallel
Status: Phase 2 PR 8b'de aktif (admin route ownership taşıması).

Public API:
    router  — FastAPI APIRouter for /admin/prompts/* endpoints
              (GET / PUT / DELETE / POST restore + history)

Storage dependency:
    `app.shared.runtime_config.prompts_store` (Phase 2 PR 8a'da taşındı)

See:
- wiki/plans/modular-monolith-transition-master-plan.md §2
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/import-direction-rules.md
- wiki/decisions/admin-route-domain-ownership.md
"""

from app.modules.prompts_admin.routes import router

__all__ = ["router"]
