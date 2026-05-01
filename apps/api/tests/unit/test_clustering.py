"""Event clustering pure-function tests (#20).

DB integration testleri testcontainers ile gelecek.
Burada compute_status + compute_importance_score + vec serialize test edilir.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.clustering import (
    SEMANTIC_THRESHOLD,
    TITLE_TRIGRAM_THRESHOLD,
    WINDOW_HOURS,
    _vec_lit,
    compute_importance_score,
    compute_status,
)


# ---------------------------------------------------------------------------
# compute_status — state machine
# ---------------------------------------------------------------------------


def test_status_developing_solo():
    """Son 72h + 1 article → developing."""
    now = datetime.now(timezone.utc)
    s = compute_status(last_seen_at=now, article_count=1, now=now)
    assert s == "developing"


def test_status_active_multi_articles():
    """Son 72h + ≥2 article → active."""
    now = datetime.now(timezone.utc)
    s = compute_status(last_seen_at=now - timedelta(hours=10), article_count=3, now=now)
    assert s == "active"


def test_status_cooling_after_72h():
    """72h-7d → cooling."""
    now = datetime.now(timezone.utc)
    s = compute_status(
        last_seen_at=now - timedelta(hours=80), article_count=5, now=now
    )
    assert s == "cooling"


def test_status_stale_after_7d():
    now = datetime.now(timezone.utc)
    s = compute_status(
        last_seen_at=now - timedelta(days=10), article_count=10, now=now
    )
    assert s == "stale"


def test_status_archived_after_30d():
    now = datetime.now(timezone.utc)
    s = compute_status(
        last_seen_at=now - timedelta(days=45), article_count=10, now=now
    )
    assert s == "archived"


def test_status_handles_naive_datetime():
    """tzinfo=None → UTC kabul."""
    now = datetime.now(timezone.utc)
    naive_recent = (now - timedelta(hours=5)).replace(tzinfo=None)
    s = compute_status(last_seen_at=naive_recent, article_count=2, now=now)
    assert s == "active"


# ---------------------------------------------------------------------------
# compute_importance_score
# ---------------------------------------------------------------------------


def test_importance_zero():
    assert compute_importance_score(source_count=0, article_count=0) == 0.0


def test_importance_single():
    """1 source / 1 article → düşük (~0.29)"""
    score = compute_importance_score(source_count=1, article_count=1)
    assert 0.2 < score < 0.4


def test_importance_high_event():
    """10 source × 10 article → ~1.0"""
    score = compute_importance_score(source_count=10, article_count=10)
    assert 0.9 <= score <= 1.0


def test_importance_clamped_max():
    """50 source / 100 article → 1.0 (clamped)"""
    score = compute_importance_score(source_count=50, article_count=100)
    assert score == 1.0


def test_importance_more_sources_higher():
    """Aynı article_count, daha çok source → yüksek skor."""
    s_few = compute_importance_score(source_count=2, article_count=10)
    s_many = compute_importance_score(source_count=10, article_count=10)
    assert s_many > s_few


# ---------------------------------------------------------------------------
# Threshold sanity
# ---------------------------------------------------------------------------


def test_thresholds_in_valid_range():
    assert 0 < SEMANTIC_THRESHOLD < 1
    assert 0 < TITLE_TRIGRAM_THRESHOLD < 1


def test_window_hours_72():
    """PRD §2.5 — 72h matching window."""
    assert WINDOW_HOURS == 72


def test_semantic_threshold_reasonable():
    """Threshold 0.7-0.9 arasında (çok düşük → false positive, çok yüksek → kümelenmez)."""
    assert 0.7 <= SEMANTIC_THRESHOLD <= 0.9


# ---------------------------------------------------------------------------
# Vector literal
# ---------------------------------------------------------------------------


def test_vec_lit_format():
    assert _vec_lit([0.1, -0.5]) == "[0.1000000,-0.5000000]"


def test_vec_lit_empty():
    assert _vec_lit([]) == "[]"
