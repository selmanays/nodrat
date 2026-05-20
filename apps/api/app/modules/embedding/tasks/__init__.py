"""Embedding Celery tasks — Phase 3 PR 3'te modules/embedding altına taşındı.

Task names AYNEN (string-bound, decorator'dan kanıt):
    tasks.embedding.chunk_article             — bind=True, max_retries=2 (article → chunks INSERT)
    tasks.embedding.embed_chunks              — chunks → embedding column UPDATE
    tasks.embedding.embed_article_summary     — article summary embedding
    tasks.embedding.backfill_article_summaries — maintenance
    tasks.embedding.rechunk_all               — manuel toplu rechunk (kullanıcı invariant: smoke'da TETİKLENMEZ)
    tasks.embedding.extract_chunk_keywords    — LLM-based keyword extraction

Queue routing: tasks.embedding.* → embedding_queue (celery_app.py task_routes)
Fast lane constant: FAST_EMBED_QUEUE = "embedding_fast_queue" (adanmış worker_embedding_fast)

Beat schedule: Embedding tasks direkt Beat'te YOK; articles chain-dispatch ile tetiklenir
  - articles.backfill_missing_chunks (every 2h) → embedding_queue
  - articles fetch_detail → cleaned status → chain → tasks.embedding.chunk_article

Pre-existing per-article re-chunk behavior preserved, not modified:
  - chunk_article içinde `DELETE FROM article_chunks WHERE article_id = :aid` (idempotent re-process)
  - PR 3 sadece dosya konumu değiştirir; bu SQL davranışına dokunulmaz.
"""
