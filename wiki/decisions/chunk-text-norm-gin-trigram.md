---
type: decision
title: "chunk_text_norm + functional GIN trigram index (#781)"
slug: "chunk-text-norm-gin-trigram"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "apps/api/alembic/versions/20260514_1100_chunk_text_norm.py"
  - "apps/api/app/core/retrieval.py"
tags: ["locked-decision", "performance", "rag"]
aliases: []
---

# chunk_text_norm + functional GIN trigram

> **Karar:** `article_chunks.chunk_text_norm` text kolonu + BEFORE INSERT/UPDATE trigger + `idx_article_chunks_text_norm_trgm` GIN gin_trgm_ops. Sparse BM25 query 14s → 5s.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

Sparse SQL `LOWER(REPLACE(REPLACE(...c.chunk_text...)))` inline ifade mevcut `idx_article_chunks_text_trgm` GIN trigram index'i **bypass** ediyordu (functional expression mismatch). PostgreSQL her query'de 12K satır × 19 REPLACE + LOWER full scan yapıyordu (10-16 sn).

## Çözüm

1. **Nullable column:** `ALTER TABLE article_chunks ADD COLUMN chunk_text_norm text` — anlık, table rewrite yok
2. **Trigger:** `fn_chunk_text_norm()` PL/pgSQL + `trg_chunk_text_norm BEFORE INSERT/UPDATE OF chunk_text` — yeni satırlarda otomatik populate
3. **Backfill:** single UPDATE 13169 satır (~10s)
4. **GIN index:** `CREATE INDEX idx_article_chunks_text_norm_trgm ON article_chunks USING gin (chunk_text_norm gin_trgm_ops)`
5. **Retrieval SQL:** inline ifade yerine `c.chunk_text_norm` direkt referans

## NOT — GENERATED STORED reddedildi

PostgreSQL container `/dev/shm` default 64MB. `ADD COLUMN ... GENERATED ALWAYS STORED` table rewrite shared memory'yi patlatıyor (`DiskFullError: could not resize shared memory segment to 1GB`). Trigger + nullable kolon yaklaşımı aynı sonucu memory-güvenli verir.

## Sonuç

Sparse 14s → 5s (#781). Sonraki adım tsvector FTS ile 5s → 1s (#782 / [[chunk-text-tsv-fts]]).

## İlişkiler

- [[chunk-text-tsv-fts]] — bir sonraki adım, FTS ile sparse 5s → 1s
- [[perf-sprint-2026-05-14]]
- [[chunks-first-retrieval]]

## Kaynaklar

- [PR #781](https://github.com/selmanays/nodrat/pull/781)
- [Migration 20260514_1100](apps/api/alembic/versions/20260514_1100_chunk_text_norm.py)
