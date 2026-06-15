---
type: topic
title: "Gündem kaynak kataloğu (19 TR haber/doğrulama)"
slug: "gundem-source-catalog"
status: live
created: 2026-06-16
updated: 2026-06-16
sources:
  - "docs/engineering/data-model.md§3.1"
  - "docs/engineering/architecture.md§3.3"
tags: [sources, crawl, gundem, images, reliability]
aliases: [gundem-sources, gundem-catalog]
---

# Gündem kaynak kataloğu (19 TR haber/doğrulama)

## TL;DR
Bakınazık (genel-ilgi) kataloğundan farklı olarak **politik/güncel haber** odaklı 19 Türkçe kaynak (#1524). Seed Alembic migration ile (`is_active=FALSE`, idempotent) eklendi; **15 RSS + T24 + ANKA = 17 kaynak prod'da aktif** ve makale üretiyor. Diken + Resmî Gazete erişim/format engelleriyle deferred. Kaynak-bazlı `reliability_score` + her kaynağa özel [[generic-extractor-cascade|görsel site-profili]].

## Kaynaklar ve durum

### Aktif RSS (15) — feed Nodrat fetch_feed ile prod'dan doğrulandı
Cumhuriyet, Sözcü, BirGün, Medyascope, Kısa Dalga, DW Türkçe, Euronews Türkçe, Independent Türkçe, Teyit, Doğruluk Payı, Journo, Gerçek Gündem, Halk TV, dokuz8Haber, Yetkin Report.

### Aktif category_page — [[sitemap-ingestion-mode|sitemap mode]] ile
- **T24** — `/rss/*` Cloudflare challenge'da; `sitemap.xml` (dated sub) ile çözüldü → aktif.
- **ANKA Haber Ajansı** — public RSS yok; flat `sitemap.xml` (per-article lastmod) ile çözüldü → aktif.

### Deferred (#1526)
- **Diken** — tüm site Cloudflare (robots.txt bile 403) → bypass projenin "robots sıfır-tolerans + şeffaf NodratBot UA" kilitli kararıyla çelişir → **kurulmadı** (kullanıcı kararı).
- **Resmî Gazete** — WAF tüm bot-UA'ları (Googlebot dahil) timeout'luyor → çekirdeğe yaygın UA-spoof gerek; içerik regülasyon/PDF, marjinal fit → **defer**.

## reliability_score bandları (per-source, NUMERIC(3,2))
Fact-check ~0.92–0.95 (Doğruluk Payı 0.95, Teyit 0.92) · resmi-otorite 0.98 (Resmî Gazete) · uluslararası kurumsal ~0.84–0.86 (DW, Euronews) · uzman/analiz ~0.83 (Yetkin) · kurumsal-ulusal ~0.80–0.82 (Cumhuriyet, Sözcü, Journo) · bağımsız-dijital ~0.68–0.78. `source_configs` PATCH'te değişmez → migration'da set edilir.

## Aktivasyon
Tanım seed'le (`is_active=FALSE`); aktivasyon AYRI — `POST /admin/sources/{id}/activate` (canlı robots re-check + 5-maddelik compliance checklist + audit; compliance-bypass önleme). Bu oturumda agent prod API ile sürüldü (tek super_admin selmanaycom@gmail.com). ai-train sorunu YOK — Nodrat arama-motoru olarak çalışır (AI-training crawl'ı değil); NodratBot adlı bot-blok listelerinde değil, `*` altında izinli.

## Görsel düzeltmesi (#1538)
Yeni kaynaklar profil olmadığı için makalenin kendi görseli yerine boilerplate (ilgili-haber/sidebar/galeri-thumbnail/yazar-foto/UI-ikon) çekiyordu. 6 [[generic-extractor-cascade|site-profili]] + generic `.svg`-skip eklendi (≥10 makale/kaynak doğrulandı; örn. independent 16.4→1.4, halk-tv 11.7→1.8 görsel/makale). Eski temizlik: **1671 yanlış görsel silindi, 65 doğru eklendi**, tekrar-eden boilerplate sinyali 25→1.
- **known-gap:** yetkin-report/dw-turkce/dogruluk-payi 0 görsel (yanlış görsel YOK) — hero makale `<header>`'ında, global boilerplate-decompose siliyor (ayrı generic iş, regresyon riski).

## İlişkiler
- [[sitemap-ingestion-mode]] — T24/ANKA'yı açan mekanizma.
- [[generic-extractor-cascade]] — görsel site-profilleri + svg-skip.
- [[title-fallback-discovery]] — sitemap/başlıksız sayfalarda başlık kurtarma.
- [[risk-source-fragility]] — Cloudflare/JS-render/WAF kaynak kırılganlığı.
- [[robots-transient-vs-genuine-deactivation|robots compliance / transient]] — robots zero-tolerance + NodratBot şeffaf UA.

## Kaynaklar
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) §3.1 (sources, reliability_score)
- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §3.3 (crawl/discovery)
- Migration: `apps/api/alembic/versions/20260615_1300_seed_gundem_19_sources.py`
- Issue/PR: [#1524](https://github.com/selmanays/nodrat/issues/1524), [#1526](https://github.com/selmanays/nodrat/issues/1526), [#1538](https://github.com/selmanays/nodrat/issues/1538)
