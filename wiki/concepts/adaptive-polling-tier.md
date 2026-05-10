---
type: concept
title: "Adaptive polling tier — hot/normal/cold/hibernate"
slug: "adaptive-polling-tier"
status: "live"  # Faz 2 (#578) shadow mode production'da; tier hesabı her başarılı fetch'te çalışıyor
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/models/source.py"
  - "apps/api/app/core/polling_tier.py"
  - "apps/api/alembic/versions/20260510_0100_sources_realtime_polling.py"
  - "apps/api/alembic/versions/20260510_0400_sources_polling_tier_shadow.py"
tags: ["scheduling", "rss", "freshness", "performance"]
aliases: ["polling-tier", "hot-cold-rss", "rss-tier"]
---

# Adaptive polling tier — hot/normal/cold/hibernate

> **TL;DR:** Her aktif RSS kaynağına yayın hızı izlenerek 4 tier'dan biri atanır: **hot** (60sn), **normal** (5dk), **cold** (30dk), **hibernate** (4 saat). Tier hesabı her başarılı fetch sonunda rolling-window üstünden çalışır. **Faz 0+1** (#565, PR [#571](https://github.com/selmanays/nodrat/pull/571)) schema foundation ship etti; **Faz 2** (#578, PR [#581](https://github.com/selmanays/nodrat/pull/581) + [#582](https://github.com/selmanays/nodrat/pull/582) hotfix) tier hesap fonksiyonunu shadow mode'da production'a aldı (2026-05-10). Şu an `would_be_tier` hesaplanıyor + `tier_metadata` JSONB telemetri yazılıyor ama `polling_tier` DEĞİŞMEZ. **Faz 3**'te apply mode aktif olunca polling_tier transition başlar.

## Tanım / Bağlam

Sabit `crawl_interval_minutes` modelinde nadir güncellenen kaynaklar (haftada 1-2 haber) sık güncellenenlerle aynı interval'ı kullanır → ya hızlı kaynak gecikir ya yavaş kaynak gereksiz kez yoklanır. [[realtime-rss-polling]] kararı altında bu disconnect tier sistemi ile çözülür: her kaynak gerçek yayın hızıyla orantılı sıklıkta poll edilir.

## Tier matrisi

| Tier | Kriter (rolling 24h) | Polling | Davranış notu |
|---|---|---|---|
| **hot** | son 1 saatte ≥2 yeni item | 60 sn | Conditional GET + jitter şart; gündem radarının canlı feed kaynağı |
| **normal** | son 6 saatte ≥1 item; default başlangıç | 5 dk | Yeni eklenen kaynak default tier |
| **cold** | 6+ saattir yeni item yok | 30 dk | Eski sabit interval davranışı; çoğu Türkçe haber feed'i bu tier'a düşer |
| **hibernate** | 24+ saat değişmedi (`consecutive_unchanged ≥ 24` proxy) | 4 saat | Az günceleyen blog/aggregator |

## Tier transition kuralları (Faz 2 implementasyon)

Production'a alınmış kurallar ([apps/api/app/core/polling_tier.py](../../apps/api/app/core/polling_tier.py)):

1. **Yön:** Tier her başarılı fetch sonunda yeniden hesaplanır (200 + 304 path).
2. **Dwell-time:** Her tier'da minimum **15 dk** kalınmalı (oscillation önleme).
3. **Cold start:** Kaynak `created_at < 24h` ise tier her zaman `'normal'` (DB query yok, telemetri için `cold_start=true` flag).
4. **Hibernate'den çıkış:** Önceki tier `hibernate` + `items_1h > 0` → direkt `normal`'e atla (dwell-time bypass).
5. **`consecutive_unchanged` sayacı:** [[conditional-http-get]] 304 path'inde artar; `tier_metadata`'da gözlem amaçlı tutulur (Faz 2'de doğrudan tier kararına etki etmez; ama hibernate proxy'si gibi gelecekte kullanılabilir).

İmplementasyon ayrılmış 3 saf fonksiyon:

```python
# 1. Sınıflandırıcı (state'siz)
def _classify_tier(*, items_1h, items_6h, hours_since_new) -> str:
    if items_1h >= 2: return "hot"
    if items_6h >= 1: return "normal"
    if hours_since_new is None or hours_since_new >= 24: return "hibernate"
    return "cold"

# 2. Transition kuralları
def _apply_transition_rules(*, candidate, current, tier_changed_at, items_1h, now):
    # Hibernate exit (dwell bypass)
    if current == "hibernate" and items_1h > 0:
        return "normal", True, 0.0
    # No transition
    if candidate == current:
        return current, False, 0.0
    # Dwell-time guard
    if tier_changed_at and (now - tier_changed_at) < timedelta(minutes=15):
        return current, False, dwell_remaining_sec
    return candidate, True, 0.0

# 3. Async entegre + DB query
async def compute_tier(source, db, *, now=None) -> TierComputation:
    # cold_start guard (DB query yok)
    if source.created_at < now - timedelta(hours=24):
        return TierComputation(tier="normal", metadata={"cold_start": True, ...}, transitioned=...)
    # rolling window count
    items_1h = await _count_items(db, source.id, now - timedelta(hours=1))
    items_6h = await _count_items(db, source.id, now - timedelta(hours=6))
    last_at = await _last_item_at(db, source.id)
    candidate = _classify_tier(...)
    final, transitioned, _ = _apply_transition_rules(...)
    return TierComputation(tier=final, metadata={...}, transitioned=transitioned)
```

Worker entegrasyonu (`tasks/sources.py:_compute_and_persist_tier`): shadow mode kontrolü `settings_store.get('rss.tier_shadow_mode', default=True)`. Hata path'i try/except — fetch task'ının başarısı tier hesabından bağımsız.

## DB schema

**Faz 0+1 (PR [#571](https://github.com/selmanays/nodrat/pull/571)):**

```python
realtime_enabled: bool = False        # per-source opt-in
polling_tier: str = 'normal'          # CHECK ('hot','normal','cold','hibernate')
consecutive_unchanged: int = 0        # 304 sayacı
```

**Faz 2 (PR [#581](https://github.com/selmanays/nodrat/pull/581) + [#582](https://github.com/selmanays/nodrat/pull/582)):**

```python
would_be_tier: str | None = None      # shadow mode hesabı; CHECK NULL OR ('hot',...)
tier_changed_at: datetime | None      # dwell-time guard (15dk minimum)
tier_metadata: dict | None            # JSONB telemetri
```

`tier_metadata` örneği (production'dan haberturk için):
```json
{
  "items_1h": 0,
  "items_6h": 3,
  "last_item_at": "2026-05-10T07:18:53+00:00",
  "hours_since_new": 3.15,
  "consecutive_unchanged": 0,
  "computed_at": "2026-05-10T10:27:52+00:00",
  "cold_start": false,
  "candidate_tier": "normal",
  "dwell_remaining_sec": 0.0
}
```

**Flag hiyerarşisi:**

```
master_enabled=false  → hiçbir kaynak adaptive tier kullanmaz (legacy crawl_interval_minutes)
master_enabled=true + tier_shadow_mode=true  (Faz 2 default) → would_be_tier hesaplanır, polling_tier dokunulmaz
master_enabled=true + tier_shadow_mode=false + tier_apply_enabled=true (Faz 3) → polling_tier = would_be_tier transition
```

`app_settings`:
- `rss.realtime_master_enabled` (default false) — global kill-switch
- `rss.tier_shadow_mode` (default true) — Faz 2 default
- `rss.tier_apply_enabled` (default false) — Faz 3'te true

## Worker concurrency etkisi (Faz 3 ön bilgi)

50 kaynak × hot tier (60 sn poll) = saatte **3000 task** (mevcut worker concurrency 1-2 ile **saatte 50 task**). Faz 3'te:

- `crawl_queue` worker concurrency 1-2 → 6 (12 vCPU VPS'te güvenli)
- Beat 15 dk → 30 sn due-check
- Jitter ±%15 dispatch offset (50 kaynak aynı saniyede tetiklenmesin)
- HTTP 429 + Retry-After handling (yayıncı banlama signal'i geldiğinde tier'ı `cold`'a düşür)

[[queue-management]] sayfası Faz 3 ship'inde güncellenecek.

## İlişkiler

- [[realtime-rss-polling]] — Bu concept'in kullanıldığı locked decision
- [[conditional-http-get]] — `consecutive_unchanged` sayacı için kaynak
- [[queue-management]] — Faz 3'te beat schedule + worker concurrency güncellenecek
- [[data-pipelines]] §1 — Source crawl pipeline; tier ile parametrik akış

## Kaynaklar

- [GitHub Issue #565](https://github.com/selmanays/nodrat/issues/565) / [PR #571](https://github.com/selmanays/nodrat/pull/571) — Faz 0+1 schema
- Faz 2 implementasyonu için ayrı issue açılacak (TODO)
