"""Unit — #619 PR-3 query decomposition orchestration wiring helpers.

PR-3 `_research_stream_body` wiring'i iki küçük helper'a dayanır:
- `_build_decomposition_hint` — alt-sorgu planı → LLM bağlam hint string'i (saf)
- `_decompose_for_research` — flag-gated decompose (kapalı/hata/tek-konu → None)

Orchestrator full-integration (15+ mock) proje genelinde "first-yield only"
kabul edilmiştir (`test_research_stream_orchestrator.py`); PR-3 de o disipline
uyar: davranış-kararı helper seviyesinde test edilir. **Flag-OFF byte-identical**
mevcut SSE-replay/orchestrator testleriyle (default flag-OFF) garanti edilir;
**citation/cite_n zinciri** PR-1 baseline (`test_query_decomposition_baseline.py`)
ile korunur (PR-3 tool-loop/_dispatch/execute_search_news'e dokunmaz).
"""

from __future__ import annotations

import pytest

# app.api.app_research_stream import zinciri pyotp (Docker-only) çeker.
pytest.importorskip("pyotp")

from app.api.app_research_stream import (
    _build_decomposition_hint,
    _decompose_for_research,
    _decomposition_telemetry,
)
from app.prompts.query_decomposition import DecompositionResult

# =============================================================================
# _build_decomposition_hint (saf)
# =============================================================================


def test_hint_contains_all_subqueries_and_search_news_instruction():
    hint = _build_decomposition_hint(["faiz kararları", "döviz kuru gelişmeleri"])
    assert "faiz kararları" in hint
    assert "döviz kuru gelişmeleri" in hint
    # LLM-driven (3b): her alt-sorguyu search_news ile ayrı arama talimatı
    assert "search_news" in hint


# =============================================================================
# _decompose_for_research (flag-gated)
# =============================================================================


@pytest.mark.asyncio
async def test_disabled_returns_none():
    # enabled False → None (byte-identical no-op); decompose hiç çağrılmaz
    out = await _decompose_for_research(
        "Türkiye ekonomisi ve faiz kararları son durum", None, enabled=False
    )
    assert out is None


@pytest.mark.asyncio
async def test_enabled_multi_topic_is_decomposed():
    # Gerçek primitive (heuristic): marker'lı çok-bileşen → is_decomposed
    out = await _decompose_for_research(
        "Türkiye ekonomisi ve faiz kararları son durum", None, enabled=True
    )
    assert out is not None
    assert out.is_decomposed
    assert len(out.sub_queries) == 2


@pytest.mark.asyncio
async def test_enabled_single_topic_not_decomposed():
    # Tek-konu → method=single → is_decomposed False (caller hint/event üretmez)
    out = await _decompose_for_research("Türkiye ekonomisi son durum analizi", None, enabled=True)
    assert out is not None
    assert not out.is_decomposed


@pytest.mark.asyncio
async def test_enabled_short_query_baseline():
    out = await _decompose_for_research("ekonomi haberleri", None, enabled=True)
    assert out is not None
    assert not out.is_decomposed


@pytest.mark.asyncio
async def test_decompose_exception_returns_none(monkeypatch):
    # decompose_query beklenmedik raise → graceful degrade → None (baseline akış)
    async def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.prompts.query_decomposition.decompose_query", _boom)
    out = await _decompose_for_research(
        "Türkiye ekonomisi ve faiz kararları son durum", None, enabled=True
    )
    assert out is None


# =============================================================================
# Settings registry
# =============================================================================


def test_settings_registry_has_flag_default_false():
    from app.modules.settings_admin.routes import SETTING_REGISTRY

    assert "research.query_decomposition_enabled" in SETTING_REGISTRY
    entry = SETTING_REGISTRY["research.query_decomposition_enabled"]
    assert entry["default"] is False
    assert entry["type"] == "bool"
    assert entry["group"] == "research"


# =============================================================================
# _decomposition_telemetry (#619 PR-5 — PII-suz payload)
# =============================================================================


def test_telemetry_payload_heuristic():
    r = DecompositionResult("orijinal sorgu", ["alt sorgu 1", "alt sorgu 2"], "heuristic")
    tele = _decomposition_telemetry(r, 42)
    assert tele["method"] == "heuristic"
    assert tele["sub_query_count"] == 2
    assert tele["llm_used"] is False
    assert tele["fallback_reason"] is None
    assert tele["duration_ms"] == 42


def test_telemetry_payload_llm_used():
    r = DecompositionResult("q", ["a", "b", "c"], "llm")
    tele = _decomposition_telemetry(r, 100)
    assert tele["method"] == "llm"
    assert tele["llm_used"] is True
    assert tele["sub_query_count"] == 3


def test_telemetry_payload_single_fallback():
    r = DecompositionResult("q", ["q"], "single", fallback_reason="too_short")
    tele = _decomposition_telemetry(r, 5)
    assert tele["method"] == "single"
    assert tele["llm_used"] is False
    assert tele["fallback_reason"] == "too_short"


def test_telemetry_payload_is_pii_free():
    # Payload yalnız metrik içerir; query/sub-query METNİ sızmamalı
    r = DecompositionResult("GIZLI kullanıcı sorgusu", ["GIZLI alt sorgu metni"], "heuristic")
    tele = _decomposition_telemetry(r, 10)
    assert "GIZLI" not in str(tele)
    assert set(tele.keys()) == {
        "method",
        "sub_query_count",
        "llm_used",
        "fallback_reason",
        "duration_ms",
    }
