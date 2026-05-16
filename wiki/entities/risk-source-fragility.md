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

> **TL;DR:** Bir kaynak site redesign yaparsa HTML/DOM değişir. **#904 öncesi** skor **9 🔴** (selector kırılır, 24-72h data durur, kurtarılamayan kayıp). **#904 sonrası skor 6 🟡:** extraction kaynaktan-bağımsız generic ([[generic-extractor-cascade]] — Tier-0 schema.org JSON-LD → trafilatura density → fallback); thin_content terminal değil → `quarantine` (retryable, sessiz kalıcı kayıp YOK); per-domain extract-confidence telemetri + <eşik warning alarmı erken uyarı. Per-site DETAY selector kavramı kaldırıldı (liste selector yalnız `category_page` keşfi).

## Tanım

Web scraping kırılganlığın yapısal bir kaynağıdır: hedef site CSS selector'ları, DOM yapısı, hatta domain'i değiştirebilir. Nodrat 3 RSS kaynağıyla MVP-1'i başlattı (low-fragility) ama MVP-2'de category page kaynak desteği (#71) eklenerek riske girdi.

Site profile sistemi (`app/core/site_profiles.py` — MVP-1.4) her domain için özel selector kuralları tanımlar: container, whitelist (sadece bu img'ler), exclude (decompose).

## Skor

| Boyut | Değer | Açıklama |
|---|---|---|
| **Olasılık** | 3 | Yıllık 2-3 kaynak değişir (gerçekçi tahmin). |
| **Etki** | 2 | #904 sonrası: generic cascade + quarantine ⇒ tek-site redesign veri akışını DURDURMAZ, etkilenen makaleler retryable (kalıcı kayıp yok). |
| **Skor** | **6** | 🟡 (eski 9 🔴 → #904 ile düştü). |

## Mitigation (risk-register §3.4 — #904 ile yeniden yazıldı)

| ID | Önlem | Durum |
|---|---|---|
| M1 | Source health monitor + per-domain extract-confidence ([[extraction-confidence-telemetry]]) | ✅ #904 (recompute_extract_health, 6 saatte bir) |
| M2 | Generic Tier-0 schema.org JSON-LD ([[structured-data-extraction]]) — HTML class değişse de stabil | ✅ #904 |
| M3 | trafilatura multi-mode density backbone (DOM-bağımsız) | ✅ #529 + #904 |
| M4 | Quality gate **yönlendirici**: thin_content terminal değil → `quarantine` (retryable, sessiz kayıp YOK) | ✅ #904 |
| M5 | Per-domain extract-confidence < eşik → warning DLQ alarmı (runtime-tunable, #911) | ✅ #904/#911 |
| M6 | RSS-only kaynaklar daha stable (preferans) | ✅ MVP-1 RSS, category page #71 |
| M7 | `recover_quarantined` — toplu kurtarma (yeni cascade ile yeniden işle) | ✅ #904 |
| ~~eski M2/M3~~ | ~~Selector test ekranı / selector versioning~~ | ❌ #904 — per-site DETAY selector KALDIRILDI (liste selector category_page için korunur) |
| ~~eski M7~~ | Site profile sistemi (#320/#324/#325) | ✅ KORUNUR — yalnız **görsel** extraction (metin generic) |

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

## İlişkiler

- **#904 mitigation kararı:** [[generic-extractor-cascade]] (R-OPS-01 skor 9→6 — generic cascade + quarantine)
- **#904 kavramlar:** [[structured-data-extraction]] (M2), [[extraction-confidence-telemetry]] (M1/M5 erken-uyarı)
- [[conditional-http-get]]
- [[data-pipelines]]
- [[realtime-rss-polling]]
- [[risk-register-md]]

## Kaynaklar

- [docs/strategy/risk-register.md §3.4 (R-OPS-01 detay)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §2.1](../../docs/strategy/risk-register.md)
- [docs/product/prd.md §1.10 (source health)](../../docs/product/prd.md)
- [docs/product/prd.md §1.4 (selector test)](../../docs/product/prd.md)
- [docs/engineering/architecture.md §3.1.1 (site profile sistemi)](../../docs/engineering/architecture.md)
