---
type: decision
title: "Sitemap-ingestion discovery mode"
slug: "sitemap-ingestion-mode"
status: live
created: 2026-06-16
updated: 2026-06-16
sources:
  - "docs/engineering/architecture.md§3.3"
  - "docs/engineering/data-model.md§3.2"
tags: [crawl, discovery, sources, extraction]
aliases: [sitemap-mode, sitemap-discovery]
---

# Sitemap-ingestion discovery mode

## TL;DR
JS-render'lı / statik HTML'de makale listesi olmayan haber siteleri için **sitemap tabanlı makale keşfi**. `category_page` kaynağının aktif config'inde `sitemap_url` varsa, kart-scraping yerine sitemap'ten (`<urlset>`/`<sitemapindex>`) makale URL'leri keşfedilip mevcut generic extraction pipeline'ına beslenir. Şema değişikliği YOK (#1527 / PR [#1528](https://github.com/selmanays/nodrat/pull/1528)).

## Bağlam — neden var?
[[gundem-source-catalog]] eklenirken **T24** ve **ANKA** gibi siteler liste sayfalarını JavaScript ile render ediyordu → statik fetch'te HTML'de ~1 makale görünüyor, [[generic-extractor-cascade|kart-scraping]] (`extract_listing_cards`) çalışmıyor. Ancak bu sitelerin `sitemap.xml`'i **server-rendered** (T24: 5000 dated sub-sitemap, ANKA: 5025 URL + per-article lastmod). Sitemap = "hangi URL'ler makale" sorusunun JS-bağımsız cevabı.

## Karar / Mekanizma
- **Pure parser:** `app/shared/crawl/sitemap.py` → `parse_sitemap(xml) -> (entries, is_index)`. `<urlset>` (makale URL'leri) ve `<sitemapindex>` (alt-sitemap'ler), namespace-agnostik, `lastmod` ISO8601 parse. DOCTYPE/ENTITY reddi + 25MB guard (XXE/billion-laughs savunması).
- **Branch:** `category_page` Celery task'ı (`_discover_from_sitemap`) — config'de `sitemap_url` görünce kart-scraping yerine bu yol çalışır. **Yeni `type` / scheduler / şema değişikliği yok** — `category_page` zaten dispatch ediliyor.
- **Index → en yeni:** sitemapindex ise `subsitemap_pattern` (regex, örn. `sitemap-\d{8}`) ile filtre + en yeni `subsitemap_latest` alt-sitemap açılır.
- **Filtre:** `url_include` substring + `max_age_days` (lastmod recency) + `max_items` cap (5000 tarihsel URL ingest edilmez).
- **Başlık:** sitemap `<loc>` başlık taşımaz → URL slug'ından geçici başlık üretilir; gerçek başlığı [[title-fallback-discovery|title-fallback]] / `article_fetch_detail` doldurur.
- **Idempotent:** `discover` canonical-URL dedup → tekrar çalıştırma no-op.

## config_json alanları (`source_configs`)
`sitemap_url` (zorunlu, modu tetikler) · `subsitemap_pattern` (regex, opt) · `subsitemap_latest` (default 1) · `url_include` (substring) · `max_age_days` (int, opt) · `max_items` (default 50).

## Uygulanan kaynaklar
- **T24** (`sitemap-\d{8}` dated sub + `/haber/`) → 60 makale `cleaned` doğrulandı.
- **ANKA** (flat urlset + `url_include=/haber/`) → 60 makale `cleaned`.
- Diken (Cloudflare) + Resmî Gazete (WAF UA-block + PDF) bu modla çözülmedi → [[gundem-source-catalog]] known-gap.

## İlişkiler
- [[generic-extractor-cascade]] — keşfedilen URL'ler aynı generic cascade ile işlenir; sitemap yalnız KEŞİF katmanı.
- [[gundem-source-catalog]] — bu modun ana tüketicisi.
- [[title-fallback-discovery]] — sitemap başlıksız URL'lerin başlığını kurtarır.
- [[risk-source-fragility]] — JS-render/anti-bot kaynak kırılganlığı.

## Kaynaklar
- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §3.3 (crawl/discovery)
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) §3.2 (source_configs config_json)
- Kod: `app/shared/crawl/sitemap.py`, `app/modules/sources/tasks/sources.py` (`_discover_from_sitemap`)
