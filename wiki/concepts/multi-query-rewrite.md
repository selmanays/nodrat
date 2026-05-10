---
type: concept
title: "Multi-query rewrite — Perplexity-style RAG retrieval"
slug: "multi-query-rewrite"
category: "rag"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/api/app_generate.py§391-470"
  - "GitHub Issue #618 / PR #626"
  - "GitHub Issue #618 PR-E.1 / PR #633 (rebalance)"
tags: ["rag", "retrieval", "perplexity", "multi-query", "rrf", "mvp-1-8"]
aliases: ["query-rewrite", "rrf-fusion"]
---

# Multi-query rewrite

> **TL;DR:** Tek arama yerine **2 query varyantı** (orijinal + sınırlı genişletilmiş) paralel çağrılır → **RRF füzyon (k=60)** ile birleşir → daha geniş recall + sıkı precision. LLM cost ek yok (kod-level rewrite, planner çıktısından türetilir).

## Bağlam

[[realtime-rss-polling]] sonrası kaynak sayısı 6 → 27'ye çıkınca tek-arama RAG'ı zayıf kaldı. Kullanıcı vakası: "Azıcık radyasyon kemiklere yararlıdır" Bianet article'ı vardı ama tek varyant yakalayamadı (planner topic_query soyut çıkarınca). Perplexity'nin temel mimarisi multi-query RAG ([Perplexity ZipTie analizi](https://ziptie.dev/blog/how-perplexity-ai-answers-work/)).

## Tasarım — 2 varyant (PR-E sıkılaştırması sonrası)

PR-B ilk versiyonu **3 varyant**: orijinal + enriched + keywords-only. **3. varyant kaldırıldı** (#633) çünkü "Toprakaltı sergisi" sorgusu için planner `["sergi","tünel","kültürel"]` keywords çıkarınca varyant 3 = "tünel sergi" Slovenya Nova Gorica tünelini çekiyordu — too broad.

Mevcut tasarım:
```python
query_variants = [plan.topic_query]                      # v1: orijinal
if plan.keywords:
    kw_top = plan.keywords[:3]                            # 5 → 3 (sıkı)
    query_variants.append(f"{plan.topic_query} {' '.join(kw_top)}")  # v2: enriched
```

- **v1 (orijinal)**: kullanıcı sorgusu, sıkı match için
- **v2 (enriched, sınırlı)**: topic_query + ilk 3 keyword (planner çıktısından)

## RRF (Reciprocal Rank Fusion)

Standart formül, k=60:
```
score(card) = Σ 1 / (60 + rank_in_variant_i)
```

Aynı article birden fazla varyantta üst sıralarda dönerse RRF skoru artar → daha güvenli sıralama.

## Embedding optimizasyonu

Tek embedding call (en kapsamlı varyant — `enriched_query`), iki varyant arama bunu paylaşır. Sparse search varyant başına farklı (text farklı). HyDE varyantı varsa kendi embedding'i (PR-C, [[hyde-feature-flag]]).

## Etki

- Üretim: F-16 21 ülke sorgusu → Northrop Grumman article doğru cevap (yeni eklenen C4Defence kaynağından)
- Latency: tek-varyanta göre +200-400ms (paralel hybrid_search SQL)
- LLM cost: 0 (kod-level rewrite)

## İlişkiler

- [[source-diversity-cap]] — RRF sonrası uygulanır
- [[chunks-always-on-fallback]] — agenda<3 ise chunks ekle
- [[hyde-feature-flag]] — opsiyonel 3. varyant
- [[planner-cache]] — varyant 1 keywords planner çıktısından

## Kaynaklar

- `apps/api/app/api/app_generate.py` §391-470 (multi-query + RRF füzyon)
- [PR #626](https://github.com/selmanays/nodrat/pull/626) — ilk implementation
- [PR #633](https://github.com/selmanays/nodrat/pull/633) — PR-E.1 rebalance (3. varyant kaldır)
