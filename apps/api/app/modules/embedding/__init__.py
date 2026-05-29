"""Module: embedding

Layer: middle (master plan §1.3 — articles/entities kernel'in üstü; rag/generations'ın altı)
Status: Phase 3 PR 3'te aktif (Celery tasks taşıması — admin route YOK).

Public API:
    tasks   — Celery task module (string-bound: tasks.embedding.*)

Task surface (6 task — string identity DEĞİŞMEZ):
    tasks.embedding.chunk_article
    tasks.embedding.embed_chunks
    tasks.embedding.embed_article_summary
    tasks.embedding.backfill_article_summaries
    tasks.embedding.rechunk_all
    tasks.embedding.extract_chunk_keywords

Storage dependency:
    `app.shared.workers.db_session` (Phase 3 PR 1a)
    `app.modules.articles.models` — Article (T8-12b: 2026-05-28 taşındı)

Provider dependency:
    `app.providers.registry` + `app.providers.local_embedding` (NIM/local SBERT)
    `app.providers.base.Message` (LLM keyword extraction)

Legacy dependencies (Phase 4'e kadar):
    `app.core.chunker` — chunking config + segmentation
    `app.core.cost_tracker` — provider call accounting
    `app.core.semantic_chunker` — embedding-based semantic chunking (lazy)
    `app.prompts.chunk_keywords` — LLM keyword extraction prompt
    `app.shared.runtime_config.{settings_store, prompts_store}` — runtime config

Cross-module lazy imports (allowed direction):
    `app.modules.entities.tasks.entities` — extract_article_entities (lazy)
    `app.modules.clusters.tasks.clustering` — cluster_article (lazy; chain dispatch)

Admin route: YOK (embedding'in kendi admin endpoint'i yok; observability admin_rag context'inde)

See:
- wiki/plans/modular-monolith-transition-master-plan.md §1.3 / §12.3
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/import-direction-rules.md
"""
