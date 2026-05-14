---
type: decision
title: "LLM rerank default OFF — A/B kanıt"
slug: "llm-rerank-default-off"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/architecture.md§3"
tags: ["locked-decision", "rag", "performance"]
aliases: []
---

# LLM rerank default OFF

> **Karar:** `retrieval.llm_rerank_enabled` default `false`. Question-tipi sorgularda DeepSeek "passage cevaplıyor mu" judgement çağrısı atlanır.
> **Durum:** locked
> **Tarih:** 2026-05-14

## A/B kanıt (niche_chunks_golden 11 sorgu)

| Metrik | ON | OFF | Δ |
|---|---|---|---|
| recall@5 | 0.727 (8/11) | 0.727 (8/11) | aynı |
| recall@10 | 0.727 | 0.727 | aynı |
| MRR@10 | 0.636 | 0.636 | aynı |
| avg_latency | 5,032 ms | 4,102 ms | **-%18** |

## Bağlam

Faz 4 LLM rerank (#652, 2026-05): DeepSeek top-3 chunk'a "Bu passage sorguyu cevaplıyor mu?" sorar, evet/hayır boost. Cost guard: sadece question marker'lı sorgularda tetiklenir.

#778 sprintında pipeline güçlendirildi: RRF (sparse tsvector + dense pgvector + summary) + critical_entities MUST_MATCH + chunk_keywords stream + NER entity boost. Bu setup'ta LLM rerank ek değer katmıyor.

## Alternatifler

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| ON tutmak | Question query'lerde "küçük tweak" şans | ~1s latency + ~$0.001/query, kalite katkısı 0 (A/B) | **reddedildi** |
| Cross-encoder rerank (geri) | Lokal, ~50ms | #758 eval gate fail (NDCG 0.627→0.509, recall 8→7) | reddedildi |
| **Default OFF + admin tunable** | Hız + cost + geri açma kolay | Yeni model gelirse re-test gerek | **seçildi** |

## Sonuçlar

- Admin /settings/retrieval → `llm_rerank_enabled = true` ile açılabilir
- Mevcut production DB override `true` idi → `false`'a güncellendi
- Cost: ~%70 user query question-tipiydi, ~$0.001 her birinde → ~$0.7/1000 query tasarruf
- Latency: ~1s azalma her question-tipi query'de

## Geri alma maliyeti

> Admin /settings/retrieval'dan tek tık. Yeni reranker modeli (BAAI v2-gemma / mxbai / Cohere v3.5) test edilirse cross-encoder geri açılabilir.

## İlişkiler

- [[cross-encoder-rerank-disabled]] — #758 eski karar
- [[perf-sprint-2026-05-14]] — bu sprintın parçası
- [[chunks-first-retrieval]] — mevcut pipeline yeterli

## Kaynaklar

- [PR #783](https://github.com/selmanays/nodrat/pull/783)
- [`apps/api/app/core/rerank.py`](apps/api/app/core/rerank.py)
