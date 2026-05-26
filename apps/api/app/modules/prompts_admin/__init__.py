"""Module: prompts_admin

Layer: parallel
Status: Phase 2 PR 8b'de aktif (admin route ownership taşıması).

Public API (T8-PRE-1 sonrası — submodule path):
    `app.modules.prompts_admin.routes.router` — FastAPI APIRouter (/admin/prompts/*)

Storage dependency:
    `app.shared.runtime_config.prompts_store` (Phase 2 PR 8a'da taşındı)

See:
- wiki/plans/modular-monolith-transition-master-plan.md §2
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/import-direction-rules.md
- wiki/decisions/admin-route-domain-ownership.md
- wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop 11 (lazy `__init__.py`)
"""

# T8-PRE-1 (v68): route eager re-export kaldırıldı (collect-time circular
# import koruması).

__all__: list[str] = []
