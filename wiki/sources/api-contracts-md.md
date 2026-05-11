---
type: source
title: "docs/engineering/api-contracts.md — API Sözleşmeleri (OpenAPI Spec)"
slug: "api-contracts-md"
status: "ingested-summary"
source_path: "docs/engineering/api-contracts.md"
source_version: "v0.7"
created: "2026-05-11"
updated: "2026-05-11 (#698 v0.7 — admin RAG 4 yeni endpoint yansıması)"
ingest_method: "summary-only (full endpoint extraction deferred)"
tags: ["docs", "api", "openapi", "rest", "engineering"]
---

# Source: docs/engineering/api-contracts.md

> **TL;DR:** Nodrat REST API'nin kanonik sözleşme dokümanı (OpenAPI tarzı). 11 ana bölüm, 80+ endpoint, 2217 satır. Public + auth + admin + user generation kapsar.

## Section Map

| § | Başlık | Kapsam |
|---|---|---|
| 0 | Yönetici Özeti | API design prensipleri |
| 1 | Genel Konvansiyonlar | RFC 7807 errors; pagination; rate limit; auth flow; idempotency |
| 2 | Public Endpoints | health, readiness, **trial generate** |
| 3 | Auth Endpoints | register/login/refresh/logout/forgot/reset/verify; 2FA (Faz 6) |
| 4 | Admin: Source Management | CRUD + test-listing/test-detail/crawl-now/health |
| 5 | Admin: Article Management | list/get/reprocess/raw |
| 6 | Admin: Queue Management | overview, retry, dead-letter |
| 7 | Admin: Provider Config | model_providers CRUD + telemetry |
| 8 | Admin: Image & Entity (Faz 4) | VLM tagging, entity review |
| 9 | Admin: User & Plan Management | quota, plan upgrades, KVKK |
| 10 | Admin: Observability | RAG dashboard endpoints, citation stats, rerank stats, **inspect-query**, **benchmark/run**, raptor clusters |
| 11 | User: Generation (Ana Akış) | `POST /api/generate`, `POST /api/generate/stream` (SSE) |
| 11.X | Admin: Settings Panel (#262) | `GET/PUT /admin/settings`, group-aware |
| 11.Y | Admin: SFT Data Pipeline (#569) | training_samples lifecycle |

## #696 Sprint açısından önemli endpointler

### Admin: RAG İzlencesi (§10)

| Endpoint | Bu sprint değişiklik |
|---|---|
| `GET /admin/rag/health` | #696 B6 — `warm_up` alanı eklendi (duration_ms / embedding_ms / rerank_ms) |
| `POST /admin/rag/benchmark/run` | #696 Faz A — `suite=cards\|chunks`, `candidate_pool` param; #700 async background |
| `GET /admin/rag/benchmark/history` | (mevcut) |
| **`GET /admin/rag/benchmark/status`** | #700 yeni — polling endpoint |
| `POST /admin/rag/inspect-query` | #696 B4 — response'a `ner: InspectNerInfo` + `suite` param |
| **`GET /admin/rag/ner-stats`** | #696 B5 yeni — mode dağılımı (process-lifetime) |

### User: Generation (§11)

| Endpoint | #684 değişiklik |
|---|---|
| `POST /api/generate/stream` | PR-D: `top_k` 15→**10** default; `content_max_tokens` 2000→**1500**; HyDE conditional (PR-C); batch embedding |

### Admin: Settings (§11.X)

`GET /admin/settings?group=retrieval` — 9 yeni `retrieval.*` key (PR #701 sonrası):
- ner_df_threshold, ner_k_multi, ner_k_single_rare, ner_fetch_per_entity_limit, ner_final_aids_cap
- rrf_k, rrf_k_summary, rrf_phrase_boost, rrf_gram_boost

## İlişkiler

- [[pipeline-optimization]] — PR-D endpoint defaults (top_k, max_tokens)
- [[idf-entity-weighting]] — retrieval.* settings keys
- [[hyde-feature-flag]] — HyDE conditional behavior
- [[eval-benchmark-divergence]] — cards vs chunks suite

## Versiyon takibi

| Doküman v | Tarih | Notlar |
|---|---|---|
| v0.5 | 2026-05-08 | Pre #684 |
| v0.6 | 2026-05-10 | SFT pipeline endpoints (§11.Y) |
| (gelecek #698) | — | top_k=10 / max_tokens=1500 defaults yansıması + warm_up/ner-stats/benchmark/status yeni endpoint'leri |

## Açık takip

1. **#698 stale değer güncellemesi**: `/api/generate` top_k default 15→10, max_tokens 2000→1500, HyDE conditional davranışı
2. **#696/#700 yeni endpoint'leri ekle**: `/admin/rag/ner-stats`, `/admin/rag/benchmark/status`
3. **Detay endpoint extraction** sonraki sprintte (her endpoint için kendi sayfası gerekiyorsa)

## Kaynaklar

- [docs/engineering/api-contracts.md](../../docs/engineering/api-contracts.md) (v0.6)
