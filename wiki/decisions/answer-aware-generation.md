---
type: decision
title: "Answer-aware generation context — pre-extracted numerical spans"
slug: "answer-aware-generation"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/prompt-contracts.md§4"
  - "apps/api/app/core/answer_span.py (#710 Faz 7c)"
tags: ["locked-decision", "rag", "generation"]
aliases: ["answer-spans", "numerical-spans-context"]
---

# Answer-aware generation context

> **Karar:** Generator'a verilen her `supplementary_chunk` için `answer_spans` field eklenir — chunk_text içinden otomatik tespit edilmiş sayısal/spesifik ifadeler (yüzde, oran, sayı, skor, tarihsel yıl, miktar). Generator rakamsal sorgularda bu listeyi öncelikle tarar.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

niche_007 ("ABD'nin hürmüz boğazının yüzde kaçını kullanma hakkı") gibi sorgularda hedef article zaten retrieval top-K'da, ama generator chunk içinde **yanlış paragraf** seçiyor — niş cevap dimensiyon bilgisi kaybediliyor.

`extract_numerical_spans` helper'ı zaten vardı (`apps/api/app/core/answer_span.py`, #710 Faz 7c) ama sadece diagnostic. Generator'a iletmiyorduk.

## Evergreen tasarım

- Generic regex patterns: `_PCT`, `_FRAC`, `_MONEY`, `_QUANTITY`, `_SCORE`, `_ORDINAL`, `_HISTORICAL_YEAR`
- **Hardcoded entity/sorgu kalıbı YOK**
- Her chunk için aynı extraction — sorgu-agnostic
- Span boşsa field eklenmez (LLM context'i şişirmez)

## Generator prompt eklemesi

```
📊 ANSWER_SPANS — pre-extracted sayısal/spesifik ifadeler:
Bazı chunk'larda "answer_spans" field'ı bulunur — chunk_text içinden
otomatik çıkarılmış yüzde/oran/sayı/skor/tarihsel yıl ifadeleri.
Sorgu "kaç X / yüzde kaç / ne kadar / kaçıncı" tipi rakamsal sorduğunda,
önce answer_spans listesini tara, sorguya uyuyorsa cevap olarak kullan.
Span boş ise chunk'ı normal oku.
```

## Test sonucu

E2E production-parity test (niche_007):
- BASELINE: target article top-15 dahi giremedi (critical_entities 'abd' article'da yok)
- AFTER A1: target hâlâ top-15'te yok — **A1 retrieval'ı kurtaramaz, sadece generation tarafına yarar**

Sonuç: A1 niche_007'yi tek başına düzeltmedi ama **retrieval'ın target'ı bulduğu vakalarda** doğru paragraf seçimi sağlar. Genel kalite iyileştirmesi (rakamsal sorularda).

## İlişkiler

- [[chunk-keyword-extraction]] — chunk-level metadata
- [[critical-entity-must-match]] — retrieval gate
- [[perf-sprint-2026-05-14]] — hız sprintı

## Kaynaklar

- [PR #788](https://github.com/selmanays/nodrat/pull/788)
- [`apps/api/app/core/answer_span.py`](apps/api/app/core/answer_span.py)
- [`apps/api/app/prompts/content_generator.py`](apps/api/app/prompts/content_generator.py)
