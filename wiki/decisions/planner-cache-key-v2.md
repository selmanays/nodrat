---
type: decision
title: "Planner cache key v1 → v2 (critical_entities schema bump, #778)"
slug: "planner-cache-key-v2"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-17"
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

## #947 — cache key'e PROMPT_VERSION (gizli-stale çözümü)

> 🔧 **Kök:** `_cache_key = sha1(request_text|locale|tier|date_yyyymmdd)` — `CACHE_KEY_VERSION` (şema, manuel) vardı ama **planner prompt/mantık sürümü (PROMPT_VERSION) YOKtu**. TTL 24h. Sonuç: bir prompt/planner-mantığı düzeltmesi deploy edildiğinde, **o gün içinde deploy-öncesi (eski/bozuk) yazılmış cached planlar 24h boyunca servis edilmeye devam ediyordu**. conv 06a034cf kanıt: "Özgür özelle…son gelişmeler neler" Redis'te `critical_entities=['gelişmeler','özgür']` (BOZUK) ttl~24h; #947-A kodu doğru olsa da chat-path cache-hit eski planı döndürüyordu (`use_cache=False` izole test "çözüldü" derken). **Gizli sistemik:** #939/#940/#942 dahil tüm geçmiş planner-prompt fix'lerinin "canlıda gecikmeli/etkisiz" görünmesinin muhtemel ortak nedeni buydu.
>
> **Fix:** `_cache_key`/`get_cached_plan`/`set_cached_plan` opsiyonel `prompt_version` param; `plan_query` `PROMPT_VERSION` geçirir. `raw = f"{prompt_version}|{request}|{locale}|{tier}|{date}"`. **Circular import yok** — `planner_cache` `query_planner`'ı import etmez (caller besler). Prompt/planner her değişince (PROMPT_VERSION bump) eski gün-içi cache otomatik MISS → fresh plan; **deploy etkisi anında + tüm gelecek planner fix'leri kapsanır**. `CACHE_KEY_VERSION` (şema) korunur — iki bağımsız invalidation ekseni. Geriye-uyumlu (`prompt_version=""` default → eski davranış). Ders [[chat-knowledge-evolution]] #30 (cache key daima onu besleyen kod/prompt sürümünü içermeli; izole test ≠ prod-path).

## İlişkiler

- [[critical-entity-must-match]] — schema bump'a neden olan feature
- [[chunks-first-retrieval]] — retrieval gate
- [[planner-bypass-short-query]] — paralel cache mekanizması
- [[planner-critical-entity-tr-guard]] — #947: bu sayfanın PROMPT_VERSION-invalidation'ı, o sayfadaki prompt/backstop fix'inin canlıya ANINDA yansımasının önkoşulu (yoksa 24h gizli-stale)

## Kaynaklar

- PR [#779](https://github.com/selmanays/nodrat/pull/779) (commit 78e7daa)
- `apps/api/app/core/planner_cache.py`
