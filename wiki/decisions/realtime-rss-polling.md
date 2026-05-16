---
type: decision
title: "RSS realtime polling — adaptive tier + Conditional GET"
slug: "realtime-rss-polling"
status: "locked"
decided_on: "2026-05-10"
decided_by: "founder"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/alembic/versions/20260510_0100_sources_realtime_polling.py"
  - "apps/api/app/models/source.py"
  - "apps/api/app/core/rss.py"
  - "apps/api/app/workers/tasks/sources.py"
  - "apps/api/app/api/admin_sources.py"
  - "docs/engineering/data-model.md§3.1"
  - "docs/engineering/api-contracts.md§4.4"
  - "docs/legal/scraping-policy.md§3.2"
  - "GitHub Issue #565 / PR #571"
tags: ["locked-decision", "performance", "infrastructure", "mvp-3", "freshness"]
aliases: ["adaptive-rss", "rss-conditional-get", "rss-near-realtime"]
---

# RSS realtime polling — adaptive tier + Conditional GET

> **Karar:** RSS pipeline'ı sabit `crawl_interval_minutes=30` polling'den **adaptive tier**'a (hot=60sn / normal=5dk / cold=30dk / hibernate=4saat) dönüşüyor. Faz 0+1 (PR [#571](https://github.com/selmanays/nodrat/pull/571)) schema + Conditional GET + admin runtime edit foundation'ı; **Faz 2 (PR [#581](https://github.com/selmanays/nodrat/pull/581) + [#582](https://github.com/selmanays/nodrat/pull/582) hotfix) tier hesap fonksiyonunu shadow mode'da production'a aldı**. Beat refactor + worker concurrency Faz 3'tedir; tier_apply_enabled o zaman true yapılır. URL/scrape opt-in realtime Faz 4'tedir.
> **Durum:** locked (Faz 2 ship 2026-05-10, shadow mode aktif)
> **Tarih:** 2026-05-10 (PR [#571](https://github.com/selmanays/nodrat/pull/571) Faz 0+1 + PR [#581](https://github.com/selmanays/nodrat/pull/581)/[#582](https://github.com/selmanays/nodrat/pull/582) Faz 2 — production deploy)

## Bağlam

Mevcut RSS scheduler'ı her aktif kaynak için **sabit** `crawl_interval_minutes` (default 30 dk) kullanıyordu; Celery beat 15 dk'da bir due-check yapıyordu. Sonuç:

- **Anlık gündem kaçırma riski:** Bir haber yayınlandıktan sonra Nodrat'a gelmesi 0–30 dk arası.
- **Bandwidth israfı:** Her poll full feed indirir; yayıncı sunucusu için her seferinde `cache hit` olamayan trafik.
- **Banlanma riski:** İnterval'ı düşürmek yayıncıyı rahatsız eder; HTTP 429 + Retry-After handling yoktu.

[[data-pipelines]] §1 (source crawl) bu sınırlı modelin üstüne kuruluydu. "Gündem radarı" (#561 backlog) için ön gerek olarak **dakika seviyesinde freshness** lazımdı — kaynak banlanmasından kaçınarak.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Sabit interval'ı 30 dk → 1 dk düşür | Basit | Yayıncı banlama + queue saturation (50 source × 60 poll/saat = 3000 task/saat, mevcut worker ~50 task/saat işler) | reddedildi |
| WebSub / PubSubHubbub push | Gerçek zamanlı, polling yok | Türk haber siteleri tipik desteklemez; entegrasyon başına PR | reddedildi (sahanın gerçeği) |
| External Trends API (Google Trends, Twitter) | Zaten gündem signal'i hazır | Dış bağımlılık + maliyet + KVKK m.9 transfer riski | reddedildi (CLAUDE.md "dışa bağımlı olmasın") |
| **Adaptive tier + Conditional GET (selected)** | Tek katmanlı: kendi pipeline'ımızı verimleştir; sıfır dış bağımlılık; ETag ile yayıncı dostu (~%80 bandwidth ↓) | Faz'lar arasında dikkatli rollout (queue saturation Faz 3'te gözle) | **seçildi** |

## Mimari değişiklikler (Faz 0+1 ship — locked)

### Schema ([apps/api/alembic/versions/20260510_0100_sources_realtime_polling.py](../../apps/api/alembic/versions/20260510_0100_sources_realtime_polling.py))

`sources` tablosuna **5 nullable / default-eski-davranış kolon**:

| Kolon | Tip | Default | Amaç |
|---|---|---|---|
| `etag` | VARCHAR(255) | NULL | Önceki fetch ETag (`If-None-Match` için) |
| `last_modified` | VARCHAR(255) | NULL | Önceki fetch Last-Modified (`If-Modified-Since` için) |
| `realtime_enabled` | BOOLEAN | FALSE | Per-source opt-in (Faz 2 adaptive tier kapsama) |
| `polling_tier` | VARCHAR(16) | `'normal'` | `hot` \| `normal` \| `cold` \| `hibernate` (Faz 2'de hesaplanır) |
| `consecutive_unchanged` | INTEGER | 0 | Peş peşe 304 sayacı |

`app_settings` seed: `rss.realtime_master_enabled` (bool, default `false`) — global kill-switch.

### Conditional GET ([apps/api/app/core/rss.py](../../apps/api/app/core/rss.py), [[conditional-http-get]])

- `fetch_feed(etag=..., last_modified=...)` → `If-None-Match` + `If-Modified-Since` header'ları gider
- 304 Not Modified → `FeedReport.not_modified=True` early return; body parse yok, queue dispatch yok
- 200 OK → response header'larından yeni ETag/Last-Modified yakalanır, `FeedReport`'a yazılır
- Curl fallback (httpx h11 protocol err) extra_headers düşer; çağıran 200 OK fallback'i kabul eder (no harm)

Worker entegrasyonu ([apps/api/app/workers/tasks/sources.py](../../apps/api/app/workers/tasks/sources.py)):
- 304 path: `consecutive_unchanged++`, dispatch atlar
- 200 path: yeni etag/last_modified persist + `consecutive_unchanged=0`

### Admin ([apps/api/app/api/admin_sources.py](../../apps/api/app/api/admin_sources.py))

`PATCH /admin/sources/{id}` (yeni endpoint) — runtime tunable alanlar: `crawl_interval_minutes` (5–1440), `realtime_enabled`, `name`, `category`. Slug/domain/type/base_url **immutable**. Audit log: `source.update` from/to snapshot.

Web UI: `/admin/sources/[id]` detay sayfasında **"Polling ayarları"** kartı (interval input + realtime mode Switch).

### Adaptive tier ([[adaptive-polling-tier]] — Faz 2 ön schema)

| Tier | Kriter | Polling |
|---|---|---|
| **hot** | son 1 saatte ≥2 yeni item | 60 sn |
| **normal** | son 6 saatte ≥1 item (default) | 5 dk |
| **cold** | 6+ saattir yeni item yok | 30 dk |
| **hibernate** | 24+ saat değişmedi | 4 saat |

Tier dwell-time: 15 dk minimum (oscillation önleme). Yeni eklenen kaynak default `normal`, 24 saat sonra otomatik kalibre olur.

## Sonuçlar

- **Etkilenen entity/concept'ler:** [[conditional-http-get]] (yeni concept), [[adaptive-polling-tier]] (yeni concept Faz 2 prep), [[data-pipelines]] §1 (source crawl güncellendi), [[queue-management]] (Faz 3'te beat schedule değişecek), [[risk-source-fragility]] (R-OPS-01 mitigation güçlendi).
- **Bandwidth tasarrufu:** ETag desteği veren kaynaklarda ~%80 ↓ (production'da haberturk doğrulandı; BBC/TRT/Evrensel ETag göndermez — sunucu tarafı, kod hatası değil).
- **Hiç regression yok:** Migration nullable + global flag default false; mevcut RSS testleri davranış değişmediği için hâlâ yeşil.
- **API contract:** [docs/engineering/api-contracts.md §4.4](../../docs/engineering/api-contracts.md) PATCH spec güncel.
- **Data model:** [docs/engineering/data-model.md §3.1](../../docs/engineering/data-model.md) sources +5 kolon kanonik.

## Faz 2 ship sonrası gözlemler (2026-05-10)

Production'da PR [#581](https://github.com/selmanays/nodrat/pull/581) + [#582](https://github.com/selmanays/nodrat/pull/582) deploy sonrası ilk smoke:

- haberturk crawl → `would_be_tier='normal'`, `polling_tier='normal'` (DEĞİŞMEDİ — shadow mode çalışıyor ✅)
- `tier_metadata`: `{items_1h: 0, items_6h: 3, hours_since_new: 3.15, candidate_tier: 'normal', cold_start: false}`
- Migration zinciri: `20260509_0900` → `20260510_0100` → `20260510_0200` (SFT) → `20260510_0300` (consent) → `20260510_0400` (tier shadow). Hotfix gerekçesi: PR #581 ile #575/#574 paralel merge edildiği için ilk PR'da 0200 revision çakıştı; #582 ile zincirin sonuna alındı.

## Açık sorular / TODO

- **Faz 2 7-gün gözlem:** Tier hesabı production'da shadow modda. 7 gün boyunca `tier_metadata.computed_at` + `would_be_tier` distribution'ı izlenmeli. Gözlem soruları: oscillation oluyor mu (dwell-time yeterli mi)? haberturk gibi yoğun yayıncılar gerçekten `hot`'a giriyor mu (rolling 1h ≥ 2 yeterli proxy mi)? hibernate'de takılan kaynak var mı (false negative)?
- **Faz 3 (sonraki PR):** Celery beat 15dk → 30 sn due-check, `crawl_queue` worker concurrency 1-2 → 6 (DB pool size doğrulaması ile), jitter ±%15, HTTP 429 + Retry-After handling. `app_settings.rss.tier_apply_enabled=true` ile transition aktive edilir.
- **Faz 4 (sonraki PR):** URL/scrape kaynakları için opt-in `realtime_enabled` (default kapalı, min 5 dk cap, banlanma uyarısı + per-domain budget).
- **Hot tier polling süresi:** 60 sn ile başla, gözleme göre 30 sn'ye düşülebilir (Conditional GET aktifken yayıncı banlama riski düşük).
- **CDN davranışı:** haberturk gibi Merlin CDN arkası kaynaklar her node'dan farklı ETag dönebilir — 304 path nadiren tetiklenir. Bu sunucu davranışı; long-term Cache-Control `max-age` parsing ile fetch skip eklenebilir (yeni issue).

## İlişkiler

- [[extraction-confidence-telemetry]] — #578 shadow `would_be_tier`/`tier_metadata` sinyalini Teslimat 1 düşük-hacim gate'i tüketir ("tek sinyal, ayrı teslimat"; dinamik tarama sıklığı = bu kararın Faz 3 aktivasyonu, ayrı/ileride)
- [[multi-query-rewrite]]

## Kaynaklar

- [docs/engineering/data-model.md §3.1](../../docs/engineering/data-model.md) — sources tablosu yeni kolonlar
- [docs/engineering/api-contracts.md §4.4](../../docs/engineering/api-contracts.md) — PATCH /admin/sources/{id} tam spec
- [docs/legal/scraping-policy.md §3.2](../../docs/legal/scraping-policy.md) — rate limiting (Conditional GET source-friendly)
- [GitHub Issue #565](https://github.com/selmanays/nodrat/issues/565) / [PR #571](https://github.com/selmanays/nodrat/pull/571)
- İlgili: [[sse-streaming-default]] (paralel performans iyileştirmesi), [[risk-source-fragility]] (R-OPS-01)
