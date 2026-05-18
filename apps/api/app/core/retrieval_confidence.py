"""Retrieval Confidence Router — 5-signal fusion (#809 Faz 2 2A).

Plan: /Users/selmanay/.claude/plans/nerdi-in-ekilde-faz-2-unified-nebula.md
Wiki: wiki/concepts/retrieval-confidence-score.md (oluşturulacak)

Chat stream routing'i 3 yol arasında karar verir:
- score >= T_high           → Layer 1 STRICT (haber arşivi)
- T_low <= score < T_high   → Hybrid (cevap üret + Wikipedia CTA banner)
- score < T_low             → Wikipedia fallback CTA (cevap üretme)

Sinyal seti — `apps/api/app/core/retrieval.py:RetrievedChunk`'tan beslenir:
  1. semantic_top3_mean    (RetrievedChunk.semantic_score top 3 ortalama)
  2. source_count_norm     (kaç DISTINCT kaynak chunk geldi → min(N,5)/5)
  3. recency_match         (planner.timeframes ↔ published_at hit oranı)
  4. entity_must_match     (planner.critical_entities ↔ chunk_text hit oranı)
  5. citation_density      (post-generation; cevaptaki [N] sayısı / cümle)

Ağırlıklar `retrieval.confidence_weights` admin-tunable JSON setting'inden okunur.
Hot reload: settings_store yeni değeri 30 saniye içinde tüm container'lara yayar.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.prompts.query_planner import QueryPlan

logger = logging.getLogger(__name__)


# Default ağırlıklar — admin override `retrieval.confidence_weights` JSON
DEFAULT_WEIGHTS: dict[str, float] = {
    "w1": 0.40,  # semantic_top3_mean
    "w2": 0.20,  # source_count_normalized
    "w3": 0.15,  # recency_match
    "w4": 0.15,  # entity_must_match
    "w5": 0.10,  # citation_density (post-gen)
}

DEFAULT_T_HIGH = 0.70
DEFAULT_T_LOW = 0.40


class _ChunkLike(Protocol):
    """RetrievedChunk-uyumlu minimum shape (Protocol = duck typing).

    apps/api/app/core/retrieval.py:RetrievedChunk bu protocol'ü zaten karşılar.
    Test'lerde simple namedtuple veya dict-wrapper geçilebilir.
    """

    semantic_score: float
    chunk_text: str
    source_id: object  # UUID veya str — sadece set() için __hash__ lazım
    published_at: datetime | None


@dataclass
class RetrievalConfidence:
    """5-signal fusion sonucu."""

    score: float
    """0-1 — w_i * signal_i fusion."""

    semantic: float
    source_count: float
    recency: float
    entity_match: float
    citation_density: float | None
    """Post-generation hesaplanır; pre-gen `compute_retrieval_confidence` None döner."""

    missing: list[str] = field(default_factory=list)
    """Hangi sinyaller eşik altı kaldı — UI insufficiency CTA için.

    Olası değerler: 'low_semantic', 'low_source_count', 'recency_mismatch',
    'entity_mismatch', 'low_citation_density'.
    """

    weights_used: dict[str, float] = field(default_factory=dict)


# ============================================================================
# Public API
# ============================================================================


def compute_retrieval_confidence(
    plan: QueryPlan,
    chunks: list[_ChunkLike],
    *,
    weights: dict[str, float] | None = None,
    answer_text: str | None = None,
) -> RetrievalConfidence:
    """5-signal confidence skoru hesapla.

    Args:
        plan: QueryPlan (timeframes + critical_entities + topic_query okunur).
        chunks: Retrieved chunks (RetrievedChunk veya uyumlu Protocol).
        weights: Override (default DEFAULT_WEIGHTS).
        answer_text: Eğer cevap üretildiyse [N] citation density hesaplanır.
            None ise citation_density=None döner ve fusion'da skip edilir
            (kalan 4 sinyal yeniden normalize edilir).

    Returns:
        RetrievalConfidence — score 0-1 arası.
    """
    w = (weights or DEFAULT_WEIGHTS).copy()

    semantic = _signal_semantic_top3_mean(chunks)
    source_count = _signal_source_count_normalized(chunks)
    recency = _signal_recency_match(plan, chunks)
    entity_match = _signal_entity_must_match(plan, chunks)
    citation = _signal_citation_density(answer_text) if answer_text is not None else None

    missing: list[str] = []
    if semantic < 0.50:
        missing.append("low_semantic")
    if source_count < 0.40:
        missing.append("low_source_count")
    if recency < 0.30 and plan.timeframes:
        missing.append("recency_mismatch")
    if entity_match < 0.50 and plan.critical_entities:
        missing.append("entity_mismatch")
    if citation is not None and citation < 0.20:
        missing.append("low_citation_density")

    # Fusion — citation None ise w5'i kalan ağırlıklara dağıt (renormalize)
    if citation is None:
        # Sadece 4 sinyal — w5 atlanır, kalan w'ler 1.0'a normalize
        active = {"w1": w["w1"], "w2": w["w2"], "w3": w["w3"], "w4": w["w4"]}
        total = sum(active.values()) or 1.0
        score = (
            (active["w1"] / total) * semantic
            + (active["w2"] / total) * source_count
            + (active["w3"] / total) * recency
            + (active["w4"] / total) * entity_match
        )
    else:
        score = (
            w["w1"] * semantic
            + w["w2"] * source_count
            + w["w3"] * recency
            + w["w4"] * entity_match
            + w["w5"] * citation
        )

    score = max(0.0, min(1.0, score))
    return RetrievalConfidence(
        score=round(score, 4),
        semantic=round(semantic, 4),
        source_count=round(source_count, 4),
        recency=round(recency, 4),
        entity_match=round(entity_match, 4),
        citation_density=(round(citation, 4) if citation is not None else None),
        missing=missing,
        weights_used=w,
    )


# ============================================================================
# Settings loader
# ============================================================================


async def load_weights_from_settings(db: AsyncSession) -> dict[str, float]:
    """Admin /settings'ten ağırlıkları oku; bozuksa default'a düş.

    Setting key: `retrieval.confidence_weights` (JSON, stored as JSONB).
    Hot reload — settings_store Redis pub/sub ile ~30sn yayar.
    """
    try:
        from app.core.settings_store import settings_store

        raw = await settings_store.get(db, "retrieval.confidence_weights", None)
        if not raw or not isinstance(raw, dict):
            return DEFAULT_WEIGHTS.copy()
        # 5 anahtar zorunlu, hepsi float 0-1
        normalized = {}
        for key in ("w1", "w2", "w3", "w4", "w5"):
            try:
                val = float(raw[key])
                if 0.0 <= val <= 1.0:
                    normalized[key] = val
                else:
                    raise ValueError(f"{key} out of range")
            except (KeyError, TypeError, ValueError):
                logger.warning(
                    "confidence_weights invalid key=%s, using default",
                    key,
                )
                return DEFAULT_WEIGHTS.copy()
        return normalized
    except Exception as exc:
        logger.warning("confidence_weights load failed: %s, using default", exc)
        return DEFAULT_WEIGHTS.copy()


async def load_thresholds_from_settings(db: AsyncSession) -> tuple[float, float]:
    """T_high + T_low — `retrieval.confidence_t_high` + `..._t_low`."""
    try:
        from app.core.settings_store import settings_store

        t_high = await settings_store.get_float(
            db,
            "retrieval.confidence_t_high",
            DEFAULT_T_HIGH,
        )
        t_low = await settings_store.get_float(
            db,
            "retrieval.confidence_t_low",
            DEFAULT_T_LOW,
        )
        # Sanity: t_low < t_high, ikisi de 0-1 arası
        if not (0.0 <= t_low < t_high <= 1.0):
            logger.warning(
                "confidence thresholds invalid (t_low=%s, t_high=%s), using defaults",
                t_low,
                t_high,
            )
            return DEFAULT_T_HIGH, DEFAULT_T_LOW
        return t_high, t_low
    except Exception as exc:
        logger.warning("confidence thresholds load failed: %s, using default", exc)
        return DEFAULT_T_HIGH, DEFAULT_T_LOW


# ============================================================================
# Signal calculators (private)
# ============================================================================


def _signal_semantic_top3_mean(chunks: list[_ChunkLike]) -> float:
    """Top 3 chunks'ın semantic_score ortalaması (0-1)."""
    if not chunks:
        return 0.0
    top = sorted(chunks, key=lambda c: c.semantic_score, reverse=True)[:3]
    scores = [c.semantic_score for c in top]
    return sum(scores) / len(scores)


def _signal_source_count_normalized(chunks: list[_ChunkLike]) -> float:
    """Distinct kaynak sayısı / 5 (cap)."""
    if not chunks:
        return 0.0
    distinct_sources = {str(c.source_id) for c in chunks}
    return min(len(distinct_sources), 5) / 5.0


def _signal_recency_match(plan: QueryPlan, chunks: list[_ChunkLike]) -> float:
    """Chunks'ın published_at değerleri planner.timeframes'e ne oranda uyuyor.

    Planner timeframe yoksa (general_knowledge gibi) → 1.0 (gating'i kapatır).
    Aksi halde: hit_count / len(chunks).
    """
    if not chunks:
        return 0.0
    if not plan.timeframes:
        return 1.0  # neutral — timeframe constraint yok

    def in_any_tf(dt: datetime | None) -> bool:
        if dt is None:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        for tf in plan.timeframes:
            try:
                tf_from = datetime.fromisoformat(tf.from_iso.replace("Z", "+00:00"))
                tf_to = datetime.fromisoformat(tf.to_iso.replace("Z", "+00:00"))
                if tf_from.tzinfo is None:
                    tf_from = tf_from.replace(tzinfo=UTC)
                if tf_to.tzinfo is None:
                    tf_to = tf_to.replace(tzinfo=UTC)
                if tf_from <= dt <= tf_to:
                    return True
            except (ValueError, AttributeError):
                continue
        return False

    hits = sum(1 for c in chunks if in_any_tf(c.published_at))
    return hits / len(chunks)


def _signal_entity_must_match(plan: QueryPlan, chunks: list[_ChunkLike]) -> float:
    """Critical entities chunks'ın ne oranında geçiyor.

    plan.critical_entities boşsa → 1.0 (gating'i kapatır).
    Aksi halde: her entity için hit oranı, sonra mean (entity-bazlı recall).
    """
    if not chunks:
        return 0.0
    entities = [e.lower().strip() for e in (plan.critical_entities or []) if e.strip()]
    if not entities:
        return 1.0  # neutral

    entity_hit_ratios = []
    for ent in entities:
        chunk_hits = sum(1 for c in chunks if ent in (c.chunk_text or "").lower())
        entity_hit_ratios.append(chunk_hits / len(chunks))

    # Tüm entity'lerin recall mean — yüksek score = tümü çok geçiyor
    return sum(entity_hit_ratios) / len(entity_hit_ratios)


_CITATION_RE = re.compile(r"\[\d+\]")
_SENTENCE_END_RE = re.compile(r"[.!?]+")


def _signal_citation_density(answer_text: str) -> float:
    """Cevaptaki [N] sayısı / cümle sayısı, cap 1.0.

    Ideal: her cümlede ortalama 0.5+ citation → ~1.0 score.
    Hiç citation yoksa → 0.0 (halüsinasyon riski).
    """
    if not answer_text:
        return 0.0
    citation_count = len(_CITATION_RE.findall(answer_text))
    sentence_count = max(1, len(_SENTENCE_END_RE.findall(answer_text)))
    raw = citation_count / sentence_count
    # 0.5 citation/sentence → ideal; 1.0+ → 1.0 cap
    normalized = min(raw / 0.5, 1.0)
    return normalized
