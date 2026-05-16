---
type: decision
title: "Generic extraction cascade + quarantine model (#904)"
slug: "generic-extractor-cascade"
status: "locked"
decided_on: "2026-05-16"
decided_by: "founder"
created: "2026-05-16"
updated: "2026-05-16"
sources:
  - "docs/engineering/architecture.md§3.2"
  - "docs/engineering/data-model.md§3.4"
  - "docs/product/prd.md§1.5"
  - "docs/strategy/risk-register.md§3.4"
  - "INDEX.md§4"
tags: ["locked-decision", "scrape", "extraction", "R-OPS-01"]
aliases: ["quarantine-model", "tier-0-jsonld-cascade", "904"]
---

# Generic extraction cascade + quarantine model (#904)

> **Karar:** Haber detay extraction'ı kaynağa-özel selector OLMADAN, kademeli generic sinyallerle yap (Tier-0 schema.org JSON-LD `articleBody` → trafilatura multi-mode density → meta/paragraf fallback); "iyi çıkarım yok" durumunu **sessiz kalıcı silme değil**, görünür+retryable `quarantine` durumu say.
> **Durum:** locked
> **Tarih:** 2026-05-16

## Bağlam

Production'da makalelerin **~%13'ü** (1212, günde ~180 artarak) kalıcı `status='archived'` ("İşlenemiyor") durumundaydı. Canlı DB + HTML probe ile kök neden kesinleşti: **%98,7'si `article.thin_content`** — `content_quality._is_thin_content` ham sayfa-geneli `<p>` sayımı yapıyor; `check_response_quality` extraction'dan **önce** çalışıp `<div>`-tabanlı / JSON-LD-gövdeli modern siteleri (Anadolu Ajansı 440, Fotomaç 337, Habertürk 313 = %92) terminal `archived`'a atıyordu. `severity='permanent_info'` DLQ auto-resolve nedeniyle kayıp **görünmezdi** ([[queue-management]] §483/#478 semantik karmaşası).

HTML probe kanıtı: bu URL'ler HTTP 200, server-rendered, içerik MEVCUT, hiçbiri SPA değil. Habertürk/Fotomaç tam metni schema.org JSON-LD `articleBody`'de (1300+/827 char) — JS'siz generic kurtarılabilir. AA SSR, gövde `<p>` değil; trafilatura density gerekir ([[data-pipelines]] §Kural A6 / #529 zaten vardı ama gate by-pass ediyordu). Yani sorun "selector bozuk" değil — **kaynağa-özel detay selector hiç doldurulmamıştı** (17 aktif kaynaktan 4'ünde config), tüm yük zaten generic trafilatura/fallback'teydi ve `<p>`-sayan terminal gate kurtarılabilir içeriği sessizce yok ediyordu.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Per-site detay selector'ları doldur (R-OPS-01 M2/M3 eski mitigation) | Temiz extraction | Her kaynakta bakım yükü; site redesign'da kırılır; 17 kaynakta hiç doldurulmamıştı (kanıtlı işlemiyor) | reddedildi |
| Sadece thin_content eşiğini gevşet | Küçük değişiklik | `<p>`-sayım heuristiği yapısal yanlış; `<div>`-CMS hâlâ kaçar | reddedildi |
| Headless render (Playwright) tüm sitelere | JS-SPA çözer | MVP cut-list #71 LATER; canlı veri mevcut kaybın SPA OLMADIĞINI kanıtladı (gereksiz maliyet) | **ertelendi** (deferred `RenderClient` seam, impl yok) |
| **Generic Tier-0 JSON-LD → density → fallback cascade + quarantine** | Per-site kod YOK; site redesign'a dayanıklı (JSON-LD stabil); kurtarılabilir hata kalıcı kaybedilmez | Kademe başına biraz CPU | **seçildi** |

## Sonuçlar

- **Extraction kademesi** ([[structured-data-extraction]]): selectors(legacy/None) → **Tier-0 structured-data** → trafilatura multi-mode density (#529) → fallback → `.successful`/longest tie-break (Tier-0 dahil). `extract_article` (apps/api/app/core/extractor.py).
- **Quality gate yönlendirici** (infazcı değil): gerçek `soft_404`/duplicate/invalid → terminal `discarded`; `thin_content` artık advisory → cascade yine çalışır; tüm kademe başarısızsa → `quarantine`.
- **Status taksonomisi:** `archived` status DEĞERİ kaldırıldı (#483 overload çözüldü) → `quarantine` (extraction-miss, GÖRÜNÜR + retryable) + `discarded` (gerçek kalıcı: true soft_404/duplicate/invalid — TEK terminal). Cold-tier `archived_at`/`cold_storage_key` AYRI alanlar, ETKİLENMEZ ([[hot-cold-tier]]).
- **Retry deneme-tabanlı:** `articles.extract_attempts` sayacı; `retry_failed` yaş-tabanlı (`created_at` 72h) yerine `extract_attempts < max_attempts`; tükenmiş quarantine → discarded. `recover_quarantined` tek-seferlik toplu kurtarma (admin maintenance run-now).
- **Görünürlük:** yeni `severity='discarded_info'` (yalnız gerçek kalıcı auto-resolve+gizli); extraction-miss `severity='warning'` (GÖRÜNÜR, auto-resolve YOK) — [[queue-management]] severity modeli güncellendi.
- **Telemetri:** [[extraction-confidence-telemetry]] — per-domain extract-confidence; <eşik → warning DLQ alarmı (R-OPS-01 gate, [[risk-source-fragility]] skor 9→6).
- **Legacy temizlik:** ölü detay-selector yolu + `crawler_jobs` tablosu/model/endpoint kaldırıldı. `category_page` liste selector'ları (`crawl_category`) KORUNUR.
- **Prod sonuç (2026-05-16):** 1197 quarantine → recover; `cleaned` 7769 → 8938 (+1169 kurtarıldı), `archived`=0, AA/Fotomaç/Habertürk generic cascade ile `cleaned`'e geçti.

İlişkili: [[structured-data-extraction]], [[extraction-confidence-telemetry]], [[queue-management]], [[data-pipelines]], [[risk-source-fragility]], [[hot-cold-tier]].

## Geri alma maliyeti

> Geri alınırsa: `articles.status` CHECK migration (0100) downgrade (quarantine/discarded → archived, lossy), `extract_attempts`/`discarded_info` geri (0200/0300), `crawler_jobs` recreate (0400 down). Kod: extractor cascade + content_quality gate + cleaning state machine + retry/recovery + admin UI lockstep + telemetri geri alınır. ~1200 kurtarılan makale yeniden değerlendirilir. Pratikte geri alınmaz — kök neden çözümü, kalite makinesi (RRF/top_k/rerank) DEĞİŞMEDİ.

## Kaynaklar

- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §3.2 — extraction cascade + failure routing
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) §3.4 — articles.status taksonomi + extract_attempts
- [docs/strategy/risk-register.md](../../docs/strategy/risk-register.md) §3.4 — R-OPS-01 mitigation (9→6)
- Epic [#904](https://github.com/selmanays/nodrat/issues/904) · PR [#905](https://github.com/selmanays/nodrat/pull/905)/[#908](https://github.com/selmanays/nodrat/pull/908)/[#911](https://github.com/selmanays/nodrat/pull/911)/[#913](https://github.com/selmanays/nodrat/pull/913)
