---
type: decision
title: "Retrieval result Redis cache (1h TTL) — warm hit sub-saniye"
slug: "retrieval-cache-1h-ttl"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/architecture.md§3"
tags: ["locked-decision", "rag", "performance", "cache"]
aliases: ["retrieval-cache"]
---

# Retrieval result Redis cache

> **Karar:** `hybrid_search_chunks` pipeline çıktısı Redis-backed 1h TTL ile cache'lenir. Warm hit'lerde tüm retrieve pipeline atlanır.
> **Durum:** locked
> **Tarih:** 2026-05-14

## A/B kanıt (niche_chunks_golden 11 sorgu, FLUSHDB sonrası)

| Senaryo | recall@5 | avg_latency |
|---|---|---|
| COLD (cache miss) | 0.727 | 4,099 ms |
| **WARM (cache hit)** | **0.727** | **1,001 ms** (-%76) |

## Tasarım

**Cache key:** `rqc:v1:{sha1(norm_query + top_k + candidate_pool + since_hours + tf_from + tf_to + sorted(critical_entities))}`

**TTL:** 1 saat — haber gündem dinamiği, 1h içinde yeni article gelse bile cache kabul edilebilir.

**Hit:** tüm pipeline atlanır (sparse + dense + summary + NER + keyword + critical_entity + rerank + parent_doc), direkt `list[dict]` döner.

**Miss:** pipeline çalışır + sonuç cache'lenir.

**Serialization:** UUID/datetime → ISO str. Re-deserialize `published_at` geri datetime.

**Fail-silent:** Redis hata durumunda pipeline normal çalışır (kullanıcı etkilenmez).

## Alternatifler

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| 24h TTL (planner cache gibi) | Daha çok hit | Bayat sonuç riski (haber 24h içinde değişir) | reddedildi |
| 5min TTL | Çok güncel | Düşük hit ratio | reddedildi |
| **1h TTL** | Hit ratio + freshness dengesi | Stale window 1h | **seçildi** |
| Materialized view | Disk üzeri | Schema rigid, update karmaşık | reddedildi |

## Geri alma maliyeti

> `retrieval_cache.py:get_cached_retrieval` her zaman None döndürse hit kapanır (kod-değişikliği). Veya Redis flushdb manuel. TTL otomatik (1h sonra hiç hit yok).

## İlişkiler

- [[planner-cache-key-v2]] — paralel cache (planner output)
- [[chunks-first-retrieval]] — wrap'lanan fonksiyon
- [[perf-sprint-2026-05-14]] — bu sprintın parçası

## Kaynaklar

- [PR #784](https://github.com/selmanays/nodrat/pull/784)
- [`apps/api/app/core/retrieval_cache.py`](apps/api/app/core/retrieval_cache.py)
