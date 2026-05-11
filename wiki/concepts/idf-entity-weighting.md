---
type: concept
title: "IDF entity weighting — NER scoring scale-realistic fix (chunks + cards)"
slug: "idf-entity-weighting"
category: "rag"
status: "live"
created: "2026-05-11"
updated: "2026-05-11 (#714 — cards path eklendi)"
sources:
  - "apps/api/app/core/retrieval.py (NER_DF_THRESHOLD, _ner_idf_match_aids, hybrid_search_chunks + hybrid_search_agenda_cards)"
  - "apps/api/app/core/rerank.py (_extract_entity_candidates + stopword genişletme + apostrof fix)"
  - "GitHub Issue #691 / PR #693 (Faz 6.1 chunks)"
  - "GitHub Issue #714 (Faz 6.2 cards path + locked decision revoke)"
tags: ["rag", "ner", "retrieval", "idf", "scoring", "cards", "chunks", "mvp-1-8"]
aliases: ["entity-rarity-boost", "multi-entity-and"]
---

# IDF Entity Weighting

> **TL;DR:** Faz 6 NER pipeline'ı 9 article entity'liyken ölçüldü; NER backfill ile 4391 article entity'li olunca her sorguda `ILIKE %X% LIMIT 20` cap'i doluyor → sinyal sulanıyor → kazanım siliniyor. Çözüm: **entity rarity (df) threshold + multi-entity AND** hibrit. 4 mode (multi_and / multi_and_common / single_rare / no_match) + mode-aware K weight (20/30). Sonuç: recall@5 **63.6% scale-realistic** olarak geri kazanıldı.

## Bağlam — backfill scale etkisi

[[ner-pipeline|Faz 6 NER]] ile recall@5 45.5% → 63.6% sıçraması ölçüldü, **ama** o ölçüm sadece 9 test article entity'liyken yapıldı:
- Query "Karşıyaka" → entities tablosunda 1-2 article match → nadir entity → kesin doğru article'ı işaret eder
- RRF K=30 ile en güçlü boost veriliyordu

Production NER backfill ([[pipeline-optimization|#684 PR-B ops]]) ile 4391 article entity-li hale geldiğinde:
- Query "Karşıyaka" → 20 article match (LIMIT cap dolu): semt, belediye, taciz davası, ESHOT, CHP, vs.
- Hepsi aynı K=30 boost → doğru article başka 19 article ile yarışıyor → sinyal sulanıyor
- Multi-entity sorgularda (Karşıyaka + Bursaspor) → 40 article aynı boost
- **A/B test (NER stream disabled) ile teyit:** Aynı 5/11 sonuç → NER stream effective olarak hiçbir şey yapmıyordu

## Çözüm — IDF + multi-entity AND hibrit

`apps/api/app/core/retrieval.py` `_resolve_ner_target_aids` pure logic + `_ner_idf_match_aids` DB wrapper.

### Algoritma

```text
1. Her query entity için DB'den article id'leri çek (exact match → ILIKE fallback)
2. df_map = {entity: article_count} (her entity için)
3. Mode seç:
   a) 2+ rare entity (df < NER_DF_THRESHOLD=30) varsa:
      - Intersect dolu → "multi_and" → K=20 (en güçlü)
      - Intersect boş → en nadir entity → "single_rare" → K=30
   b) 1 rare entity → "single_rare" → K=30 (Faz 6 eski seviye)
   c) 0 rare + 2+ common entity intersect dar (<30) → "multi_and_common" → K=20
   d) Hiçbiri → "no_match" → boost yok (sinyal güvensiz)
```

### Mode tablosu

| Mode | Koşul | K | Örnek |
|---|---|---|---|
| `multi_and` | 2+ nadir entity intersect dolu | 20 | "Karşıyaka + Bursaspor" → maç article'ı |
| `multi_and_common` | Common entity AND intersect dar (<30) | 20 | İki popüler entity'nin dar kesişimi |
| `single_rare` | 1 rare entity (df<30) | 30 | "Aydınbelge" — kişi adı |
| `no_match` | Hiçbiri | yok | "Trump" tek başına (df>>30) |

### Yan iyileştirmeler (PR #693 birlikte)

1. **Stopword genişletme** (`_ENTITY_STOPWORDS`): Türkçe morpho/question kelimeleri
   - `maçı`, `kaç`, `bitti`, `nedir`, `işleri`, `nereye`, vs.
   - NER backfill yan etkisi olarak DeepSeek bu common kelimeleri entity sayıyordu

2. **Apostrof handling** (`_APOSTROPHE_VARIANTS`): possessive ekleri ayrıştır
   - `Tutak'ın` → `tutak` + `ın` (`ın` < min_len=3 → drop)
   - 7 varyant (ASCII `'`, smart `'`, smart `'`, modifier letter, backtick, prime)
   - Test: `apps/api/tests/unit/test_rerank.py` (8 case, 7 OK; Türkçe büyük "İ" lowercase bug ayrı issue)

3. **Telemetri** ([[#696 admin RAG İzlencesi yansıma]]):
   - `/admin/rag/inspect-query` response'a NER mode + df_map + target_aids
   - `/admin/rag/ner-stats` mode dağılımı (multi_and % / single_rare % / no_match %)

## Ölçüm — Faz 6 vs Faz 6.1

| Aşama | recall@5 | recall@10 | Koşul |
|---|---|---|---|
| Faz 5 baseline | 45.5% | 45.5% | bge-m3 ceiling |
| Faz 6 NER (9 article test) | 63.6% | 81.8% | sentetik, scale-relevant değil |
| Post #684 backfill (broken) | 45.5% | 45.5% | NER stream effective olarak ölü |
| **Faz 6.1 (PR #693 final)** | **63.6%** | **72.7%** | scale-realistic, sürdürülebilir |

> Recall@10 Faz 6'nın altında (72.7% vs 81.8%) ama bu **scale-realistic** sayı. 4391 article entity'li corpus'ta agresif boost yerine sıkı filtreleme + multi-entity AND ile sürdürülebilir.

## Trade-off

**Pro:**
- ✅ Backfill ölçeğine dayanıklı (scale-realistic)
- ✅ Yaygın entity'ler (Karşıyaka semt) false-positive vermez
- ✅ Niş entity (F-16, Aydınbelge) hâlâ büyük boost alır
- ✅ Multi-entity sorgularda intersect ile narrowing
- ✅ Latency neutral (+0.3s, IDF DB lookup ~10-15ms ekledi)
- ✅ 9 birim test pure logic için

**Con:**
- Threshold (df=30) sabit, corpus büyüdükçe re-tune gerekir
- IDF formal değil (basit < threshold), gerçek `log(N/df)` weighting daha smooth olabilir
- LIMIT 100 per entity (df sayımı için) — production'da p99 latency ~50ms ekstra

## İlişkiler

- [[ner-pipeline]] — §Faz 6.1 detay implementasyon
- [[pipeline-optimization]] — #684 sprint context
- [[ragflow-tier-rebuild]] — Faz 1-5 retrieval mimari
- [[cards-path-ner-out-of-scope]]
- [[eval-benchmark-divergence]]
- [[api-contracts-md]]
- [[data-model-md]]

## Açık takip

1. df threshold dinamik (corpus size'a göre orantılı) yapılabilir
2. Log-IDF tabanlı smooth weighting (basit `<30` yerine)
3. Türkçe büyük "İ" lower() combining char bug — apostrof testinde 1/8 fail
   (ayrı issue açılacak)
4. df hesabını materialized view'a taşı (latency optimization)

## Kaynaklar

- [Issue #691](https://github.com/selmanays/nodrat/issues/691)
- [PR #693](https://github.com/selmanays/nodrat/pull/693) — NER scoring overhaul
- [Issue #696](https://github.com/selmanays/nodrat/issues/696) — admin telemetri + benchmark suite fix
