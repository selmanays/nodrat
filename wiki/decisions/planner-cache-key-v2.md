---
type: decision
title: "Planner cache key v1 → v2 (critical_entities schema bump, #778)"
slug: "planner-cache-key-v2"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "apps/api/app/core/planner_cache.py"
tags: ["locked-decision", "cache", "planner"]
aliases: []
---

# Planner cache key v1 → v2

> **Karar:** `apps/api/app/core/planner_cache.py:CACHE_KEY_VERSION` "v1" → "v2". Cache key namespace değişti (Redis prefix `qp:v2:*`).
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

Query Planner PROMPT_VERSION 1.2.1 → 1.3.0 ile yeni JSON field eklendi: `critical_entities` (1-3 diskriminatif kelime). Eski cache'lenmiş plan'larda bu field YOK.

Cache key v1'de tutulan plan'lar deserialize edildiğinde `critical_entities = []` döner → must-match retrieval gate boş list ile çalışır → niş entity sorgularında recall kaybı (target article kayıp).

## Çözüm

`CACHE_KEY_VERSION = "v2"` — namespace değişikliği. Eski `qp:v1:*` key'leri 24h TTL ile doğal expire olur (Redis FLUSH gerek yok).

```python
# Before
CACHE_KEY_VERSION = "v1"

# After (#778)
CACHE_KEY_VERSION = "v2"  # critical_entities schema bump
```

Cache miss durumunda yeni plan oluşturulur, `qp:v2:*` namespace'inde saklanır. 24h sonra eski v1 cache tamamen temizlenir.

## Sonuç

24h içinde tüm planner cache "yeni schema"ya geçer. Mevcut user'lar 24h boyunca cache-miss yaşar (LLM çağrısı yapılır, ~1.5s), sonra normal cache hit oranı.

## İlişkiler

- [[critical-entity-must-match]] — schema bump'a neden olan feature
- [[chunks-first-retrieval]] — retrieval gate
- [[planner-bypass-short-query]] — paralel cache mekanizması

## Kaynaklar

- PR [#779](https://github.com/selmanays/nodrat/pull/779) (commit 78e7daa)
- `apps/api/app/core/planner_cache.py`
