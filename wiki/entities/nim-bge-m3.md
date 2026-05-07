---
type: entity
title: "NIM bge-m3 (embedding provider)"
slug: "nim-bge-m3"
category: "provider"
status: "live"
created: "2026-05-07"
updated: "2026-05-08"
last_op_status_check: "2026-05-08"
sources:
  - "docs/engineering/architecture.md§4.2"
  - "docs/engineering/architecture.md§5.6"
  - "INDEX.md§4"
tags: ["embedding", "provider", "nim", "vector", "rag"]
aliases: ["nim-embedding", "default-embedding-provider"]
---

# NIM bge-m3 (embedding provider)

> **TL;DR:** Nodrat'ın default embedding provider'ı. Adapter adı `nim_bge_m3` ama NIM endpoint'i pratikte `nvidia/nv-embedqa-e5-v5` modelini serve eder (1024-dim). Tüm article chunk + agenda card embedding'leri bu sağlayıcıdan üretilir. ⚠️ Adı yanıltıcı — orijinal BAAI/bge-m3'ten farklı bir model — bkz. çelişki notu.

## Tanım

NIM `nim_bge_m3` provider'ı, adından beklendiği gibi BAAI/bge-m3 embedding modelini değil, NVIDIA'nın kendi `nvidia/nv-embedqa-e5-v5` modelini serve ediyor (1024-boyut). Bu farkın keşfi 2026-05-01 civarında yapıldı: NIM'de gerçek `baai/bge-m3` endpoint'i HTTP 500 verdiği için default `nvidia/nv-embedqa-e5-v5`'e değişti — schema `vector(1024)` korundu ama embedding semantik uzayı farklı.

> **Sonuç:** Local `BAAI/bge-m3` modelinden gelen embedding'ler ile NIM `nim_bge_m3`'ten gelenler **orthogonal** (cosine ≈ 0). Bu nedenle `USE_LOCAL_EMBEDDING` flag flip'i için DB'deki tüm chunks + agenda_cards re-embed migration gerekiyor (#345).

## Nodrat'ta kullanım

- **Hangi servis kullanır:** `apps/api/app/workers/embedding.py` → `NimEmbeddingProvider` (`packages/model-providers/nim_embed.py`).
- **Hangi MVP'de aktif:** MVP-1'den itibaren production'da.
- **Kullanım frekansı:** Tüm yeni article chunk'larında + agenda card oluşturulurken. Worker queue: `embedding_queue` (concurrency=1, batch=100).
- **Cache:** Redis embedding cache (TTL 24h, popular queries) — architecture.md §5.3.

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| Adapter adı | `nim_bge_m3` | architecture.md §4.2 |
| Asıl serve edilen model | `nvidia/nv-embedqa-e5-v5` | architecture.md §4.2 |
| Boyut | 1024-dim | architecture.md §4.2 |
| Endpoint | NIM | architecture.md §4.2 |
| API key env | `NIM_API_KEY` (eskiden DeepSeek chat ile ortaktı; #163'ten beri DeepSeek chat ayrı `DEEPSEEK_API_KEY` kullanıyor — embedding hâlâ NIM tarafında) | architecture.md §7.2 |
| Cost | $0 (NIM free tier) | architecture.md §4.2 |
| DB schema | `article_chunks.embedding vector(1024)` | architecture.md §5.5 |
| Local fallback | `LocalBgeM3Provider` (BAAI/bge-m3 ~2.3 GB FP32) | architecture.md §5.6 |
| Default config flag | `DEFAULT_EMBEDDING_PROVIDER=nim_bge_m3` | architecture.md §7.2 |

## Local fallback (MVP-1.5 PR-8 #223)

```text
LocalBgeM3Provider     BAAI/bge-m3 ~2.3 GB FP32
NimEmbeddingProvider   nvidia/nv-embedqa-e5-v5 (default)

Settings flag (default False — eval gate öncesi):
  USE_LOCAL_EMBEDDING (#223)

Latency (warm, smoke 2026-05-06):
  bge-m3 single:    106 ms
  bge-m3 batch 16:  297 ms (19 ms/text — NIM ~250ms/single, 13x hızlı)

Maliyet: $0/1M token (CPU compute, NIM bağımlılığı kalkar).
```

## 🟡 Açık operasyonel migration & kritik bilgi

1. **Adapter ismi vs. asıl model:** `nim_bge_m3` ismi yanıltıcı. architecture.md §4.2 ve bu wiki sayfası tutarlı şekilde "asıl model nv-embedqa-e5-v5" diyor — wiki ↔ docs çelişkisi yok. Adapter adını yeniden adlandırmak kod-düzeyinde refactor gerektiriyor — backward-compat için tutuldu.
2. **Embedding uzayı orthogonal:** Local bge-m3 ↔ NIM nv-embedqa-e5-v5 cosine ≈ 0. Flag flip için DB chunk + agenda_cards re-embed migration zorunlu (#345).
   - **Scaffold durumu (2026-05-08):** ✅ #345 (`2c8e1a2 feat(rag): NIM → local bge-m3 embedding migration + rerank eval gate`) ve #346 (`bb230ae feat/223-local-bge-m3-primary`) merged. LocalBgeM3Provider hazır, Dockerfile preload aktif, eval gate ekli.
   - **Production durumu:** `apps/api/app/config.py:128-146` `use_local_embedding: bool = False` default'u korunuyor. `.env.example:100` `DEFAULT_EMBEDDING_PROVIDER=nim_bge_m3`. Re-embed task production'da koşturulmadığı için DB hâlâ `nv-embedqa-e5-v5` embeddings içeriyor.
   - **Gerçek kapanış:** DB chunks + agenda_cards re-embed task çalıştırılıp `USE_LOCAL_EMBEDDING=true` flag flip yapıldığında.
3. **NIM'de baai/bge-m3 HTTP 500:** Orijinal model NIM endpoint'inde çalışmıyor (provider tarafı sorun, scaffold'ın local'e gitmesinin nedenlerinden).

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]], [[binary-quantization]] (1024-dim → bit(1024) sıkışma).
- **İlgili varlıklar:** [[deepseek-v3]] (eskiden NIM_API_KEY ortaktı; #163 sonrası DeepSeek chat native API + DEEPSEEK_API_KEY'e geçti, embedding hâlâ NIM_API_KEY).
- **İlgili kararlar:** [[deepseek-default-llm]] (NIM ekosistem kilitlenmesi nedenlerinden).
- **İlgili topics:** [[llm-provider-strategy]].

## Açık sorular / TODO

- **#345 migration:** Tüm chunks + agenda_cards re-embed task'ı planlandı mı? Storage etkisi (embedding kolonu yeniden yazılır) kontrol edildi mi?
- **#347 eval gate:** Local bge-m3'e geçiş için NDCG@10 eval'i geçilince flag flip yapılacak. Şu an default False.
- **Schema rename consideration:** Adapter `nim_bge_m3` → `nim_embed_default` veya benzeri rename adapter abstraction'a (concept) takılı; backward-compat tutmak istiyoruz.

## Kaynaklar

- [docs/engineering/architecture.md §4.2](../../docs/engineering/architecture.md) — adapter listesi + kritik NIM not
- [docs/engineering/architecture.md §5.6](../../docs/engineering/architecture.md) — local model providers
- [docs/engineering/architecture.md §5.5](../../docs/engineering/architecture.md) — DB schema, binary quantization
- [INDEX.md §4](../../INDEX.md) — Çekirdek kararlar
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) — `article_chunks` ve `agenda_cards` tabloları
