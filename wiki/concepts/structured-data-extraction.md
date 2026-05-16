---
type: concept
title: "Structured-data extraction — schema.org JSON-LD Tier-0"
slug: "structured-data-extraction"
category: "technique"
status: "live"
created: "2026-05-16"
updated: "2026-05-16"
sources:
  - "docs/engineering/architecture.md§3.2"
  - "docs/product/prd.md§1.5"
tags: ["scrape", "extraction", "json-ld", "schema-org"]
aliases: ["tier-0", "json-ld-extraction", "articleBody"]
---

# Structured-data extraction — schema.org JSON-LD Tier-0

> **TL;DR:** Türk haber siteleri `<script type="application/ld+json">` içinde schema.org `NewsArticle.articleBody` yayınlar; bu, site HTML class'ları/DOM yapısı değişse de stabil kalan kaynaktan-bağımsız bir sözleşmedir. Nodrat extraction cascade'inin en güvenilir ilk kademesi (Tier-0) bunu parse eder — per-site selector OLMADAN.

## Tanım

schema.org/JSON-LD, yayıncıların sayfa içeriğini makine-okunur yapısal veri olarak gömme standardıdır (Google/Bing/Yandex zengin sonuç için bunu okur). Haber için kanonik tip `NewsArticle` (ayrıca `Article`, `ReportageNewsArticle`, `LiveBlogPosting` vb.); `articleBody` alanı tam gövde metnini düz proza olarak taşır. Nodrat'a özgü uyarlama: `apps/api/app/core/structured_data.py` `parse_jsonld()` — tüm ld+json script'lerini parse eder, `@graph`/dizi/`@type`-listesi/`{"@value"}` sarmallarını yürür, en uzun `articleBody`'li haber/makale düğümünü seçer (bazı sayfalar hem kısa özet hem tam gövde yayar); malformed JSON'a toleranslı (bir script bozuksa diğerine geçer).

## Neden Nodrat'ta var

- **Hangi probleme cevap veriyor:** modern haber siteleri (Habertürk, Fotomaç, Hürriyet, Sabah...) gövdeyi `<p>` yerine `<div>`/JS-hidrate yapıda sunar; `<p>`-sayan heuristikler içeriği "thin" sanıp kaybeder ([[generic-extractor-cascade]] kök nedeni). JSON-LD `articleBody` bu yapıdan bağımsız tam metni verir (canlı probe: Habertürk 1300+, Fotomaç 827 char).
- **Hangi alternatife karşı seçildi:** kaynağa-özel CSS selector (bakım yükü, redesign'da kırılır) yerine kaynaktan-bağımsız standart.
- **Hangi locked karar çağırıyor:** [[generic-extractor-cascade]] (#904) — Tier-0 kademesi.

## Formül / kural / parametre

- `parse_jsonld(html, min_body_len=200)` → `StructuredArticle(found, title, clean_text, author, published_raw, image_url, schema_type)`.
- `articleBody` düz proza → doğrudan `clean_text`'e atanır, `_to_clean_text` (`<div>`+<20 char satır drop sorunu) **BYPASS** edilir.
- Cascade'de slot: selectors-sonrası, trafilatura-öncesi; **dön: `successful AND extraction_confidence >= 0.6`** (Habertürk/Fotomaç burada kazanır; AA'nın 76-159 char özeti `.successful` olmaz → density kademesine düşer).
- Confidence: title 0.35 + body≥200 0.45 + date 0.10 + author 0.05 + image 0.05, cap 0.95.
- Tarih parse caller'a bırakılır (`published_raw` ham; `extractor._parse_iso_date` — circular import'tan kaçınma).

## İlişkiler

- **İlgili kararlar:** [[generic-extractor-cascade]] — bu kademeyi tanımlayan locked karar
- **İlgili kavramlar:** [[extraction-confidence-telemetry]] — kademe çıktısının güven ölçümü
- **İlgili topics:** [[data-pipelines]] — Pipeline 1 (Source Crawl) extraction adımı

## Kaynaklar

- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §3.2 — extraction cascade
- [docs/product/prd.md](../../docs/product/prd.md) §1.5 — Extractor stratejileri (#904 generic)
- PR [#908](https://github.com/selmanays/nodrat/pull/908) — `core/structured_data.py` + cascade entegrasyonu
