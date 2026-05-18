---
type: topic
title: "Pipeline Performance Baseline & Tracking"
slug: "pipeline-performance-baseline"
category: "metrics"
status: "live"
created: "2026-05-08"
updated: "2026-05-08"
sources:
  - "apps/api/app/api/app_generate.py"
  - "apps/api/app/core/retrieval.py"
  - "apps/api/app/core/citation.py"
  - "apps/api/app/providers/deepseek.py"
  - "wiki/topics/mvp-roadmap.md (MVP-2.1)"
  - "GitHub Issue #391 (epic), #392-#398 (sub-issues)"
tags: ["performance", "baseline", "metrics", "rag", "tracking", "mvp-2.1"]
aliases: ["pipeline-baseline", "perf-tracking", "rag-baseline"]
---

# Pipeline Performance Baseline & Tracking

> **TL;DR:** /app/generate akışının baseline performans metrikleri (token, latency, cost, call count) MVP-2.1 milestone başlangıcında (**2026-05-08**) ölçüldü. Her PR'dan sonra bu sayfa güncellenir; gelişim ve regresyon tek bakışta izlenebilir.

## Bağlam

2026-05-08'de **`/app/generate` içerik üretim hattındaki** verimsizlikleri tespit etmek için kod tabanı taraması yapıldı. Bu sayfa **iki amaç** için var:

1. **Baseline:** Optimizasyondan önceki gerçek durum kaydedilir (token volume, latency breakdown, NIM/DeepSeek call sayıları, settings DB hit'leri).
2. **Tracking:** [[mvp-roadmap]]'taki MVP-2.1 epic'inde her PR merge sonrası güncellenir; before/after delta'sı net görülür.

> ⚠️ **Kapsam netliği:** Bu pipeline `/app/generate` endpoint'idir — kullanıcının doğal dil talebinden (örn. "şu konuda 3 tweet") **içerik üretimi** (X post / summary / thread / headline). Retrieval (embedding + reranking) bu akışın **alt adımları**dır, RAG pattern'i. `/ara` ise ayrı bir endpoint (Search-as-a-Service Phase B [#261](https://github.com/selmanays/nodrat/issues/261)) — sadece arama, içerik üretimi yok. MVP-2.1 optimizasyonlarının çoğunluğu `/app/generate`'e özgü (Content Generator context, citation validation batch, settings paralel yükleme); embedding/rerank-katmanı iyileştirmeleri (#396 short query, #398 embedding reuse) `/ara` akışına da kısmen yansır çünkü altyapı paylaşılır.

Ölçüm metodu: kod analizi + DeepSeek API response pattern + NIM provider call patterns. **Production runtime ölçümü değil** — gerçek prod metrikleri için `provider_call_logs` tablosu üzerinden 7-günlük rolling avg sonradan eklenmeli (TODO).

## Pipeline call sequence (baseline — 6 adım)

```
KULLANICI: "İsrail-Filistin bu hafta sert tonlu 3 tweet"
   │
   ▼
┌─ ADIM 1 ─ Query Planner ─────────────────────────┐
│ Provider: DeepSeek v4-flash (LLM call #1)         │
│ Input:  ~800 token                                │
│ Output: ~300 token                                │
│ Latency hedef: <2s P95                            │
└───────────────────────────────────────────────────┘
   │
   ▼
┌─ ADIM 2 ─ Query Embedding ───────────────────────┐
│ Provider: Local BAAI/bge-m3 (sentence-trans, CPU) │
│           registry name 'local_bge_m3', 1024-dim  │
│ Input:  ~50 token (topic + 5 keyword)             │
│ Output: 1024-dim vektör                           │
│ Latency: ~0.05-0.15s (local CPU)   │
└───────────────────────────────────────────────────┘
   │
   ▼
┌─ ADIM 3 ─ Hybrid Search (model değil, DB) ───────┐
│ pgvector dense + trigram sparse + RRF fusion      │
│ pool=30, top-k=10                                 │
│ Latency: ~0.1-0.2s                                │
└───────────────────────────────────────────────────┘
   │
   ▼
┌─ ADIM 4 ─ Reranker ──────────────────────────────┐
│ Provider: NIM nv-rerankqa-mistral-4b-v3           │
│           (cross-encoder)                         │
│ Input:  query + 10 passage (~6,000 char)          │
│ Output: skor sıralaması (top-k=10)                │
│ Latency: ~0.5-1s                                  │
└───────────────────────────────────────────────────┘
   │
   ▼
┌─ ADIM 5 ─ Content Generator ─────────────────────┐
│ Provider: DeepSeek v4-flash (LLM call #2)         │
│ Input:  ~5,000 token  ⚠️ EN AĞIR ADIM             │
│   (system prompt + retrieval plan + 10 kart       │
│    + supplementary chunks)                         │
│ Output: ~1,500 token                              │
│ Latency: 2-4s                                     │
└───────────────────────────────────────────────────┘
   │
   ▼
┌─ ADIM 6 ─ Citation Validation ───────────────────┐
│ Provider: Local bge-m3 (embedding #2 ile aynı)    │
│ Input: her post için ayrı (1 post + 10 fragment)  │
│ Output: cosine similarity skoru                   │
│ Latency: ~0.1-0.3s (5 post için 5 batch, lokal)   │
└───────────────────────────────────────────────────┘
   │
   ▼
KULLANICIYA SUN  (toplam: 4-8s P95)
```

## Baseline metrikleri (2026-05-08, MVP-2.1 ÖNCESİ)

### Per-request kaynak tüketimi

| Metrik | Baseline | Kaynak (kod referansı) |
|---|---|---|
| **DeepSeek input tokens** (Content Gen + Planner) | **~5,800** | [content_generator.py:29](../../apps/api/app/prompts/content_generator.py:29) + render payload |
| **DeepSeek output tokens** (Content Gen + Planner) | **~1,800** | max_tokens=2000 + planner ~300 |
| **DeepSeek cache hit ratio** | **~0%** | [deepseek.py:264-291](../../apps/api/app/providers/deepseek.py:264) — mekanik açık ama prompt prefix dynamic ([content_generator.py:406-437](../../apps/api/app/prompts/content_generator.py:406)) → cache miss garanti |
| **Embedding call/req** (local-primary, post-#345) | **6** | 1 query ([app_generate.py:369](../../apps/api/app/api/app_generate.py:369)) + 5 citation per-post ([app_generate.py:697-728](../../apps/api/app/api/app_generate.py:697)). Production VPS'te local CPU compute — NIM fallback. |
| **NIM rerank call/req** | **1** (her sorgu) | [retrieval.py:743-750](../../apps/api/app/core/retrieval.py:743) — `USE_LOCAL_RERANK=false` default, NIM aktif |
| **Settings store DB call/req** | **9** | candidate_pool, content_temp, max_tokens, citation_thr, suggest_enabled, prompts_store, retrieval.candidate_pool, min_semantic, min_text |
| **TR normalize call/req** | **1-2** | retrieval.py:511 (agenda) + retrieval.py:775 (chunks fallback) |

### Latency tahminleri (P50/P95)

| Aşama | P50 | P95 | Bottleneck |
|---|---|---|---|
| Query Planner | 1.0-1.5s | 1.5-2.0s | DeepSeek API round-trip |
| Embedding (query) | 0.05-0.1s | 0.1-0.2s | sentence-transformers CPU compute |
| Hybrid search (DB) | 0.05-0.1s | 0.1-0.2s | pgvector + trigram |
| Reranker | 0.4-0.7s | 0.5-1.0s | NIM cross-encoder |
| Content Generator | 2.0-3.0s | 2.5-4.0s | DeepSeek + uzun input |
| Citation validation | 0.2-0.5s | 0.3-0.8s | 6 NIM round-trip serial |
| Settings overhead | 0.05-0.1s | 0.1s | 9 sequential DB |
| **TOPLAM** | **~4s** | **~6-8s** | Content Gen + Citation dominantsı |

### Cost tahminleri (DeepSeek v4-flash liste fiyatı — indirim YOK, #990)

| Volume | Aylık DeepSeek \$/ay | Notlar |
|---|---|---|
| 100 req/gün | ~$8 | dev/test seviyesi |
| 1.000 req/gün | ~$80 | early prod |
| 10.000 req/gün | ~$800 | scale-up |
| 100.000 req/gün | ~$8.000 | mature SaaS |

> NIM (embedding+rerank) free tier — bu fiyatlandırmaya dahil değil. ⚠️ #990 (2026-05-18): "%75 kampanya" v4-flash için YANILGIYDI (yalnız deepseek-v4-pro). Yukarıdaki kaba projeksiyonlar v4-flash indirimsiz liste fiyatı ($0.14/$0.0028/$0.28) bazına göre yeniden türetilmeli (mertebe-tahmin; kesin re-derive ayrı follow-up — uydurma sayı yok).

## Tespit edilen verimsizlikler (baseline'da)

Sıralama: ROI'ye göre.

| # | Verimsizlik | Etki | İlgili PR/issue |
|---|---|---|---|
| 1 | **Content Generator context şişkin** (10 kart, ~5K input token) | Input token %40 fazla | [#393](https://github.com/selmanays/nodrat/issues/393) |
| 2 | **DeepSeek prompt cache hit ~0%** (system prompt'ta dinamik interpolation) | Cache savings %50+ kaybı | [#392](https://github.com/selmanays/nodrat/issues/392) |
| 3 | **Citation validation post başına ayrı NIM call** (5 post → 5 round-trip) | Latency 200-400ms | [#394](https://github.com/selmanays/nodrat/issues/394) ✅ PR [#411](https://github.com/selmanays/nodrat/pull/411) |
| 4 | **Settings store 9 ayrı DB call/req** | Latency 50-100ms | [#395](https://github.com/selmanays/nodrat/issues/395) ✅ PR [#411](https://github.com/selmanays/nodrat/pull/411) |
| 5 | **Kısa sorgularda gereksiz reranker pool** (pool=30 yine de) | Latency 300ms (short queries) | [#396](https://github.com/selmanays/nodrat/issues/396) |
| 6 | **Citation embedding source fragment'ları her seferinde re-embed** | NIM call -%80 fırsat | [#398](https://github.com/selmanays/nodrat/issues/398) |
| 7 | **Türkçe normalize duplicate** (chunks fallback path'te 2x) | -10ms (cleanup) | [#397](https://github.com/selmanays/nodrat/issues/397) ✅ PR [#411](https://github.com/selmanays/nodrat/pull/411) |

## Tracking — her PR merge sonrası güncelle

| Tarih | Olay | Δ Input tokens | Δ Latency P50 | Δ Latency P95 | Δ \$/req | Notlar |
|---|---|---|---|---|---|---|
| 2026-05-08 | **BASELINE** | 5,800 | ~4s | ~6-8s | $0.0036/req | İlk ölçüm — kod analizi |
| **2026-05-08** | **PR [#411](https://github.com/selmanays/nodrat/pull/411) ✅ MERGED** (#394+#395+#397) — commit `5de6461` | aynı | **tahmini -250-440ms** | **tahmini -300-500ms** | aynı | Citation 6→1 batch + settings 5→1 gather + normalize 1x. NIM free → \$ kazanç yok. CI runner allocation outage'ı nedeniyle admin override + manuel VPS deploy. Lokal pytest 25/26 PASS. Smoke test PASS (nodrat.com /api/health 200, /ara 200, /app/generate 401-no-auth). |
| **2026-05-08** | **PR [#416](https://github.com/selmanays/nodrat/pull/416) ✅ MERGED** (#396+#398) — commit `eddcca21` | aynı | **tahmini -50-90ms** (citation reuse) | **tahmini -150-300ms** (short queries) | aynı | Citation source fragment'lar agenda_cards.embedding'den reuse → embed_fn input %50-100 azalır. Short query candidate_pool 30→10. Lokal pytest 29/30 PASS. Smoke test PASS. |
| **2026-05-08** | **PR [#418](https://github.com/selmanays/nodrat/pull/418) ✅ MERGED** (#392+#393) — commit `4ad9ac11` | **5,800 → ~3,200 (-%36)** | aynı | aynı | **-%25 to -%35** (cache hit + token reduction birleşik) | PROMPT_VERSION 1.1.0: 4 SYSTEM_PROMPT_* tamamen STATIC; max_posts/tone user_payload'tan; tone instruction dynamic append KALDIRILDI. Content top_k 10→5 (admin tunable `retrieval.content_top_k`, range 3-10). DeepSeek implicit prompt cache hit ratio ≥%40 hedef. **⚠️ Eval-gated**: production halü <%2 + citation accuracy ≥%95 monitor; alarm fire ederse rollback (`4ad9ac11` revert). |
| **2026-05-08** | **PR [#431](https://github.com/selmanays/nodrat/pull/431) ✅ MERGED** (#429 + #432) — epic close-out preparation | aynı | aynı | aynı | aynı | prompt-contracts.md v0.1 → v0.2 (kod-doküman uyumu). Yeni `/admin/dashboard/mvp-2-1-delta` ölçüm endpoint'i (geçici isim, #441 ile refactor edildi). Lokal pytest 48/48 PASS. |
| **2026-05-08** | **PR [#441](https://github.com/selmanays/nodrat/pull/441) ✅ MERGED** (#440) — endpoint + UI refactor | aynı | aynı | aynı | aynı | Eski `/admin/dashboard/mvp-2-1-delta` SİLİNDİ. Yerine jenerik `GET /admin/rag/pipeline-comparison` (iki tarih aralığı, milestone-bound değil). UI: `/admin/rag` Performans sekmesi (browser üzerinden kullanılabilir). Lokal pytest 49/49 PASS. Karar sayfaları: [[endpoint-naming-policy]], [[pipeline-observability-location]]. |
| **2026-05-08** | 🎯 **MVP-2.1 epic [#391](https://github.com/selmanays/nodrat/issues/391) — kod tamam** | **5,800 → ~3,200** | tahmini iyileşme | tahmini iyileşme | **~%25-35** | 7/7 sub-issue closed (#392-#398). 5 PR (#411 + #416 + #418 + #431 + #441). 19 gün öncesinde teslim (hedef 2026-05-28). Production verisi 2026-05-15 sonrası ölçülecek (post window 7-gün dolduğunda). |
| _beklenen 2026-05-15_ | **Production 7-day delta ölçüm** | (gerçek değer) | (gerçek değer) | (gerçek değer) | (gerçek değer) | `/admin/rag/pipeline-comparison?from_a=2026-05-01&to_a=2026-05-08&from_b=2026-05-08&to_b=2026-05-15` çağrısı. Acceptance hedefleri: input_tokens ≤ -25%, p95 ≤ -8%, $/req ≤ -20%, halu_flag_rate ≤ +0%. Tutuyorsa epic [#391](https://github.com/selmanays/nodrat/issues/391) kapatılır. |
| **2026-05-09** | 🚀 **MVP-2.2 — PR [#528](https://github.com/selmanays/nodrat/pull/528) ✅ MERGED** (#527) — commit `e29b26a8` | aynı | aynı (toplam wall-time aynı) | **TTFT 5-7s → ~600-800ms (-%85)** | aynı (cost tracking final chunk'tan birebir) | **SSE streaming + speculative retrieval + planner cache.** TTFT artık first-token-visible; toplam content gen latency aynı, kullanıcı blank page yerine ~700ms'de yazılan ilk post'u görüyor. 4 değişiklik: (1) DeepSeek `stream:true` + `stream_options.include_usage:true` ([[deepseek]] streaming kapasitesi); (2) `embed(raw_query)` planner ile paralel ([[speculative-retrieval]]); (3) Redis 24h gün-granülü plan cache ([[planner-cache]]); (4) Server-side incremental JSON parser ([[streaming-json-parser]]) → post-by-post `event: post` SSE emit. Citation + image post-stream paralel; FSEK 25-kelime + halü gate'leri korunur ([[twenty-five-word-quote-cap]] + [[pii-redaction-mandatory]] aktif). Eski `/app/generate` aynen duruyor (backward-compat). Karar sayfası: [[sse-streaming-default]]. CI runner allocation outage → admin override + manuel SSH deploy 2026-05-09 17:58 UTC. Lokal: 31 yeni test PASS, frontend tsc/lint/build clean, smoke test PASS (nodrat.com /api/app/generate-stream 401-no-auth, /api/app/generate 401-no-auth, /api/health 200/165ms). |

> **PR #411 production'da aktif (2026-05-08, ~22:43 UTC):**
> - `validate_citations_batch` artık `/app/generate` citation phase'inde tek mega-batch'te çalışıyor — N post için N+1 NIM call yerine 1
> - 5 settings (rerank.candidate_pool, llm.content_temperature, llm.content_max_tokens, citation.cosine_threshold, media.suggestion_enabled) request başında `asyncio.gather` ile paralel yükleniyor
> - Türkçe normalize (`normalize_tr_query`) handler düzeyinde tek seferde — `pre_normalized` parametresiyle hybrid_search_*'a geçiyor

> **PR #416 production'da aktif (2026-05-08, ~23:04 UTC):**
> - Citation source fragment'ları artık agenda_cards.embedding'den DB üzerinden geliyor (NIM re-embed gereksiz). validate_citations + validate_citations_batch source.embedding pre-set ise sadece sentence'ları embed_fn'e gönderiyor.
> - Query Planner çıktısına `is_short_query` bayrağı eklendi (post-normalize topic_query ≤2 kelime). Handler kısa sorgularda candidate_pool 30→10 override yapıyor (rerank zaten skip ediyordu, dense+sparse pool da küçüldü).

> **PR #418 production'da aktif (2026-05-08, ~23:30 UTC) — MVP-2.1 epic kapanış commit'i:**
> - PROMPT_VERSION 1.0.0 → 1.1.0. Tüm 4 SYSTEM_PROMPT_* (X_POST/SUMMARY/THREAD/HEADLINE) artık STATIC: `{max_posts}`/`{item_count}` placeholder'lar kaldırıldı, sayı bilgisi user payload'undaki `output_constraints.max_posts`'tan okunur.
> - Tone instruction dynamic append (`TON KURALI:`) KALDIRILDI; system prompt rule 10 kanonik 9-tone tablosu. `output_constraints.tone` user payload'undan referans.
> - Content Generator top_k 10→5 (admin tunable `retrieval.content_top_k`, default 5, range 3-10). Supplementary chunks 8→4.
> - **⚠️ Eval-gated:** production halü oranı + citation accuracy 30-60 dk monitor. Alarm fire ederse rollback (revert `4ad9ac11`).
> - 7 günlük rolling avg `provider_call_logs` query'si TODO listesinde (production data ile gerçek delta'yı doğrulamak için).

> **PR #528 production'da aktif (2026-05-09, ~17:58 UTC) — MVP-2.2 SSE streaming:**
> - Yeni endpoint `POST /app/generate-stream` (`text/event-stream`); event sequence: `meta` → `progress` → `chunk` → `post` (her tamamlanan post anlık) → `parsed` → `citation` (post-stream) → `image` → `done`. Eski `/app/generate` aynen korunur.
> - DeepSeek `stream:true` + `stream_options.include_usage:true`; final chunk usage+cost dolu, cost tracking eski path ile birebir aynı kayıt → R-FIN-01 etkilenmez.
> - **Planner cache** (qp:v1:sha1(req+locale+tier+yyyymmdd)) Redis 24h TTL; gün-granülasyonu gündem semantiği için. Hit ratio %20-40 hedef (7-day rolling sonra ölçülecek). Cache hit ~10ms vs LLM ~1.5s.
> - **Speculative retrieval:** `embed(raw_query)` planner ile paralel başlar; raw≈enriched ise embedding reuse (~150-300ms net kazanç).
> - **StreamingPostExtractor:** server-side incremental JSON parser; `posts[N]` objelerini tamamlanır tamamlanmaz `event: post` ile emit eder. Edge case'ler tested: chunk boundary, escape `\"`, string içi `}`, malformed obje skip, posts array close.
> - **Citation + image post-stream:** `asyncio.gather` paralel; FSEK 25-kelime + halü gate'leri korunur, kullanıcının ilk byte'ını bloklamaz (Perplexity yaklaşımı).
> - **Frontend:** `useGenerationStream` hook + `StreamingPreview` component; `/app/generate` page'i SSE consumer oldu. Eski `apiFetch /app/generate` admin/diğer flow'larda hâlâ kullanılıyor.
> - Manuel deploy (CI runner allocation outage devam ediyor): admin override merge + SSH rsync + docker compose build/up. Smoke test PASS.
> - **TTFB metric:** `done` event'inde `ttfb_ms` döner; `/admin/rag` Performans sekmesine kalıcı kolon eklenmesi sonraki tur (provider_call_logs schema değişikliği gerekiyor).

> Bu tablo **wiki/topics/pipeline-performance-baseline.md** içinde tutulur. Her PR merge sonrası güncellenir.

## Production telemetry hooks

İlk yazıldığında bu liste TODO idi. PR [#441](https://github.com/selmanays/nodrat/pull/441) ile gerçek production telemetry endpoint'i + UI deploy edildi.

- [x] ~~`provider_call_logs` tablosundan 7-günlük rolling avg input_tokens sorgusu~~ → ✅ [`apps/api/app/api/admin_rag.py`](../../apps/api/app/api/admin_rag.py) `_PIPELINE_PROVIDER_METRICS_SQL`
- [x] ~~`generation_log.cached_tokens / total_input_tokens` cache hit ratio metric~~ → ✅ Aynı endpoint, response.period_*.cache_hit_ratio
- [x] ~~Pipeline performance comparison UI~~ → ✅ `/admin/rag` "Performans" sekmesi (PR #441)
- [ ] Eval suite ([#386](https://github.com/selmanays/nodrat/issues/386)) production runner ile entegre et — her PR sonrası otomatik delta hesaplama (MVP-3 cut-over)
- [ ] CI cron / Slack alerting — pipeline-comparison her hafta otomatik koş, sapma varsa uyar

### Production endpoint kullanım

```bash
# Default: son 7 gün (B) vs önceki 7 gün (A)
GET /admin/rag/pipeline-comparison

# Custom: belirli bir deploy etrafında pre/post
GET /admin/rag/pipeline-comparison?from_a=2026-05-01T00:00:00Z&to_a=2026-05-08T00:00:00Z&from_b=2026-05-08T00:00:00Z&to_b=2026-05-15T00:00:00Z
```

Browser yolu: https://nodrat.com/admin/rag → "Performans" sekmesi. Detaylı sözleşme: [docs/engineering/api-contracts.md §10.4](../../docs/engineering/api-contracts.md).

## İlişkiler

- **İlgili kararlar:** [[deepseek-default-llm]] (cache mekanik), [[claude-haiku-premium-llm]] (Pro tier'da metrikler farklı olacak), [[endpoint-naming-policy]] (jenerik endpoint adı), [[pipeline-observability-location]] (UI yeri)
- **İlgili varlıklar:** [[deepseek]] (Content Generator + Planner), [[local-bge-m3]] (Embedding adımları 2+6), [[risk-cost-runaway]] (R-FIN-01 mitigation M7)
- **İlgili kavramlar:** [[provider-abstraction]] (tek arayüz cost tracking)
- **İlgili topics:** [[mvp-roadmap]] (MVP-2.1 milestone), [[llm-provider-strategy]] (cache risk satırı)
- [[data-pipelines]]

## Açık sorular / TODO

- **Production data eklenmedi:** Tahmini ölçümler kod tabanı + provider response pattern'e dayalı. Gerçek `/app/generate` request log'undan 7-günlük percentile çıkarmak gerekli. `provider_call_logs` query yazılmalı.
- **Eval suite delta automation:** [#386](https://github.com/selmanays/nodrat/issues/386) production runner ile bu sayfanın "Tracking" tablosunu otomatik güncelleyecek script (CI cron) yazılabilir.
- **Tier-bazlı baseline farklılığı:** Pro/Agency tier'da Content Generator Haiku'ya geçer — metrikler değişir. Şu an MVP-2 sonrası prod'da %100 free tier; Pro launch (MVP-3) sonrası bu sayfa "Free tier" + "Pro tier" iki sekme halinde tutulmalı.
- **Embedding/rerank local'e geçişi:** USE_LOCAL_EMBEDDING ve USE_LOCAL_RERANK flag'leri açılınca latency profili değişir (NIM HTTP yerine CPU compute). Migration sonrası bu sayfada ayrı bir snapshot satırı.

## Kaynaklar

- [apps/api/app/api/app_generate.py](../../apps/api/app/api/app_generate.py) — handler call sequence
- [apps/api/app/core/retrieval.py](../../apps/api/app/core/retrieval.py) — hybrid search + reranker integration
- [apps/api/app/core/citation.py](../../apps/api/app/core/citation.py) — validate_citations + (yeni) validate_citations_batch
- [apps/api/app/providers/deepseek.py](../../apps/api/app/providers/deepseek.py) §264-291 — cache hit/miss parsing
- GitHub Epic [#391](https://github.com/selmanays/nodrat/issues/391) + sub-issues #392-#398
- GitHub PR [#411](https://github.com/selmanays/nodrat/pull/411) — first 3-issue batch
- [[mvp-roadmap]] §MVP-2.1
- [[risk-cost-runaway]] M7 mitigation
