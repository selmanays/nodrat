---
type: concept
title: "Query Planner Redis cache — gün granülü"
slug: "planner-cache"
category: "performance"
status: "live"
created: "2026-05-09"
updated: "2026-05-09"
sources:
  - "apps/api/app/core/planner_cache.py"
  - "apps/api/app/prompts/query_planner.py"
  - "GitHub Issue #527 / PR #528"
tags: ["performance", "rag", "redis", "cache", "mvp-2.2"]
aliases: ["query-plan-cache", "qp-cache"]
---

# Query Planner Redis cache

> **TL;DR:** Query Planner LLM çıktısı (QueryPlan dict) Redis'te 24h TTL ile saklanır. Cache key: `qp:v1:{sha1(request_text + locale + tier + yyyymmdd)}`. Hit durumunda planner çağrısı yapılmaz; ~10ms vs ~1.5s LLM round-trip.

## Bağlam

[[pipeline-performance-baseline]] gözlemi: gündem sorguları **gün içinde tekrarlı** ("Bu hafta İsrail-Filistin", "Türkiye ekonomisi 5 madde özet" gibi sorgular farklı kullanıcılar tarafından gün içinde defalarca yazılır). Planner bu sorguların hepsi için aynı plan üretir — kullanıcı kelimesi normalize ediliyor, mode/output_type/tone parsing aynı çıkıyor.

24h TTL + gün granülü key cache hit ratio'yu %20-40 arası getiriyor (ilk gözlem; 7-gün rolling avg sonradan ölçülecek).

## Cache key tasarımı

```python
key = f"qp:v1:{sha1(request_text + '|' + locale + '|' + tier + '|' + yyyymmdd)}"
```

- **`request_text`:** kullanıcının ham metni — strip edilir, lowercase YAPILMAZ (case değişikliği farklı sorgu sayılır; ileride normalize eklenebilir).
- **`locale`:** `tr-TR`/`en-US` — planner output'u dil farklı verir, ayrı key.
- **`tier`:** `free`/`starter`/`pro`/`agency` — planner future'da tier'a göre `geographic_focus` defaultu farklı verebilir; key'de ayrı tutuyoruz.
- **`yyyymmdd`:** **gün granülasyonu** — "bugün" semantiği için kritik. Aynı sorgu 2026-05-09 ve 2026-05-10'da farklı timeframe içerir; cache day-roll yapmalı.

`v1` prefix ileride şema değişikliklerinde key bump için (örn. plan dict'e yeni alan eklenirse `v2`).

## TTL = 24h

- Daha kısa (örn. 6h) yapsak miss oranı artar; gündem sorguları gün içinde stabil.
- Daha uzun (örn. 48h) yapsak gün-roll edge case'i: gece 23:59 cache'lenen plan ertesi gün 00:01'de hâlâ canlı, ama key zaten `yyyymmdd` içerdiği için yeni key yazılır → eski entry doğal olarak expire olur.

24h optimal: gün-roll değişimini yansıtır + Redis memory pressure düşük (sorgu başına ~500B JSON).

## Hit ratio hedefi

İlk MVP-2.2 ölçümü: **%20-40 hit ratio**. Ölçüm:

```bash
redis-cli --scan --pattern "qp:v1:*" | wc -l   # toplam key
# Hit/miss telemetry — application logger'da "planner_cache HIT" satırları
```

Gerçek prod ratio 7-day rolling avg sonra eklenecek; eğer %15 altına düşerse key tasarımı revisable (case normalize, locale fallback gibi).

## Quality preservation

Cache'lenen plan **deterministic** olmalı:

- `parse_response` saf fonksiyondur, aynı LLM cevabı aynı QueryPlan üretir.
- Plan dict'i serialize ederken (`_plan_to_cache_dict`) tüm alanlar dahil; deserialize (`_plan_from_cache_dict`) bozuk veride None döner → caller miss kabul eder, planner LLM çağrılır.
- **Halü riski yok:** plan, retrieval kararıdır, içerik üretmez. Cache hit → aynı agenda kartlarına ulaşılır.
- **Cost runaway yok (R-FIN-01):** cache hit demek **planner LLM çağrısı tamamen atlanır** → ek harcama eksi yönde.

## Implementasyon notu

```python
# Get
cached = await get_cached_plan(
    request_text=user_request, locale=user_locale, tier=user_tier,
    current_time=now,
)
if cached:
    return _plan_from_cache_dict(cached)  # ~10ms

# LLM call (miss path)
result = await provider.generate_text(...)
parsed = parse_response(result.text)

# Set (best-effort, hatada sessiz)
if isinstance(parsed, QueryPlan):
    await set_cached_plan(
        request_text=user_request, locale=user_locale, tier=user_tier,
        plan_dict=_plan_to_cache_dict(parsed), current_time=now,
    )
```

Detay: [apps/api/app/core/planner_cache.py](../../apps/api/app/core/planner_cache.py), [apps/api/app/prompts/query_planner.py:495](../../apps/api/app/prompts/query_planner.py).

## Override / debug

- **Bypass:** `plan_query(use_cache=False)` cache'e bakmadan LLM çağırır (test/eval path).
- **Manual evict:** `redis-cli DEL qp:v1:<sha1>` veya pattern delete `redis-cli --scan --pattern 'qp:v1:*' | xargs redis-cli DEL` (gün rolling automatic, manual eviction nadir).

## İlişkiler

- **İlgili karar:** [[sse-streaming-default]] (planner cache, SSE streaming kararının alt-mimarisi)
- **İlgili konseptler:** [[speculative-retrieval]] (cache + speculative birlikte → planner kritik path 0)
- **İlgili topics:** [[pipeline-performance-baseline]] (MVP-2.2 row)
- **İlgili varlıklar:** [[deepseek]] (planner LLM — cache miss durumunda çağrılır)

## Açık sorular / TODO

- Cache hit/miss metric'i `provider_call_logs` üzerinden değil; ayrı counter (Redis INCR) gerekli — sonraki tur.
- Locale-cross-fallback: tr-TR ve tr ayrı key — ileride normalize edilebilir.
- Compression: 500B JSON için worth it değil; >2KB plan dict'i çıkarsa msgpack düşünülür.
