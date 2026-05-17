---
type: decision
title: "Chunks-first retrieval — RAG hazinesini görünür kılma"
slug: "chunks-first-retrieval"
category: "rag"
status: "live"
created: "2026-05-10"
updated: "2026-05-16"
sources:
  - "apps/api/app/api/app_generate.py§620-650"
  - "GitHub Issue #637 / PR #638"
  - "GitHub PR #907/#909 (#906 — since_hours artık planner-sürücülü)"
tags: ["rag", "retrieval", "perplexity", "primary-source", "mvp-1-8"]
aliases: ["chunks-primary", "article-level-retrieval"]
---

# Chunks-first retrieval

> **TL;DR:** RAG primary arama uzayı **chunks** (article-level), agenda_cards secondary (event/kategori özeti). Chunks 90 gün penceresi + top_k 15+. 3800+ cleaned article hazinesinin tamamı arama uzayında. Singleton article'lar + eski article'lar görünür. Tek-kaynak haberi disclaimer ile cevaplanır (PR-H Plan B).

> ⚠️ **Güncelleme (#906, 2026-05-16):** "90 gün penceresi" artık **SABİT değil** — `agentic-generate-orchestration` (#845) chat akışında `execute_search_news` `since_hours`'ı planner timeframe'inden türetir ([[news-timeframe-retrieval-contract]]). `news_query` için pencere son ~7 güne daralır (örtük güncellik kontratı); 90 gün artık **fallback tavanı** (dar pencere boş dönerse). Bu sayfadaki `since_hours=24*90` örnekleri **content-generation/app_generate** yolu için geçerli; chat (search_news) yolunda planner-sürücülü. Eski-haber sızması bug'ının (#906) yapısal düzeltmesi.

## Bağlam — sorun

Önceki mimari:
1. PRIMARY: `hybrid_search_agenda_cards` — event-level cluster özet
2. FALLBACK: `hybrid_search_chunks` — sadece agenda<3 ise, son 7 gün

**Sonuç (kullanıcı feedback'i — boruhattındaki yapısal sorunlar):**
- **Singleton article'lar görünmez** — Northrop Grumman F-16 article'ı tek başına bir haber, kendi agenda_card'ı oluşmadı, RAG göremiyor
- **Eski article'lar görünmez** — chunks fallback 7 gün, 3800+ cleaned article'ın çoğu 1-2 ay öncesi → "hazinemizi çöpe atıyoruz"
- **Tek-kaynak haberleri reddediliyor** — multi-source bias (PR-G empty-posts guard) F-16 vakasını yetersiz veri'ye düşürüyordu

## Tasarım — Plan A + Plan B

### Plan A: chunks-first

```python
# Önceden: agenda<3 koşulu + 7 gün
needs_chunks = len(agenda_cards) < 3
if needs_chunks:
    supplementary_chunks = await hybrid_search_chunks(top_k=4, since_hours=168)

# Yeni (PR-H): chunks always-on + 90 gün + geniş top_k
supplementary_chunks = await hybrid_search_chunks(
    top_k=max(15, content_top_k * 2),
    since_hours=24 * 90,  # 90 gün corpus
    ...
)
```

agenda_cards search yine yapılır ama **secondary** rolde — event/kategori sentez katmanı.

### Plan B: tek-kaynak disclaimer cevap

PR-G empty-posts guard gevşetildi: sadece `summary>150 char + irrelevant_sources warning YOK` koşulunda tetiklenir (Toprakaltı tarzı belirgin halüsinasyon). Tek-kaynak vakaları yakalanmaz.

content_generator prompt Kural #16 eklendi:
```
ALAKALI tek kaynak DA HAZİNE — cevap üret, disclaimer ile.
"Bu konuda tek kaynak (X) — gelişmeler için sektörel takip önerilir"
"Yetersiz veri" DEMEME zorunluluğu.
```

## Etki

| Senaryo | Eski | Yeni |
|---|---|---|
| Northrop F-16 (singleton + tek-kaynak) | yetersiz veri | cevap + tek-kaynak disclaimer |
| 7+ gün öncesi article | görünmez | chunks 90 gün penceresi ile bulunur |
| Toprakaltı sergisi (alakasız) | uydurma başlık (eski) | yetersiz veri (entity match korunur) |
| Generic kategori sorgu (Türkiye ekonomi) | çoklu agenda_card | chunks + agenda merge, daha geniş kapsam |

## Trade-off

**Pro:**
- 3800+ article'ın **tamamı** görünür (önceden ~10% görünüyordu agenda'da)
- Singleton + niş haberler ulaşılabilir
- Perplexity benzeri "tüm corpus arama uzayı" davranışı

**Con:**
- Latency +200-400ms (geniş chunks SQL)
- Cost +%5-10 (daha çok rerank candidate)
- agenda_cards underutilized (sentez için kalır)

## İlişkiler

- [[multi-query-rewrite]] — chunks search üzerinde uygulanır
- [[source-diversity-cap]] — chunks sonrası max 2/domain
- [[entity-match-relevance]] — alaka kontrolü (chunks-level de geçerli)
- [[multi-source-synthesis]] — sentez generation'da
- [[hyde-feature-flag]] — chunks search ile ek kazanım
- [[ragflow-tier-rebuild]]
- [[smart-quote-normalization]]
- [[sufficiency-soft-gate]] — #726 (2026-05-12): mode='current' için sufficiency hard-gate kaldırıldı, chunks-first her zaman fırsat bulur (önceden hard-gate bypass ediyordu)
- [[chunk-keyword-extraction]] — #778 (2026-05-14): Her chunk için LLM keyword + question_keyword TEXT[] kolonları; retrieval'da yeni keyword stream (RRF K=15/20/30). Niş entity sorgularında ("çocuk bahis") kritik recall artışı.
- [[critical-entity-must-match]] — #778 (2026-05-14): `hybrid_search_chunks` yeni param `critical_entities`; 2-aşamalı (RESCUE + FILTER) gate. Planner'dan gelen 1-3 diskriminatif kelime article'da geçmeli; aksi halde soft fallback.
- [[news-timeframe-retrieval-contract]] — #906/#907/#909 (2026-05-16): chat (search_news) yolunda `since_hours` artık planner timeframe-sürücülü; 90g sabit pencere değil fallback tavanı. Eski-haber sızması yapısal fix.
- [[turkish-collation-entity-match]] — #939 (2026-05-17): critical_entities RESCUE/FILTER `LOWER(...)` C-locale Türkçe büyük harf küçültmüyordu (Türkçe entity exact-match çöküktü); `COLLATE "tr-TR-x-icu"` ile düzeltildi. Benchmark recall@10 0.818→0.909.

## Kaynaklar

- `apps/api/app/api/app_generate.py` §620-650 (chunks-primary loop)
- `apps/api/app/prompts/content_generator.py` §190-220 (tek-kaynak disclaimer kural)
- [PR #638](https://github.com/selmanays/nodrat/pull/638)
- [Perplexity ZipTie analizi](https://ziptie.dev/blog/how-perplexity-ai-answers-work/) — "casts a wide net" yaklaşımı
