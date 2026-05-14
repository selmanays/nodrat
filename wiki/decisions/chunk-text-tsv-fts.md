---
type: decision
title: "tsvector FTS — sparse trigram bypass (#782)"
slug: "chunk-text-tsv-fts"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "apps/api/alembic/versions/20260514_1200_chunk_text_tsv.py"
  - "apps/api/app/core/retrieval.py"
tags: ["locked-decision", "performance", "rag", "postgres-fts"]
aliases: ["tsvector", "ragflow-bm25-vibes"]
---

# tsvector FTS — sparse trigram bypass

> **Karar:** `article_chunks.chunk_text_tsv tsvector` + GIN tsvector index + `to_tsquery('simple', word1 | word2 | ...)` OR semantics. Sparse 5s → ~1s.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

[[chunk-text-norm-gin-trigram]] sparse'ı 14s → 5s'ye indirdi. EXPLAIN ANALYZE: uzun Türkçe query'lerde GIN trigram bitmap **13208 satır match** ediyor (common trigram'lar yüzünden tablonun çoğu), heap recheck 2.8s alıyor.

## Çözüm

PostgreSQL native FTS — inverted index (Elasticsearch BM25 vibes):

1. **Column:** `ALTER TABLE article_chunks ADD COLUMN chunk_text_tsv tsvector`
2. **Trigger:** `fn_chunk_text_tsv()` PL/pgSQL — `to_tsvector('simple', chunk_text_norm)`, `BEFORE INSERT/UPDATE OF chunk_text_norm`
3. **Backfill:** single UPDATE 13169 satır
4. **GIN index:** `CREATE INDEX idx_article_chunks_text_tsv ON article_chunks USING gin (chunk_text_tsv)`
5. **Retrieval SQL:** trigram `c.chunk_text_norm % :q` → `c.chunk_text_tsv @@ to_tsquery('simple', :tsq)`

## Neden OR semantics ('word1 | word2 | word3')?

`websearch_to_tsquery` default AND — TÜM kelimeler match olmalı. Türkçe suffix variant'larında (`maçının` ≠ `maç`) AND çok sıkı → recall düşer.

Python-side: `tsq = " | ".join([w for w in query.split() if 3 <= len(w) <= 30])` (special chars temizlenir). `to_tsquery('simple', :tsq)` herhangi bir kelime match yeterli. `ts_rank` skoru overlap'i ödüllendirir (BM25-vibes).

## Neden 'simple' config?

Türkçe stemmer yok. Stemming `maçının → maç` istenmeyen match yaratırdı (entity'ler exact match gerekir).

## Sonuç

Sparse 5s → ~1s. recall@5 sabit (0.727 → 0.727). PR-F2 [#782](https://github.com/selmanays/nodrat/pull/782).

## İlişkiler

- [[chunk-text-norm-gin-trigram]] — bir önceki adım
- [[perf-sprint-2026-05-14]]
- [[chunks-first-retrieval]]

## Kaynaklar

- [PR #782](https://github.com/selmanays/nodrat/pull/782)
- [Migration 20260514_1200](apps/api/alembic/versions/20260514_1200_chunk_text_tsv.py)
