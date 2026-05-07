---
type: entity
title: "Local BAAI/bge-m3 (production primary embedding provider)"
slug: "local-bge-m3"
category: "provider"
status: "live (primary)"
created: "2026-05-08"
updated: "2026-05-08"
last_op_status_check: "2026-05-08"
sources:
  - "apps/api/app/providers/local_embedding.py"
  - "apps/api/app/api/admin_settings.py§llm.use_local_embedding"
  - "apps/api/app/workers/tasks/maintenance.py§_reembed_chunks_async"
  - "apps/api/app/workers/tasks/embedding.py"
  - "apps/api/app/providers/registry.py§80"
  - "docs/engineering/architecture.md§4.2"
  - "docs/engineering/architecture.md§5.6"
  - "INDEX.md§4"
  - "PR #345, #346, #350"
tags: ["embedding", "provider", "local", "bge-m3", "vector", "rag", "primary"]
aliases: ["bge-m3-local", "local-embedding", "primary-embedding-provider", "LocalBgeM3Provider"]
---

# Local BAAI/bge-m3 (production primary embedding provider)

> **TL;DR:** Nodrat'ın **production primary embedding provider'ı** (2026-05-06 itibarıyla). `BAAI/bge-m3` modelini sentence-transformers ile **VPS CPU üzerinde** çalıştırır (1024-dim). Tüm `article_chunks` ve `agenda_cards` embedding'leri buradan üretilir. NIM bağımlılığı kalkmıştır — admin panel telemetry doğruluyor (NIM yedek 0 çağrı/gün, local 340 çağrı/gün, 2026-05-07 örnek). Maliyet $0/1M token (VPS CPU compute).

## Tanım

`LocalBgeM3Provider` ([apps/api/app/providers/local_embedding.py](../../apps/api/app/providers/local_embedding.py)) — `BAAI/bge-m3` SentenceTransformer modelini **build-time'da Dockerfile preload** ile container içine alır (~2.3 GB FP32). Runtime'da NIM endpoint çağırmaz, doğrudan kendi process'inde inference yapar. CPU mode'da çalışır (GPU gerekmez); Contabo Cloud VPS 40'ın 12 vCPU'su yeterli.

## Production durumu (2026-05-08 telemetry)

Admin panel (RAG İzlencesi → Özellik Anahtarları + Son 24 saat):

| Metric | Değer | Anlam |
|---|---|---|
| `llm.use_local_embedding` runtime override | **TRUE** (admin panel toggle) | Local primary aktif |
| `bge-m3 (local)` çağrı sayısı (örn. 2026-05-07) | **340** | Production primary embedding |
| `bge-m3 (NIM yedek)` çağrı sayısı | **0** | Fallback hiç tetiklenmiyor |
| `bge-reranker-v2-m3 (local)` | 0 | Local reranker scaffold (henüz aktif değil — ayrı feature flag `llm.use_local_rerank`) |

## Migration timeline

| Tarih | Commit / PR | Aşama |
|---|---|---|
| 2026-05-01 | architecture.md §4.2 not | Orthogonal keşfi (NIM nv-embedqa-e5-v5 ≠ BAAI/bge-m3, cosine ≈ 0) |
| 2026-04-XX | [#223](https://github.com/selmanays/nodrat/pull/223) | LocalBgeM3Provider scaffold (~2.3 GB FP32 Dockerfile preload) |
| 2026-04-XX | [#346](https://github.com/selmanays/nodrat/pull/346) (`bb230ae`) | feat/223-local-bge-m3-primary — primary'lik niyetli registry |
| 2026-04-XX | [#347](https://github.com/selmanays/nodrat/pull/347) | Eval gate — NDCG@10 acceptance threshold |
| 2026-05-06 | [#350](https://github.com/selmanays/nodrat/pull/350) (`3366ab3`) | **Migration tamamlandı:** `_reembed_chunks_async` + `_reembed_agenda_cards_async` task'ları; admin_settings entegrasyonu; registry primary swap. Closes #345. |
| 2026-05-06+ | (production) | DB chunks + agenda_cards re-embed task koşturuldu; `llm.use_local_embedding=true` admin panel'de set edildi; NIM yedek 0 trafiğe düştü |

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| Adapter sınıfı | `LocalBgeM3Provider` | apps/api/app/providers/local_embedding.py |
| Registry name | `local_bge_m3` | apps/api/app/providers/local_embedding.py:153 |
| Model | `BAAI/bge-m3` (orijinal HuggingFace) | sentence-transformers indirir |
| Boyut | 1024-dim | architecture.md §5.6 |
| Compute | CPU (Contabo VPS 40, 12 vCPU) | Dockerfile preload |
| Disk | ~2.3 GB FP32 (build-time) | Dockerfile §preload |
| Maliyet | $0/1M token | Dış sağlayıcı çağrısı yok |
| Runtime config key | `llm.use_local_embedding` (admin panel — production: TRUE) | apps/api/app/api/admin_settings.py:257 |
| Code default fallback | `use_local_embedding: bool = False` (env-var fallback only; `app_settings` DB row yoksa) | apps/api/app/config.py:128 |
| DB schema | `article_chunks.embedding vector(1024)` (re-embed edildi #350 ile) | architecture.md §5.5 |

## Latency (warm, smoke 2026-05-06)

```text
bge-m3 single:    106 ms
bge-m3 batch 16:  297 ms (19 ms/text — NIM ~250ms/single, 13x hızlı)
```

NIM endpoint round-trip eliminasyonu büyük kazanç sağladı — özellikle citation validation gibi yüksek-frekanslı işlerde.

## Kullanım yerleri (kod tabanı)

- **Worker:** [apps/api/app/workers/tasks/embedding.py](../../apps/api/app/workers/tasks/embedding.py) — yeni article chunk + agenda card embedding üretimi (Celery task `embedding_queue`, concurrency=1, batch=100)
- **`/app/generate` pipeline:** Her istekte ≥1 kez (query embedding) + citation validation phase (PR [#411](https://github.com/selmanays/nodrat/pull/411) ile batch refactor: tek mega-batch, N+1 → 1 round-trip)
- **`/ara` endpoint (Search-as-a-Service):** Public arama sorgu embedding'i
- **Re-embed maintenance:** [maintenance.py:522-697](../../apps/api/app/workers/tasks/maintenance.py:522) — `_reembed_chunks_async` + `_reembed_agenda_cards_async` (artık nadir kullanılır; #350 ile bir kez koşturulup tamamlandı)

## Cache durumu (doğrulanmadı)

⚠️ Architecture.md §5.3 "Redis embedding cache (TTL 24h, popular queries)" claim'i var ama **kod tabanında Redis embedding cache referansı bulunamadı** (2026-05-08 doğrulama). İki olasılık:

1. Cache plan aşamasında kaldı, henüz implement edilmedi
2. Cache var ama farklı naming ile (örn. provider-call cache, RAG context cache)

Re-doğrulama gerek; eğer gerçekten yoksa architecture.md sürüm bump'ı (§5.3 düzeltmesi) ayrı `nodrat-dev` görevi olabilir.

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]] (registry, factory pattern), [[binary-quantization]] (1024-dim → bit(1024) sıkışma scaffold).
- **İlgili varlıklar:** [[nim-bge-m3]] (legacy fallback — #350 öncesi primary'di, şimdi 0 trafik), [[deepseek]] (chat tarafı; embedding ile bağımsız feature flag).
- **İlgili kararlar:** [[deepseek-default-llm]] (provider abstraction sayesinde bağımsız migration mümkündü).
- **İlgili topics:** [[llm-provider-strategy]], [[pipeline-performance-baseline]] (embedding call sayısı tracking).

## Açık sorular / TODO (opsiyonel)

- **Local rerank flip:** `llm.use_local_rerank=false` hâlâ; production rerank NIM `nvidia/rerank-qa-mistral-4b` (62 çağrı/gün). Local bge-reranker-v2-m3 scaffold (#224) hazır. Embedding'in aksine reranker stateless — DB migration gerekmiyor; sadece eval gate (NDCG@10 ≥0.90, #347).
- **Cache claim doğrulaması:** Redis embedding cache architecture.md'de var, kodda yok — ya implement ya doc düzelt.
- **CPU vs GPU:** VPS CPU yeterli mi yoksa traffic ölçek alınca latency darboğaz oluyor mu? Şu an batch 16'da 19ms/text — kullanıcıya değer.

## Kaynaklar

- [apps/api/app/providers/local_embedding.py](../../apps/api/app/providers/local_embedding.py) — LocalBgeM3Provider class
- [apps/api/app/api/admin_settings.py:257](../../apps/api/app/api/admin_settings.py) — `llm.use_local_embedding` runtime tunable
- [apps/api/app/workers/tasks/maintenance.py:522-697](../../apps/api/app/workers/tasks/maintenance.py) — re-embed migration tasks
- [apps/api/app/core/settings_store.py](../../apps/api/app/core/settings_store.py) — runtime config singleton (`app_settings` DB tablosu, MVP-1.2 #262/#264)
- [apps/api/app/providers/registry.py:80](../../apps/api/app/providers/registry.py) — `_fallback("local_bge_m3", "nim_bge_m3")` routing
- [docs/engineering/architecture.md §4.2](../../docs/engineering/architecture.md) — adapter listesi
- [docs/engineering/architecture.md §5.6](../../docs/engineering/architecture.md) — local model providers
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) — `article_chunks` + `agenda_cards` + `app_settings` tablo şemaları
- PR [#223](https://github.com/selmanays/nodrat/pull/223), [#346](https://github.com/selmanays/nodrat/pull/346), [#347](https://github.com/selmanays/nodrat/pull/347), [#350](https://github.com/selmanays/nodrat/pull/350)
