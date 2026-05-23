"""Module: crawler

Layer: middle (Seviye 3 — master plan §2.2).

Sorumluluk: HTTP fetch + **extraction cascade *orchestration*** (extraction
primitives `app/shared/extraction/` altındadır — P4 PR-D1/PR-D2, 2026-05-23;
bkz. wiki/decisions/modular-monolith-boundary.md §"Karar notu") + cleaning +
site_profiles + content_quality.

Status: Phase 4 PR-D2 (2026-05-23) — `modules/crawler/extractor/` re-export
facade'ı SİLİNDİ (0-caller; extraction primitives shared/extraction'a taşındı).
Crawler ilerleyen fazlarda `fetcher`, `cleaning`, `site_profiles`,
`content_quality`, `fetch_detail` modüllerini içerecek; tümü ortak primitive
olarak `app.shared.extraction`'ı kullanır.

Public API (mevcut): yok — Phase 4 full migration ileride.

Future surface (Phase 4 full migration):
    fetcher, cleaning, site_profiles, content_quality, fetch_detail
    (extraction primitives `app.shared.extraction`'da kalır)

Boundary (import-linter contracts 2/3 ENFORCED):
    Middle layer. **Kernel modules (articles, sources) crawler'a İMPORT
    ETMEZ** (kernel→middle yasak). Kernel extraction ihtiyacını doğrudan
    `app.shared.extraction`'dan karşılar. rag/generations crawler'a import
    etmez (yukarı yön yasak).

See:
- wiki/plans/modular-monolith-transition-master-plan.md §2 / §9 Phase 4
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/import-direction-rules.md
"""
