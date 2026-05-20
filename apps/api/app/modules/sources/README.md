# `modules/sources/`

**Layer:** kernel — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3.

**Status:** Active — Phase 3 PR 1b'de aktive edildi (admin route + Celery tasks ownership taşıması).

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
- `app.core.http_client.fetch_text`
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

## References

- Responsibility + allowed/forbidden imports: [`docs/engineering/modular-monolith-architecture.md`](../../../../../docs/engineering/modular-monolith-architecture.md) §3
- Boundary decision: [`wiki/decisions/modular-monolith-boundary.md`](../../../../../wiki/decisions/modular-monolith-boundary.md)
- Import direction rules (CI-enforced): [`wiki/decisions/import-direction-rules.md`](../../../../../wiki/decisions/import-direction-rules.md)
- Admin route domain ownership: [`wiki/decisions/admin-route-domain-ownership.md`](../../../../../wiki/decisions/admin-route-domain-ownership.md)
- Refactor playbook: [`docs/engineering/refactor-playbook.md`](../../../../../docs/engineering/refactor-playbook.md)
