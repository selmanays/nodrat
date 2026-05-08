"""Unit tests — admin_dashboard.mvp_2_1_delta endpoint (#432).

Epic #391 acceptance #4-#6 ölçüm endpoint'i. DB-siz unit test'ler:
router wiring, schema invariants, _delta_pct helper edge case'leri,
window hesaplama doğruluğu.

Gerçek DB query doğrulaması için integration suite testcontainers ile
ayrı çalışır (`tests/integration/test_admin_rag_sql.py` paterni).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

# ---------------------------------------------------------------------------
# Router wiring
# ---------------------------------------------------------------------------


def test_router_registered_mvp_2_1_delta_path():
    """app.main /admin/dashboard/mvp-2-1-delta mount edilmiş mi?"""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/dashboard/mvp-2-1-delta" in paths


def test_endpoint_method_is_get():
    from app.main import app

    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path == "/admin/dashboard/mvp-2-1-delta" and methods:
            methods_by_path[path] = set(methods)

    assert "GET" in methods_by_path["/admin/dashboard/mvp-2-1-delta"]


# ---------------------------------------------------------------------------
# Default cutoff = PR #418 deploy timestamp
# ---------------------------------------------------------------------------


def test_default_cutoff_is_pr_418_deploy():
    """Default cutoff PR #418 production deploy timestamp olmalı (2026-05-08T23:30Z)."""
    from app.api.admin_dashboard import MVP_2_1_DEFAULT_CUTOFF

    assert MVP_2_1_DEFAULT_CUTOFF == datetime(2026, 5, 8, 23, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _delta_pct helper — edge cases
# ---------------------------------------------------------------------------


def test_delta_pct_normal_decrease():
    """Pozitif → daha küçük: negatif yüzde."""
    from app.api.admin_dashboard import _delta_pct

    # 5800 → 3800 = %-34.48
    result = _delta_pct(5800.0, 3800.0)
    assert result == -34.48


def test_delta_pct_normal_increase():
    """Pozitif → daha büyük: pozitif yüzde."""
    from app.api.admin_dashboard import _delta_pct

    # 0.05 → 0.50 (cache hit ratio jump): %+900
    result = _delta_pct(0.05, 0.50)
    assert result == 900.0


def test_delta_pct_none_pre_returns_none():
    from app.api.admin_dashboard import _delta_pct

    assert _delta_pct(None, 100.0) is None


def test_delta_pct_none_post_returns_none():
    from app.api.admin_dashboard import _delta_pct

    assert _delta_pct(100.0, None) is None


def test_delta_pct_zero_pre_returns_none():
    """Bölme sıfır koruması — pre=0 olduğunda yüzde tanımsız."""
    from app.api.admin_dashboard import _delta_pct

    assert _delta_pct(0.0, 50.0) is None


def test_delta_pct_zero_change():
    """Aynı değer → 0.0%."""
    from app.api.admin_dashboard import _delta_pct

    assert _delta_pct(100.0, 100.0) == 0.0


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------


def test_window_metrics_allows_none_for_empty_window():
    """sample_count=0 senaryosu — diğer metrikler None olabilmeli."""
    from app.api.admin_dashboard import WindowMetrics

    now = datetime.now(timezone.utc)
    wm = WindowMetrics(
        window_start=now - timedelta(days=7),
        window_end=now,
        sample_count=0,
        avg_input_tokens=None,
        avg_output_tokens=None,
        cache_hit_ratio=None,
        avg_cost_usd_per_req=None,
        p50_latency_ms=None,
        p95_latency_ms=None,
        halu_flag_rate=None,
        insufficient_data_rate=None,
        completed_generation_count=0,
    )
    assert wm.sample_count == 0
    assert wm.avg_input_tokens is None


def test_response_model_includes_required_keys():
    """Mvp21DeltaResponse delta_pct dict'i acceptance metriklerini içeriyor."""
    from app.api.admin_dashboard import (
        Mvp21DeltaResponse,
        WindowMetrics,
    )

    now = datetime.now(timezone.utc)
    cutoff = datetime(2026, 5, 8, 23, 30, tzinfo=timezone.utc)
    empty = WindowMetrics(
        window_start=cutoff - timedelta(days=7),
        window_end=cutoff,
        sample_count=0,
        avg_input_tokens=None,
        avg_output_tokens=None,
        cache_hit_ratio=None,
        avg_cost_usd_per_req=None,
        p50_latency_ms=None,
        p95_latency_ms=None,
        halu_flag_rate=None,
        insufficient_data_rate=None,
        completed_generation_count=0,
    )
    response = Mvp21DeltaResponse(
        cutoff_at=cutoff,
        window_days=7,
        pre=empty,
        post=empty,
        delta_pct={
            "avg_input_tokens": None,
            "avg_output_tokens": None,
            "cache_hit_ratio": None,
            "avg_cost_usd_per_req": None,
            "p50_latency_ms": None,
            "p95_latency_ms": None,
            "halu_flag_rate": None,
        },
        note="test",
    )

    expected_keys = {
        "avg_input_tokens",
        "avg_output_tokens",
        "cache_hit_ratio",
        "avg_cost_usd_per_req",
        "p50_latency_ms",
        "p95_latency_ms",
        "halu_flag_rate",
    }
    assert expected_keys.issubset(response.delta_pct.keys())


# ---------------------------------------------------------------------------
# SQL invariants
# ---------------------------------------------------------------------------


def test_provider_metrics_sql_filters_chat_only():
    """Sadece operation='chat' (LLM çağrıları) sayılır — embedding/rerank hariç."""
    from app.api.admin_dashboard import _PROVIDER_METRICS_SQL

    assert "operation = 'chat'" in _PROVIDER_METRICS_SQL
    # success=TRUE filter — failed çağrılar metrik kirletmesin
    assert "success = TRUE" in _PROVIDER_METRICS_SQL


def test_generation_quality_sql_filters_content_output_types():
    """Halü/insufficient sadece Content Generator output_type'larında ölçülür."""
    from app.api.admin_dashboard import _GENERATION_QUALITY_SQL

    for output_type in ("x_post", "x_thread", "summary", "headline"):
        assert f"'{output_type}'" in _GENERATION_QUALITY_SQL


def test_provider_metrics_sql_uses_percentile_disc():
    """P50/P95 latency için PostgreSQL PERCENTILE_DISC kullanılıyor."""
    from app.api.admin_dashboard import _PROVIDER_METRICS_SQL

    assert "PERCENTILE_DISC(0.5)" in _PROVIDER_METRICS_SQL
    assert "PERCENTILE_DISC(0.95)" in _PROVIDER_METRICS_SQL


# ---------------------------------------------------------------------------
# Window math
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_window_math_pre_post_around_cutoff(monkeypatch):
    """Pre = [cutoff-7d, cutoff), Post = [cutoff, cutoff+7d) (now ile sınırlı).

    Cutoff'ı geçmiş bir tarihe sabitleyip pre+post window'ların doğru
    hesaplandığını monkeypatched _window_metrics ile doğrularız.
    """
    from app.api import admin_dashboard

    captured: list[tuple[datetime, datetime]] = []

    async def fake_window_metrics(db, *, start, end):
        captured.append((start, end))
        return admin_dashboard.WindowMetrics(
            window_start=start,
            window_end=end,
            sample_count=0,
            avg_input_tokens=None,
            avg_output_tokens=None,
            cache_hit_ratio=None,
            avg_cost_usd_per_req=None,
            p50_latency_ms=None,
            p95_latency_ms=None,
            halu_flag_rate=None,
            insufficient_data_rate=None,
            completed_generation_count=0,
        )

    monkeypatch.setattr(admin_dashboard, "_window_metrics", fake_window_metrics)

    # Geçmiş bir cutoff seç → post window cutoff+7d kadar sürecek
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)  # 14 gün önce — cutoff+7d hala geçmişte
    response = await admin_dashboard.mvp_2_1_delta(  # type: ignore[call-arg]
        admin=None,  # require_admin bypass — direct fn call
        db=None,
        cutoff_at=cutoff,
        window_days=7,
    )

    # 2 çağrı yapılmış: pre, post
    assert len(captured) == 2
    pre_start, pre_end = captured[0]
    post_start, post_end = captured[1]

    # Pre window doğru: [cutoff-7d, cutoff)
    assert pre_end == cutoff
    assert pre_start == cutoff - timedelta(days=7)

    # Post window: [cutoff, cutoff+7d) — full window çünkü cutoff+7d < now
    assert post_start == cutoff
    assert post_end == cutoff + timedelta(days=7)
    assert post_end > post_start

    assert response.cutoff_at == cutoff
    assert response.window_days == 7


@pytest.mark.asyncio
async def test_window_math_future_cutoff_clamps_post_to_empty(monkeypatch):
    """Cutoff henüz gelmemişse post window boş (post_start == post_end).

    Default cutoff (2026-05-08T23:30Z) deploy öncesi sistem zamanından küçükse
    post window kapanmamalı, sample_count=0 olarak dönmeli.
    """
    from app.api import admin_dashboard

    captured: list[tuple[datetime, datetime]] = []

    async def fake_window_metrics(db, *, start, end):
        captured.append((start, end))
        return admin_dashboard.WindowMetrics(
            window_start=start,
            window_end=end,
            sample_count=0,
            avg_input_tokens=None,
            avg_output_tokens=None,
            cache_hit_ratio=None,
            avg_cost_usd_per_req=None,
            p50_latency_ms=None,
            p95_latency_ms=None,
            halu_flag_rate=None,
            insufficient_data_rate=None,
            completed_generation_count=0,
        )

    monkeypatch.setattr(admin_dashboard, "_window_metrics", fake_window_metrics)

    # Gelecekte bir cutoff
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=30)
    await admin_dashboard.mvp_2_1_delta(  # type: ignore[call-arg]
        admin=None,
        db=None,
        cutoff_at=cutoff,
        window_days=7,
    )

    post_start, post_end = captured[1]
    # Post window invariant: post_end >= post_start (boş ama negative değil)
    assert post_end >= post_start
    # Spesifik: cutoff > now → post_end = post_start (boş window)
    assert post_end == post_start
