"""Module: settings_admin

Domain: runtime tunable `app_settings` (34+ key) admin CRUD yüzeyi. Storage
altyapısı `shared/runtime_config/settings_store` (Redis pub/sub state).

Public API (T8-PRE-1 sonrası — submodule path):
    `app.modules.settings_admin.routes.router` — FastAPI router (URL prefix `/admin/settings`)
    `app.modules.settings_admin.routes.SETTING_REGISTRY` — schema validation registry

See:
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
    wiki/decisions/modular-monolith-boundary.md
    wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop 11 (lazy `__init__.py`)
"""

# T8-PRE-1 (v68): route eager re-export kaldırıldı (collect-time circular
# import koruması). `router` ve `SETTING_REGISTRY` doğrudan submodule path'inden
# import edilir.

__all__: list[str] = []
