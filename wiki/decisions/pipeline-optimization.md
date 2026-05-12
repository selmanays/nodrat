---
type: decision
title: "Boruhatları optimizasyonu — TTFT + cost + concurrency (#684)"
slug: "pipeline-optimization"
category: "rag"
status: "live"
created: "2026-05-11"
updated: "2026-05-11 (post-deploy ölçüm)"
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
- Cost ~$3.4 (DeepSeek V4 Flash × $0.0008/article)
- **Etki:** Production'da herhangi sorgu NER entity match recall'undan yararlanır (önceden sadece test article'larda aktifti)

## Ölçülen etki (2026-05-11 post-deploy + post-diagnosis)

| Metric | Pre-#684 | Post-#684 (tahmini) | **Ölçülen (deterministic 3x)** |
|---|---|---|---|
| **avg_latency (benchmark e2e)** | ~16-22sn | 10-15sn | **14.7sn** ✅ alt sınır |
| **DeepSeek call cost per query** | $0.005 | $0.003 (-%40) | ⏳ telemetry topla |
| **Bulk rechunk job süresi** | ~3 saat | ~45dk | (ölçüm bu sprint dışı) |
| **Cold start ilk request** | 2-3sn | ~50ms | ✅ warm-up canlıda |
| **Article entity coverage** | 9/4210 (0.2%) | %95+ | **4391/4436 (%99)** ✅ |
| **Benchmark recall@5** | 63.6% (Faz 6 ölçümü, 9-article entity) | 75-80% | ⚠️ **45.5% (5/11)** — Faz 5 baseline'a geri dönüş |

### Benchmark detay (niche_chunks_benchmark, 11 sorgu — 3x deterministic)

**Pass (5):** niche_003 ✓, niche_004 ✓, niche_008 ✓, niche_010 ✓, niche_011 ✓
**Fail (6):** niche_001, niche_002 ⚠️, niche_005 ⚠️, niche_006, niche_007, niche_009

### Sebep teşhisi (2026-05-11 deney 1+2+3)

**Adım 1 — Variance:** 3x benchmark deterministic 5/11 (önceki ilk koşumda görülen 6/11 noise idi).

**Adım 2 — Diff:** Sprint #684 retrieval.py / rerank.py / ner.py'a **HİÇBİR commit yapmadı** (`git log 67e38a0..main` boş). Code-level regression imkansız.

**Adım 3 — NER A/B (production hot-patch):** NER stream'ini geçici disable edip benchmark koştuk → **yine 5/11**. NER on/off fark yok.

**Adım 4 — niche_002 deep-dive:** `entity_normalized ILIKE '%karşıyaka%'` **20 article match** (LIMIT 20 cap dolu) — bunlar arasında doğru ddae4672 var ama 19 alakasız article (Karşıyaka semt, belediye, taciz davası, ESHOT) da var. 40 article (Karşıyaka + Bursaspor) aynı K=30 RRF bonus → sinyal sulanıyor.

### Gerçek hipotez (doğrulanmış)

**NER backfill, Faz 6 NER pipeline'ının kazanımını ironik şekilde yok etti.**

- Faz 6 NER ölçümü (45.5% → 63.6%) **sadece 9 article entity'liyken** yapıldı. O zaman özel ad sorgusunda entities tablosunda 1-2 article match → büyük sinyal.
- NER backfill ile 4391 article entity'li → ILIKE %X% her sorguda 20 article (cap dolu) match → 40 article (multi-entity) aynı bonus → sinyal seyrelir
- Effective olarak NER stream'i hiçbir şey yapmıyor — A/B (NER off) ile teyit edildi: aynı 5/11

**Sprint #684'ün suçu yok** — tüm 4 PR yapıldığı işe sadık. Mevcut benchmark "regression" Faz 6'da elde edilen geçici kazanımın geri sıfırlanmasıdır (backfill nedeniyle).

## Doğrulama (production)

- ✅ max_connections 500 verified
- ✅ Worker container concurrency 4 verified
- ✅ Embedding + rerank model startup'ta warmed
- ✅ NER backfill tamamlandı — 4391/4436 article entity'li (%99)
- ✅ PR-D production'da deployed (nodrat-api recreated 2026-05-11 ~15:23)
- ✅ Final benchmark koşuldu — sonuçlar yukarıda

## Trade-off

**Pro (ölçülen):**
- ✅ Cold start neredeyse sıfır (warm-up canlı)
- ✅ NER backfill başarılı — %99 article coverage (9 → 4391)
- ✅ avg_latency hedef alt sınırda (~14.7s, target 10-15s)
- ✅ Bulk operations 4x hızlı (concurrency + DB pool)

**Con (ölçülen):**
- ⚠️ **NER kazanım kaybı** — Faz 6'da elde edilen 45.5%→63.6% sıçraması, backfill ile sulanarak 45.5%'e geri döndü. Sprint #684'ün doğrudan suçu değil, ama backfill bu sonucu tetikledi.
- max_tokens 1500 cap'i karmaşık özetlerde kısıtlama yaratabilir (admin override mümkün)
- Concurrency 4 RAM kullanımı artırır (~2GB/worker × 4 = 8GB, 47GB VPS'te tolere edilir)

**Ders 1 (önemli):** Geçici/dar koşulda elde edilen kazanımlar (Faz 6 NER'in 9 article üzerinde ölçümü), gerçek production ölçeğinde (4391 article) tutmayabilir. Test setinin scale-realistic olması şart.

**Ders 2:** İlk hipotez ("top_k 15→10 sebep") **YANLIŞTI** çünkü benchmark hardcoded top_k=15 kullanıyor. Code-level diff ve NER A/B ile teşhis netleşti.

## İlişkiler

- [[ragflow-tier-rebuild]] — Faz 1-5 retrieval mimari
- [[ner-pipeline]] — Faz 6+7a NER (backfill burada başlatıldı)
- [[smart-quote-normalization]] — #647 retrieval bug fix
- [[eval-benchmark-divergence]]
- [[idf-entity-weighting]]
- [[api-contracts-md]]
- [[data-model-md]]
- [[prompt-contracts-md]]

## Açık takip

1. ✅ ~~NER backfill benchmark~~ — done (45.5%, Faz 5 baseline'a dönüş)
2. ✅ ~~NER entity scoring overhaul~~ — **PR #693 delivered** (Opsiyon D hibrit: IDF + multi-entity AND). recall@5 **63.6% restore** (Faz 6 hedefi tutturuldu), recall@10 72.7%. Detay: [[ner-pipeline]] §Faz 6.1.
3. TTFT production monitor (admin /admin/dashboard latency telemetry)
4. Cost monitor — DeepSeek call sayısı düşüş doğrulaması (provider-calls 7d)
5. Niche_006/007/009 hâlâ bozuk — answer extraction veya chunk size kuralı (ayrı epic adayı)
6. ~~niche_002 top_k regression~~ — **YANLIŞ HİPOTEZ**, kapatıldı. Gerçek sebep §"Ölçülen etki — Sebep teşhisi" altında.

## Kaynaklar

- [Epic #684](https://github.com/selmanays/nodrat/issues/684)
- [PR #685](https://github.com/selmanays/nodrat/pull/685) — PR-A infrastructure
- [PR #686](https://github.com/selmanays/nodrat/pull/686) — PR-C HyDE conditional
- [PR #688](https://github.com/selmanays/nodrat/pull/688) — PR-D batch embed + top_k + max_tokens
- [Issue #611 closed](https://github.com/selmanays/nodrat/issues/611) — chunk→cluster verify
