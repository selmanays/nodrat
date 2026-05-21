"""Module: crawler

Layer: middle (master plan §2.2 — HTML fetch + extraction cascade + cleaning +
structured_data + site_profiles + content_quality)

Status: Phase 4 mini-cycle başladı; extractor facade re-export ile aktive
(`modules/crawler/extractor/` re-exports `app.core.extractor` public surface).
Phase 4 full migration (core/extractor.py → modules/crawler/extractor/ internal
split, fetcher, cleaning, structured_data, site_profiles, content_quality)
ileride genişler — bu PR yalnız facade-first + caller flip.

Public API (mevcut):
    extractor — Pure re-export facade (app.core.extractor symbol surface)

Future surface (Phase 4 full migration):
    fetcher, cleaning, structured_data, site_profiles, content_quality, fetch_detail

Boundary:
    Middle layer. Kernel modules (articles, sources) crawler'a import edebilir;
    rag/generations crawler'a import etmez (mevcut contract).

See:
- wiki/plans/modular-monolith-transition-master-plan.md §2 / §9 Phase 4
- wiki/decisions/modular-monolith-boundary.md
- wiki/decisions/import-direction-rules.md
"""
