# `modules/articles/`

**Layer:** kernel — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** Phase 3 PR 2b'de **active**. Admin route + Celery tasks taşıması tamamlandı.

## Yapı

```
modules/articles/
├── __init__.py        Module facade (router re-export)
├── models.py          Article + ArticleImage ORM (T8-12b: app/models/article.py'den taşındı; Vector(1024) summary_embedding + relationship)
├── admin/
│   ├── __init__.py    Admin router facade
│   └── routes.py      Admin route (FastAPI APIRouter, /admin/articles/*)
├── tasks/
│   ├── __init__.py    Tasks module docstring (string-bound task names)
│   └── articles.py    Celery task definitions (tasks.articles.*)
└── README.md          Bu dosya
```

## Migration history

- 2026-05-28: **T8-12b** — `Article` + `ArticleImage` ORM `app/models/article.py`'den
  `models.py`'e taşındı (T8 harvest; article split FAZ B). T8-12a ile sources→articles
  decouple (raw SQL) yapılmış → relocation contract-temiz. **relationship() internal**
  (Article.images ↔ ArticleImage.article cascade all,delete-orphan; 2 class birlikte →
  mapper-safe). **Vector(1024) summary_embedding** ORM declaration KONUMU değişti; tablo
  `articles` / ivfflat index / migration `20260511_0100` / raw-SQL write (embedding/tasks)
  + read (core/retrieval) path'leri DEĞİŞMEZ (tablo adına bağlı). 12 dosya flip (facade +
  10 production caller DIRECT: api/admin_queue + articles/admin + articles/tasks +
  clusters/tasks + embedding/tasks + media/admin + media_suggest + image_vlm + media/tasks +
  ops/maintenance + test). import-linter 16/16 (clusters/embedding/media/ops → articles LEGAL;
  articles kernel alt-katman). ORM birebir; no migration, no schema change, embedding/RAG/index
  VERİSİNE dokunulmaz. Bkz. [[t8-12-article-split-mini-plan]].

## Dependency chain

**Storage layer (PR 1a):**
- `app.shared.workers.db_session` — Celery sync→async DB bridge helpers (`_get_session_factory`, `_run_async`, `open_session`)

**Model layer (flat — Faz N+1'e kadar):**
- `app.models.article.Article, ArticleImage`
- `app.models.source.Source` (FK reference)
- `app.models.job.FailedJob, AdminAuditLog`
- `app.modules.accounts.models.User`

**Legacy crawler/cleaning (Phase 4'e kadar `tasks/articles.py` içinde kalır — sources PR 1b deseni):**
- `app.core.cleaning` — STATUS_DISCOVERED, normalize_text
- `app.core.content_quality` — quality gating (NoneType errors guard)
- `app.core.extractor` — extract_article (body parse)
- `app.shared.http.client` — fetch_text

**Cross-module references (allowed direction):**
- `app.modules.media.tasks.image_vlm.process_article_image_vlm` — lazy Python import (media kernel'in altında değil; "articles must not import upper layers" contract'ında media forbidden listede YOK)
- `app.workers.tasks.embedding` — legacy worker path (lazy ×2); embedding `modules/`'a taşındığında Celery dispatch decoupling gerekecek (A1 deseni)

## Public API

- `router` (mount prefix `/admin/articles`) — 3 GET + 1 POST endpoint
- Celery task names (string-bound, registry'de **DEĞİŞMEZ**):
  - `tasks.articles.discover` — RSS/category card → article discovery
  - `tasks.articles.fetch_detail` — full article fetch + extract
  - `tasks.articles.backfill_missing_chunks` — chunk backfill (#166)
  - `tasks.articles.backfill_discovered` — denemeli fetch (#917)
  - `tasks.articles.retry_failed` — saatlik :25 retry
  - `tasks.articles.recover_quarantined` — manuel kurtarma (#904)

## Worker registry (post-PR 2b)

`workers/celery_app.py:30`:

```python
celery_app.autodiscover_tasks([
    "app.modules.articles.tasks.articles",   # PR 2b
    ...
])
```

## Smoke acceptance (PR 2b)

**Passive (zorunlu):**
1. API container: `from app.modules.articles.admin.routes import router` OK
2. Worker container: `from app.modules.articles.tasks.articles import article_discover, ...` OK
3. Eski path'ler: `app.api.admin_articles` ModuleNotFoundError; `app.workers.tasks.articles` ModuleNotFoundError
4. Celery registered task list: 6 `tasks.articles.*` task aynen
5. Beat schedule entries değişmedi
6. Queue routing `tasks.articles.* → crawl_queue` korundu
7. 7 container × 6 pattern × ≥5 dk log scan: 0/0/0/0/0/0

**Active (READ-only zorunlu):**
8. `GET /admin/articles` (list) → 200
9. `GET /admin/articles/{id}` (detail) → 200
10. POST/PATCH/DELETE YAPILMAZ; backfill/recover trigger YOK; direct DB/Redis YOK

**Worker natural fire (best-effort, ≤15 dk, non-blocking):**
11. Beat'in doğal fire'ı ile `tasks.articles.*` task'larından herhangi biri succeeded → kanıt
12. 15 dk içinde fire görülmezse "not observed within window, non-blocking"

## References

- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- Import direction: [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- Refactor playbook: [`docs/engineering/refactor-playbook.md`](../../../../docs/engineering/refactor-playbook.md)
- Admin route ownership: [`wiki/decisions/admin-route-domain-ownership.md`](../../../../wiki/decisions/admin-route-domain-ownership.md)
