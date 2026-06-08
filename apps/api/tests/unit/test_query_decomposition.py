"""Unit — query decomposition primitive (#619 PR-2).

Saf primitive testleri: heuristic split, LLM-fallback (mock), timeout/fail/
invalid-JSON → tek-query baseline, dedup, cap, parse-never-raise.

DB-suz, provider mock'lu. Production wiring YOK (PR-3) — bu testler yalnız
``app/prompts/query_decomposition.py`` saf davranışını sabitler.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.prompts.query_decomposition import (
    MAX_SUB_QUERIES,
    DecompositionResult,
    decompose_heuristic,
    decompose_query,
    decompose_query_llm,
    parse_decompose_response,
    render_decompose_payload,
)


def _provider(text: str):
    """generate_text → SimpleNamespace(text=...) döndüren mock provider."""
    return SimpleNamespace(generate_text=AsyncMock(return_value=SimpleNamespace(text=text)))


# =============================================================================
# Heuristic split (deterministik, LLM-suz)
# =============================================================================


def test_heuristic_splits_multi_topic_ve():
    out = decompose_heuristic("Türkiye ekonomisi ve faiz kararları son durum")
    assert len(out) == 2
    assert "Türkiye ekonomisi" in out[0]
    assert "faiz kararları" in out[1]


def test_heuristic_splits_ayrica_marker():
    out = decompose_heuristic("deprem bölgesi yardımları ayrıca konut projesi gelişmeleri")
    assert len(out) == 2


def test_heuristic_single_topic_returns_empty():
    assert decompose_heuristic("Türkiye ekonomisi son durum") == []


def test_heuristic_short_parts_rejected():
    # "Ahmet ve Mehmet" → her parça 1 kelime → elenir → bölme yok (agresif değil)
    assert decompose_heuristic("Ahmet ve Mehmet") == []


def test_heuristic_caps_at_max():
    q = (
        "ekonomi haberleri ve faiz kararları ve döviz kuru ve borsa endeksi "
        "ve altın fiyatları ve petrol piyasası gelişmeleri"
    )
    out = decompose_heuristic(q)
    assert len(out) == MAX_SUB_QUERIES


def test_heuristic_dedup_repeated_subquery():
    out = decompose_heuristic("faiz kararları ve faiz kararları ve döviz kuru hareketi")
    # "faiz kararları" tekrarı dedup → faiz + döviz = 2
    assert len(out) == 2


def test_heuristic_empty_and_whitespace():
    assert decompose_heuristic("") == []
    assert decompose_heuristic("   ") == []


def test_heuristic_no_marker_returns_empty():
    assert decompose_heuristic("son dakika ekonomi gelişmeleri analizi") == []


# =============================================================================
# parse_decompose_response — ASLA raise etmez
# =============================================================================


def test_parse_json_array():
    out = parse_decompose_response(
        '["faiz kararları", "döviz kuru gelişmeleri"]', original="çok bileşenli sorgu metni"
    )
    assert out == ["faiz kararları", "döviz kuru gelişmeleri"]


def test_parse_markdown_fence():
    raw = '```json\n["ekonomi haberleri", "siyaset gündemi"]\n```'
    out = parse_decompose_response(raw, original="çok bileşenli sorgu metni")
    assert out == ["ekonomi haberleri", "siyaset gündemi"]


def test_parse_non_json_line_fallback():
    raw = "- faiz kararları detayı\n- döviz kuru gelişmeleri"
    out = parse_decompose_response(raw, original="çok bileşenli sorgu metni")
    assert out == ["faiz kararları detayı", "döviz kuru gelişmeleri"]


def test_parse_object_not_list_returns_empty():
    # JSON ama dizi değil → aday yok → []
    assert parse_decompose_response('{"a": 1}', original="çok bileşenli sorgu") == []


def test_parse_caps_and_dedup():
    raw = '["a haberleri", "a haberleri", "b kuru", "c borsa", "d altın", "e petrol"]'
    out = parse_decompose_response(raw, original="çok bileşenli sorgu metni")
    assert len(out) == MAX_SUB_QUERIES  # dedup sonrası cap


def test_parse_drops_subquery_equal_to_original():
    out = parse_decompose_response(
        '["faiz kararları haberi", "ekonomi gündemi özet"]',
        original="faiz kararları haberi",
    )
    # orijinale eşit alt-sorgu elenir
    assert out == ["ekonomi gündemi özet"]


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "{{{", "[1, 2, 3]", '{"x": 1}', "ölçüsüz metin \x00 burada", "null"],
)
def test_parse_never_raises_returns_list(bad):
    out = parse_decompose_response(bad, original="bir iki üç dört beş")
    assert isinstance(out, list)


# =============================================================================
# decompose_query_llm — fail/timeout → [] (graceful degrade)
# =============================================================================


@pytest.mark.asyncio
async def test_llm_parses_provider_json():
    p = _provider('["faiz kararı detayları", "döviz kuru gelişmeleri"]')
    out = await decompose_query_llm(p, "uzun çok bileşenli sorgu metni")
    assert out == ["faiz kararı detayları", "döviz kuru gelişmeleri"]


@pytest.mark.asyncio
async def test_llm_provider_exception_returns_empty():
    p = SimpleNamespace(generate_text=AsyncMock(side_effect=RuntimeError("boom")))
    assert await decompose_query_llm(p, "sorgu metni burada") == []


@pytest.mark.asyncio
async def test_llm_timeout_returns_empty():
    p = SimpleNamespace(generate_text=AsyncMock(side_effect=TimeoutError()))
    assert await decompose_query_llm(p, "sorgu metni burada") == []


@pytest.mark.asyncio
async def test_llm_empty_query_skips_call():
    p = _provider('["a haberleri", "b kuru"]')
    assert await decompose_query_llm(p, "") == []
    p.generate_text.assert_not_awaited()


# =============================================================================
# decompose_query — orkestrasyon (heuristic → LLM → tek-query baseline)
# =============================================================================


@pytest.mark.asyncio
async def test_query_empty_is_single_empty():
    r = await decompose_query("")
    assert r.method == "single"
    assert r.sub_queries == []
    assert not r.is_decomposed


@pytest.mark.asyncio
async def test_query_short_is_single_baseline():
    r = await decompose_query("ekonomi haberleri")  # 2 kelime < eşik
    assert r.method == "single"
    assert r.sub_queries == ["ekonomi haberleri"]


@pytest.mark.asyncio
async def test_query_heuristic_path():
    r = await decompose_query("Türkiye ekonomisi ve faiz kararları son durum")
    assert r.method == "heuristic"
    assert len(r.sub_queries) == 2
    assert r.is_decomposed


@pytest.mark.asyncio
async def test_query_llm_disabled_does_not_call_provider():
    p = _provider('["a haberleri", "b kuru"]')
    r = await decompose_query(
        "son ekonomik gelişmeler hakkında kapsamlı analiz",
        provider=p,
        llm_enabled=False,
    )
    assert r.method == "single"
    p.generate_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_llm_path_when_heuristic_empty():
    p = _provider('["faiz kararı detayları", "döviz kuru hareketleri"]')
    r = await decompose_query(
        "son ekonomik gelişmeler hakkında kapsamlı analiz",
        provider=p,
        llm_enabled=True,
    )
    assert r.method == "llm"
    assert len(r.sub_queries) == 2
    p.generate_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_llm_fail_falls_back_to_single():
    p = SimpleNamespace(generate_text=AsyncMock(side_effect=RuntimeError("boom")))
    q = "son ekonomik gelişmeler hakkında kapsamlı analiz"
    r = await decompose_query(q, provider=p, llm_enabled=True)
    assert r.method == "single"
    assert r.sub_queries == [q]


@pytest.mark.asyncio
async def test_query_provider_none_with_llm_enabled_is_single():
    r = await decompose_query(
        "son ekonomik gelişmeler hakkında kapsamlı analiz",
        provider=None,
        llm_enabled=True,
    )
    assert r.method == "single"


@pytest.mark.asyncio
async def test_query_heuristic_precedes_llm():
    # Marker'lı sorgu → heuristic tutar, LLM HİÇ çağrılmaz (provider verilse bile)
    p = _provider('["llm should not be used", "ignored"]')
    r = await decompose_query(
        "ekonomi haberleri ve siyaset gündemi son durum",
        provider=p,
        llm_enabled=True,
    )
    assert r.method == "heuristic"
    p.generate_text.assert_not_awaited()


# =============================================================================
# render + dataclass
# =============================================================================


def test_render_payload_contains_query():
    assert "faiz haberleri" in render_decompose_payload("faiz haberleri")


def test_result_is_decomposed_property():
    assert DecompositionResult("q", ["a haberi", "b kuru"], "heuristic").is_decomposed
    assert not DecompositionResult("q", ["q"], "single").is_decomposed
    assert not DecompositionResult("q", ["tek alt"], "heuristic").is_decomposed


def test_result_fallback_reason_defaults_none():
    # PR-5: yeni alan default None → PR-2 pozisyonel constructor geriye-uyumlu
    assert DecompositionResult("q", ["a", "b"], "heuristic").fallback_reason is None


# =============================================================================
# fallback_reason (#619 PR-5 telemetry — coarse)
# =============================================================================


@pytest.mark.asyncio
async def test_fallback_reason_empty_query():
    r = await decompose_query("")
    assert r.method == "single"
    assert r.fallback_reason == "empty_query"


@pytest.mark.asyncio
async def test_fallback_reason_too_short():
    r = await decompose_query("ekonomi haberleri")  # 2 kelime < eşik
    assert r.fallback_reason == "too_short"


@pytest.mark.asyncio
async def test_fallback_reason_heuristic_success_is_none():
    r = await decompose_query("Türkiye ekonomisi ve faiz kararları son durum")
    assert r.method == "heuristic"
    assert r.fallback_reason is None


@pytest.mark.asyncio
async def test_fallback_reason_llm_disabled():
    # Uzun marker'sız sorgu + LLM kapalı → heuristic boş, LLM denenmedi
    r = await decompose_query("son ekonomik gelişmeler hakkında kapsamlı analiz", llm_enabled=False)
    assert r.method == "single"
    assert r.fallback_reason == "llm_disabled"


@pytest.mark.asyncio
async def test_fallback_reason_llm_disabled_when_provider_none():
    r = await decompose_query(
        "son ekonomik gelişmeler hakkında kapsamlı analiz",
        provider=None,
        llm_enabled=True,
    )
    assert r.fallback_reason == "llm_disabled"


@pytest.mark.asyncio
async def test_fallback_reason_llm_no_result():
    # LLM denendi ama yetersiz (<2 alt-sorgu) → llm_no_result
    p = _provider('["tek alt sorgu kaldı"]')
    r = await decompose_query(
        "son ekonomik gelişmeler hakkında kapsamlı analiz",
        provider=p,
        llm_enabled=True,
    )
    assert r.method == "single"
    assert r.fallback_reason == "llm_no_result"


@pytest.mark.asyncio
async def test_fallback_reason_llm_success_is_none():
    p = _provider('["faiz kararı detayları", "döviz kuru hareketleri"]')
    r = await decompose_query(
        "son ekonomik gelişmeler hakkında kapsamlı analiz",
        provider=p,
        llm_enabled=True,
    )
    assert r.method == "llm"
    assert r.fallback_reason is None
