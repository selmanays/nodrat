"""Quota tier config + QuotaStatus testleri (free=10/AY — sistem-testi Bulgu 10).

Pure-config + dataclass davranışı (Redis/DB gerektirmez). Free tier'ın aylık
pencereye + 10 limite geçişini kilitler; paid tier'lar 24h pencerede kalır.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.billing.services.quota import (
    DEFAULT_WINDOW_SECONDS,
    MONTH_WINDOW_SECONDS,
    TIER_LIMITS,
    TIER_WINDOW_SECONDS,
    QuotaStatus,
)


def test_free_tier_is_10_per_month() -> None:
    """Free tier 10/AY (plans.monthly_generation_limit['free'] ile birebir; eski 5/24h değil)."""
    assert TIER_LIMITS["free"] == 10
    assert TIER_WINDOW_SECONDS["free"] == MONTH_WINDOW_SECONDS
    assert MONTH_WINDOW_SECONDS == 30 * 24 * 60 * 60


def test_paid_tiers_stay_24h_window() -> None:
    """Paid tier'lar + trial 24h pencerede (bu değişiklik yalnız free'yi aylığa çevirir)."""
    for tier in ("trial", "starter", "pro", "agency_seat"):
        assert TIER_WINDOW_SECONDS.get(tier, DEFAULT_WINDOW_SECONDS) == DEFAULT_WINDOW_SECONDS
    assert DEFAULT_WINDOW_SECONDS == 24 * 60 * 60
    # paid limitler korundu (regresyon kilidi)
    assert TIER_LIMITS["starter"] == 30
    assert TIER_LIMITS["pro"] == 150
    assert TIER_LIMITS["agency_seat"] == 500


def test_quota_status_exceeded_logic() -> None:
    """exceeded: used >= limit (free limit=10)."""
    now = datetime.now(UTC)
    at_limit = QuotaStatus(tier="free", limit=10, used=10, remaining=0, reset_at=now)
    under = QuotaStatus(tier="free", limit=10, used=9, remaining=1, reset_at=now)
    over = QuotaStatus(tier="free", limit=10, used=11, remaining=0, reset_at=now)
    assert at_limit.exceeded is True
    assert under.exceeded is False
    assert over.exceeded is True
