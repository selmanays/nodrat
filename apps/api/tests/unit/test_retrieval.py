"""Vector retrieval scoring + serialization tests (#22).

DB integration testleri testcontainers ile gelecek.
Burada saf fonksiyonları (freshness_decay, compute_final_score, vector serialize)
ve mod weight tablolarını test ederiz.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.retrieval import (
    CURRENT_MODE_FALLBACKS_HOURS,
    WEIGHTS_CURRENT,
    WEIGHTS_DEFAULT,
    _vector_to_pg_literal,
    compute_final_score,
    freshness_decay,
)


# ---------------------------------------------------------------------------
# freshness_decay
# ---------------------------------------------------------------------------


def test_freshness_now_is_one():
    assert freshness_decay(datetime.now(timezone.utc)) > 0.99


def test_freshness_one_half_life_is_half():
    """24h sonra 0.5 (default half-life=24h)."""
    past = datetime.now(timezone.utc) - timedelta(hours=24)
    assert abs(freshness_decay(past) - 0.5) < 0.05


def test_freshness_two_half_lives_is_quarter():
    past = datetime.now(timezone.utc) - timedelta(hours=48)
    assert abs(freshness_decay(past) - 0.25) < 0.03


def test_freshness_far_past_near_zero():
    past = datetime.now(timezone.utc) - timedelta(days=365)
    assert freshness_decay(past) < 0.01


def test_freshness_naive_datetime_handled():
    """tzinfo=None → UTC kabul edilir."""
    naive = datetime.utcnow().replace(tzinfo=None)
    score = freshness_decay(naive)
    # Naive UTC + 0..1 second offset → score yaklaşık 1
    assert 0.99 <= score <= 1.0


def test_freshness_none_returns_half():
    assert freshness_decay(None) == 0.5


def test_freshness_custom_half_life():
    """48h half-life ile 48h önce 0.5."""
    past = datetime.now(timezone.utc) - timedelta(hours=48)
    assert abs(freshness_decay(past, half_life_hours=48) - 0.5) < 0.05


# ---------------------------------------------------------------------------
# compute_final_score
# ---------------------------------------------------------------------------


def test_score_default_weights_sum_to_one():
    assert abs(sum(WEIGHTS_DEFAULT.values()) - 1.0) < 1e-6


def test_score_current_weights_sum_to_one():
    assert abs(sum(WEIGHTS_CURRENT.values()) - 1.0) < 1e-6


def test_score_all_max_returns_one():
    s = compute_final_score(
        semantic=1.0,
        freshness=1.0,
        importance=1.0,
        reliability=1.0,
        weights=WEIGHTS_DEFAULT,
    )
    assert abs(s - 1.0) < 1e-6


def test_score_all_zero_returns_zero():
    s = compute_final_score(
        semantic=0.0,
        freshness=0.0,
        importance=0.0,
        reliability=0.0,
        weights=WEIGHTS_DEFAULT,
    )
    assert s == 0.0


def test_score_semantic_dominates_default():
    """Default weights'te semantic en ağır faktör."""
    s_only_sem = compute_final_score(
        semantic=1.0, freshness=0, importance=0, reliability=0, weights=WEIGHTS_DEFAULT
    )
    s_only_fresh = compute_final_score(
        semantic=0, freshness=1.0, importance=0, reliability=0, weights=WEIGHTS_DEFAULT
    )
    assert s_only_sem > s_only_fresh
    assert s_only_sem == WEIGHTS_DEFAULT["semantic"]


def test_score_current_freshness_higher_weight_than_default():
    """Current modda freshness ağırlığı default'tan yüksektir."""
    assert WEIGHTS_CURRENT["freshness"] > WEIGHTS_DEFAULT["freshness"]
    assert WEIGHTS_CURRENT["semantic"] < WEIGHTS_DEFAULT["semantic"]


# ---------------------------------------------------------------------------
# _vector_to_pg_literal
# ---------------------------------------------------------------------------


def test_pg_literal_basic():
    result = _vector_to_pg_literal([0.1, 0.2, -0.3])
    assert result == "[0.1000000,0.2000000,-0.3000000]"


def test_pg_literal_empty():
    assert _vector_to_pg_literal([]) == "[]"


def test_pg_literal_high_precision():
    result = _vector_to_pg_literal([1 / 3])
    # 7 hane precision
    assert "0.3333333" in result


# ---------------------------------------------------------------------------
# Mode constants
# ---------------------------------------------------------------------------


def test_current_fallback_levels():
    """24h → 48h → 72h sıralı."""
    assert CURRENT_MODE_FALLBACKS_HOURS == (24, 48, 72)
