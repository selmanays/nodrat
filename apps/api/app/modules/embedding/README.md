# `modules/embedding/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §1.3.

**Status:** Phase 3 PR 3'te **active**. Celery tasks taşıması tamamlandı (admin route YOK).

## Yapı

```
modules/embedding/
├── __init__.py        Module facade (middle-layer docstring, no router)
├── tasks/
│   ├── __init__.py    Tasks module docstring (6 string-bound task names)
│   └── embedding.py   Celery task definitions (tasks.embedding.*) — 1007 LoC
└── README.md          Bu dosya
```

**Admin route:** YOK — embedding'in kendi admin endpoint'i yok. (RAG observability `admin_rag.py`'de.)

## Dependency chain

**Storage layer (PR 1a):**
- `app.shared.workers.db_session` — `_get_session_factory`, `_run_async`, `open_session`

**Model layer (flat — Faz N+1'e kadar):**
- `app.models.article.Article` (FK reference)

**Provider layer (flat — şu an scope dışı):**
- `app.providers.registry.{bootstrap_default_providers, registry}`
- `app.providers.base.Message`
- `app.providers.local_embedding` (NIM/local SBERT — yerel embedding pipeline)

**Legacy (Phase 4'e kadar):**
- `app.core.chunker` — ChunkingConfig + chunk_text
- `app.core.cost_tracker` — estimate_cost_usd, track_provider_call
- `app.core.semantic_chunker` — embedding-based semantic chunking (lazy)
- `app.prompts.chunk_keywords` — LLM keyword extraction prompt (lazy)
- `app.shared.runtime_config.settings_store` — runtime config (lazy ×3)
- `app.shared.runtime_config.prompts_store` — runtime prompts (lazy ×1)

**Cross-module references (allowed direction):**
- `app.modules.entities.tasks.entities.extract_article_entities` — lazy (chain dispatch)
- `app.modules.clusters.tasks.clustering.cluster_article` — lazy (chain dispatch)

## Public API

Celery task names (string-bound; registry'de **DEĞİŞMEZ**):

| Task name | Signature | Notes |
|---|---|---|
| `tasks.embedding.chunk_article` | `(article_id: str, fast: bool = False)` | bind=True, max_retries=2; idempotent (per-article re-chunk) |
| `tasks.embedding.embed_chunks` | `(article_id: str, fast: bool = False)` | chain dispatch (chunk_article → embed_chunks) |
| `tasks.embedding.embed_article_summary` | `(article_id: str)` | article summary embedding |
| `tasks.embedding.backfill_article_summaries` | `(batch_size, dry_run)` | maintenance |
| `tasks.embedding.rechunk_all` | `(batch_size, dry_run)` | **⚠️ manuel toplu rechunk — veri güvenliği invariant'ı: smoke'da TETİKLENMEZ** |
| `tasks.embedding.extract_chunk_keywords` | `(article_id: str)` | LLM-based keyword extraction |

**Queue routing:** `tasks.embedding.* → embedding_queue` ([celery_app.py:68](../../workers/celery_app.py))
**Fast lane:** `FAST_EMBED_QUEUE = "embedding_fast_queue"` (constant; adanmış worker_embedding_fast consumer; `chunk_article` `fast=True` parameter ile)

## Worker registry (post-PR 3)

`workers/celery_app.py:31`:

```python
celery_app.autodiscover_tasks([
    ...
    "app.modules.embedding.tasks.embedding",   # PR 3
    ...
])
```

## Pre-existing per-article re-chunk behavior (PRESERVED, not modified)

PR 3 sadece dosya konumu değiştirir. Mevcut idempotent re-chunk davranışı **AYNEN korunur**:

- `chunk_article` içinde `DELETE FROM article_chunks WHERE article_id = :aid` SQL var — bir article re-process edildiğinde önceki chunks silinir + yenisi eklenir.
- Bu **bulk DELETE değil**; tek article scope.
- PR 3 bu davranışı **değiştirmez, genişletmez, batch hale getirmez ve smoke sırasında manuel tetiklemez**.

## Smoke acceptance (PR 3)

**Passive (BLOCKING):**
1. Worker registry: 6 `tasks.embedding.*` task names korundu
2. Queue routing `tasks.embedding.* → embedding_queue` korundu
3. Fast lane constant `FAST_EMBED_QUEUE = "embedding_fast_queue"` accessible
4. New paths import OK: `app.modules.embedding.tasks.embedding` modülü load + 6 task attr present
5. Old path: `app.workers.tasks.embedding` → `ModuleNotFoundError`
6. AST audit: embedding.py runtime sağlam
7. SQL/data safety: `git diff` SQL string'lerinde 0 satır değişim (mevcut DELETE/INSERT/UPDATE korundu)
8. 7 container × 6 pattern × ≥5 dk log scan: 0/0/0/0/0/0

**Active (READ-only) — N/A:**
- Embedding admin route YOK; READ-only active smoke step yok.

**Worker natural fire (NON-BLOCKING, ≤15 dk):**
9. Eğer pencerede fresh cleaned article olursa: `tasks.embedding.chunk_article` doğal dispatch + success log'da görülür → end-to-end zincir kanıtı
10. Pencerede fire görülmezse: "not observed within 15 min window, non-blocking"

**Manuel trigger: YAPILMAZ:**
- `tasks.embedding.rechunk_all` (toplu rechunk) — veri güvenliği invariant'ı
- Manual `chunk_article` — bulk reprocess yasak
- Direct DB/Redis manipulation — yasak

## Veri güvenliği invariant (kullanıcı kuralı)

- Existing chunks silinmeyecek
- Embeddings silinmeyecek
- Vector/index kayıtları silinmeyecek
- Truncate YOK
- Bulk reprocess / rechunk / reembed YOK
- Manual backfill / chunk trigger YOK
- Direct DB/Redis YOK
- Production article üzerinde state-changing smoke YOK

İhlal gerektirebilecek ihtiyaç çıkarsa: **implementation DUR + mini plan + açık onay**.

## References

- Boundary: [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- Import direction: [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- Refactor playbook: [`docs/engineering/refactor-playbook.md`](../../../../docs/engineering/refactor-playbook.md)
- Veri güvenliği memory: `feedback_embedding_rag_index_safety.md`
