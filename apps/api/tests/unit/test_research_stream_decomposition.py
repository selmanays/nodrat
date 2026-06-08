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
)

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
