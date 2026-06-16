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
    compute_relative_momentum,
    compute_source_diversity,
    compute_trend_score,
    compute_trend_state,
    compute_velocity,
    compute_window_burst,
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
    # #1566 yeni imza: (cur, prev, rel_momentum, burst_z)
    # cur=0 → fading (prev>0)
    assert compute_trend_state(0, 5, None, 0.0) == "fading"
    # yeni (prev=0, rel=None) + güçlü pencere-içi yükseliş → breaking
    assert compute_trend_state(10, 0, None, 1.5) == "breaking"


# ---------------------------------------------------------------------------
# #1566 — korpus-normalize trend_state (A + B + D)
# ---------------------------------------------------------------------------


def test_relative_momentum_cancels_corpus_growth():
    # Entity 3.26× büyümüş AMA korpus 3.03× → relatif yalnız +%7.6 (gerçek trend zayıf).
    rel = compute_relative_momentum(241, 74, 1749, 577)
    assert rel == pytest.approx(0.076, abs=0.01)
    # Korpustan yavaş büyüyen → negatif (İsviçre 2.125× vs korpus 3.03×).
    assert compute_relative_momentum(68, 32, 1749, 577) < 0
    # prev=0 → None (baseline yok). corpus baseline yoksa → ham orana düşer.
    assert compute_relative_momentum(5, 0, 100, 50) is None
    assert compute_relative_momentum(10, 5, 0, 0) == 1.0


def test_window_burst_direction():
    # yükselen seri → pozitif, düşen → negatif, düz → ~0
    assert compute_window_burst([1, 1, 2, 3, 8, 9]) > 1.0
    assert compute_window_burst([9, 8, 3, 2, 1, 1]) < 0
    assert compute_window_burst([5, 5, 5, 5, 5, 5]) == pytest.approx(0.0, abs=1e-9)
    assert compute_window_burst([3, 3]) == 0.0  # <3 bucket → 0


def test_trend_state_corpus_rider_not_breaking():
    # Korpusla birlikte büyüyen (rel≈0) yükselen grafik → breaking DEĞİL, developing.
    assert compute_trend_state(241, 74, 0.076, 1.5) == "developing"
    # Korpusu belirgin geçen + yükselen → breaking.
    assert compute_trend_state(50, 10, 0.6, 1.5) == "breaking"


def test_trend_state_follows_graph_direction():
    # Düşen grafik (burst<=FADING) → fading, rel pozitif olsa bile (grafikle uyum).
    assert compute_trend_state(50, 10, 0.6, -1.0) == "fading"
    # Düz grafik + korpus-altı → stable.
    assert compute_trend_state(50, 50, -0.1, 0.0) == "stable"
    # Yükselen ama korpus-altı → developing (fading DEĞİL — grafik yükseliyor).
    assert compute_trend_state(50, 40, -0.3, 1.5) == "developing"


def test_trend_state_low_evidence():
    # cur<BREAKING_MIN_ARTICLES: yükselişte developing, düzde stable
    assert compute_trend_state(2, 0, None, 1.0) == "developing"
    assert compute_trend_state(2, 0, None, 0.0) == "stable"


def test_constants_sane():
    assert TRENDS_ALGO_VERSION == 1
    assert BURST_BASELINE_BUCKETS == 24


# ---------------------------------------------------------------------------
# compute_trend_score (#1518 birleşik skor)
# ---------------------------------------------------------------------------


def test_trend_score_bounds_and_monotonic_volume():
    # #1566 yeni imza: (cur, unique_sources, reliability, recency, rel_momentum)
    s = compute_trend_score(10, 4, 0.7, 0.9, 0.2)
    assert 0.0 <= s <= 1.0
    # Daha fazla haber → daha yüksek volume bileşeni → daha yüksek skor (cet. par.).
    low = compute_trend_score(2, 2, 0.5, 0.5, 0.0)
    high = compute_trend_score(40, 2, 0.5, 0.5, 0.0)
    assert high > low


def test_trend_score_momentum_uses_relative():
    # #1566: momentum bileşeni KORPUS-NORMALIZE rel → korpus-rider (rel≈0) düşük,
    # korpusu geçen (rel yüksek) yüksek kredi alır (doygunluk kırılır).
    rider = compute_trend_score(50, 5, 0.7, 0.5, 0.05)
    outperformer = compute_trend_score(50, 5, 0.7, 0.5, 0.8)
    assert outperformer > rider


def test_trend_score_new_subject_gets_partial_momentum():
    # rel=None (prev=0, baseline yok) → momentum bileşeni 0.5 kredisi (tam değil).
    new = compute_trend_score(5, 3, 0.5, 0.5, None)
    flat = compute_trend_score(5, 3, 0.5, 0.5, 0.0)  # rel 0 → momentum kredisi 0
    assert new > flat


def test_trend_score_zero_when_empty():
    # Tüm bileşenler 0 + reliability 0.0 → skor tam 0.
    assert compute_trend_score(0, 0, 0.0, 0.0, 0.0) == 0.0
    # reliability=None → 0.5 default (yalnız reliability bileşeni 0.05*0.5=0.025).
    assert compute_trend_score(0, 0, None, 0.0, 0.0) == 0.025


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
