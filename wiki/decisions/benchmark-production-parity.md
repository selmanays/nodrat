---
type: decision
title: "Benchmark production-parity — V2 niche_chunks_benchmark"
slug: "benchmark-production-parity"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "apps/api/tests/eval/niche_chunks_benchmark.py (V1 — raw query)"
  - "apps/api/tests/eval/niche_chunks_benchmark_v2.py (V2 — production parity)"
tags: ["locked-decision", "eval", "benchmark"]
aliases: ["v2-benchmark", "production-parity-eval"]
---

# Benchmark production-parity (V2)

> **Karar:** Recall ölçümü artık **V2 niche_chunks_benchmark_v2** üzerinden yapılır. V2 tam production akışını taklit eder (planner + HyDE + multi-query embedding + critical_entities). V1 (raw query path) backward-compat için korunur ama kullanıcı kalite ölçümünde V2 referans alınır.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

V1 benchmark `hybrid_search_chunks`'ı raw query ile çağırıyor. Production `/app/generate-stream` akışı şunları yapar:
1. `plan_query` — `topic_query` + `critical_entities` çıkarımı
2. HyDE conditional — hipotetik passage üret (niş/soru-tipi sorgular için)
3. Multi-query batch embedding — `[raw, topic_query, hyde_doc]`
4. Her embed için `hybrid_search_chunks` → **RRF birleştirme**
5. `critical_entities` filter + RESCUE stream
6. Parent-doc retrieval

V1 sadece (4)'ün tek varyant versiyonunu test ediyordu — **production parity DEĞİL**.

## V1 vs V2 karşılaştırma

```
                 V1 (raw)         V2 (production)
  recall@5       0.727 (8/11)     0.727 (8/11)
  recall@10      0.727 (8/11)     0.818 (9/11)     ← +1 (niche_006 ✅)
  mrr@10         0.636            0.493
  avg_latency    4,099 ms         32,790 ms        (planner+HyDE+3x embed)
```

niche_006 V1'de fail görünüyordu ama V2'de #1 — yani **production'da kullanıcı niche_006 sorduğunda doğru cevabı alıyordu**. V1 recall ölçümü yanıltıcıydı.

## Hâlâ broken vakalar (V2, 2/11)

| ID | Query | Sebep |
|---|---|---|
| niche_007 | "ABD'nin hürmüz boğazının yüzde kaçını kullanma hakkı" | critical_entities = ['hürmüz boğazı', 'abd'] — "abd" article'da geçmiyor (ChatGPT'nin sözü), RESCUE pas geçer |
| niche_009 | "15 temmuz darbe girişimi mağdurun röportajı" | critical_entities = ['15 temmuz', 'mağdur'] — meta-kelimeler article gövdesinde yok |

Bu vakalar **chunk-level keyword extraction doğal limiti**. Article başlığı + chunk içeriği LLM'in dominant tema seçimine bağlı. Çözüm yolu: **sub-chunk indexing** (her paragraf için ayrı dense embedding + sentence-level retrieval) — gelecek sprint.

## Latency notu

V2 32s avg — pipeline tam: planner (~2s) + HyDE (~2s) + 3x embed (~0.5s) + 3x retrieve (~3s × 3 = 9s) + RRF (~0.05s). Production'da bu sürenin çoğu streaming TTFT'ye perde arkası gizlenir (kullanıcı planner sonrası ilk token'ı görür).

Hız optimize değil — V2 recall doğruluğu için.

## İlişkiler

- [[chunks-first-retrieval]] — retrieve fonksiyonu
- [[critical-entity-must-match]] — RESCUE stream
- [[chunk-keyword-extraction]] — chunk metadata
- [[perf-sprint-2026-05-14]] — hız sprint

## Kaynaklar

- [PR #789](https://github.com/selmanays/nodrat/pull/789)
- [`apps/api/tests/eval/niche_chunks_benchmark_v2.py`](apps/api/tests/eval/niche_chunks_benchmark_v2.py)
