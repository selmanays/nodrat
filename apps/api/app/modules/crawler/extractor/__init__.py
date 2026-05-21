"""Pure re-export facade — `app.core.extractor` public surface.

Phase 4 T6 PR-B (#1085 god-file facade-first strategy):
  - Source-of-truth: `app.core.extractor` (1189 LoC) — DOKUNULMADI
  - Bu facade: callers'ın import path'i için yeni "ana yol"
  - Behavior değişmez (pure re-export); davranış characterization
    test'leri (`tests/unit/test_extractor.py` `extract_body_images`
    grubu, PR #1144) safety-net olarak çalışır

Next:
  - PR-C: küçük internal split (image extraction / structured tier ayrı
    dosya); characterization test'ler refactor sırasında PASS kalmalı
  - Tam Phase 4 migration: `core/extractor.py` → `modules/crawler/
    extractor/{cascade.py, images.py, structured.py, ...}` (büyük adım)

See:
- wiki/plans/modular-monolith-transition-master-plan.md §6 (God-file Strategy)
- apps/api/tests/unit/test_extractor.py `extract_body_images` characterization
"""

from app.core.extractor import (
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

__all__ = [
    "MIN_TEXT_LENGTH",
    "BodyImage",
    "ExtractedArticle",
    "ListingCard",
    "extract_article",
    "extract_body_images",
    "extract_fallback",
    "extract_listing_cards",
    "extract_structured_tier",
    "extract_with_selectors",
    "extract_with_trafilatura",
]
