---
type: concept
title: "Adaptive polling tier — hot/normal/cold/hibernate"
slug: "adaptive-polling-tier"
status: "planned"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/models/source.py"
  - "apps/api/alembic/versions/20260510_0100_sources_realtime_polling.py"
tags: ["scheduling", "rss", "freshness", "performance"]
aliases: ["polling-tier", "hot-cold-rss", "rss-tier"]
---

# Adaptive polling tier — hot/normal/cold/hibernate

> **TL;DR:** Her aktif RSS kaynağına yayın hızı izlenerek 4 tier'dan biri atanır: **hot** (60sn), **normal** (5dk), **cold** (30dk), **hibernate** (4 saat). Tier hesabı her başarılı fetch sonunda rolling-window üstünden çalışır. Faz 0+1'de **schema foundation** ship edildi (default `'normal'` sabit); aktif tier hesabı **Faz 2** kapsamı.

## Tanım / Bağlam

Sabit `crawl_interval_minutes` modelinde nadir güncellenen kaynaklar (haftada 1-2 haber) sık güncellenenlerle aynı interval'ı kullanır → ya hızlı kaynak gecikir ya yavaş kaynak gereksiz kez yoklanır. [[realtime-rss-polling]] kararı altında bu disconnect tier sistemi ile çözülür: her kaynak gerçek yayın hızıyla orantılı sıklıkta poll edilir.

## Tier matrisi

| Tier | Kriter (rolling 24h) | Polling | Davranış notu |
|---|---|---|---|
| **hot** | son 1 saatte ≥2 yeni item | 60 sn | Conditional GET + jitter şart; gündem radarının canlı feed kaynağı |
| **normal** | son 6 saatte ≥1 item; default başlangıç | 5 dk | Yeni eklenen kaynak default tier |
| **cold** | 6+ saattir yeni item yok | 30 dk | Eski sabit interval davranışı; çoğu Türkçe haber feed'i bu tier'a düşer |
| **hibernate** | 24+ saat değişmedi (`consecutive_unchanged ≥ 24` proxy) | 4 saat | Az günceleyen blog/aggregator |

## Tier transition kuralları (Faz 2 spec)

1. **Yön:** Tier her başarılı fetch sonunda yeniden hesaplanır.
2. **Dwell-time:** Her tier'da minimum **15 dk** kalınmalı (oscillation önleme — bir kaynağın hot ↔ normal arasında dakikada zıplaması istemiyoruz).
3. **Cold start:** Yeni eklenen kaynak default `normal`. 24 saat boyunca tier kalibre olmaz; sonra normal akış.
4. **Hibernate'den çıkış:** İlk başarılı fetch'te 200 OK + yeni item gelirse direkt `normal`'e atla (4 saat beklemeyi atla — yeni içerik gelmiş anlamı).
5. **`consecutive_unchanged` sayacı:** [[conditional-http-get]] 304 path'inde artar; tier kararında "yayıncı ne kadar süredir hiç güncellemedi" proxy'si.

Pseudo-code (Faz 2'de yazılacak):

```python
def compute_tier(source: Source, now: datetime) -> str:
    items_last_1h = count_items(source.id, since=now - timedelta(hours=1))
    items_last_6h = count_items(source.id, since=now - timedelta(hours=6))
    hours_since_new = (now - source.last_item_at).total_seconds() / 3600

    if items_last_1h >= 2:
        candidate = "hot"
    elif items_last_6h >= 1:
        candidate = "normal"
    elif hours_since_new < 24:
        candidate = "cold"
    else:
        candidate = "hibernate"

    # Dwell-time guard
    if source.tier_changed_at and (now - source.tier_changed_at) < timedelta(minutes=15):
        return source.polling_tier  # respect dwell-time

    return candidate
```

## DB schema (foundation — Faz 0+1 ship)

[apps/api/app/models/source.py:68](../../apps/api/app/models/source.py) (PR [#571](https://github.com/selmanays/nodrat/pull/571)):

```python
realtime_enabled: bool = False        # per-source opt-in (Faz 2 kapsama)
polling_tier: str = 'normal'          # CHECK ('hot','normal','cold','hibernate')
consecutive_unchanged: int = 0        # 304 sayacı
```

CHECK constraint: `ck_sources_polling_tier`. Default `'normal'` — Faz 2 implementasyonu gelene kadar tüm kaynaklar aynı davranır.

Global kill-switch: `app_settings.rss_realtime_master_enabled` (default `false`). Hiyerarşi:

```
master_enabled=false  → hiçbir kaynak adaptive tier kullanmaz (legacy crawl_interval_minutes)
master_enabled=true   → realtime_enabled=true olan kaynaklar tier'a göre poll edilir
```

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
