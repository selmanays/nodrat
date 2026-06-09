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
    _parse_decomposition_allowlist,
    _resolve_decomposition_gate,
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
    tele = _decomposition_telemetry(r, 10, cohort="allowlist")
    assert "GIZLI" not in str(tele)
    # #619 PR-E: cohort eklendi (PII-suz etiket); user_id/email sızmaz.
    assert set(tele.keys()) == {
        "method",
        "sub_query_count",
        "llm_used",
        "fallback_reason",
        "duration_ms",
        "cohort",
    }
    assert tele["cohort"] == "allowlist"


# =============================================================================
# #619 PR-E — _parse_decomposition_allowlist (saf, DB-suz)
# =============================================================================

_U1 = "11111111-1111-1111-1111-111111111111"
_U2 = "22222222-2222-2222-2222-222222222222"


def test_parse_allowlist_empty_and_none():
    assert _parse_decomposition_allowlist("") == frozenset()
    assert _parse_decomposition_allowlist(None) == frozenset()
    assert _parse_decomposition_allowlist("   ") == frozenset()
    assert _parse_decomposition_allowlist(",, ,") == frozenset()


def test_parse_allowlist_valid_csv():
    out = _parse_decomposition_allowlist(f"{_U1},{_U2}")
    assert out == frozenset({_U1, _U2})


def test_parse_allowlist_whitespace_and_case_normalized():
    # Boşluk trim + UUID canonical lowercase
    out = _parse_decomposition_allowlist(f"  {_U1.upper()}  , {_U2} ")
    assert out == frozenset({_U1, _U2})  # upper → lowercase normalize


def test_parse_allowlist_invalid_tokens_ignored():
    # Geçersiz token sessizce atlanır, patlamaz; geçerli olan kalır
    out = _parse_decomposition_allowlist(f"not-a-uuid, {_U1}, 12345, ")
    assert out == frozenset({_U1})


# =============================================================================
# #619 PR-E — _resolve_decomposition_gate (saf; enabled + cohort)
# =============================================================================


def test_gate_global_off_empty_allowlist_baseline():
    # (1) Boş allowlist + global false → disabled, baseline (byte-identical)
    enabled, cohort = _resolve_decomposition_gate(
        global_enabled=False, allowlist_raw="", user_id=_U1
    )
    assert enabled is False
    assert cohort == "baseline"


def test_gate_global_on_global_cohort():
    # (2) global true → enabled, global cohort (allowlist yok sayılır)
    enabled, cohort = _resolve_decomposition_gate(
        global_enabled=True, allowlist_raw="", user_id=_U1
    )
    assert enabled is True
    assert cohort == "global"


def test_gate_user_in_allowlist_global_off():
    # (3) user.id allowlist'te + global false → enabled, allowlist cohort
    enabled, cohort = _resolve_decomposition_gate(
        global_enabled=False, allowlist_raw=f"{_U1},{_U2}", user_id=_U1
    )
    assert enabled is True
    assert cohort == "allowlist"


def test_gate_user_not_in_allowlist_global_off():
    # (4) user.id allowlist'te DEĞİL + global false → disabled, baseline
    enabled, cohort = _resolve_decomposition_gate(
        global_enabled=False, allowlist_raw=_U2, user_id=_U1
    )
    assert enabled is False
    assert cohort == "baseline"


def test_gate_global_on_overrides_allowlist():
    # global true, user allowlist'te DEĞİL → yine global (tüm trafik)
    enabled, cohort = _resolve_decomposition_gate(
        global_enabled=True, allowlist_raw=_U2, user_id=_U1
    )
    assert enabled is True
    assert cohort == "global"


def test_telemetry_cohort_default_and_values():
    r = DecompositionResult("q", ["a", "b"], "heuristic")
    assert _decomposition_telemetry(r, 1)["cohort"] == "global"  # default
    assert _decomposition_telemetry(r, 1, cohort="baseline")["cohort"] == "baseline"
    # cohort PII içermez (enum etiket)
    assert _decomposition_telemetry(r, 1, cohort="allowlist")["cohort"] == "allowlist"


# =============================================================================
# #619 PR-F observability — cohort → thinking_step (Alt A) + warning payload (Alt B)
# =============================================================================

_COHORT_ENUM = {"baseline", "allowlist", "global"}


def test_pr_f_cohort_in_thinking_step_metadata_contract():
    """#619 PR-F (Alt A) — cohort, query_decomposition thinking_step metadata'sına
    aktarılan key-setinde bulunur (`_log_step(..., method=, sub_query_count=, llm_used=,
    fallback_reason=, cohort=)` → Message.thinking_steps JSONB). Mevcut metadata korunur.
    """
    r = DecompositionResult("q", ["a", "b"], "heuristic")
    tele = _decomposition_telemetry(r, 42, cohort="allowlist")
    thinking_step_meta = {"method", "sub_query_count", "llm_used", "fallback_reason", "cohort"}
    assert thinking_step_meta <= set(tele), "cohort + mevcut metadata thinking_step'e aktarılabilir"
    assert tele["cohort"] == "allowlist"
    # Mevcut alanlar korunur (PR-5 metadata):
    assert tele["method"] == "heuristic"
    assert tele["sub_query_count"] == 2
    assert tele["llm_used"] is False
    assert tele["fallback_reason"] is None


def test_pr_f_cohort_values_are_enum():
    """#619 PR-F — thinking_step/log cohort'u yalnız {baseline, allowlist, global}."""
    r = DecompositionResult("q", ["a", "b"], "heuristic")
    for c in _COHORT_ENUM:
        assert _decomposition_telemetry(r, 1, cohort=c)["cohort"] == c


def test_pr_f_warning_payload_no_pii():
    """#619 PR-F (Alt B) — warning ile loglanan payload PII İÇERMEZ (user_id/email/raw query yok)."""
    r = DecompositionResult("GIZLI kullanıcı sorgusu", ["GIZLI alt sorgu metni"], "heuristic")
    tele = _decomposition_telemetry(r, 10, cohort="allowlist")
    blob = str(tele)
    assert "GIZLI" not in blob  # raw query / sub-query metni yok
    assert "user_id" not in blob and "email" not in blob and "@" not in blob
    # yalnız metrik anahtarlar (PII alanı yok)
    assert set(tele) == {
        "method",
        "sub_query_count",
        "llm_used",
        "fallback_reason",
        "duration_ms",
        "cohort",
    }
