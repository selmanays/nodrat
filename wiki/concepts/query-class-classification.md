---
type: concept
title: "query_class — 4-sınıf kullanıcı sorgu sınıflandırma"
slug: "query-class-classification"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/prompts/query_planner.py§VALID_QUERY_CLASSES"
  - "GitHub Issue #809 / PR #810"
tags: ["rag", "planner", "intent", "router", "mvp-1-8", "faz-2"]
aliases: ["user-query-class", "intent-router"]
---

# query_class

> **TL;DR:** Query Planner output'unda yeni 4-sınıf field — kullanıcı sorgusunun NE tür bilgi gerektirdiğini söyler. `news_query | general_knowledge | meta_query | mixed`. Mevcut `intent` (content-generation) ile karıştırılmamalı.

## Bağlam

Query Planner'ın eski `intent` enum'u 7 değer içeriyor (`current_content_generation`, `weekly_summary_generation`, vb.) — bunlar **content üretim tipi** intent'i. Faz 2'de Confidence Router gerekti, bu da **kullanıcı sorgu tipi** (haber mi, evergreen mi, meta mi) gerektirdi. İki kavram ayrı:

- `intent` → "Hangi format çıktı üreteceğim?" (x_post, summary, thread, ...)
- `query_class` → "Kullanıcı NE tür bilgi sorduğu?" (haber, evergreen, meta)

## 4 sınıf

### `news_query` — Güncel/realtime olay/haber

Tarih sinyali (bugün, dün, son, geçen hafta) veya event-driven kişi/yer/kurum.

Örnek:
- "Trump bugün ne dedi?"
- "İstanbul depremi son durum"
- "Merkez Bankası faiz kararı 2026"
- "Türkiye savunma sanayi 2026 ihracat" (tarih spesifik → news arşivinde aranır)

**Routing:** ASLA Wikipedia leak yok (C2). Sadece Layer 1.

### `general_knowledge` — Evergreen factual

Statik bilgi (nüfus, doğum tarihi, kurum kuruluş yılı, başkent, GDP). Realtime değil.

Örnek:
- "Çin nüfusu kaç?"
- "NATO ne zaman kuruldu?"
- "Trump kaç yaşında?"
- "Türkiye başkenti"
- "Apple CEO'su kim?"

**Routing:** Confidence < T_low → Wikipedia CTA. Confidence >= T_high → Layer 1 (haber arşivinde tesadüfen var).

### `meta_query` — Konuşma kendisi hakkında

Pronoun veya self-reference ("az önce", "demin", "bu konu", "konumuz") + soru.

Örnek:
- "Az önce ne dedin?"
- "Bunun konumuzla ne ilgisi var?"
- "Tekrar özetle"
- "Bu yorumu açıklar mısın?"

**Routing:** Retrieval ATLANIR. `_stream_meta_query_answer` — conversation.summary + son 6 mesaj LLM'e inject.

### `mixed` — Hibrit (haber + evergreen)

Hem güncel hem evergreen bilgi gerektirir. Genelde tarihsel/karşılaştırmalı analiz.

Örnek:
- "Trump'ın Çin politikası tarihte nasıl bir şeye benziyor?"
- "Bu ekonomik kriz 2008'le karşılaştırılırsa nasıl?"

**Routing:** Confidence score'a göre — yüksekse Layer 1, düşükse Wikipedia CTA, ortada hybrid+banner.

## Kararsız durumlar

Planner prompt kuralı:
- Güncel + evergreen karışıksa → `mixed`
- Net karar veremezsen → `news_query` (default — Nodrat news-first sistem)

8 few-shot örnek planner prompt'a inject:

```
1) "Trump bugün ne dedi?" → news_query
2) "Çin'in nüfusu kaç?" → general_knowledge
3) "Az önce hangi haberi anlattın?" → meta_query
4) "İran-İsrail çatışması tarihsel olarak nasıl?" → mixed
5) "İstanbul depreminde son durum" → news_query
6) "NATO ne zaman kuruldu?" → general_knowledge
7) "Bu olay konumuzla nasıl bağlanıyor?" → meta_query
8) "Türkiye savunma sanayi 2026 ihracat" → news_query
```

## Implementation

`apps/api/app/prompts/query_planner.py`:

- `VALID_QUERY_CLASSES = {"news_query", "general_knowledge", "meta_query", "mixed"}`
- `QueryPlan.query_class: Literal[...] = "news_query"` (default — Nodrat news-first)
- `parse_response()` query_class parse + invalid değerde fallback `news_query`
- `_plan_to_cache_dict` + `_plan_from_cache_dict` query_class serialize ediyor (Redis cache uyumlu)
- `PROMPT_VERSION` 1.3.0 → 1.4.0

## Eval

`apps/api/scripts/evals/faz2_query_class.jsonl` (gelecek):
- 20 news_query
- 15 general_knowledge
- 8 meta_query
- 7 mixed
- Accuracy ≥85% hedef

## İlişkiler

- Üst karar: [[tiered-knowledge-architecture]]
- Confidence router: [[confidence-based-routing]]
- News leak engelleme: [[news-first-strict-contamination-guard]]
- Wikipedia route: [[wikipedia-fallback-controlled]]

## Kaynaklar

- `apps/api/app/prompts/query_planner.py:26-48` (VALID_QUERY_CLASSES + system prompt)
- `apps/api/app/prompts/query_planner.py:280` (QueryPlan.query_class field)
- GitHub Issue #809 / PR #810
