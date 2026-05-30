# `modules/sources/`

**Layer:** kernel — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3.

**Status:** Active — Phase 3 PR 1b'de aktive edildi (admin route + Celery tasks ownership taşıması). **T7-3 (2026-05-28):** `services/polling_tier.py`. **T8-11 (2026-05-28):** `models.py` (Source + SourceConfig + SourceHealth).

## Migration history

- 2026-05-28: **T8-11** — `Source` + `SourceConfig` + `SourceHealth` ORM `app/models/source.py`'den `models.py`'e taşındı (3-model FK ailesi TEK PR; relationship() back_populates internal → same-module mapper-safe). T7-3 polling_tier service zaten sources/services'te → model gelince sources domain'de TAM. 8 dosya flip (facade + articles/admin + articles/tasks + media/admin + sources/admin + sources/services/polling_tier + sources/tasks + test; hepsi eager). import-linter: articles/media → sources LEGAL ("articles can read sources" — kernel alt katman). ORM birebir (no migration). **T8 12/22 → 13/22.** Bkz. [[t8-model-relocation-mini-plan]].

## Public API

### `admin/routes.py` — Admin route (`/admin/sources/*`)

- `GET /admin/sources` — Sources list
- `POST /admin/sources` — Create source
- `GET /admin/sources/{id}` — Source detail
- `PATCH /admin/sources/{id}` — Update source
- `DELETE /admin/sources/{id}` — Delete source
- + Healthcheck / test fetch / extraction preview endpoints

All endpoints require admin authentication (`require_admin`).

### `tasks/sources.py` — Celery tasks (string-bound)

- `tasks.sources.healthcheck_source` — Per-source health check
- `tasks.sources.healthcheck_all` — Beat: every 6h
- `tasks.sources.recompute_extract_health` — Beat: periodic
- `tasks.sources.crawl_active_sources` — Beat: every 15min
- `tasks.sources.fetch_source_rss` — RSS feed fetch + article enqueue
- `tasks.sources.fetch_source_category_page` — Category page extraction

Queue routing: `tasks.sources.* → crawl_queue` (defined in `celery_app.py`).

## Dependency chain (Phase 3 PR 1 split)

- **PR 1a** (`shared/workers/db_session`) — Celery worker DB/session helpers (extracted from `workers/tasks/sources.py`)
- **PR 1b** (this PR) — sources module ownership: admin route + Celery tasks

`modules/sources/tasks/sources.py` imports `_get_session_factory`, `_run_async` from `app.shared.workers.db_session` (allowed: modules → shared).

## Legacy crawler dependencies (Phase 4)

`admin/routes.py` still imports from `app.core.*` for crawler-domain utilities. These remain in `core/` until Phase 4 (crawler module migration):

- `app.core.extractor.extract_listing_cards`
- `app.core.rss.fetch_feed`, `FeedReport`
- `app.shared.http.client.fetch_text`
- `app.core.robots.fetch_robots`, `RobotsDisallowed`

These imports are **out of scope for PR 1b** — they remain legacy until Phase 4 crawler refactor.

## Active runtime smoke acceptance (PR 1b)

Active write smoke runs end-to-end through real admin route (Playwright MCP):

1. **READ current state:** source count = N
2. **CREATE:** POST `/admin/sources` with `__SMOKE_TEST_PR_1B__` (URL: `https://nodrat-smoke-test.invalid/feed.xml`, inactive if possible)
3. **READ same-process:** GET `/admin/sources/{id}` returns persisted source
4. **UPDATE:** PATCH metadata or active flag
5. **DELETE:** Source removed
6. **READ final:** source count = N (production state untouched)
7. **§9.4 log scan:** 7 container × 5+ patterns × 5min = 0

**Forbidden shortcuts** (PR #1112 §12.2):
- Direct DB INSERT/DELETE
- Direct Redis PUBLISH
- Same-process only read
- Skipping cleanup

## Migration history

- 2026-05-28: **T7-3** — `core/polling_tier.py` → `services/polling_tier.py`
  (100% rename, 247 satır; NEW `services/` alt-paket). Core-consumer cleanup
  (T7 initiative): `core/polling_tier` `Source` model import ediyordu (adaptive
  polling tier hesabı #578); core/'ta kalması T8-11 (Source/SourceConfig/
  SourceHealth → sources) relocation'ı `core/* must not import modules/*` ile
  blocklardı. Service sources domain'e taşındı. 2 caller flip:
  `tasks/sources.py:574` (compute_tier lazy) + `tests/unit/test_polling_tier.py`
  (1 import + ~8 `patch()` target string yeni path'e — patch-string dersi).
  Behavior-preserving; no DB/migration; shadow-mode tier hesabı AYNEN; manual
  polling trigger yok. T8-11 sources model relocation unblock. Bkz.
  [[t7-cost-tracker-core-consumer-cleanup-mini-plan]].

## References

- Responsibility + allowed/forbidden imports: [`docs/engineering/modular-monolith-architecture.md`](../../../../../docs/engineering/modular-monolith-architecture.md) §3
- Boundary decision: [`wiki/decisions/modular-monolith-boundary.md`](../../../../../wiki/decisions/modular-monolith-boundary.md)
- Import direction rules (CI-enforced): [`wiki/decisions/import-direction-rules.md`](../../../../../wiki/decisions/import-direction-rules.md)
- Admin route domain ownership: [`wiki/decisions/admin-route-domain-ownership.md`](../../../../../wiki/decisions/admin-route-domain-ownership.md)
- Refactor playbook: [`docs/engineering/refactor-playbook.md`](../../../../../docs/engineering/refactor-playbook.md)
