"""Unit tests for retrieval_confidence module (#809 Faz 2 2A).

Test plan:
  - 5 signal compute (semantic, source_count, recency, entity_match, citation)
  - Default weights fusion
  - Weights override
  - Missing signals correctly flagged
  - Edge cases: empty chunks, no critical_entities, no timeframes, no answer
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.retrieval_confidence import (
    DEFAULT_T_HIGH,
    DEFAULT_T_LOW,
    DEFAULT_WEIGHTS,
    RetrievalConfidence,
    compute_retrieval_confidence,
)
from app.prompts.query_planner import QueryPlan, TimeframeSpec


@dataclass
class _FakeChunk:
    """RetrievedChunk-uyumlu test fixture (Protocol kontratı)."""

    semantic_score: float
    chunk_text: str
    source_id: str
    published_at: datetime | None


def _make_plan(
    *,
    timeframes: list[TimeframeSpec] | None = None,
    critical_entities: list[str] | None = None,
    query_class: str = "news_query",
) -> QueryPlan:
    return QueryPlan(
        intent="current_content_generation",
        topic_query="test",
        mode="current",
        timeframes=timeframes or [],
        output_type="x_post",
        tone=None,
        constraints=[],
        needs_sources=True,
        minimum_evidence_per_period=2,
        critical_entities=critical_entities or [],
        query_class=query_class,  # type: ignore[arg-type]
    )


# =============================================================================
# Signal compute tests
# =============================================================================


def test_empty_chunks_returns_zero():
    plan = _make_plan()
    result = compute_retrieval_confidence(plan, [])
    assert result.score == 0.0
    assert result.semantic == 0.0
    assert result.source_count == 0.0


def test_semantic_top3_mean_only_top3():
    """5 chunk verilir, sadece top 3 semantic_score'un mean'i alınır."""
    plan = _make_plan()
    chunks = [
        _FakeChunk(0.9, "x", str(uuid4()), None),
        _FakeChunk(0.8, "x", str(uuid4()), None),
        _FakeChunk(0.7, "x", str(uuid4()), None),
        _FakeChunk(0.3, "x", str(uuid4()), None),
        _FakeChunk(0.1, "x", str(uuid4()), None),
    ]
    result = compute_retrieval_confidence(plan, chunks)
    expected_semantic = round((0.9 + 0.8 + 0.7) / 3, 4)
    assert result.semantic == expected_semantic


def test_source_count_normalized_caps_at_5():
    """5+ distinct kaynaktan 1.0; 3 kaynaktan 0.6."""
    plan = _make_plan()
    src_a, src_b, src_c = str(uuid4()), str(uuid4()), str(uuid4())

    chunks_3 = [
        _FakeChunk(0.5, "x", src_a, None),
        _FakeChunk(0.5, "x", src_b, None),
        _FakeChunk(0.5, "x", src_c, None),
    ]
    result = compute_retrieval_confidence(plan, chunks_3)
    assert result.source_count == 0.6  # 3/5

    # 6 distinct → cap 1.0
    chunks_6 = [
        _FakeChunk(0.5, "x", str(uuid4()), None) for _ in range(6)
    ]
    result6 = compute_retrieval_confidence(plan, chunks_6)
    assert result6.source_count == 1.0


def test_recency_no_timeframe_returns_neutral():
    """Plan timeframe yoksa → recency 1.0 (gating kapalı)."""
    plan = _make_plan(timeframes=[])
    chunks = [_FakeChunk(0.7, "x", str(uuid4()), None)]
    result = compute_retrieval_confidence(plan, chunks)
    assert result.recency == 1.0


def test_recency_in_timeframe_hits():
    """3 chunk var; 2'si timeframe içinde → recency 2/3."""
    now = datetime.now(UTC)
    plan = _make_plan(
        timeframes=[
            TimeframeSpec(
                label="last_24h",
                from_iso=(now - timedelta(hours=24)).isoformat(),
                to_iso=now.isoformat(),
            ),
        ],
    )
    chunks = [
        _FakeChunk(0.7, "x", str(uuid4()), now - timedelta(hours=1)),   # in
        _FakeChunk(0.7, "x", str(uuid4()), now - timedelta(hours=12)),  # in
        _FakeChunk(0.7, "x", str(uuid4()), now - timedelta(days=5)),    # out
    ]
    result = compute_retrieval_confidence(plan, chunks)
    assert result.recency == round(2 / 3, 4)


def test_entity_match_no_critical_returns_neutral():
    """Critical entities yoksa → entity_match 1.0."""
    plan = _make_plan(critical_entities=[])
    chunks = [_FakeChunk(0.7, "lorem ipsum dolor", str(uuid4()), None)]
    result = compute_retrieval_confidence(plan, chunks)
    assert result.entity_match == 1.0


def test_entity_match_hit_ratio():
    """2 entity, 3 chunk: trump→2/3, çin→1/3 → mean 0.5."""
    plan = _make_plan(critical_entities=["trump", "çin"])
    chunks = [
        _FakeChunk(0.7, "Trump bugün açıklama yaptı.", str(uuid4()), None),
        _FakeChunk(0.7, "Trump'ın Çin politikası", str(uuid4()), None),
        _FakeChunk(0.7, "Macron Avrupa zirvesinde", str(uuid4()), None),
    ]
    result = compute_retrieval_confidence(plan, chunks)
    # trump: 2/3, çin: 1/3 → mean (2/3 + 1/3) / 2 = 0.5
    assert result.entity_match == 0.5


def test_citation_density_zero_when_no_answer():
    plan = _make_plan()
    chunks = [_FakeChunk(0.7, "x", str(uuid4()), None)]
    result = compute_retrieval_confidence(plan, chunks, answer_text=None)
    assert result.citation_density is None


def test_citation_density_normalized():
    """3 cümle, 2 citation → raw=2/3≈0.67, normalize 0.67/0.5=1.33→cap 1.0."""
    plan = _make_plan()
    chunks = [_FakeChunk(0.7, "x", str(uuid4()), None)]
    answer = "Trump açıklama yaptı [1]. Çin tepki gösterdi. Anlaşma sağlandı [2]."
    result = compute_retrieval_confidence(plan, chunks, answer_text=answer)
    assert result.citation_density == 1.0


def test_citation_density_zero_when_no_citations():
    plan = _make_plan()
    chunks = [_FakeChunk(0.7, "x", str(uuid4()), None)]
    answer = "Trump açıklama yaptı. Çin tepki gösterdi. Anlaşma sağlandı."
    result = compute_retrieval_confidence(plan, chunks, answer_text=answer)
    assert result.citation_density == 0.0


# =============================================================================
# Fusion tests
# =============================================================================


def test_fusion_with_default_weights_no_citation():
    """Citation None → 4 sinyal renormalize."""
    plan = _make_plan()  # no timeframes, no critical → recency=1.0, entity=1.0
    chunks = [
        _FakeChunk(0.8, "x", str(uuid4()), None),
        _FakeChunk(0.7, "x", str(uuid4()), None),
        _FakeChunk(0.6, "x", str(uuid4()), None),
    ]
    result = compute_retrieval_confidence(plan, chunks, answer_text=None)

    semantic = (0.8 + 0.7 + 0.6) / 3   # ≈ 0.70
    source_count = 3 / 5               # 0.60
    recency = 1.0
    entity = 1.0
    # Renormalize w1..w4 to sum 1
    w = DEFAULT_WEIGHTS
    total = w["w1"] + w["w2"] + w["w3"] + w["w4"]
    expected = (
        (w["w1"] / total) * semantic
        + (w["w2"] / total) * source_count
        + (w["w3"] / total) * recency
        + (w["w4"] / total) * entity
    )
    assert abs(result.score - round(expected, 4)) < 0.001


def test_fusion_with_custom_weights():
    """Override ağırlık tüm score'u semantic'e atar (w1=1.0)."""
    plan = _make_plan()
    chunks = [_FakeChunk(0.85, "x", str(uuid4()), None)]
    custom = {"w1": 1.0, "w2": 0.0, "w3": 0.0, "w4": 0.0, "w5": 0.0}
    result = compute_retrieval_confidence(
        plan, chunks, weights=custom, answer_text="Test [1].",
    )
    # 5 sinyal aktif (citation hesaplandı)
    assert abs(result.score - 0.85) < 0.001


# =============================================================================
# Missing signals
# =============================================================================


def test_missing_flags_low_semantic():
    plan = _make_plan()
    chunks = [_FakeChunk(0.3, "x", str(uuid4()), None)]
    result = compute_retrieval_confidence(plan, chunks)
    assert "low_semantic" in result.missing


def test_missing_flags_entity_mismatch():
    plan = _make_plan(critical_entities=["trump"])
    chunks = [_FakeChunk(0.7, "Macron açıklama yaptı.", str(uuid4()), None)]
    result = compute_retrieval_confidence(plan, chunks)
    assert "entity_mismatch" in result.missing


def test_missing_no_false_positive_when_no_critical_entities():
    """plan.critical_entities boş → entity_match=1.0, missing flag YOK."""
    plan = _make_plan(critical_entities=[])
    chunks = [_FakeChunk(0.7, "x", str(uuid4()), None)]
    result = compute_retrieval_confidence(plan, chunks)
    assert "entity_mismatch" not in result.missing


# =============================================================================
# Defaults sanity
# =============================================================================


def test_default_weights_sum_close_to_one():
    """Default ağırlıklar toplamı ≈ 1.0 (renormalize gerekmesin)."""
    total = sum(DEFAULT_WEIGHTS.values())
    assert abs(total - 1.0) < 0.01


def test_default_thresholds_ordered():
    assert DEFAULT_T_LOW < DEFAULT_T_HIGH
    assert 0 < DEFAULT_T_LOW < 1
    assert 0 < DEFAULT_T_HIGH < 1


def test_score_clamped_to_unit_interval():
    """Aşırı durum: weights toplam >1 olsa bile score 0-1 arası."""
    plan = _make_plan()
    chunks = [_FakeChunk(1.0, "x", str(uuid4()), None)]
    bad_weights = {"w1": 2.0, "w2": 2.0, "w3": 2.0, "w4": 2.0, "w5": 2.0}
    result = compute_retrieval_confidence(
        plan, chunks, weights=bad_weights, answer_text="Test [1]. End [2].",
    )
    assert 0.0 <= result.score <= 1.0
