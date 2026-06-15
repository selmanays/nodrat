"""Admin Trend Overview — Faz 1 unit tests (#1500).

Saf metrik fonksiyonları (momentum/novelty/diversity/trend_state/sparkline) +
router wiring + window/sort validation + flag-OFF no-op envelope. DB-bağımsız
(integration testleri testcontainers ile test_admin_trends_sql.py'de).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.api.admin_trends import (
    SPARKLINE_BUCKETS,
    VALID_SORTS,
    WINDOW_SECONDS,
    TrendListResponse,
    build_sparkline,
    compute_momentum,
    compute_novelty,
    compute_source_diversity,
    compute_trend_state,
    list_trends,
    resolve_window,
)

# ---------------------------------------------------------------------------
# Router wiring
# ---------------------------------------------------------------------------


def test_router_registered_admin_trends_path():
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/trends" in paths


def test_admin_trends_get_method():
    from app.main import app

    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            methods_by_path.setdefault(path, set()).update(methods)
    assert "GET" in methods_by_path["/admin/trends"]


# ---------------------------------------------------------------------------
# Sabitler / config tutarlılığı
# ---------------------------------------------------------------------------


def test_window_keys_match_sparkline_keys():
    assert set(WINDOW_SECONDS) == set(SPARKLINE_BUCKETS)


def test_sparkline_buckets_cover_window():
    """bucket_count * bucket_seconds == window saniyesi (tam kaplama)."""
    for win, seconds in WINDOW_SECONDS.items():
        count, bucket_sec = SPARKLINE_BUCKETS[win]
        assert count * bucket_sec == seconds, win


def test_valid_sorts():
    assert {
        "score",  # #1518 birleşik skor (varsayılan)
        "momentum",
        "article_count",
        "source_count",
        "novelty",
        "credibility",
    } == VALID_SORTS


# ---------------------------------------------------------------------------
# resolve_window
# ---------------------------------------------------------------------------


def test_resolve_window_valid_passthrough():
    assert resolve_window("6h", "24h") == "6h"


def test_resolve_window_none_uses_fallback():
    assert resolve_window(None, "7d") == "7d"


def test_resolve_window_invalid_raises():
    with pytest.raises(ValueError, match="invalid window"):
        resolve_window("3h", "24h")


# ---------------------------------------------------------------------------
# compute_momentum
# ---------------------------------------------------------------------------


def test_momentum_new_when_prev_zero_cur_positive():
    assert compute_momentum(20, 0) is None  # yeni — baseline yok


def test_momentum_zero_when_both_zero():
    assert compute_momentum(0, 0) == 0.0


def test_momentum_normal_growth():
    assert compute_momentum(10, 5) == 1.0


def test_momentum_decline():
    assert compute_momentum(2, 10) == -0.8


# ---------------------------------------------------------------------------
# compute_novelty (recency, yarı-ömür 12h)
# ---------------------------------------------------------------------------


def test_novelty_none_first_seen():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    assert compute_novelty(None, now) == 0.0


def test_novelty_brand_new_near_one():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    assert compute_novelty(now, now) == 1.0


def test_novelty_half_life_12h():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    assert compute_novelty(now - timedelta(hours=12), now) == pytest.approx(0.5, abs=1e-4)


def test_novelty_24h_quarter():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    assert compute_novelty(now - timedelta(hours=24), now) == pytest.approx(0.25, abs=1e-4)


def test_novelty_future_first_seen_clamped_to_one():
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    # gelecekteki first_seen (saat kayması) → yaş 0'a clamp → 1.0
    assert compute_novelty(now + timedelta(hours=5), now) == 1.0


# ---------------------------------------------------------------------------
# compute_source_diversity
# ---------------------------------------------------------------------------


def test_diversity_zero_articles():
    assert compute_source_diversity(0, 0) == 0.0


def test_diversity_ratio():
    assert compute_source_diversity(3, 10) == 0.3


def test_diversity_clamped_to_one():
    # benzersiz > toplam (teorik) → 1.0'a clamp
    assert compute_source_diversity(10, 5) == 1.0


# ---------------------------------------------------------------------------
# compute_trend_state (4 durum)
# ---------------------------------------------------------------------------


def test_state_breaking_new():
    assert compute_trend_state(10, 0, None, "developing") == "breaking"


def test_state_breaking_high_momentum():
    mom = compute_momentum(10, 5)  # 1.0
    assert compute_trend_state(10, 5, mom, "active") == "breaking"


def test_state_developing():
    mom = compute_momentum(4, 3)  # ~0.333 > 0, < 0.5
    assert compute_trend_state(4, 3, mom, "active") == "developing"


def test_state_fading_decline():
    mom = compute_momentum(2, 10)  # -0.8 <= -0.3
    assert compute_trend_state(2, 10, mom, "cooling") == "fading"


def test_state_fading_no_current():
    assert compute_trend_state(0, 5, compute_momentum(0, 5), "cooling") == "fading"


def test_state_stable_flat():
    mom = compute_momentum(5, 5)  # 0.0 → ne >0 ne <=-0.3
    assert compute_trend_state(5, 5, mom, "active") == "stable"


def test_state_stable_when_empty():
    assert compute_trend_state(0, 0, compute_momentum(0, 0), "stale") == "stable"


# ---------------------------------------------------------------------------
# build_sparkline
# ---------------------------------------------------------------------------


def test_sparkline_zero_filled_length():
    win_start = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
    pts = build_sparkline({}, win_start, bucket_count=6, bucket_seconds=600)
    assert len(pts) == 6
    assert all(p.article_count == 0 for p in pts)


def test_sparkline_maps_counts_to_buckets():
    win_start = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
    pts = build_sparkline({0: 3, 2: 5}, win_start, bucket_count=4, bucket_seconds=3600)
    assert [p.article_count for p in pts] == [3, 0, 5, 0]
    # ilk bucket başlangıcı win_start; ikinci +1sa
    assert pts[0].bucket_start == win_start.isoformat()
    assert pts[1].bucket_start == (win_start + timedelta(hours=1)).isoformat()


# ---------------------------------------------------------------------------
# Endpoint — flag OFF no-op + validation (DB monkeypatch'li doğrudan çağrı)
# ---------------------------------------------------------------------------


class _FakeSettingsStore:
    """settings_store yerine — get_bool/get sabit döndürür, DB'ye dokunmaz."""

    def __init__(self, enabled: bool, window_default: str = "24h"):
        self._enabled = enabled
        self._window_default = window_default

    async def get(self, db, key, default=None):
        if key == "trends.overview.window_default":
            return self._window_default
        return default

    async def get_bool(self, db, key, default):
        if key == "trends.enabled":
            return self._enabled
        return default

    async def get_int(self, db, key, default):
        return default  # #1516 gate eşikleri — default (2) döner


async def test_flag_off_returns_noop_envelope(monkeypatch):
    import app.api.admin_trends as mod

    monkeypatch.setattr(mod, "settings_store", _FakeSettingsStore(enabled=False))
    resp = await list_trends(
        admin=object(), db=object(), window="6h", sort="momentum", limit=50, offset=0
    )
    assert isinstance(resp, TrendListResponse)
    assert resp.enabled is False
    assert resp.data == []
    assert resp.total == 0
    assert resp.window == "6h"
    assert resp.sort == "momentum"


async def test_flag_off_resolves_window_default_when_none(monkeypatch):
    import app.api.admin_trends as mod

    monkeypatch.setattr(
        mod, "settings_store", _FakeSettingsStore(enabled=False, window_default="7d")
    )
    resp = await list_trends(
        admin=object(), db=object(), window=None, sort="momentum", limit=50, offset=0
    )
    assert resp.window == "7d"
    assert resp.enabled is False


async def test_invalid_sort_raises_422(monkeypatch):
    import app.api.admin_trends as mod
    from fastapi import HTTPException

    monkeypatch.setattr(mod, "settings_store", _FakeSettingsStore(enabled=False))
    with pytest.raises(HTTPException) as exc:
        await list_trends(
            admin=object(), db=object(), window="24h", sort="bogus", limit=50, offset=0
        )
    assert exc.value.status_code == 422


async def test_invalid_window_raises_422(monkeypatch):
    import app.api.admin_trends as mod
    from fastapi import HTTPException

    monkeypatch.setattr(mod, "settings_store", _FakeSettingsStore(enabled=False))
    with pytest.raises(HTTPException) as exc:
        await list_trends(
            admin=object(), db=object(), window="3h", sort="momentum", limit=50, offset=0
        )
    assert exc.value.status_code == 422


async def test_score_is_valid_sort(monkeypatch):
    # #1518: "score" varsayılan/geçerli sort (flag OFF → no-op, validation geçer).
    import app.api.admin_trends as mod

    monkeypatch.setattr(mod, "settings_store", _FakeSettingsStore(enabled=False))
    resp = await list_trends(
        admin=object(), db=object(), window="24h", sort="score", limit=50, offset=0
    )
    assert resp.enabled is False
    assert resp.sort == "score"
