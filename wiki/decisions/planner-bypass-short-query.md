---
type: decision
title: "Planner-bypass kısa entity-tipi sorgular için"
slug: "planner-bypass-short-query"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/prompt-contracts.md§2"
tags: ["locked-decision", "performance", "planner"]
aliases: []
---

# Planner-bypass kısa entity-tipi sorgular

> **Karar:** ≤4 kelime + soru marker yok → planner LLM çağrısı (~2s) atlanır, sensible defaults uygulanır.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Heuristic

```python
word_count = len(query.split())
has_question = any marker in (?, ne, kim, nedir, neden, nasıl, nerede, kaç, hangi, ne_zaman)

if 1 <= word_count <= 4 and not has_question:
    bypass()
```

## Bypass plan defaults

- `topic_query` = user_request as-is
- `mode` = "current"
- `timeframes` = [] (default 90 gün retrieval'da)
- `output_type` = "x_post"
- `critical_entities` = en uzun 2 kelime (3-30 char, lowercase)
- `is_short_query = True` (telemetri)

Sonuç planner cache'ine yazılır → sonraki tekrar bypass.

## Test sonuçları (use_cache=False, planner çağrısı isolated)

| Sorgu | Süre | Davranış |
|---|---|---|
| "Trump" (1 word) | 509ms | bypass ✅ |
| "Karşıyaka skor" (2) | 0ms | bypass + cache hit ✅ |
| "Trump ne dedi" (3+soru) | 2349ms | LLM ✓ |
| "Sovyetler Birliği dağıldığında..." (8 word) | 2305ms | LLM ✓ |

## Bağlam

Cache miss durumunda planner DeepSeek LLM çağrısı 2-3s harcar. Kısa entity-tipi sorgular ("Trump", "Karşıyaka skor") için bu marjinal değer katar — kullanıcı zaten net entity yazıyor, mode "current" default, timeframe default 90 gün.

Soru-tipi sorgular ("ne dedi", "kim", "kaç") LLM gerek — disambiguation/timeframe extraction. Uzun sorgular (5+ kelime) zaten daha karmaşık, LLM değer katar.

## Alternatifler

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Hep LLM (bypass yok) | En kaliteli plan | Her sorguda ~2s | reddedildi |
| Hep bypass (LLM yok) | En hızlı | Timeframe / mode disambiguation kayıp | reddedildi |
| **≤4 kelime + no question marker bypass** | Hız + kalite | Edge case'lerde "Trump 6 Mayıs" gibi tarih ipucu içeren kısa sorgularda LLM kaçırılır | **seçildi** |

## Sonuçlar

- Kısa entity-tipi user query (~%20 production trafiği) — ~2s tasarruf/query
- Cold miss latency (kısa query): ~4s → ~2s
- Soru-tipi ve uzun sorgular hâlâ LLM planner'a gider (kalite kritik)

## Geri alma maliyeti

> `query_planner.py:plan_query`'de bypass koşulunu `False` yap → tüm sorgular LLM'e gider. Veya admin /settings ile flag haline getirilebilir (gelecek).

## İlişkiler

- [[query-planner]] (mevcut [[ner-pipeline]] arasında — planner output schema)
- [[planner-cache-key-v2]] — paralel cache
- [[perf-sprint-2026-05-14]] — bu sprintın parçası

## Kaynaklar

- [PR #785](https://github.com/selmanays/nodrat/pull/785)
- [`apps/api/app/prompts/query_planner.py`](apps/api/app/prompts/query_planner.py)
