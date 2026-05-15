---
type: decision
title: "Confidence-based routing — 5-signal score fusion"
slug: "confidence-based-routing"
category: "rag"
status: "superseded"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/core/retrieval_confidence.py"
  - "apps/api/app/api/admin_settings.py§141-180 (settings)"
  - "GitHub Issue #809 / PR #810 (superseded by #823→#828)"
tags: ["rag", "retrieval", "confidence", "router", "mvp-1-8", "faz-2", "superseded"]
aliases: ["5-signal-fusion"]
---

> ⚠️ **SUPERSEDED (#823→#828):** Bu routing mimarisi terk edildi. Confidence skoru artık **routing yapmaz — sadece telemetri** (admin observability + done event). Wikipedia tetikleme [[llm-tool-use-wikipedia]] ile (LLM kendi karar verir). Sebep: planner+RRF skoru "konu geçiyor mu" der, "cevap var mı" demez → yanlış routing, production'da defalarca kırıldı. 5-signal compute kodu durur ama akışı yönlendirmez. Aşağısı **tarihsel**.

# Confidence-based routing

> **TL;DR:** Chat retrieval'in kalitesini tek bir 0-1 skoruna çeviren 5-signal formula. Score `T_high` (0.70) üstü → Layer 1 STRICT, `T_low` (0.40) altı → Wikipedia CTA, arası → hybrid+banner. Ağırlıklar admin tunable JSON (single setting `retrieval.confidence_weights`).

## Bağlam

Mevcut sufficiency-soft-gate (#727) binary "yeterli mi" sinyalini telemetri için kullanıyordu. Faz 2'de Wikipedia fallback eklenince **3-katmanlı routing** gerekti (STRICT / hybrid / Wikipedia). Tek skor + iki eşik = 3 yol.

## Karar

**Formula:**

```
retrieval_confidence_score =
    w1 * semantic_top3_mean        # 0-1, NIM bge-m3 cosine_sim
  + w2 * source_count_normalized   # min(N, 5) / 5
  + w3 * recency_match             # haber tarihi vs planner.timeframes
  + w4 * entity_must_match         # planner.critical_entities hit oranı
  + w5 * citation_density          # post-generation; [N] / sentence
```

**Default ağırlıklar** (`retrieval.confidence_weights` JSON):
```json
{ "w1": 0.40, "w2": 0.20, "w3": 0.15, "w4": 0.15, "w5": 0.10 }
```

**Eşikler:**
- `T_high` = 0.70 → Layer 1 STRICT (Wikipedia leak yok)
- `T_low`  = 0.40 → Wikipedia CTA göster (kullanıcı onayı)
- Arası → hybrid (Layer 1 cevap + insufficiency banner)

## Sinyal kaynakları

`apps/api/app/core/retrieval.py:RetrievedChunk` dict'inden okunur:

| Sinyal | Kaynak | Compute |
|---|---|---|
| `semantic` | `c.semantic_score` (pgvector cosine) | Top 3 chunks mean |
| `source_count` | distinct `c.source_id` | `min(N, 5) / 5` cap |
| `recency` | `c.published_at` vs `plan.timeframes` | Timeframe içine düşen chunks oranı (timeframe yoksa 1.0) |
| `entity_match` | `c.chunk_text` ⊇ `plan.critical_entities` | Her entity için hit oranı, sonra mean |
| `citation_density` | `answer_text` `[N]` regex | `count / sentence_count`, normalize `/0.5` cap 1.0 |

## Citation density "None" davranışı

`compute_retrieval_confidence(plan, chunks, answer_text=None)` çağrısı (pre-generation):
- w5 atlanır
- Kalan w1-w4 renormalize edilir (toplam 1.0)
- `RetrievalConfidence.citation_density = None`

Post-generation çağrıda answer_text geçilir → 5 sinyal fusion. Done event'a `final_confidence.citation_density` dahil.

## Missing signals (UI insufficiency CTA için)

`RetrievalConfidence.missing` array — hangi sinyaller eşik altı:
- `low_semantic` (semantic < 0.50)
- `low_source_count` (source_count < 0.40)
- `recency_mismatch` (recency < 0.30 AND planner.timeframes var)
- `entity_mismatch` (entity_match < 0.50 AND critical_entities var)
- `low_citation_density` (citation < 0.20 AND answer_text var)

InsufficiencySignal UI banner (2D) bu listeyi kullanıcıya gösterir.

## Admin tunable

`apps/api/app/api/admin_settings.py:141-180`:

- `retrieval.confidence_weights` (JSON) — single setting, 5 ağırlık birlikte
- `retrieval.confidence_t_high` (float, 0-1)
- `retrieval.confidence_t_low` (float, 0-1, T_low < T_high zorunlu)

Hot reload: `settings_store` Redis pub/sub ile ~30 saniyede tüm container'lara yayar.

## Why bu formula?

- **semantic_top3_mean (w1=0.40):** En güçlü kalite sinyali — bottom chunks gürültü, top 3 ortalama sağlam.
- **source_count (w2=0.20):** Multi-source teyit (PR-G empty-posts guard mirası).
- **recency (w3=0.15):** Haber sorularında kritik, evergreen sorularda neutral 1.0 (cap).
- **entity_match (w4=0.15):** [[critical-entity-must-match]] decision'ı zaten var; bu sinyal onun continuous versiyonu.
- **citation_density (w5=0.10):** Halüsinasyon tespiti — cevapta kaynak yoksa sorun var.

## Eval set

`apps/api/scripts/evals/faz2_query_class.jsonl` — 50 manuel etiketli sorgu (gelecekte oluşturulacak):
- 20 news_query, 15 general_knowledge, 8 meta_query, 7 mixed
- Hedef: query_class accuracy ≥85%, routing decision ≥80%

Eşik kalibrasyonu eval-driven (production verisi 1 hafta toplandıktan sonra grid search).

## İlişkiler

- Üst karar: [[tiered-knowledge-architecture]]
- Entity must-match sinyali: [[critical-entity-must-match]]
- Sufficiency mirası: [[sufficiency-soft-gate]]
- Wikipedia tetikleyici: [[wikipedia-fallback-controlled]]
- News-first guard: [[news-first-strict-contamination-guard]]

## Kaynaklar

- `apps/api/app/core/retrieval_confidence.py` (modul)
- `apps/api/tests/unit/test_retrieval_confidence.py` (18 test)
- `apps/api/app/api/app_chat_stream.py:366-417` (kullanım)
- GitHub Issue #809 / PR #810
