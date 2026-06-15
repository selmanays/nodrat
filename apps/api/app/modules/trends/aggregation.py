"""Trend skor fonksiyonları — saf, deterministik (Faz 2 PR-2b, #1505).

Faz 1 (admin_trends.py) ile PAYLAŞILAN kanonik scoring + worker'a özel burst.
DB-bağımsız (unit-testable). admin_trends.py compute_* fonksiyonlarını buradan
import eder (tek doğruluk kaynağı).
"""

from __future__ import annotations

import statistics
from datetime import datetime

# =============================================================================
# Sabitler
# =============================================================================

TRENDS_ALGO_VERSION = 1  # formül değişince bump → eski snapshot'lar korunur
BUCKET_SECONDS = 3_600  # saatlik bucket (refresh-clusters ile hizalı)
SUBJECT_TYPE_TOPIC = "topic"

# trend_state eşikleri (v1 sabit; ileride settings'e taşınabilir)
BREAKING_MOMENTUM = 0.5
BREAKING_MIN_ARTICLES = 3
FADING_MOMENTUM = -0.3

# novelty yarı-ömrü (saat): brand-new ≈1.0, 12sa ≈0.5, 24sa ≈0.25
NOVELTY_HALFLIFE_HOURS = 12.0

# burst (z-score) trailing baseline penceresi + sinyal eşiği
BURST_BASELINE_BUCKETS = 24
BURST_SIGNAL_THRESHOLD = 2.0


# =============================================================================
# Saf scoring fonksiyonları (Faz 1 ile paylaşılan)
# =============================================================================


def compute_momentum(cur: int, prev: int) -> float | None:
    """(cur-prev)/prev. prev=0 & cur>0 → None ('yeni', baseline yok). Aksi 0.0."""
    if prev > 0:
        return round((cur - prev) / prev, 4)
    if cur > 0:
        return None
    return 0.0


def compute_novelty(first_seen_at: datetime | None, now: datetime) -> float:
    """Recency tabanlı novelty [0,1]: 0.5 ** (yaş_saat / yarı-ömür)."""
    if first_seen_at is None:
        return 0.0
    age_hours = max(0.0, (now - first_seen_at).total_seconds() / 3_600.0)
    return round(0.5 ** (age_hours / NOVELTY_HALFLIFE_HOURS), 4)


def compute_source_diversity(unique_sources: int, article_count: int) -> float:
    """Basit v1 yayılım proxy'si: benzersiz_kaynak / toplam_haber, [0,1]."""
    if article_count <= 0:
        return 0.0
    return round(min(1.0, unique_sources / article_count), 4)


def compute_trend_state(
    cur: int, prev: int, momentum: float | None, cluster_status: str | None = None
) -> str:
    """Deterministik durum: breaking | developing | stable | fading."""
    if cur == 0:
        return "fading" if prev > 0 else "stable"
    if prev == 0:
        # #1516: baseline yok (yeni). Tek/iki haber "breaking" sayılmaz —
        # ancak yeterli kanıt (≥BREAKING_MIN_ARTICLES) varsa breaking, yoksa
        # developing. Gürültülü tek-haber "Patlıyor" rozetini engeller.
        return "breaking" if cur >= BREAKING_MIN_ARTICLES else "developing"
    assert momentum is not None
    if momentum >= BREAKING_MOMENTUM and cur >= BREAKING_MIN_ARTICLES:
        return "breaking"
    if momentum > 0:
        return "developing"
    if momentum <= FADING_MOMENTUM:
        return "fading"
    return "stable"


# =============================================================================
# Worker'a özel — burst (z-score vs trailing baseline)
# =============================================================================


def compute_burst_score(cur: int, baseline_counts: list[int]) -> float:
    """Trailing baseline'a göre z-score: (cur - mean) / max(stddev, 1.0).

    baseline_counts = current bucket'tan ÖNCEKİ (≤ BURST_BASELINE_BUCKETS)
    bucket'ların article_count'ları (aynı subject, aynı algo_version). Boşsa 0.0.
    """
    if not baseline_counts:
        return 0.0
    mu = statistics.fmean(baseline_counts)
    sigma = statistics.pstdev(baseline_counts) if len(baseline_counts) > 1 else 0.0
    return round((cur - mu) / max(sigma, 1.0), 4)


def compute_velocity(cur: int, prev: int | None) -> float | None:
    """Δ count (cur - prev). prev yoksa None."""
    if prev is None:
        return None
    return float(cur - prev)
