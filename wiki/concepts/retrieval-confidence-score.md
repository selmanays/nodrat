---
type: concept
title: "Retrieval Confidence Score — 5-signal fusion formula"
slug: "retrieval-confidence-score"
category: "rag"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/core/retrieval_confidence.py"
  - "GitHub Issue #809 / PR #810"
tags: ["rag", "retrieval", "metric", "scoring", "faz-2"]
aliases: ["confidence-formula", "5-signal"]
---

# Retrieval Confidence Score

> **TL;DR:** Retrieve sonucunun kalitesini 0-1 arası tek skora çevirir. 5 sinyal (semantic + source_count + recency + entity_match + citation_density) ağırlıklı fusion. Routing kararı için Confidence Router tarafından kullanılır.

## Formula

```
score =
    w1 * semantic_top3_mean        # 0-1, NIM bge-m3 cosine_sim
  + w2 * source_count_normalized   # min(N, 5) / 5
  + w3 * recency_match             # planner.timeframes ↔ chunks.published_at
  + w4 * entity_must_match         # planner.critical_entities hit oranı
  + w5 * citation_density          # post-generation, cevaptaki [N]
```

Default ağırlıklar:
```json
{ "w1": 0.40, "w2": 0.20, "w3": 0.15, "w4": 0.15, "w5": 0.10 }
```

## Sinyal hesabı

### semantic_top3_mean (w1=0.40)

```python
top = sorted(chunks, key=lambda c: c.semantic_score, reverse=True)[:3]
score = sum(c.semantic_score for c in top) / len(top)
```

NIM bge-m3 cosine sim. Top 3 chunks ortalaması (bottom chunks gürültü olabilir; top 3 sağlam sinyal).

### source_count_normalized (w2=0.20)

```python
distinct_sources = {str(c.source_id) for c in chunks}
score = min(len(distinct_sources), 5) / 5.0
```

5+ distinct kaynak → 1.0 cap. Multi-source teyit (Nodrat'ın PR-G "empty-posts guard" mirası).

### recency_match (w3=0.15)

```python
if not plan.timeframes:
    return 1.0  # neutral — gating yok
hits = sum(1 for c in chunks if c.published_at in any(plan.timeframes))
return hits / len(chunks)
```

Planner timeframe yoksa (general_knowledge gibi) → 1.0 (gating'i kapatır). News query'de sıkı filter.

### entity_must_match (w4=0.15)

```python
if not plan.critical_entities:
    return 1.0  # neutral
entity_hit_ratios = []
for ent in critical_entities:
    chunk_hits = sum(1 for c in chunks if ent in c.chunk_text.lower())
    entity_hit_ratios.append(chunk_hits / len(chunks))
return sum(entity_hit_ratios) / len(entity_hit_ratios)
```

`critical_entities` (#778 decision) sinyalinin continuous versiyonu. Entity'lerin chunks'ta görünme oranı.

### citation_density (w5=0.10, post-generation)

```python
citation_count = len(re.findall(r"\[\d+\]", answer_text))
sentence_count = max(1, len(re.findall(r"[.!?]+", answer_text)))
raw = citation_count / sentence_count
return min(raw / 0.5, 1.0)  # 0.5/cumle ideal, /0.5 normalize, cap 1.0
```

Post-generation hesaplanır. Halüsinasyon tespiti — cevapta `[N]` yoksa kaynaksız konuşuyor demektir.

## "answer_text=None" davranışı

Pre-generation çağrı (`compute_retrieval_confidence(plan, chunks)`):
- `citation_density = None`
- w5 atlanır, w1-w4 renormalize (toplam 1.0)
- Score 4 sinyalden hesaplanır

Post-generation çağrı (`compute_retrieval_confidence(plan, chunks, answer_text=text)`):
- 5 sinyal tam fusion
- `final_confidence.citation_density` SSE done event'a dahil

## missing list — UI insufficiency CTA için

```python
missing = []
if semantic < 0.50: missing.append("low_semantic")
if source_count < 0.40: missing.append("low_source_count")
if recency < 0.30 and plan.timeframes: missing.append("recency_mismatch")
if entity_match < 0.50 and plan.critical_entities: missing.append("entity_mismatch")
if citation is not None and citation < 0.20: missing.append("low_citation_density")
```

InsufficiencySignal UI banner (2D) bu listeyi kullanıcıya gösterir (gelecekte).

## Eşikler

`retrieval.confidence_t_high` (default 0.70):
- score >= T_high → **Layer 1 STRICT** (haber arşivi, Wikipedia leak yok)

`retrieval.confidence_t_low` (default 0.40):
- score < T_low → **Wikipedia CTA** (kullanıcı onayı zorunlu)
- arası → **hybrid** (Layer 1 cevap + insufficiency banner)

Eşikler admin tunable (`apps/api/app/api/admin_settings.py`).

## Eval-driven kalibrasyon

Şu an default ağırlıklar tahmin. Production verisi (1 hafta) toplandıktan sonra:
- 50 manuel etiketli sorgu (mix)
- Grid search w1-w5 + T_high/T_low
- Routing decision accuracy ≥80% hedef

## Performance

- Compute süresi: ~0.5ms (in-memory, 10 chunks için)
- Yan etki yok (chunks dict'i okur, mutate etmez)
- Hot path'te: chat_stream Step 3.5

## İlişkiler

- Üst decision: [[confidence-based-routing]]
- Üst karar: [[tiered-knowledge-architecture]]
- Entity sinyali: [[critical-entity-must-match]]

## Kaynaklar

- `apps/api/app/core/retrieval_confidence.py`
- `apps/api/tests/unit/test_retrieval_confidence.py` (18 test)
- GitHub Issue #809 / PR #810
