"""Unit tests — admin_rag.pipeline_comparison endpoint (#440).

İki tarih aralığı arasında LLM pipeline metriklerini karşılaştıran jenerik
endpoint. DB-siz unit test'ler:
- Router wiring + HTTP method
- Schema invariants (boş pencere edge case)
- _pipeline_delta_pct helper edge case'leri
- SQL invariants (chat-only filter, output_type filter, PERCENTILE_DISC)
- Period math (default: son 7d vs önceki 7d, custom range, validation)

Gerçek DB query doğrulaması integration suite testcontainers ile ayrı
çalışır (`tests/integration/test_admin_rag_sql.py` paterni).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Router wiring
# ---------------------------------------------------------------------------


def test_router_registered_pipeline_comparison_path():
    """app.main /admin/rag/pipeline-comparison mount edilmiş mi?"""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/rag/pipeline-comparison" in paths


def test_endpoint_method_is_get():
    from app.main import app

    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path == "/admin/rag/pipeline-comparison" and methods:
            methods_by_path[path] = set(methods)

    assert "GET" in methods_by_path["/admin/rag/pipeline-comparison"]


def test_old_mvp_2_1_delta_endpoint_removed():
    """Eski endpoint silindi — milestone-bound isim artık yok."""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/dashboard/mvp-2-1-delta" not in paths


# ---------------------------------------------------------------------------
# _pipeline_delta_pct helper — edge cases
# ---------------------------------------------------------------------------


def test_delta_pct_normal_decrease():
    """Pozitif → daha küçük: negatif yüzde."""
    from app.api.admin_rag import _pipeline_delta_pct

    # 5800 → 3800 = %-34.48
    result = _pipeline_delta_pct(5800.0, 3800.0)
    assert result == -34.48


def test_delta_pct_normal_increase():
    """Pozitif → daha büyük: pozitif yüzde."""
    from app.api.admin_rag import _pipeline_delta_pct

    # 0.05 → 0.50 (cache hit ratio jump): %+900
    result = _pipeline_delta_pct(0.05, 0.50)
    assert result == 900.0


def test_delta_pct_none_a_returns_none():
    from app.api.admin_rag import _pipeline_delta_pct

    assert _pipeline_delta_pct(None, 100.0) is None


def test_delta_pct_none_b_returns_none():
    from app.api.admin_rag import _pipeline_delta_pct

    assert _pipeline_delta_pct(100.0, None) is None


def test_delta_pct_zero_a_returns_none():
    """Bölme sıfır koruması — A=0 olduğunda yüzde tanımsız."""
    from app.api.admin_rag import _pipeline_delta_pct

    assert _pipeline_delta_pct(0.0, 50.0) is None


def test_delta_pct_zero_change():
    """Aynı değer → 0.0%."""
    from app.api.admin_rag import _pipeline_delta_pct

    assert _pipeline_delta_pct(100.0, 100.0) == 0.0


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------


def test_period_metrics_allows_none_for_empty_window():
    """sample_count=0 senaryosu — diğer metrikler None olabilmeli."""
    from app.api.admin_rag import PeriodMetrics

    now = datetime.now(UTC)
    pm = PeriodMetrics(
        period_start=now - timedelta(days=7),
        period_end=now,
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
    assert pm.sample_count == 0
    assert pm.avg_input_tokens is None


def test_response_model_includes_required_keys():
    """PipelineComparisonResponse delta_pct dict'i tüm metrikleri içeriyor."""
    from app.api.admin_rag import (
        PeriodMetrics,
        PipelineComparisonResponse,
    )

    now = datetime.now(UTC)
    empty = PeriodMetrics(
        period_start=now - timedelta(days=7),
        period_end=now,
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
    response = PipelineComparisonResponse(
        period_a=empty,
        period_b=empty,
        delta_pct={
            "avg_input_tokens": None,
            "avg_output_tokens": None,
            "cache_hit_ratio": None,
            "avg_cost_usd_per_req": None,
            "p50_latency_ms": None,
            "p95_latency_ms": None,
            "halu_flag_rate": None,
        },
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
    from app.api.admin_rag import _PIPELINE_PROVIDER_METRICS_SQL

    assert "operation = 'chat'" in _PIPELINE_PROVIDER_METRICS_SQL
    # success=TRUE filter — failed çağrılar metrik kirletmesin
    assert "success = TRUE" in _PIPELINE_PROVIDER_METRICS_SQL


def test_generation_quality_sql_filters_content_output_types():
    """Halü/insufficient sadece Content Generator output_type'larında ölçülür."""
    from app.api.admin_rag import _PIPELINE_GENERATION_QUALITY_SQL

    for output_type in ("x_post", "x_thread", "summary", "headline"):
        assert f"'{output_type}'" in _PIPELINE_GENERATION_QUALITY_SQL


def test_provider_metrics_sql_uses_percentile_disc():
    """P50/P95 latency için PostgreSQL PERCENTILE_DISC kullanılıyor."""
    from app.api.admin_rag import _PIPELINE_PROVIDER_METRICS_SQL

    assert "PERCENTILE_DISC(0.5)" in _PIPELINE_PROVIDER_METRICS_SQL
    assert "PERCENTILE_DISC(0.95)" in _PIPELINE_PROVIDER_METRICS_SQL


# ---------------------------------------------------------------------------
# Period math
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_period_math_default_last_7d_vs_prev_7d(monkeypatch):
    """Default: son 7 gün (B) vs önceki 7 gün (A). DB sorgularını mock'larız."""
    from app.api import admin_rag

    captured: list[tuple[datetime, datetime]] = []

    async def fake_period_metrics(db, *, start, end):
        captured.append((start, end))
        return admin_rag.PeriodMetrics(
            period_start=start,
            period_end=end,
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

    monkeypatch.setattr(admin_rag, "_pipeline_period_metrics", fake_period_metrics)

    response = await admin_rag.pipeline_comparison(  # type: ignore[call-arg]
        admin=None,
        db=None,
    )

    assert len(captured) == 2
    a_start, a_end = captured[0]
    b_start, b_end = captured[1]

    # B = [now - 7d, now]
    # A = [now - 14d, now - 7d]
    week = timedelta(days=7)
    assert b_end - b_start == week
    assert a_end - a_start == week
    assert a_end == b_start  # iki dönem komşu

    assert response.period_a.period_start == a_start
    assert response.period_b.period_start == b_start


@pytest.mark.asyncio
async def test_period_math_custom_ranges(monkeypatch):
    """Tüm parametreler verilirse onları kullan."""
    from app.api import admin_rag

    captured: list[tuple[datetime, datetime]] = []

    async def fake_period_metrics(db, *, start, end):
        captured.append((start, end))
        return admin_rag.PeriodMetrics(
            period_start=start,
            period_end=end,
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

    monkeypatch.setattr(admin_rag, "_pipeline_period_metrics", fake_period_metrics)

    fa = datetime(2026, 5, 1, tzinfo=UTC)
    ta = datetime(2026, 5, 8, tzinfo=UTC)
    fb = datetime(2026, 5, 8, tzinfo=UTC)
    tb = datetime(2026, 5, 15, tzinfo=UTC)

    await admin_rag.pipeline_comparison(  # type: ignore[call-arg]
        admin=None,
        db=None,
        from_a=fa,
        to_a=ta,
        from_b=fb,
        to_b=tb,
    )

    assert captured == [(fa, ta), (fb, tb)]


@pytest.mark.asyncio
async def test_period_math_invalid_range_raises(monkeypatch):
    """from_a >= to_a → 400 INVALID_RANGE."""
    from app.api import admin_rag

    async def fake_period_metrics(db, *, start, end):
        raise AssertionError("DB should not be called on validation failure")

    monkeypatch.setattr(admin_rag, "_pipeline_period_metrics", fake_period_metrics)

    fa = datetime(2026, 5, 8, tzinfo=UTC)
    ta = datetime(2026, 5, 1, tzinfo=UTC)  # invalid (ta < fa)

    with pytest.raises(HTTPException) as exc:
        await admin_rag.pipeline_comparison(  # type: ignore[call-arg]
            admin=None,
            db=None,
            from_a=fa,
            to_a=ta,
            from_b=fa,
            to_b=ta,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "INVALID_RANGE"
