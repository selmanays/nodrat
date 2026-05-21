"""Internal retrieval scoring helpers (T6 #1085 P5 PR-C internal split).

Pure scoring helpers: mode literal, weight presets, fallback levels, score
dataclasses, freshness/final-score math. Daha önce `app.core.retrieval`
(lines 296-401) içinde inline'dı; pure refactor — davranış değişikliği YOK.
Public consumer: `app.core.retrieval` (re-export).

Modül-dışı doğrudan import edilmez — stable API DEĞİL. Public API olarak
kullanılacaklar (`RetrievedChunk`, `RetrievalReport`, `RetrievalMode`,
`WEIGHTS_DEFAULT`, `WEIGHTS_CURRENT`, `CURRENT_MODE_FALLBACKS_HOURS`,
`freshness_decay`, `compute_final_score`) `app.core.retrieval` üzerinden
çağrılır.

Refs:
- PR #1148 — retrieval characterization tests (regression safety-net)
- PR #1149 — retrieval phrase/vector internal split (pattern source)
- core/retrieval.py — public surface bu helper'ları re-export eder
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

# ============================================================================
# Mode + weight presets
# ============================================================================

RetrievalMode = Literal["current", "weekly", "archive"]


# Score weight presets
WEIGHTS_DEFAULT = {
    "semantic": 0.50,
    "freshness": 0.25,
    "importance": 0.15,
    "reliability": 0.10,
}
WEIGHTS_CURRENT = {
    "semantic": 0.45,
    "freshness": 0.35,
    "importance": 0.10,
    "reliability": 0.10,
}

# Current mode time fallback levels (saat)
CURRENT_MODE_FALLBACKS_HOURS = (24, 48, 72)


# ============================================================================
# Score dataclasses
# ============================================================================


@dataclass
class RetrievedChunk:
    """Tek arama sonucu — caller bu listeyle agenda card / generation yapar."""

    chunk_id: UUID
    article_id: UUID
    source_id: UUID
    chunk_index: int
    chunk_text: str
    article_title: str
    article_canonical_url: str
    source_name: str | None
    source_slug: str | None
    source_reliability: float
    published_at: datetime | None

    semantic_score: float
    """Cosine similarity (0..1) — pgvector 1 - cosine_distance"""

    freshness_score: float
    """Time-decay score (0..1)"""

    importance_score: float
    """Article-level importance — MVP-1: 0.5 placeholder, Faz 2 sonu calc"""

    reliability_score: float
    """Source reliability (0..1)"""

    final_score: float


@dataclass
class RetrievalReport:
    """Tüm arama sonucu + telemetri."""

    chunks: list[RetrievedChunk]
    mode_used: str
    """current_24h / current_48h / current_72h / weekly / archive"""

    candidate_count: int
    """SQL'den dönen aday sayısı (rerank öncesi)"""

    weights_used: dict[str, float]


# ============================================================================
# Score math helpers
# ============================================================================


def freshness_decay(published_at: datetime | None, *, half_life_hours: float = 24.0) -> float:
    """Time-decay score: yeni → 1, eski → 0.

    Half-life modeli: half_life_hours geçtikçe skor /2.
    None published_at → 0.5 (orta).
    """
    if published_at is None:
        return 0.5
    now = datetime.now(UTC)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    delta_hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
    if half_life_hours <= 0:
        return 1.0
    decay = math.pow(0.5, delta_hours / half_life_hours)
    return max(0.0, min(1.0, decay))


def compute_final_score(
    *,
    semantic: float,
    freshness: float,
    importance: float,
    reliability: float,
    weights: dict[str, float],
) -> float:
    return (
        semantic * weights["semantic"]
        + freshness * weights["freshness"]
        + importance * weights["importance"]
        + reliability * weights["reliability"]
    )
