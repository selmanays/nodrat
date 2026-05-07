---
type: entity
title: "NIM bge-m3 (legacy embedding provider, fallback only)"
slug: "nim-bge-m3"
category: "provider"
status: "live (fallback)"
created: "2026-05-07"
updated: "2026-05-08"
last_op_status_check: "2026-05-08"
sources:
  - "apps/api/app/providers/nim.py§NimEmbeddingProvider"
  - "apps/api/app/providers/registry.py§80"
  - "docs/engineering/architecture.md§4.2"
  - "INDEX.md§4"
  - "PR #350"
tags: ["embedding", "provider", "nim", "legacy", "fallback"]
aliases: ["nim-embedding", "legacy-embedding-provider", "NimEmbeddingProvider"]
---

# NIM bge-m3 (legacy embedding provider, fallback only)

> **TL;DR:** Legacy embedding provider'ı. Production'da **artık kullanılmıyor** (2026-05-06'da [PR #350](https://github.com/selmanays/nodrat/pull/350) ile [[local-bge-m3]]'e migrate edildi). NIM endpoint adapter (`name='nim_bge_m3'`) pratikte `nvidia/nv-embedqa-e5-v5` modelini serve ediyordu (1024-dim) — adı yanıltıcı (BAAI/bge-m3 değildi). Şimdi sadece **runtime override fallback** rolünde: admin panel `llm.use_local_embedding=false` çevrildiğinde devreye girer.

> 📖 **Production primary için bkz:** [[local-bge-m3]] — bu sayfa sadece legacy fallback rolü için. Detaylı migration timeline, telemetry, kullanım yerleri, latency benchmark'ları orada.

## Tanım

NIM `nim_bge_m3` adapter'ı, adından beklendiği gibi BAAI/bge-m3 değil, NVIDIA'nın kendi `nvidia/nv-embedqa-e5-v5` modelini serve ediyordu (1024-dim). Bu fark 2026-05-01 civarında keşfedildi: NIM'de gerçek `baai/bge-m3` endpoint'i HTTP 500 veriyordu, default `nvidia/nv-embedqa-e5-v5`'e değişti — schema `vector(1024)` korundu ama embedding semantik uzayı farklıydı.

Local bge-m3 ile NIM nv-embedqa-e5-v5 cosine ≈ 0 (orthogonal). Bu yüzden geçiş için DB chunks + agenda_cards re-embed migration gerekti (PR #350).

## Production durumu (2026-05-08)

| Metric | Değer |
|---|---|
| `llm.use_local_embedding` runtime override | TRUE (admin panel) |
| `bge-m3 (NIM yedek)` çağrı sayısı son 24 saat | **0** |
| Rolü | **Fallback only** — primary [[local-bge-m3]] |

## Önemli özellikler

| Parametre | Değer |
|---|---|
| Adapter sınıfı | `NimEmbeddingProvider` ([apps/api/app/providers/nim.py](../../apps/api/app/providers/nim.py)) |
| Registry name | `nim_bge_m3` ([registry.py:80](../../apps/api/app/providers/registry.py:80) `_fallback("local_bge_m3", "nim_bge_m3")`) |
| Asıl serve edilen model | `nvidia/nv-embedqa-e5-v5` (BAAI/bge-m3 DEĞİL) |
| Boyut | 1024-dim (schema `vector(1024)` ile uyumlu) |
| Endpoint | NIM (NVIDIA Inference Microservice) |
| API key | `NIM_API_KEY` (rerank ve VLM için hâlâ gerekli — embedding değil) |
| Cost | $0 (NIM free tier — kullanılmadığı için maliyet hesaba girmez) |

## Ne zaman devreye girer?

`llm.use_local_embedding=false` admin panel'de manuel kapatılırsa:
1. `LocalBgeM3Provider` factory `None` döner ([local_embedding.py:155](../../apps/api/app/providers/local_embedding.py:155))
2. Registry `_fallback("local_bge_m3", "nim_bge_m3")` ikinci adaya düşer
3. NIM `nim_bge_m3` aktif olur — DB'deki embedding'ler `local-bge-m3` ile üretilmiş olduğundan **cosine ≈ 0 nedeniyle retrieval bozulur**

> ⚠️ **Önemli:** Bu fallback sadece geçici outage senaryoları için tasarlandı. Sürekli kullanım için DB tekrar re-embed (NIM modeline) gerekir.

## İlişkiler

- **İlgili varlıklar:** [[local-bge-m3]] (production primary, BAAI/bge-m3 local), [[deepseek]] (chat — bağımsız flag).
- **İlgili kararlar:** [[deepseek-default-llm]] (provider abstraction sayesinde her iki migration bağımsız oldu).
- **İlgili topics:** [[llm-provider-strategy]].

## Kaynaklar

- [apps/api/app/providers/nim.py](../../apps/api/app/providers/nim.py) — NimEmbeddingProvider class
- [apps/api/app/providers/registry.py:80](../../apps/api/app/providers/registry.py) — fallback routing
- [docs/engineering/architecture.md §4.2](../../docs/engineering/architecture.md) — adapter listesi
- [INDEX.md §4](../../INDEX.md) — Çekirdek kararlar
- PR [#350](https://github.com/selmanays/nodrat/pull/350) — migration completion (closes #345)
