# `modules/settings_admin/`

**Layer:** parallel — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 PR 7b — admin route migration on stable infra).

Runtime tunable `app_settings` (34+ key) admin CRUD yüzeyi. Storage altyapısı
`shared/runtime_config/settings_store` (Redis pub/sub state — PR 7a'da taşındı).

## Layout

- `__init__.py` — public facade (`router` + `SETTING_REGISTRY` re-export)
- `routes.py` — FastAPI admin router (URL: `/admin/settings/*`)
- `models.py` — `AppSetting` ORM model (T8-1 ile taşındı 2026-05-26)

## Phase 2 dependency chain

- **PR 7a** (#1107 merged): `core/settings_store.py` → `shared/runtime_config/settings_store.py`. 46 caller bulk-updated. Passive smoke PASS.
- **PR 7b** (this): `api/admin_settings.py` → `modules/settings_admin/routes.py`. Admin route ownership taşıma.
- **Active write smoke** PR 7b acceptance kriteri: admin route'tan setting değiştir → Redis pub/sub invalidation → cross-process consistency.

## References

- Architecture: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.4
- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- Sister module (storage): [`shared/runtime_config/`](../../shared/runtime_config/)

## Migration history

- 2026-05-26: **T8-1 (Wave A 1/3)** — `AppSetting` ORM model `app/models/app_setting.py`
  → `app/modules/settings_admin/models.py` (git mv, 66 satır, behavior-preserving).
  Facade `app/models/__init__.py` re-export'a güncellendi (caller=0; raw SQL path
  `shared/runtime_config/settings_store.py` etkilenmedi).
- 2026-05-20: Phase 2 PR 7b — migrated `app.api.admin_settings` (1551 LoC) to
  this module. Behavior-preserving (URL `/admin/settings/*` unchanged; storage
  via `shared/runtime_config/settings_store`).
- 2026-05-20: Phase 1 PR — scaffold created.
