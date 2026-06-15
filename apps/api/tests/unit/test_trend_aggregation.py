"""Trend aggregation + topic_assignment saf fonksiyonları (Faz 2 PR-2b, #1505).

DB-bağımsız: burst z-score, velocity, slugify, make_unique_slug + paylaşılan
scoring (aggregation modülü kopyası). Worker SQL/idempotency integration testte.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.trends.aggregation import (
    BURST_BASELINE_BUCKETS,
    SCORE_W_VOLUME,
    TRENDS_ALGO_VERSION,
    compute_burst_score,
    compute_momentum,
    compute_source_diversity,
    compute_trend_score,
    compute_trend_state,
    compute_velocity,
)
from app.modules.trends.topic_assignment import make_unique_slug, slugify

# ---------------------------------------------------------------------------
# compute_burst_score (z-score)
# ---------------------------------------------------------------------------


def test_burst_empty_baseline_zero():
    assert compute_burst_score(10, []) == 0.0


def test_burst_zscore_positive():
    # baseline mean=5, current 15 → belirgin pozitif z-score
    assert compute_burst_score(15, [5, 5, 5, 5]) > 0


def test_burst_sigma_floor_no_blowup():
    # tüm baseline aynı (sigma=0) → max(sigma,1) ile patlamaz
    val = compute_burst_score(8, [5, 5, 5])
    assert val == pytest.approx(3.0, abs=1e-4)  # (8-5)/max(0,1)=3


def test_burst_below_baseline_negative():
    assert compute_burst_score(1, [10, 10, 10]) < 0


# ---------------------------------------------------------------------------
# compute_velocity
# ---------------------------------------------------------------------------


def test_velocity_none_prev():
    assert compute_velocity(10, None) is None


def test_velocity_delta():
    assert compute_velocity(10, 4) == 6.0
    assert compute_velocity(3, 10) == -7.0


# ---------------------------------------------------------------------------
# Paylaşılan scoring (aggregation modülü kopyası — Faz1 ile tutarlı)
# ---------------------------------------------------------------------------


def test_shared_momentum_new_and_normal():
    assert compute_momentum(5, 0) is None
    assert compute_momentum(10, 5) == 1.0


def test_shared_diversity_and_state():
    assert compute_source_diversity(3, 10) == 0.3
    assert compute_trend_state(10, 0, None) == "breaking"
    assert compute_trend_state(0, 5, compute_momentum(0, 5)) == "fading"


def test_breaking_requires_min_articles_when_no_baseline():
    # #1516: baseline yok (prev=0) iken tek/iki haber breaking DEĞİL → developing.
    # BREAKING_MIN_ARTICLES (3) eşiğinden itibaren breaking.
    assert compute_trend_state(1, 0, None) == "developing"
    assert compute_trend_state(2, 0, None) == "developing"
    assert compute_trend_state(3, 0, None) == "breaking"
    assert compute_trend_state(7, 0, None) == "breaking"


def test_constants_sane():
    assert TRENDS_ALGO_VERSION == 1
    assert BURST_BASELINE_BUCKETS == 24


# ---------------------------------------------------------------------------
# compute_trend_score (#1518 birleşik skor)
# ---------------------------------------------------------------------------


def test_trend_score_bounds_and_monotonic_volume():
    # Skor [0,1] aralığında.
    s = compute_trend_score(10, 5, 4, 0.7, 0.9)
    assert 0.0 <= s <= 1.0
    # Daha fazla haber → daha yüksek volume bileşeni → daha yüksek skor (cet. par.).
    low = compute_trend_score(2, 1, 2, 0.5, 0.5)
    high = compute_trend_score(40, 1, 2, 0.5, 0.5)
    assert high > low


def test_trend_score_new_subject_gets_partial_momentum():
    # prev=0 (baseline yok) → momentum bileşeni 0.5 kredisi (tam değil).
    new = compute_trend_score(5, 0, 3, 0.5, 0.5)
    flat = compute_trend_score(5, 5, 3, 0.5, 0.5)  # momentum 0
    assert new > flat


def test_trend_score_zero_when_empty():
    assert compute_trend_score(0, 0, 0, None, 0.0) == 0.0


def test_trend_score_volume_weight_dominant():
    # volume ağırlığı (0.40) en büyük tek bileşen olmalı (öncelik kullanıcı kararı).
    assert SCORE_W_VOLUME == 0.40
    assert SCORE_W_VOLUME >= 0.25  # momentum'dan büyük/eşit


# ---------------------------------------------------------------------------
# slugify / make_unique_slug (topic_assignment saf)
# ---------------------------------------------------------------------------


def test_slugify_turkish_to_ascii():
    assert slugify("Merkez Bankası Faiz Kararı") == "merkez-bankasi-faiz-karari"
    assert slugify("Iğdır'da Şişli çöküşü") == "igdir-da-sisli-cokusu"


def test_slugify_empty_fallback():
    assert slugify("") == "topic"
    assert slugify("!!! ???") == "topic"


def test_slugify_truncate():
    assert len(slugify("a" * 300, max_len=140)) == 140


def test_make_unique_slug_appends_cluster_suffix():
    cid = uuid.UUID("12345678-1234-1234-1234-123456789abc")
    s = make_unique_slug("Altın Fiyatları", cid)
    assert s == "altin-fiyatlari-12345678"
