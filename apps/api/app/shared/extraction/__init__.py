"""Shared infrastructure: extraction

Layer: 0 (alt — leaf shared library; see wiki/decisions/modular-monolith-boundary
§"Karar notu (2026-05-23): Extraction primitives → shared/extraction/").

Pure HTML / content parsing primitive library. I/O yok, durum yok,
deterministik HTML→ExtractedArticle dönüşümü. Trafilatura + BeautifulSoup
sarmalayıcı; `site_profiles` aynı paket içinde sub-module (Layer 0 saflığı
korunur; site-specific image extraction kuralları); `content_quality`
bağımlılığı YOK (extraction cascade *orchestration* `modules/crawler`
üst-katmanında kalır).

Import allowed from: everyone (kernel, middle, üst, paralel — `shared/*`
herkesin altında). `shared/extraction` HİÇBİR `app.modules.*` import EDEMEZ
(import-linter contract 1: `shared/* must not import from modules/*`).

P4 PR-D1/PR-D2 (2026-05-23):
  - PR-D1 (#1222): boundary decision (docs-only; locked).
  - PR-D2 (this): `git mv app/core/{extractor, _extractor_filters,
    structured_data}.py → app/shared/extraction/{extractor.py, _filters.py,
    structured_data.py}` + 5 caller flip + facade `modules/crawler/extractor/`
    silindi (0-caller). Behavior-eş (pure code relocation; mevcut
    characterization safety-net: `tests/unit/test_extractor.py`).

Public surface (PR #1146 facade'ı ile bire bir; private `_is_*` symbols
extractor submodule üzerinden direkt erişilir — kütüphane konvansiyonu).
"""

from app.shared.extraction.extractor import (
    MIN_TEXT_LENGTH,
    BodyImage,
    ExtractedArticle,
    ListingCard,
    extract_article,
    extract_body_images,
    extract_fallback,
    extract_listing_cards,
    extract_structured_tier,
    extract_with_selectors,
    extract_with_trafilatura,
)
from app.shared.extraction.structured_data import (
    StructuredArticle,
    parse_jsonld,
)

__all__ = [
    "MIN_TEXT_LENGTH",
    "BodyImage",
    "ExtractedArticle",
    "ListingCard",
    "StructuredArticle",
    "extract_article",
    "extract_body_images",
    "extract_fallback",
    "extract_listing_cards",
    "extract_structured_tier",
    "extract_with_selectors",
    "extract_with_trafilatura",
    "parse_jsonld",
]
