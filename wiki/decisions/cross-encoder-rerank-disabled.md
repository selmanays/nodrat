---
type: decision
title: "Cross-encoder reranker production'da kalıcı kapalı — 3 model eval negatif (#750, #760)"
slug: "cross-encoder-rerank-disabled"
status: "locked-permanent"
decided_on: "2026-05-10"
eval_confirmed_on: "2026-05-13"
decided_by: "tech"
created: "2026-05-12"
updated: "2026-05-13 (#760 Jina v2 multilingual eval negatif → 3. model de başarısız, karar kalıcı)"
sources:
  - "app_settings DB: retrieval.cross_encoder_enabled=false (2026-05-13)"
  - "apps/api/app/core/rerank.py (cross-encoder + LLM rerank katmanları)"
  - "apps/api/app/providers/local_jina_rerank.py (#760 yeni provider)"
  - "apps/api/scripts/eval_rerank_ab.py (#750 eval runner — 3 mode)"
  - "apps/api/tests/eval/niche_chunks_benchmark.py (#760 standalone benchmark)"
  - "wiki/decisions/ragflow-tier-rebuild.md (Faz 4 LLM rerank)"
  - "wiki/decisions/ner-pipeline.md"
  - "GitHub Issue #251, #252, #254, #259, #260, #347, #614, #750, #758, #760"
tags: ["locked-decision", "rag", "rerank", "production-state", "mvp-1-8", "eval-confirmed", "3-models-tested"]
aliases: ["rerank-off", "no-cross-encoder", "jina-v2-rejected"]
---

# Cross-encoder reranker production'da kalıcı kapalı

> **Karar:** Cross-encoder reranker production'da **kalıcı kapalı**. 3 farklı model (NIM rerank-qa-mistral-4b, local bge-reranker-v2-m3, Jina v2 base multilingual) baseline'dan **kötü** çıktı. `retrieval.cross_encoder_enabled = false`.
> **Durum:** **locked-permanent** (3 model × eval-confirmed) — yeni model denemesi için kalite eşiği gereklilik aynı: NDCG@10 ≥ 0.90 VEYA recall@5 +5pp.
> **Tarih:** 2026-05-10 ilk kapatma → 2026-05-12 eval gate (#750, 2 model) → 2026-05-13 (#760 Jina v2 negatif → kalıcı).

## ⚠️ Eval gate kümülatif sonuç (3 model)

11 niş sorgu × hybrid_search_chunks koşumu:

| Mode | recall@5 | recall@10 | mrr@10 | NDCG@10 | avg latency |
|---|---|---|---|---|---|
| **off** (production baseline) | **0.727 (8/11)** | 0.727 | **0.591** | **0.627** | **18.0s** |
| local bge-reranker-v2-m3 (#750) | 0.636 (7/11) ⬇ | 0.727 | 0.439 ⬇ | 0.509 ⬇ | 19.2s ⬇ |
| NIM rerank-qa-mistral-4b (#750) | 0.636 (7/11) ⬇ | 0.727 | 0.484 ⬇ | 0.542 ⬇ | 18.8s ⬇ |
| **Jina v2 base multilingual (#760)** | **0.636 (7/11) ⬇** | 0.636 ⬇ | 0.518 ⬇ | ~0.547 ⬇ | **72.8s ⬇⬇** |

**Eşik:** NDCG@10 ≥ 0.90 VEYA recall@5 +5pp delta. **3 model de geçemedi.**

### #750 detay (bge-reranker + NIM, 2026-05-12)
- niche_001-005, niche_010-011 (8 başarılı sorgu) — rerank açılınca bazıları **alt sıralara düştü** (mrr@10 0.591 → 0.439/0.484).
- niche_006/007/009 (3 fail) — her 3 mode'da da rank=-1. Reranker doğru article'ı top-10'a sokmuyor (zaten top-K dışı, rerank top-K içinde işler).
- Latency: rerank ek ~2-3s (TTFT budget zarar).

### #760 Jina v2 detay (2026-05-13)
- Aynı 11 sorgu koşumu, `retrieval.cross_encoder_enabled=true` ile.
- **niche_010 ("Emine Aydınbelge ne dedi") regresyonu kritik:** baseline'da #1 sırada → Jina ile top-10 dışı. Person name + short query'de Jina yanlış chunk'a yüksek skor verdi.
- niche_003 rank #1 → #5 (recall@5 hâlâ geçer ama NDCG katkısı düştü).
- niche_001 rank #2 → #1 (tek pozitif değişim).
- niche_006/007/009 hâlâ kırık (retrieval-level miss, rerank dünyası dışı — beklenen).
- **Latency: 18s → 73s** (+304%). Jina v2 CPU inference top-15 candidate başına ~5sn (1024 max-length token cost). Üretim için kabul edilemez.

Net: 3 model ile de aynı sonuç — **cross-encoder rerank Türkçe niş entity retrieval task'imizde help etmiyor.** Bottleneck retrieval-level (chunk granularity, NER coverage, embedding dilution), rerank katmanı değil.

## Bağlam — niye kapalı

Tour 5 (Mart-Mayıs 2026) sürecinde NIM cross-encoder rerank kalite sorunları:

- **#251** — Reranker bazı niş query'leri ters sıralıyor (top-1 olması gereken card alt sıralarda)
- **#252** — Aynı topic farklı domain article'larında inconsistent skor
- **#254** — Kısa query'lerde (< 3 kelime) reranker patliyor
- **#259** — Combined score eşiği tutarsız (manuel 0.10 → 0.15 → 0.20 deneme)
- **#260** — Rerank sonrası score kaybı (RRF skor 0.95 → rerank 0.30)

PR #347 (MVP-1.5) ile alternatif olarak `LocalBgeReranker` (CrossEncoder, CPU üzerinde `BAAI/bge-reranker-v2-m3`) eklendi. Eval gate hedefi: **NDCG@10 ≥ 0.90**. Eval sonucu **negatif** — flip yapılmadı.

2026-05-10 itibarıyla mimari karar: **cross-encoder rerank by-pass + LLM rerank açık** (Faz 4 answer-aware). Bu, üretim kalitesini bozmadan reranker risklerinden kurtulma yolu.

## Mevcut pipeline durumu

```
1. Query Planner → topic + keywords + timeframes (#727 default 7 gün)
2. Embedding (local bge-m3, 1024-dim)
3. Hybrid retrieval (dense + sparse + NER stream)
   - RRF (base K=60, NER multi_and K=10, single_rare K=20)
   - Mode-aware phrase boost (#718: NER 0.03 / normal 0.05)
4. Source diversity cap (max 2/domain)
5. ⏸ Cross-encoder rerank — KAPALI (retrieval.cross_encoder_enabled=false)
   Provider altyapısı tutulur: `local_jina_rerank` registry'de kayıtlı,
   #760 ile setting ile runtime tunable. Açma = ENV ON + eval gate ≥ 0.90.
6. ✅ LLM rerank (Faz 4) — question query'ler için DeepSeek answer-aware top-3
7. Content generator (DeepSeek V4 Flash, streaming)
```

Üretim sonucu (2026-05-13 son ölçüm): **recall@5 = 0.727 (8/11)** — niche_006/007/009 retrieval-level miss; gerisi top-K içinde.

## Alternatifler ve neden

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| NIM rerank-qa-mistral-4b PRIMARY | Eski default, NIM ücretsiz | #251/#252/#254 kalite sorunları + #750 eval negatif | ❌ #758'de kod silindi |
| Local bge-reranker-v2-m3 PRIMARY | CPU local, dış bağımlılık yok | #347 ve #750 eval gate negatif | ❌ #758'de kod silindi |
| **Jina Reranker v2 Base Multilingual** | 100+ dil eğitimli, Türkçe dahil | #760 eval: -9.1pp recall@5, latency 4x | ❌ Provider modülü tutulur, setting OFF default |
| LLM rerank (Faz 4) — DeepSeek answer-aware | Question intent dahil, kalite iyi | Cost (per call ~$0.0001) | ✅ AKTİF (`retrieval.llm_rerank_enabled=true`) |
| Hiç rerank, sadece RRF + NER | En düşük cost + latency | Niş entity recall riski | ❌ NER + LLM rerank ile compensate ediliyor |
| Eval gate sonrası 4. model dene | Doğru karar yolu | 3 model fail oldu — diminishing return | 📋 Gerçek bottleneck: chunk granularity + NER coverage (#710 epic) |

## Sonuçlar

- **Etkilenen kavramlar:** [[ragflow-tier-rebuild]] (Faz 4 LLM rerank aktif), [[ner-pipeline]] (rerank-yokken NER bost'u kritik), [[chunks-first-retrieval]] (rerank-yokken candidate_pool=60 önemli)
- **Etkilenen kod:**
  - `apps/api/app/core/rerank.py` — `_cross_encoder_rerank()` setting OFF iken çağrılmaz
  - `apps/api/app/core/retrieval.py` — RRF top_k LLM'e direkt gider
  - `apps/api/app/providers/registry.py` — `_fallback("local_jina_rerank")` register kalır (lazy load, model gerek olmadıkça yüklenmez)
  - `apps/api/app/providers/local_jina_rerank.py` — provider module korunur (gelecek deneyler için altyapı)
  - `apps/api/Dockerfile` — Jina v2 multilingual HF cache pre-download kalır (~560MB; tetikleme zorluğunda hızlı flip için)
- **Etkilenen settings:**
  - `retrieval.cross_encoder_enabled = false` (#760 default OFF, 2026-05-13)
  - `retrieval.llm_rerank_enabled = true`
  - **#758 ile silinen 7 setting key** ile artık database'de yok:
    - `rerank.enabled`, `rerank.candidate_pool`, `rerank.min_combined_score`,
    - `rerank.min_query_words`, `llm.nim_rerank_model`, `llm.nim_rerank_timeout`,
    - `llm.use_local_rerank`
- **Etkilenen dokümanlar:**
  - `docs/engineering/architecture.md` §4.5 (Faz 7d) — pipeline savunma katmanları
  - `wiki/decisions/ner-pipeline.md` — NER pipeline rerank yokken kritik

## Reranker'ı geri aktif etmek için ne gerek

3 model eval gate fail oldu (NIM rerank, local bge-reranker-v2-m3, Jina v2 base multilingual). **Karar kalıcı** — yeni 4. model deneme cost/benefit:

- **Cost:** 1-2 gün provider modül + Dockerfile + eval (her seferinde +%5-10 build cache miss)
- **Beklenen kazanım:** geçmiş 3 sonuç düşük güven; bottleneck retrieval-level, rerank değil.

Daha verimli yatırım yolları:
1. **Chunk granularity reform** — semantic chunker max_tokens 400 → 256, breakpoint percentile reform
2. **NER coverage genişletme** — büyük chunk + sayısal bilgi gömülü vakaları (niche_006/007) için NER pre-processing
3. **Meta-query handling** — niche_009 tipi sorgular için query rewriting

Yine de yeni reranker denenecekse:
1. **Adaylar:** BAAI/bge-reranker-v2-gemma, mixedbread-ai/mxbai-rerank-large-v1, Cohere Rerank v3.5
2. **Eval:** Aynı `niche_chunks_benchmark.py` + `retrieval.cross_encoder_enabled` toggle, provider değiştir
3. **Eşik aynı:** NDCG@10 ≥ 0.90 VEYA recall@5 ≥ 9/11
4. **Latency bütçesi:** ≤ 3s ek (Jina 73s artışı kabul edilemezdi)

Aksi halde reranker katmanı **kalıcı bypass** kalır.

## Geri alma maliyeti

Bu kararı değiştirmek (rerank'i geri açmak):

1. Eval framework + golden set kurulumu (2-3 gün)
2. Eval run + sonuç analizi (1 gün)
3. Pozitif sonuç → flip `rerank.enabled=true`, smoke test, production monitoring 1 hafta
4. Negatif sonuç → bu sayfa "permanent disabled" durumuna çıkar

**Tahmini süre:** 4-5 gün eval + flip + monitor.

## İlişkiler

- [[ragflow-tier-rebuild]] — Faz 4 LLM rerank (alternatif rerank yolu, aktif)
- [[ner-pipeline]] — NER stream rerank-yokken kritik recall katmanı
- [[chunks-first-retrieval]] — chunks PRIMARY, rerank-yokken candidate_pool önemli
- [[sufficiency-soft-gate]] — soft-gate sonrası chunks-first başarı oranı yüksek
- [[pipeline-optimization]] — rerank-yokken bile TTFT iyileşmesi mümkün

## Kaynaklar

- [Issue #251](https://github.com/selmanays/nodrat/issues/251) (NIM rerank kalite sorunu — terslemeler)
- [Issue #252](https://github.com/selmanays/nodrat/issues/252) (inconsistent skor)
- [Issue #254](https://github.com/selmanays/nodrat/issues/254) (kısa query patliyor)
- [Issue #259](https://github.com/selmanays/nodrat/issues/259) (eşik tutarsızlığı)
- [Issue #260](https://github.com/selmanays/nodrat/issues/260) (score kaybı)
- [Issue #347](https://github.com/selmanays/nodrat/issues/347) (LocalBgeReranker eval gate)
- [Issue #614](https://github.com/selmanays/nodrat/issues/614) (housekeeping audit — bu karara yol açan)
- [Issue #750](https://github.com/selmanays/nodrat/issues/750) (eval A/B: off vs local vs NIM)
- [Issue #758](https://github.com/selmanays/nodrat/issues/758) (cross-encoder kod path cleanup)
- [Issue #760](https://github.com/selmanays/nodrat/issues/760) (Jina v2 multilingual eval — 3. model fail)
- `apps/api/app/core/rerank.py` — implementation (cross-encoder + LLM rerank katmanları)
- `apps/api/app/providers/local_jina_rerank.py` — Jina provider (setting OFF iken model yüklenmez)
