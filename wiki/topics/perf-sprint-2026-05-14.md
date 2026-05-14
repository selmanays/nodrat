---
type: topic
title: "RAG hız sprintı (2026-05-14) — 22s → 1s warm hit"
slug: "perf-sprint-2026-05-14"
status: "live"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/architecture.md§3"
tags: ["performance", "rag", "retrieval"]
aliases: ["ragflow-speed-parity", "sparse-bm25-bottleneck"]
---

# RAG hız sprintı — 2026-05-14

> **TL;DR:** Tek günde 5 PR ile niş sorgu retrieval latency'sini **21.8 sn → 1 sn warm hit / 4 sn cold miss**'e indirdik. Kalite regresyonu sıfır (recall@5 = 0.727 her aşamada). RagFlow seviyesi sub-saniye yanıt artık aynı sorgu için, cold miss de RagFlow tipik 2-3s aralığında.

## Bağlam

#778 RagFlow adaptation sprintı sonrası user UI testleri kalite konusunda büyük iyileşmeyi doğruladı ("çok ince detayları çok büyük oranda yakalıyor"). Ama hız hâlâ RagFlow'dan uzaktı. niche_chunks_golden benchmark **avg latency 21.8 saniye** gösteriyordu — RagFlow tipik 2-3 saniye.

User feedback: "RagFlow seviyesine gelelim, çok takıldık dağıldık".

## Profil tespiti — gerçek bottleneck

[`apps/api/app/core/retrieval.py:hybrid_search_chunks`] phase breakdown (DEBUG_TIMING=1 env):

| Faz | Süre (önce) |
|---|---|
| **sparse BM25 SQL** | **10-16 saniye** |
| dense pgvector | 3-30 ms |
| summary embedding | 1-3 ms |
| NER stream | 4-85 ms |
| keyword stream | 7 ms |
| critical_entity (rescue + filter) | 244-353 ms |
| parent_doc expansion | 3-1200 ms |

%99 sparse'tı. EXPLAIN ANALYZE: `idx_article_chunks_text_trgm` GIN bypass ediyor (functional expression mismatch), 13174 rows recheck.

## Sprint adımları (5 PR)

### [[chunk-text-norm-gin-trigram|PR #781 — chunk_text_norm + functional GIN trigram]]

`LOWER(REPLACE(REPLACE(...c.chunk_text...)))` inline ifade index'i bypass ediyordu. Çözüm: nullable kolon `chunk_text_norm` + BEFORE trigger + GIN trigram index. Sparse 14s → 5-6s.

### [[chunk-text-tsv-fts|PR #782 — tsvector FTS (RagFlow BM25 vibes)]]

Trigram uzun Türkçe sorgularda yine 13K satır match ediyordu (common trigram'lar). PostgreSQL native FTS — `chunk_text_tsv tsvector` + GIN + `to_tsquery('simple', word1 | word2 | ...)`. Sparse 5s → ~1s.

### [[llm-rerank-default-off|PR #783 — LLM rerank default OFF]]

A/B test: rerank ON vs OFF aynı recall (8/11), ama OFF -%18 latency. DeepSeek answer-aware "passage cevaplıyor mu" judgement mevcut pipeline'a marjinal değer katmıyor. Default'ı false yaptık.

### [[retrieval-cache|PR #784 — Redis retrieval cache (1h TTL)]]

`hybrid_search_chunks` çıktısı Redis-backed cache. Cache key: norm_query + retrieval params hash. Hit'lerde tüm pipeline atlanır. Warm-hit avg 1 saniye.

### [[planner-bypass-short|PR #785 — planner-bypass kısa entity-tipi sorgular]]

≤4 kelime + soru marker yok → planner LLM (2s) atlanır, sensible defaults uygulanır. "Trump", "Karşıyaka skor" tipi sorgular ~2s tasarruf.

## Sonuç metrik

niche_chunks_golden benchmark (11 sorgu):

| Aşama | recall@5 | avg_latency | hızlanma |
|---|---|---|---|
| #778 başlangıç | 0.727 | 21,815 ms | — |
| #781 GIN trigram | 0.727 | 9,504 ms | 2.3× |
| #782 tsvector | 0.727 | 5,032 ms | 4.3× |
| #783 LLM rerank OFF | 0.727 | 4,102 ms | 5.3× |
| **#784/#785 (cold)** | **0.727** | **4,064 ms** | **5.4×** |
| **#784/#785 (warm)** | **0.727** | **1,013 ms** | **21.5×** |

**Kalite regresyonu sıfır** — recall@5 8/11 her aşamada. Hâlâ broken 3 sorgu (niche_006/007/009) retrieval-katmanı değil **answer extraction** sorunu (chunk içi numeric span tespit eksikliği, gelecek sprint).

## Mimari sınıflandırma

| Layer | Tool |
|---|---|
| Inverted index (BM25-vibes) | PostgreSQL `tsvector` + `to_tsquery('simple', OR)` |
| Vector dense | pgvector `ivfflat` (bge-m3 1024-dim) |
| Article summary embedding | pgvector `ivfflat` |
| NER entity match | `entities` table + IDF threshold |
| Per-chunk keywords | varchar[] + GIN array overlap |
| Critical entity must-match | regex on a.clean_text + chunk.keywords (rescue + filter) |
| Cache (planner) | Redis 24h TTL |
| Cache (retrieval) | Redis 1h TTL |

## İlişkiler

- [[chunk-keyword-extraction]] — kalite altyapısı (#778)
- [[critical-entity-must-match]] — kalite altyapısı (#778)
- [[cross-encoder-rerank-disabled]] — #758 eski karar, #783 ile LLM rerank de kapatıldı
- [[chunks-first-retrieval]] — retrieval mimarisi temeli
- [[planner-cache-key-v2]] — planner cache versioning (gelecek)

## Açık konular

- **Answer extraction layer:** niche_006/007/009 chunk içi span tespiti gerek (sayısal değer / yüzde / oran)
- **Cross-encoder reranker reconsider:** yeni model (BAAI v2-gemma / mxbai / Cohere v3.5) eval gate
- **Stale risk:** retrieval cache 1h TTL içinde yeni article gelse bile bayat sonuç döner

## Kaynaklar

- [`apps/api/app/core/retrieval.py`](apps/api/app/core/retrieval.py)
- [`apps/api/app/core/retrieval_cache.py`](apps/api/app/core/retrieval_cache.py)
- [`apps/api/app/prompts/query_planner.py`](apps/api/app/prompts/query_planner.py)
- Migration [20260514_1100_chunk_text_norm.py](apps/api/alembic/versions/20260514_1100_chunk_text_norm.py)
- Migration [20260514_1200_chunk_text_tsv.py](apps/api/alembic/versions/20260514_1200_chunk_text_tsv.py)
- PRs: [#781](https://github.com/selmanays/nodrat/pull/781) [#782](https://github.com/selmanays/nodrat/pull/782) [#783](https://github.com/selmanays/nodrat/pull/783) [#784](https://github.com/selmanays/nodrat/pull/784) [#785](https://github.com/selmanays/nodrat/pull/785)
