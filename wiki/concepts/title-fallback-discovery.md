---
type: concept
title: "Title-fallback (keşif başlığı kullan)"
slug: "title-fallback-discovery"
status: live
created: 2026-06-16
updated: 2026-06-16
sources:
  - "docs/engineering/architecture.md§3.2"
tags: [extraction, crawl]
aliases: [title-fallback, apply-title-fallback]
---

# Title-fallback (keşif başlığı kullan)

## TL;DR
Bir makale sayfası `<title>`/og:title/h1 vermediğinde (gov/regülasyon HTML, bazı SSR sayfalar) `ExtractedArticle.successful` title-boş şartı yüzünden gereksiz quarantine oluyordu — gövde + güven iyi olsa bile. Keşif aşaması (RSS item / sitemap / category card) zaten anlamlı bir başlık sağlar; sayfa başlık vermezse bu başlık fallback kullanılır (#1529 / PR [#1530](https://github.com/selmanays/nodrat/pull/1530)).

## Mekanizma
- `ExtractedArticle.successful` = `title boş değil AND len(clean_text) ≥ MIN_TEXT_LENGTH(200) AND extraction_confidence ≥ 0.3`.
- `apply_title_fallback(fallback)`: `title` boşsa fallback'i atar; **dolu title'ı override ETMEZ**. Generic — per-site DEĞİL ([[generic-extractor-cascade|#904]] cascade'i bozmaz).
- `article_fetch_detail`: `extract_article(...)` sonrası, `successful` kontrolünden ÖNCE `extracted.apply_title_fallback(article.title or "")`. `article.title` = discovery (feed/sitemap/card) başlığı.
- text/conf gate korunur: conf<0.3 veya text<200 hâlâ quarantine.

## İlişkiler
- [[sitemap-ingestion-mode]] — sitemap `<loc>` başlık taşımaz; bu fallback'in ana faydalandığı yol.
- [[generic-extractor-cascade]] — extraction success kriterinin parçası.
- [[gundem-source-catalog]] — bağlam (#1526 Resmî Gazete araştırmasında çıktı).

## Kaynaklar
- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §3.2 (extraction)
- Kod: `app/shared/extraction/extractor.py` (`ExtractedArticle.apply_title_fallback`), `app/modules/articles/tasks/articles.py`
