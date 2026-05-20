"""Shared infrastructure: runtime_config

Redis pub/sub state stores for runtime-tunable configuration. Used by
multiple domains; never imports from `modules/*`.

Public API:
    settings_store  — global `AppSettings` Redis-backed singleton with
                      pub/sub cache invalidation (start_listener / publish /
                      set / get_*) — Phase 2 PR 7a'da taşındı.
    prompts_store   — global `PromptsStore` Redis-backed singleton with
                      pub/sub cache invalidation (start_listener / get / set /
                      list / history / rollback) — Phase 2 PR 8a'da taşındı.

Future additions (Phase 2 PR 8b):
    modules/prompts_admin/  — `app.api.admin_prompts` taşınacak (PR 8b).

See:
    docs/engineering/modular-monolith-architecture.md §2.3
    wiki/decisions/modular-monolith-boundary.md
"""

from app.shared.runtime_config.prompts_store import prompts_store
from app.shared.runtime_config.settings_store import settings_store

__all__ = ["prompts_store", "settings_store"]
