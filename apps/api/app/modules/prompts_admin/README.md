# `modules/prompts_admin/`

**Layer:** parallel — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** Active — Phase 2 PR 8b'de aktive edildi (admin route ownership taşıması).

## Public API

- `router` — FastAPI APIRouter (mount prefix: `/admin/prompts`)
  - `GET /admin/prompts` — Bilinen prompts list
  - `GET /admin/prompts/{name}` — Detay (current + meta)
  - `GET /admin/prompts/{name}/history` — Version history
  - `PUT /admin/prompts/{name}` — Yeni versiyon
  - `DELETE /admin/prompts/{name}` — Default'a dön (history korunur)
  - `POST /admin/prompts/{name}/restore` — Geçmiş bir version'ı current yap

All endpoints require admin authentication (`require_admin` dependency).

## Dependency chain (Phase 2 PR 8 split)

- **PR 8a** (`shared/runtime_config/prompts_store`) — storage altyapısı (Redis pub/sub state store)
- **PR 8b** (`modules/prompts_admin/routes`) — admin route ownership (this PR)

`prompts_admin/routes.py` imports `prompts_store` from `app.shared.runtime_config.prompts_store` (allowed: modules → shared).

## Active runtime smoke acceptance (PR 8b)

Active write smoke runs end-to-end through real admin route:

1. **READ current state:** `app_prompts` total_rows = 0 (DB boş); fallback used
2. **WRITE test:** Override via admin UI (`agenda_card` ya da seçilen düşük riskli key)
3. **READ same-process:** API returns persisted DB override
4. **READ worker/second-process:** Redis `prompts:invalidate` publish + worker process cache invalidation observed; NUMSUB reported
5. **RESTORE:** Override delete via admin UI (DB row → 0)
6. **READ final:** Default/fallback returned; logs clean; production state untouched

**Forbidden shortcuts** (PR #1112 §12.2):
- Direct DB `app_prompts` table UPDATE/DELETE
- Direct Redis PUBLISH on `prompts:invalidate`
- Same-process only read
- Skipping RESTORE

## References

- Responsibility + allowed/forbidden imports: [`docs/engineering/modular-monolith-architecture.md`](../../../../../docs/engineering/modular-monolith-architecture.md) §3
- Boundary decision: [`wiki/decisions/modular-monolith-boundary.md`](../../../../../wiki/decisions/modular-monolith-boundary.md)
- Import direction rules (CI-enforced): [`wiki/decisions/import-direction-rules.md`](../../../../../wiki/decisions/import-direction-rules.md)
- Admin route domain ownership: [`wiki/decisions/admin-route-domain-ownership.md`](../../../../../wiki/decisions/admin-route-domain-ownership.md)
- Refactor playbook: [`docs/engineering/refactor-playbook.md`](../../../../../docs/engineering/refactor-playbook.md)
