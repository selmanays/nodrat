"""Tests for pre-LLM relevance gate helper (#553).

Retrieval kart döndürdü diye LLM çağrısı her zaman değer vermez. Top-1 kartın
gerçekten alakalı olup olmadığını skor sinyalleriyle karar veren helper.
"""

from __future__ import annotations

from app.core.retrieval import is_top_card_relevant_for_llm


def _card(semantic: float | None = None, rerank: float | None = None) -> dict:
    """Test card factory."""
    out: dict = {"id": "c1", "title": "x", "summary": "y"}
    if semantic is not None:
        out["_score_meta"] = {"semantic_score": semantic}
    if rerank is not None:
        out["_rerank_score"] = rerank
    return out


def test_empty_cards_rejected():
    ok, reason = is_top_card_relevant_for_llm([])
    assert not ok
    assert reason == "no_cards"


def test_high_semantic_score_passes():
    ok, reason = is_top_card_relevant_for_llm([_card(semantic=0.85)])
    assert ok
    assert reason is None


def test_low_semantic_score_rejected_default_threshold():
    """Default eşik 0.50 (#558 — UX > $0.0004 trade-off); 0.45 reject."""
    ok, reason = is_top_card_relevant_for_llm([_card(semantic=0.45)])
    assert not ok
    assert reason is not None
    assert "0.450" in reason


def test_retrieval_borderline_passes():
    """Retrieval base 0.55 → gate 0.50 → her zaman pass (effective no-op
    legitimate sorgular için). Açıkça alakasız semantic < 0.50 reject."""
    # Retrieval'dan dönen tipik kart
    ok, _ = is_top_card_relevant_for_llm([_card(semantic=0.55)])
    assert ok


def test_borderline_semantic_at_threshold_passes():
    """Tam eşikteki kart pass (>= karşılaştırma)."""
    ok, _ = is_top_card_relevant_for_llm([_card(semantic=0.50)])
    assert ok


def test_negative_rerank_score_rejected_overrides_high_semantic():
    """Reranker varsa otoritedir — negatif rerank semantic yüksek olsa bile reject."""
    card = _card(semantic=0.95, rerank=-2.5)
    ok, reason = is_top_card_relevant_for_llm(card.__class__.__class__.__call__(list, [card]))
    # ok beklemediğimiz için yukarıdaki yapı saçma — düz çağıralım
    ok, reason = is_top_card_relevant_for_llm([_card(semantic=0.95, rerank=-2.5)])
    assert not ok
    assert reason is not None
    assert "rerank" in reason


def test_positive_rerank_score_passes():
    ok, _ = is_top_card_relevant_for_llm([_card(semantic=0.95, rerank=3.2)])
    assert ok


def test_zero_rerank_at_threshold_passes():
    """0.0 default threshold; tam 0 → pass (>= karşılaştırma)."""
    ok, _ = is_top_card_relevant_for_llm([_card(semantic=0.95, rerank=0.0)])
    assert ok


def test_only_top_card_evaluated():
    """Top-1 alakalı ise alttaki düşük skorlar etkilemez."""
    cards = [
        _card(semantic=0.85),  # top
        _card(semantic=0.30),  # ignored
    ]
    ok, _ = is_top_card_relevant_for_llm(cards)
    assert ok


def test_custom_thresholds_respected():
    """Settings runtime override ile threshold değişir."""
    # Default kabul ederdi (0.50), threshold 0.60'a yükseltilince reject
    ok, _ = is_top_card_relevant_for_llm(
        [_card(semantic=0.55)], min_semantic_score=0.60
    )
    assert not ok


def test_missing_score_meta_treated_as_zero():
    """_score_meta yoksa semantic 0.0 default → reddedilir."""
    bare_card = {"id": "c1", "title": "x"}
    ok, reason = is_top_card_relevant_for_llm([bare_card])
    assert not ok
    assert "0.000" in reason
