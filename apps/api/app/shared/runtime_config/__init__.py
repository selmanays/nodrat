"""Shared infrastructure: runtime_config

Redis pub/sub state stores for runtime-tunable configuration. Used by
multiple domains; never imports from `modules/*`.

Public API:
    settings_store  — global `AppSettings` Redis-backed singleton with
                      pub/sub cache invalidation (start_listener / publish /
                      set / get_*).

Future additions (Phase 2 PR 8):
    prompts_store   — `app.core.prompts_store` taşınacak (P2 PR 8 ile birlikte
                      modules/prompts_admin/ ile).

See:
    docs/engineering/modular-monolith-architecture.md §2.3
    wiki/decisions/modular-monolith-boundary.md
"""

from app.shared.runtime_config.settings_store import settings_store

__all__ = ["settings_store"]
