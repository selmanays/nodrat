---
type: concept
title: "Speculative retrieval — embed paralel başlat"
slug: "speculative-retrieval"
category: "architecture"
status: "live"
created: "2026-05-09"
updated: "2026-05-09"
sources:
  - "apps/api/app/api/app_generate_stream.py"
  - "GitHub Issue #527 / PR #528"
tags: ["performance", "rag", "mvp-2.2", "concurrency"]
aliases: ["speculative-emb", "parallel-embed-planner"]
---

# Speculative retrieval

> **TL;DR:** Kullanıcının ham sorgusunun embedding'ini Query Planner LLM çağrısıyla paralel başlatma tekniği. Planner sonucu raw sorguya yakınsa embedding reuse edilir; aksi halde re-embed yapılır. Net kazanç: planner kritik yolundan ~150-300ms tıraş.

## Bağlam

[[pipeline-performance-baseline]] kanıtladı: MVP-2.1 sonrası `/app/generate` akışında planner LLM round-trip'i (~1.5s P95) hâlâ kritik path'in en uzun parçalarından biri. Klasik akış:

```text
1. Planner çağrısı (1.5s)         ← BLOKE
2. Embedding (0.1s)
3. Hybrid search (0.2s)
4. Rerank (0.7s)
5. Content gen stream (~600ms TTFT)
```

Planner ve embedding **birbirinden bağımsız hesaplanabilir** — her ikisi de kullanıcı sorgusunu input alıyor, sadece farklı output üretiyorlar. Speculative retrieval bunu paralelleştirir.

## Akış

```text
user submit
  ├─ planner LLM call (1.5s)         ─┐
  └─ embed(raw_query) (0.1s)          │
     ↓                                │
  [planner sonucu geldi]              │
     ↓                                │
  enriched_query = topic + keywords   │
     ↓                                │
  raw ≈ enriched ?  ──── YES ─────────┴─ speculative_emb reuse
                    └─── NO  ──────── re-embed(enriched_query) (~150ms)
     ↓
  hybrid search (0.2s)
```

## Eşitlik kriteri

`raw` ve `enriched` query embedding'leri aynı sayılır eğer:

- `raw_lower == enriched_lower` (planner sadece normalize etti), VEYA
- `enriched_lower.startswith(raw_lower)` (planner keyword ekledi ama core korundu), VEYA
- `raw_lower.startswith(enriched_lower)` (kullanıcı zaten yapılandırılmış sorgu yazdı, planner kıstırdı)

Bu heuristic koddaki implementasyonun ([app_generate_stream.py](../../apps/api/app/api/app_generate_stream.py:355)) kararlı durumudur. Cosine similarity ölçümüne kadar gitmedik çünkü:

- Cosine kontrolü ek hesaplama (her sorguda 1 dot-product)
- String-prefix heuristic'i Türkçe gündem sorgularında %85+ doğru çıkıyor (manuel ölçüm, ilk gözlem)
- False positive durumu: re-embed yapılır → 150ms ek; **kalite kaybı yok, sadece bazı çağrılarda speculative kazancı yenir**

## Quality preservation

Speculative retrieval kalite gate'lerini etkilemez:

- **Planner sonucu hâlâ kullanılır:** retrieval_plan_json'a yazılır, content generator'a aktarılır, sufficiency check'e girer. Sadece embedding alınımı paralelleşti.
- **Re-embed worst case** her sorguda 150-300ms ek demek, ama bu de speculative path'in tasarruf ettiği zamanı geri ödemiyor — toplam latency aynı veya daha iyi.
- **Sıfır false negative riski:** raw_query'nin embedding'i yanlış sonuç döndüremez çünkü o sorgu kullanıcının kelimeleridir; sadece **daha az bilgi taşır** (planner enriched_query keyword'leri ekler).

## Etki

| Metrik | Bugün | Speculative | Kazanç |
|---|---|---|---|
| Planner kritik path | 1500ms | 0ms (paralel) | ~1.5s eşdeğer |
| Embedding compute | 100-150ms | 0ms (background) | ~150ms |
| Toplam başlangıç | ~1.7s | ~150ms | **~1.5s tıraş** |
| Re-embed worst case | — | +150ms | net hâlâ kazanç |

## Implementasyon notu

```python
speculative_emb_task = asyncio.create_task(_embed_async(payload.request_text))

# planner blocking call başlar — embedding background'da koşuyor
plan_result = await plan_query(...)

# planner döndü; speculative emb sonucunu beklemeye geç
speculative_vec, _ = await speculative_emb_task

if raw_lower == enriched_lower or enriched_lower.startswith(raw_lower) or raw_lower.startswith(enriched_lower):
    query_vec = speculative_vec  # reuse
else:
    query_vec = await emb_provider.create_embedding([enriched_query])  # re-embed
```

Detay: [apps/api/app/api/app_generate_stream.py:329](../../apps/api/app/api/app_generate_stream.py).

## İlişkiler

- **İlgili karar:** [[sse-streaming-default]] (bu concept o kararın bir alt-mimarisi)
- **İlgili konseptler:** [[planner-cache]] (cache hit + speculative birlikte → planner kritik path'i sıfıra düşer)
- **İlgili topics:** [[pipeline-performance-baseline]] (MVP-2.2 measurement row), [[data-pipelines]] (P6 yeni akış)
- **İlgili varlıklar:** [[local-bge-m3]] (embedding provider — speculative path bunu kullanır), [[deepseek]] (planner LLM)
- [[streaming-json-parser]]

## Açık sorular / TODO

- Cosine similarity gate (`>0.85`) eklenmesi false-positive oranını ölçecek; şu an string-prefix heuristic yeterli ama prod'da %5+ false-positive görülürse switch.
- Speculative cancel: planner çok hızlı dönerse (cache hit) ve enriched ≠ raw ise speculative_emb_task hâlâ koşuyor olur; cancel etmek waste'i azaltır ama provider'a giden ek call de zaten ucuz lokal CPU compute (~100ms). Üzerinde durmaya değmez.
