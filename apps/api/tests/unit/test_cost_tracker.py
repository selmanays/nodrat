"""Cost tracker unit tests (#23).

estimate_cost_usd saf fonksiyon — DB-free.
track_provider_call'in DB integration testleri testcontainers ile gelecek.
"""

from __future__ import annotations

from decimal import Decimal

from app.shared.observability.cost_tracker import CallTracker, estimate_cost_usd


def test_cost_zero_tokens():
    cost = estimate_cost_usd(
        provider="nim",
        input_tokens=None,
        output_tokens=None,
        cost_per_1m_input=10.0,
        cost_per_1m_output=20.0,
    )
    assert cost == Decimal("0.0")


def test_cost_free_tier():
    cost = estimate_cost_usd(
        provider="local_bge_m3",
        input_tokens=1000,
        output_tokens=0,
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
    )
    assert cost == Decimal("0.000000")


def test_cost_input_only():
    """1M token × $1/1M = $1."""
    cost = estimate_cost_usd(
        provider="x",
        input_tokens=1_000_000,
        output_tokens=0,
        cost_per_1m_input=1.0,
        cost_per_1m_output=2.0,
    )
    assert cost == Decimal("1.000000")


def test_cost_input_and_output():
    """500K input @ $1 + 500K output @ $4 = $0.50 + $2 = $2.50"""
    cost = estimate_cost_usd(
        provider="x",
        input_tokens=500_000,
        output_tokens=500_000,
        cost_per_1m_input=1.0,
        cost_per_1m_output=4.0,
    )
    assert cost == Decimal("2.500000")


def test_cost_small_token_count():
    """1000 token × $0.14/1M = $0.00014 (deepseek-v4-flash cache-miss)"""
    cost = estimate_cost_usd(
        provider="deepseek",
        input_tokens=1000,
        output_tokens=0,
        cost_per_1m_input=0.14,
        cost_per_1m_output=0.0,
    )
    assert cost == Decimal("0.000140")


def test_cost_decimal_precision():
    """6 hane precision."""
    cost = estimate_cost_usd(
        provider="x",
        input_tokens=1,
        output_tokens=1,
        cost_per_1m_input=1.0,
        cost_per_1m_output=1.0,
    )
    # 2 / 1M = 0.000002
    assert cost == Decimal("0.000002")


def test_call_tracker_record_partial():
    """tracker.record() ile metrikler doldurulur."""
    import time

    t = CallTracker(
        provider="local_bge_m3",
        operation="embedding",
        started_at_perf=time.perf_counter(),
    )
    t.record(input_tokens=100, model="BAAI/bge-m3")
    assert t.input_tokens == 100
    assert t.model == "BAAI/bge-m3"
    assert t.output_tokens is None  # untouched
    assert t.success is True


def test_call_tracker_record_cost_decimal():
    """cost_usd float verilirse Decimal'a çevrilir."""
    import time

    t = CallTracker(
        provider="x",
        operation="chat",
        started_at_perf=time.perf_counter(),
    )
    t.record(cost_usd=0.001234)
    assert isinstance(t.cost_usd, Decimal)
    assert t.cost_usd == Decimal("0.001234")
