# `modules/media/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** **active** (Phase 2 — fifth module migrated).

Görsel medya boru hattı domain modülü (#300 — NIM VLM). Image download
glue + perceptual hash + media suggest (Jaccard scoring) + VLM caption
postprocess + admin moderation.

## Layout

- `__init__.py` — public facade (`admin_router` re-export)
- `media.py` — image download + storage glue (uses `shared/http`, `shared/storage` legacy paths)
- `media_suggest.py` — Jaccard tokenize / suggestion scoring
- `vlm_postprocess.py` — VLM caption enrichment (depicts heuristics)
- `tasks/media.py` — legacy stub Celery task (`tasks.media.*` → `media_queue`)
- `tasks/image_vlm.py` — NIM VLM pipeline (`tasks.image_vlm.*` → `image_vlm_queue`):
  - `process_article_image_vlm` — per-image VLM call
  - `backfill_pending_images` — every 5 min Beat
  - `retry_failed_images` — hourly Beat (@:20)
- `admin/routes.py` — admin moderation FastAPI router (URL: `/admin/media/*`)

Model stays flat:
- `app/models/article.py` — `ArticleImage` not relocated (Phase N+1; sahibi `modules/articles/`)

## Out of scope (do NOT touch here)

- `app.core.storage` / `app.core.http_client` — storage + http will move to
  `shared/storage` + `shared/http` in a later phase. media module only **consumes**
  these via legacy paths.
- `app.providers.nim_vlm` — provider stays in legacy `providers/`. Moves to
  `shared/providers/nim_vlm` during later phase.
- VLM prompt content — frozen in this PR (no behavior change).

## References

- Architecture: [`docs/engineering/modular-monolith-architecture.md`](../../../../docs/engineering/modular-monolith-architecture.md) §3.2
- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)

## Migration history

- 2026-05-20: Phase 2 PR 5 — migrated 6 files from legacy paths
  (`app.core.media`, `app.core.media_suggest`, `app.core.vlm_postprocess`,
  `app.workers.tasks.media`, `app.workers.tasks.image_vlm`, `app.api.admin_media`).
  Behavior-preserving (URL `/admin/media/*` + Celery task names + queue
  routing + Beat schedule entries all unchanged).
- 2026-05-20: Phase 1 PR — scaffold created.
