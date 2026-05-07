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
  - "apps/api/app/providers/local_embedding.py"
  - "apps/api/app/api/admin_settings.py§llm.use_local_embedding"
  - "apps/api/app/workers/tasks/maintenance.py§_reembed_chunks_async"
  - "docs/engineering/architecture.md§4.2"
  - "docs/engineering/architecture.md§5.6"
  - "INDEX.md§4"
  - "PR #345, #346, #350"
tags: ["embedding", "provider", "nim", "vector", "rag", "fallback"]
aliases: ["nim-embedding", "legacy-embedding-provider"]
---

# NIM bge-m3 (legacy embedding provider, fallback only)

> **TL;DR:** Eski default embedding provider'ı. **Production'da artık kullanılmıyor** (2026-05-06 itibarıyla [PR #350](https://github.com/selmanays/nodrat/pull/350) ile local bge-m3'e migrate edildi). NIM endpoint adapter (`name='nim_bge_m3'`) pratikte `nvidia/nv-embedqa-e5-v5` modelini serve ediyordu (1024-dim) — adı yanıltıcı. Şimdi sadece runtime override fallback'i (admin panel `llm.use_local_embedding=false` çevrildiğinde devreye girer; aksi halde 0 trafik alır).

## Tanım

NIM `nim_bge_m3` provider'ı, adından beklendiği gibi BAAI/bge-m3 embedding modelini değil, NVIDIA'nın kendi `nvidia/nv-embedqa-e5-v5` modelini serve ediyordu (1024-boyut). Bu farkın keşfi 2026-05-01 civarında yapıldı: NIM'de gerçek `baai/bge-m3` endpoint'i HTTP 500 veriyordu, default `nvidia/nv-embedqa-e5-v5`'e değişti — schema `vector(1024)` korundu ama embedding semantik uzayı farklı.

Local `BAAI/bge-m3` ile NIM `nv-embedqa-e5-v5` cosine ≈ 0 (orthogonal). Bu yüzden geçiş için DB'deki tüm `article_chunks` + `agenda_cards` re-embed migration gerekiyordu. Bu migration **#350 ile tamamlandı** (2026-05-06).

## Production durumu (2026-05-08 telemetry)

Admin panel telemetry (RAG İzlencesi → Özellik Anahtarları + Son 24 saat):

| Metric | Değer | Anlam |
|---|---|---|
| `llm.use_local_embedding` | **AÇIK** (admin panel toggle) | Runtime override aktif |
| `bge-m3 (local)` çağrı sayısı | 340 (örn. 2026-05-07) | Primary embedding provider |
| `bge-m3 (NIM yedek)` çağrı sayısı | **0** | Fallback hiç tetiklenmiyor |
| `bge-reranker-v2-m3 (local)` | 0 | Local reranker scaffold (henüz aktif değil — NIM rerank çalışıyor) |
| `nvidia/rerank-qa-mistral-4b` | 62 | Rerank hâlâ NIM'de (ayrı feature flag `llm.use_local_rerank`) |

Yani: **embedding tarafı tamamen local'de**, NIM bge-m3 endpoint sadece kâğıt üzerinde fallback. Rerank tarafı hâlâ NIM (ayrı bir feature gate, scope dışı).

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| Adapter adı | `nim_bge_m3` (legacy) | apps/api/app/providers/registry.py |
| Asıl serve edilen model (NIM tarafında) | `nvidia/nv-embedqa-e5-v5` | architecture.md §4.2 |
| Boyut | 1024-dim | architecture.md §4.2 |
| Endpoint | NIM (sadece fallback) | architecture.md §4.2 |
| API key env | `NIM_API_KEY` (rerank ve VLM için hâlâ kullanılıyor) | architecture.md §7.2 |
| Cost (NIM tier) | $0 (NIM free, irrelevant — kullanılmıyor) | architecture.md §4.2 |
| DB schema | `article_chunks.embedding vector(1024)` (local bge-m3 ile re-embed edildi #350) | architecture.md §5.5 |
| Runtime config key | `llm.use_local_embedding` (admin panel — production: TRUE) | apps/api/app/api/admin_settings.py:257 |
| Code default | `use_local_embedding: bool = False` (env-var fallback only; runtime app_settings override eder) | apps/api/app/config.py:128 |

## Migration timeline

| Tarih | Commit / PR | Aşama |
|---|---|---|
| 2026-05-01 | architecture.md §4.2 not | Orthogonal keşfi (NIM nv-embedqa-e5-v5 ≠ BAAI/bge-m3) |
| 2026-04-XX | [#223](https://github.com/selmanays/nodrat/pull/223) (`bb230ae`) | LocalBgeM3Provider scaffold (~2.3 GB FP32, Dockerfile preload) |
| 2026-04-XX | [#346](https://github.com/selmanays/nodrat/pull/346) | Eval gate (#347) — NDCG@10 acceptance threshold |
| 2026-05-06 | [#350](https://github.com/selmanays/nodrat/pull/350) (`3366ab3`) | **Migration tamamlandı:** `_reembed_chunks_async` + `_reembed_agenda_cards_async` task'ları; admin_settings entegrasyonu; registry primary swap. Closes #345. |
| 2026-05-06+ | (production) | DB chunks + agenda_cards re-embed task koşturuldu; `llm.use_local_embedding` admin panel'de TRUE'ya çevrildi; NIM yedek 0 trafiğe düştü |

## Local bge-m3 (production primary)

```text
LocalBgeM3Provider     BAAI/bge-m3 ~2.3 GB FP32 (apps/api/app/providers/local_embedding.py)
NimEmbeddingProvider   nvidia/nv-embedqa-e5-v5 (legacy fallback — runtime override ile)

Runtime config (production):
  app_settings DB row: llm.use_local_embedding = true (admin panel'den set edildi)
  → SettingsStore singleton (apps/api/app/core/settings_store.py) cache eder
  → registry.bootstrap_default_providers LocalBgeM3Provider'ı primary yapar

Latency (warm, smoke 2026-05-06):
  bge-m3 single:    106 ms
  bge-m3 batch 16:  297 ms (19 ms/text — NIM ~250ms/single, 13x hızlı)

Maliyet: $0/1M token (VPS CPU compute, dış sağlayıcı çağrısı yok).
```

## Re-embed migration (kapanış kanıtı)

`apps/api/app/workers/tasks/maintenance.py:522-697` içinde:

- `_reembed_chunks_async(batch=100)` — `article_chunks.embedding` kolonunu local bge-m3 ile yeniden hesaplar, sentinel ile idempotent
- `_reembed_agenda_cards_async(batch=100)` — `agenda_cards.embedding` aynı pattern

Production'da koşturulduktan sonra admin panel `llm.use_local_embedding=true` çevrildi. Telemetry doğruluyor: bge-m3 (NIM yedek) son 7 gün boyunca **0 çağrı**.

## Kalan TODO (opsiyonel)

- **Adapter rename consideration:** `nim_bge_m3` → `legacy_nim_embed_default` veya benzeri rename — fallback rolünde olduğu net olsun. Backward-compat için (`generation_log.provider_name` registry name) bilinçli olarak tutuldu.
- **Local rerank flip:** `llm.use_local_rerank=false` (production hâlâ NIM `nvidia/rerank-qa-mistral-4b` kullanıyor, 62 çağrı/gün). Local bge-reranker-v2-m3 scaffold hazır (#224) ama production'da aktif değil. Embedding gibi re-evaluation gate gerekecek mi? — Reranker stateless, DB migration gerekmez.
- **NIM bağımlılığı:** Embedding bitti, rerank devam ediyor, VLM (Llama 4 Maverick) hâlâ NIM'de — `NIM_API_KEY` operasyonel olarak hâlâ gerekli.

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]], [[binary-quantization]] (1024-dim → bit(1024) sıkışma).
- **İlgili varlıklar:** [[deepseek-v3]] (DeepSeek chat artık native API; embedding ayrı path'te local'e geçti).
- **İlgili kararlar:** [[deepseek-default-llm]] (provider abstraction sayesinde embedding migration'ı kolayca yapıldı).
- **İlgili topics:** [[llm-provider-strategy]].

## Kaynaklar

- [apps/api/app/providers/local_embedding.py](../../apps/api/app/providers/local_embedding.py) — LocalBgeM3Provider
- [apps/api/app/api/admin_settings.py:257](../../apps/api/app/api/admin_settings.py) — `llm.use_local_embedding` runtime tunable
- [apps/api/app/workers/tasks/maintenance.py:522-697](../../apps/api/app/workers/tasks/maintenance.py) — re-embed migration tasks
- [apps/api/app/core/settings_store.py](../../apps/api/app/core/settings_store.py) — runtime config singleton (app_settings DB tablosu)
- [docs/engineering/architecture.md §4.2](../../docs/engineering/architecture.md) — adapter listesi + NIM not
- [docs/engineering/architecture.md §5.6](../../docs/engineering/architecture.md) — local model providers
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) — `article_chunks` ve `agenda_cards` tabloları + `app_settings`
- PR [#223](https://github.com/selmanays/nodrat/pull/223), [#346](https://github.com/selmanays/nodrat/pull/346), [#350](https://github.com/selmanays/nodrat/pull/350)
