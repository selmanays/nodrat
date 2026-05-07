---
type: entity
title: "R-OPS-01 — Kaynak HTML Kırılganlığı"
slug: "risk-source-fragility"
category: "risk"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/strategy/risk-register.md§3.4"
  - "docs/strategy/risk-register.md§2.1"
  - "docs/product/prd.md§1.10"
  - "docs/product/prd.md§1.4"
tags: ["risk", "ops", "scraping", "selectors", "red"]
aliases: ["R-OPS-01", "html-fragility", "selector-breakage"]
---

# R-OPS-01 — Kaynak HTML Kırılganlığı

> **TL;DR:** Bir kaynak (Sabah, Sözcü, Hürriyet, BBC, Habertürk vb.) site redesign yapar; selector'lar bozulur; 24-72 saat data akışı durur. Skor **9 🔴**. Mitigation: source health monitor + selector test UI + 3-tier extraction (selectors → readability → fallback) + admin alert + RSS-only kaynak preferansı + site profile sistemi (MVP-1.4 #320, #324, #325).

## Tanım

Web scraping kırılganlığın yapısal bir kaynağıdır: hedef site CSS selector'ları, DOM yapısı, hatta domain'i değiştirebilir. Nodrat 3 RSS kaynağıyla MVP-1'i başlattı (low-fragility) ama MVP-2'de category page kaynak desteği (#71) eklenerek riske girdi.

Site profile sistemi (`app/core/site_profiles.py` — MVP-1.4) her domain için özel selector kuralları tanımlar: container, whitelist (sadece bu img'ler), exclude (decompose).

## Skor

| Boyut | Değer | Açıklama |
|---|---|---|
| **Olasılık** | 3 | Yıllık 2-3 kaynak değişir (gerçekçi tahmin). |
| **Etki** | 3 | Kullanıcılar fresh content göremez, churn (D7 retention impact). |
| **Skor** | **9** | 🔴 Kırmızı. |

## Mitigation (risk-register §3.4)

| ID | Önlem | Durum |
|---|---|---|
| M1 | Source health monitor (PRD §1.10) | ✅ MVP-1 (source-health-check beat task, 6 saatte bir) |
| M2 | Selector test ekranı (PRD §1.4) | ✅ MVP-2 #70 delivered (admin operasyon kritik) |
| M3 | Selector versioning (rollback) | ✅ MVP-2 #75 delivered |
| M4 | 3-tier extraction stratejisi (selectors → readability → fallback) | ✅ implemented |
| M5 | Admin alert sistemi (failed extraction trend) | 🟡 partial — uyarı mevcut, dashboard polish |
| M6 | RSS-only kaynaklar daha stable (preferans) | ✅ MVP-1'de sadece RSS, MVP-2'de category page eklendi (#71) |
| M7 | Site profile sistemi (#320, #324, #325) | ✅ MVP-1.4 — BBC/Habertürk/Evrensel/AA/TRT/Yeşil Gazete |

## Site profile detayı (architecture.md §3.1.1)

`SiteProfile` dataclass, domain'e göre image extraction kuralları tanımlar:

```python
@dataclass(frozen=True)
class SiteProfile:
    domains: tuple[str, ...]
    container_selector: str | None = None
    main_image_selectors: tuple[str, ...] = ()  # WHITELIST
    exclude_selectors: tuple[str, ...] = ()     # BLACKLIST
```

Production source profilleri:

| Source | Container | Whitelist | Exclude (özet) |
|---|---|---|---|
| BBC (bbc.com, bbc.co.uk) | `main` | `figure img` | `ul, ol, aside, nav, [data-component=related-stories\|topic-list\|links\|mostread]` |
| Habertürk | `article.it-main` | `.widget-image img, figure img, .cms-container img` | `a.gtm-tracker (öneri haber), .sidebar-content-infinite, aside, nav` |
| Evrensel | `article, .haber-detay` | — | `.related-news, aside` |
| Yeşil Gazete (WordPress + tagDiv) | `article` | `.tdb_single_featured_image img, .tdb_single_content img` | `.tdb-author-photo, .tdb-logo-img-wrap, .td_block_related_posts` |
| AA, TRT | minimal | — | (basic) |

## Tetikleyici

```text
Tetikleyici: Site redesign / yapı değişimi (3.4)
Senaryo:    Sabah CMS değişikliği yapar. <article> id'si değişir.
            Selector eşleşmez. extract_body() boş döner.
            article.discover task'ı 24 saatlik bir cooldown'a girer.
            Source health monitor admin'e alarm yollar.
            Admin selector test UI ile (MVP-2 #70) yeni selector dener.
            Yeni source_config v2 deploy edilir; eski selector_v1 rollback ready.
```

## Kontrol checkpoint'leri

```text
Günlük:    Source health dashboard
Haftalık:  Failed extraction trend
Aylık:     Selector yenileme prosedürü drill
Saatte 1:  source_health_check beat task otomatik
```

## Çapraz referanslar

- **Bağlı kararlar:** —
- **Bağlı kavramlar:** [[risk-scoring]].
- **Bağlı varlıklar:** [[celery-worker]] (`worker_scraper`, `crawl_queue`).
- **İlgili topics:** [[risk-catalog]].
- **İlgili dokümanlar:**
  - [docs/product/prd.md §1.10 (source health)](../../docs/product/prd.md)
  - [docs/product/prd.md §1.4 (selector test)](../../docs/product/prd.md)
  - [docs/engineering/architecture.md §3.1.1 (site profiles)](../../docs/engineering/architecture.md)

## Açık sorular / TODO

- **Failed extraction trend dashboard:** Architecture.md §3.1.1'de site profile sistemi var ama "trend dashboard" ekranı net mi? Admin paneli hangi route'ta?
- **Selector versioning UI:** #75 delivered ama UX detayı açık. Eski selector v1 manuel rollback mı yoksa one-click mi?
- **Yeni source ekleme runbook:** §3.1.1 "Yeni site eklemek: PROFILES'a entry ekle, unit test yaz, deploy" der. Bu adımlar sıradan dev için ne kadar net? Operasyonel runbook eksik mi?

## Kaynaklar

- [docs/strategy/risk-register.md §3.4 (R-OPS-01 detay)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §2.1](../../docs/strategy/risk-register.md)
- [docs/product/prd.md §1.10 (source health)](../../docs/product/prd.md)
- [docs/product/prd.md §1.4 (selector test)](../../docs/product/prd.md)
- [docs/engineering/architecture.md §3.1.1 (site profile sistemi)](../../docs/engineering/architecture.md)
