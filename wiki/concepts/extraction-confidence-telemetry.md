---
type: concept
title: "Extraction-confidence telemetry — per-domain R-OPS-01 gate"
slug: "extraction-confidence-telemetry"
category: "metric"
status: "live"
created: "2026-05-16"
updated: "2026-05-17"
sources:
  - "docs/engineering/architecture.md§3.2"
  - "docs/strategy/risk-register.md§3.4"
tags: ["scrape", "telemetry", "R-OPS-01", "alarm", "source-health"]
aliases: ["extract-health", "per-domain-confidence"]
---

# Extraction-confidence telemetry — per-domain R-OPS-01 gate

> **TL;DR:** Kaynak başına 24 saatlik extraction başarı oranı (`cleaned / (cleaned+quarantine+discarded)`) hesaplanır, `source_health.avg_extract_confidence`'a yazılır; oran ayarlanabilir eşiğin altına düşerse kaynak `red` işaretlenir + görünür `warning` DLQ alarmı emit edilir. Bir kaynağın yapısı değişip extraction bozulduğunda saatler içinde yakalar (R-OPS-01 erken-uyarı).

## Tanım

`tasks.sources.recompute_extract_health` beat task'ı (6 saatte bir, :40) her kaynak için son 24h `cleaned_at`/`updated_at` üzerinden oranı hesaplar. Eskiden `source_health.avg_extract_confidence` kolonu tanımlı ama HİÇ yazılmıyordu (ölü); #904 onu canlı telemetriye çevirdi. "Confidence" burada per-makale extraction skoru değil, **kaynak düzeyinde başarı oranıdır** — operasyonel sağlık sinyali.

## Neden Nodrat'ta var

- **Hangi probleme cevap veriyor:** [[risk-source-fragility]] (R-OPS-01) — bir kaynak site redesign/SPA göçü yaptığında extraction sessizce bozulur; eski sistemde bu görünmezdi (1182 sessiz kayıp kök nedeni). Per-domain oran düşüşü erken uyarı verir.
- **Hangi alternatife karşı seçildi:** ayrı telemetri tablosu yerine mevcut 1:1 `source_health` kolonu yazılır (MVP disiplini); alarm için ayrı altyapı yerine mevcut `failed_jobs` warning severity reuse.
- **Hangi locked karar çağırıyor:** [[generic-extractor-cascade]] (#904) — görünürlük ilkesi (hata asla sessiz kaybedilmez).

## Formül / kural / parametre

- `rate = cleaned_24h / (cleaned_24h + quarantine_24h + discarded_24h)`; payda 0 ise dokunulmaz (sinyal yok).
- `rate < red_th` → `source_health.last_status='red'` (yalnız DOWNGRADE — robots/fetch kaynaklı red'i ezmez) + `warning` `failed_jobs` (`job_type='source.extract_health'`, GÖRÜNÜR, 24h tekrar-spam guard). `rate < yellow_th` → `yellow`.
- **Runtime-tunable (#911, Nodrat konvansiyonu):** `scraping.extract_health_red_threshold` (default **0.70** — R-OPS-01 KS-1 gate "%70"), `scraping.extract_health_yellow_threshold` (default **0.85**). `settings_store.get_float`; admin Ayarlar → scraping grubunda otomatik görünür; modül sabiti yalnız fallback.
- **Teslimat 1 — düşük-hacim gate'i (frekans sinyaline bağlı, #932):** Düşük-hacimli sessiz kaynaklarda 24h penceresinde küçük payda → oran istatistiksel gürültü → boş `red`+alarm (Arkitera 0.00 / IGN 0.43; extraction bozuk değil). `_is_low_volume(denom, min_sample, would_be_tier)`: `denom < scraping.extract_health_min_sample`(default **8**, runtime-tunable) **VEYA** [[realtime-rss-polling|#578 shadow frekans sinyali]] `would_be_tier ∈ {cold,hibernate}` ise → red+alarm **BASTIRILIR** + bu kaynağın açık `source.extract_health` alarmları auto-resolve + `last_status='red'`→`'unknown'` (yalnız alarm-origin red; robots/fetch-red [extract_health alarmı YOK, ör. Yeşil Gazete] **KORUNUR**). `avg_extract_confidence` yine yazılır (telemetri kaybı yok); `yellow` + aktif/yoğun kaynak davranışı **DEĞİŞMEZ**. **"Tek sinyal, ayrı teslimat":** mevcut `would_be_tier`/`tier_metadata` (her fetch'te yazılır) OKUNUR, sıfır yeni altyapı; dinamik tarama sıklığı (Teslimat 2) AYRI/ileride bir proje, bu gate onu kapsamaz — yalnız aynı sinyali tüketir.
- UI: kaynak detay sayfasında `ExtractionHealthCard` (avg conf renkli + quarantine oranı + 7g sparkline).

## İlişkiler

- **İlgili kararlar:** [[generic-extractor-cascade]] — görünürlük ilkesini uygulayan karar
- **İlgili kavramlar:** [[structured-data-extraction]] — başarısı bu metriği besleyen Tier-0
- **İlgili varlıklar:** [[risk-source-fragility]] — R-OPS-01 (skor 9→6, bu telemetri mitigation M5)
- **İlgili topics:** [[queue-management]] — warning severity DLQ yüzeyi
- **Frekans sinyali (Teslimat 1 gate girdisi):** [[realtime-rss-polling]] — #578 shadow `would_be_tier`/`tier_metadata`; düşük-hacim gate'i bu sinyali OKUR ("tek sinyal, ayrı teslimat"; dinamik tarama = ayrı/ileride Teslimat 2)

## Kaynaklar

- [docs/strategy/risk-register.md](../../docs/strategy/risk-register.md) §3.4 — R-OPS-01 mitigation
- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §3.2 — per-domain telemetri + Teslimat 1 düşük-hacim gate'i
- PR [#908](https://github.com/selmanays/nodrat/pull/908) (recompute_extract_health) · [#911](https://github.com/selmanays/nodrat/pull/911) (runtime-tunable eşik) · [#933](https://github.com/selmanays/nodrat/pull/933)/[#934](https://github.com/selmanays/nodrat/pull/934) (Teslimat 1 düşük-hacim gate + eski spurious auto-resolve)
