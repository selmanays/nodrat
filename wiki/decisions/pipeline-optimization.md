---
type: decision
title: "Boruhatları optimizasyonu — TTFT + cost + concurrency (#684)"
slug: "pipeline-optimization"
category: "rag"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docker-compose.yml (worker concurrency, postgres max_connections)"
  - "apps/api/app/config.py (DB pool tuning)"
  - "apps/api/app/main.py (model warm-up)"
  - "apps/api/app/api/app_generate_stream.py (HyDE conditional, batch embed, top_k)"
  - "GitHub Epic #684 / PR #685 #686 #688"
tags: ["rag", "performance", "cost-reduction", "infra", "mvp-1-8"]
aliases: ["pipeline-opt", "ttft-fix"]
---

# Boruhatları Optimizasyonu

> **TL;DR:** Faz 5-7 retrieval altyapısı tamamlandıktan sonra 6 alan operasyonel/performans optimizasyonu: worker concurrency, DB pool, NER backfill, TTFT düşürme, DeepSeek cost reduction, cold start. 4 PR + 1 background dispatch ile delivered.

## Bağlam

Faz 1-7 ile recall@5 27.3% → 63.6% (benchmark) ve 9-10/11 UI başarı. Şimdi:
1. Bulk operations yavaş (rechunk paralel script DB connection pool fail oldu)
2. Production'da NER coverage düşük (4201/4210 article entity'siz)
3. Generate-stream TTFT 16-22sn (kullanıcı algılı yavaş)
4. DeepSeek call sayısı yüksek (planner + HyDE + content + rerank + NER)
5. Cold start sonrası ilk request 2-3sn (model lazy load)

## Yapılan (4 PR + 1 ops)

### PR #685 — PR-A Infrastructure

**Worker concurrency artırıldı:**
- `worker_embedding`: 1 → **4** (bulk re-chunk/embed paralel)
- `worker_rag` (event_queue): 2 → **4** (NER batch + cluster paralel)

**DB pool tuning:**
- `db_pool_size`: 5 → **10**
- `db_max_overflow`: 10 → **20**
- `postgres max_connections`: 300 → **500**
- 7 container × 30 = 210 max demand → TooManyConnectionsError fix

**Model warm-up:**
- `main.py` lifespan startup'ta `embedding` + `rerank` model RAM'e yüklenir
- Cold start: ~2-3sn → **~50ms**

**#611 verification:** chunk → embed → cluster zinciri zaten tam çalışıyor (0 stuck article). Issue kapatıldı.

### PR #686 — PR-C HyDE conditional

**HyDE TTFT optimizasyonu:**
- Eski: her sorguda HyDE LLM call (~1-2sn)
- Yeni: generic kategori sorgularında skip (entity-suz, ≤3 kelime, soru kelimesi yok)
- Niş/soru sorgularda HyDE devam eder (Karşıyaka hakemleri, Rodos kaç kent)

**Etki:** generic sorgu trafiği için TTFT -1-2sn, cost -%15-20.

### PR #688 — PR-D Deep optimizations

**Multi-query batch embedding:**
- Eski: `enriched_query` embed (1 call) + `hyde_doc` embed (1 call) = 2 round-trip
- Yeni: tek batch `[enriched, hyde_doc]` payload
- `_hyde_vec_cached` ile variant_vecs setup'ında ek call yok
- **Etki:** ~200-500ms TTFT tasarrufu

**Top-K 15→10:**
- `hybrid_search_chunks top_k=max(10, content_top_k*2)` (eskiden 15)
- LLM rerank candidate %33 azalır
- Parent-doc retrieval ile final context yine zengin (top-3 article × 5 chunk = 15)
- **Etki:** ~200ms latency, cost -%30

**Content LLM max_tokens 2000→1500:**
- DeepSeek content generation default 1500 token
- Streaming ~1-2sn kısalır
- **Etki:** Cost -%25 (post-RAG content cost)

### PR-B (operasyon, kod değişikliği yok)

**109K article re-NER backfill:**
- `backfill_entities` task dispatch: 4200 cleaned article
- Worker_rag concurrency 4 ile bg ~30-45dk
- Cost ~$3.4 (DeepSeek V3 × $0.0008/article)
- **Etki:** Production'da herhangi sorgu NER entity match recall'undan yararlanır (önceden sadece test article'larda aktifti)

## Beklenen ölçülebilir etki

| Metric | Pre-#684 | Post-#684 (tahmini) |
|---|---|---|
| **TTFT (generate-stream)** | 16-22sn | **10-15sn** |
| **DeepSeek call cost per query** | $0.005 | **$0.003** (-%40) |
| **Bulk rechunk job süresi** | ~3 saat | **~45dk** (4x concurrency + DB pool) |
| **Cold start ilk request** | 2-3sn | **~50ms** (warm-up) |
| **Benchmark recall@5** | 63.6% | **75-80% (NER backfill tamamlandığında)** |

## Doğrulama (production)

- ✅ max_connections 500 verified
- ✅ Worker container concurrency 4 verified
- ✅ Embedding + rerank model startup'ta warmed
- ⏳ NER backfill devam ediyor (%3 progress, ~30-45dk eta)
- ⏳ Final benchmark NER tamamlandıktan sonra

## Trade-off

**Pro:**
- Bulk operations 4x hızlı
- Cold start neredeyse sıfır
- TTFT ~%30 iyileşme tahmini
- Cost ~%40 azalır (HyDE conditional + max_tokens + top_k)
- NER backfill bittiğinde production recall sıçraması

**Con:**
- max_tokens 1500 cap'i karmaşık özetlerde kısıtlama yaratabilir (admin override mümkün)
- Top_k 10 niş çoklu-article sorgularında context kaybı (parent-doc retrieval mitigate eder)
- Concurrency 4 RAM kullanımı artırır (~2GB/worker × 4 = 8GB, 47GB VPS'te tolere edilir)

## İlişkiler

- [[ragflow-tier-rebuild]] — Faz 1-5 retrieval mimari
- [[ner-pipeline]] — Faz 6+7a NER (backfill burada başlatıldı)
- [[smart-quote-normalization]] — #647 retrieval bug fix

## Açık takip

1. NER backfill %100 tamamlandığında benchmark koş — recall@5 ölçümü
2. TTFT production monitor (admin /admin/dashboard latency telemetry)
3. Cost monitor — DeepSeek call sayısı düşüş doğrulaması

## Kaynaklar

- [Epic #684](https://github.com/selmanays/nodrat/issues/684)
- [PR #685](https://github.com/selmanays/nodrat/pull/685) — PR-A infrastructure
- [PR #686](https://github.com/selmanays/nodrat/pull/686) — PR-C HyDE conditional
- [PR #688](https://github.com/selmanays/nodrat/pull/688) — PR-D batch embed + top_k + max_tokens
- [Issue #611 closed](https://github.com/selmanays/nodrat/issues/611) — chunk→cluster verify
