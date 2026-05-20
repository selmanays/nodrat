"""Module: settings_admin

Domain: runtime tunable `app_settings` (34+ key) admin CRUD yüzeyi. Storage
altyapısı `shared/runtime_config/settings_store` (Redis pub/sub state).

Public API:
    router          — FastAPI router (URL prefix `/admin/settings`)
    SETTING_REGISTRY — exported for downstream consumers (e.g. tests, schema validation)

See:
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
    wiki/decisions/modular-monolith-boundary.md
"""

from app.modules.settings_admin.routes import SETTING_REGISTRY, router

__all__ = ["SETTING_REGISTRY", "router"]
