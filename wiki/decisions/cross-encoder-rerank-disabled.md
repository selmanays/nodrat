---
type: decision
title: "Cross-encoder reranker production'da kalıcı kapalı — eval gate negatif (#750)"
slug: "cross-encoder-rerank-disabled"
status: "locked-permanent"
decided_on: "2026-05-10"
eval_confirmed_on: "2026-05-12"
decided_by: "tech"
created: "2026-05-12"
updated: "2026-05-12 (#750 eval gate negatif → kalıcı)"
sources:
  - "app_settings DB: rerank.enabled=false (2026-05-10)"
  - "apps/api/app/core/rerank.py"
  - "apps/api/app/providers/local_rerank.py + nim_rerank.py"
  - "apps/api/scripts/eval_rerank_ab.py (#750 eval runner)"
  - "wiki/decisions/ragflow-tier-rebuild.md (Faz 4 LLM rerank)"
  - "wiki/decisions/ner-pipeline.md"
  - "GitHub Issue #251, #252, #254, #259, #260, #347, #614, #750"
tags: ["locked-decision", "rag", "rerank", "production-state", "mvp-1-8", "eval-confirmed"]
aliases: ["rerank-off", "no-cross-encoder"]
---

# Cross-encoder reranker production'da kalıcı kapalı

> **Karar:** Cross-encoder reranker (NIM rerank-qa-mistral-4b + local bge-reranker-v2-m3) production'da **kalıcı olarak kapalı**. `rerank.enabled = false`. Eval gate koşumu (#750, 2026-05-12) iki mevcut implementation'ın da baseline'dan **kötü** olduğunu doğruladı.
> **Durum:** **locked-permanent** (eval-confirmed) — geri açma için yeni reranker modeli denenmesi gerekir.
> **Tarih:** 2026-05-10 ilk kapatma. 2026-05-12 eval gate ile karar kalıcı (#750).

## ⚠️ Eval gate sonucu (#750, 2026-05-12)

11 niş sorgu × 3 konfigürasyon × hybrid_search_chunks koşumu:

| Mode | recall@5 | recall@10 | mrr@10 | NDCG@10 | avg latency |
|---|---|---|---|---|---|
| **off** (production) | **0.727 (8/11)** | 0.727 | **0.591** | **0.627** | 16.9s |
| local bge-reranker | 0.636 (7/11) ⬇ | 0.727 | 0.439 ⬇ | 0.509 ⬇ | 19.2s ⬇ |
| NIM rerank | 0.636 (7/11) ⬇ | 0.727 | 0.484 ⬇ | 0.542 ⬇ | 18.8s ⬇ |

**Eşik:** NDCG@10 ≥ 0.90 VEYA recall@5 +5pp delta. **Her ikisi de geçilemedi.**

Detay:
- niche_001-005, niche_010-011 (8 başarılı sorgu) — rerank açılınca bazıları **alt sıralara düştü** (mrr@10 0.591 → 0.439/0.484).
- niche_006/007/009 (3 fail sorgu) — her 3 mode'da da rank=-1. Reranker doğru article'ı top-10'a sokmuyor (zaten top-K dışı, rerank top-K içinde işler).
- Latency: rerank ek ~2-3s (TTFT budget zarar).

Net: Mevcut reranker implementation'ları RRF + NER + mode-aware phrase boost + LLM rerank kombinasyonundan **daha kötü**.

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
5. ⏸ Cross-encoder rerank — KAPALI (rerank.enabled=false)
6. ✅ LLM rerank (Faz 4) — question query'ler için DeepSeek answer-aware top-3
7. Content generator (DeepSeek V4 Flash, streaming)
```

Üretim sonucu (2026-05-12 son ölçüm): **9-10/11 niş entity recall@5** (#719 sonrası).

## Alternatifler ve neden

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| NIM rerank-qa-mistral-4b PRIMARY | Eski default, NIM ücretsiz | #251/#252/#254 kalite sorunları, latency 1-3s | ❌ 2026-05-10 ile kapatıldı |
| Local bge-reranker-v2-m3 PRIMARY | CPU local, dış bağımlılık yok | NDCG@10 eval gate negatif (#347) | ❌ Flip yapılmadı |
| LLM rerank (Faz 4) — DeepSeek answer-aware | Question intent dahil, kalite iyi | Cost (per call ~$0.0001) | ✅ AKTİF (`retrieval.llm_rerank_enabled=true`) |
| Hiç rerank, sadece RRF + NER | En düşük cost + latency | Niş entity recall riski | ❌ NER + LLM rerank ile compensate ediliyor |
| Eval gate sonrası geri aç | Doğru karar yolu | Eval framework + golden set gerek | 📋 Future epic (#TBD — B opsiyonu olarak takip) |

## Sonuçlar

- **Etkilenen kavramlar:** [[ragflow-tier-rebuild]] (Faz 4 LLM rerank aktif), [[ner-pipeline]] (rerank-yokken NER bost'u kritik), [[chunks-first-retrieval]] (rerank-yokken candidate_pool=60 önemli)
- **Etkilenen kod:**
  - `apps/api/app/core/rerank.py` — provider çağrılır ama setting flag false'sa skip
  - `apps/api/app/core/retrieval.py` — RRF top_k LLM'e direkt gider
  - `apps/api/app/providers/registry.py:84` — `_fallback("local_bge_reranker", "nim_rerank")` register kalır
- **Etkilenen settings:**
  - `rerank.enabled = false` (2026-05-10)
  - `llm.use_local_rerank = false`
  - `retrieval.llm_rerank_enabled = true`
- **Etkilenen dokümanlar:**
  - `docs/engineering/architecture.md` §4.5 (Faz 7d) — pipeline savunma katmanları
  - `wiki/decisions/ner-pipeline.md` — NER pipeline rerank yokken kritik

## Reranker'ı geri aktif etmek için ne gerek

#750 eval gate sonrası karar **kalıcı**. Mevcut iki implementation (`local_bge_reranker` + `nim_rerank`) **yeniden test edilirse bile aynı sonuç bekleniyor** — bge-m3 embedding + Türkçe niş entity domain ile uyumsuzluk eval'de net.

Yeni reranker test etmek için yapılması gereken:

1. **Yeni reranker modeli seç** (mevcut 2 implementation değil):
   - `BAAI/bge-reranker-v2-gemma` (yeni nesil, Türkçe daha iyi olabilir)
   - `mixedbread-ai/mxbai-rerank-large-v1`
   - Cohere Rerank v3.5 (API, paid)
2. **Eval framework var:** `apps/api/scripts/eval_rerank_ab.py` — yeni model ekle, 3 → 4 konfig
3. **Eşik aynı:** NDCG@10 ≥ 0.90 VEYA recall@5 ≥ 9/11

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
- `apps/api/app/core/rerank.py` — implementation
- `apps/api/app/providers/local_rerank.py` + `nim_rerank.py` — provider'lar
