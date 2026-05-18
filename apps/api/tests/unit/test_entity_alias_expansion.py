"""#927 Faz-C — Wikidata-alias entity genişletme (flag-OFF spike).

Kapsam:
  - WikipediaProvider.wikidata_aliases (parse/dedupe/cap/graceful/cache)
  - QueryPlan.entity_synonyms + planner cache round-trip + legacy-miss
  - _attach_entity_synonyms (flag-OFF no-op / flag-ON / idempotent / boş CE)
  - retrieval_cache._cache_key (boş synonyms → BİREBİR key = no-op kanıtı)

Network httpx.MockTransport ile mock'lanır; Redis cache patch'lenir; flag
+ DB + provider unittest.mock ile izole edilir (gerçek DB/HTTP YOK).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.providers.wikipedia import WikipediaProvider
from app.prompts.query_planner import (
    QueryPlan,
    _attach_entity_synonyms,
    _plan_from_cache_dict,
    _plan_to_cache_dict,
)
from app.core.retrieval_cache import _cache_key


# =============================================================================
# Helpers
# =============================================================================


def _mk_plan(
    critical_entities: list[str],
    entity_synonyms: dict[str, list[str]] | None = None,
) -> QueryPlan:
    return QueryPlan(
        intent="current_content_generation",
        topic_query="t",
        mode="current",
        timeframes=[],
        output_type="x_post",
        tone=None,
        constraints=[],
        needs_sources=True,
        minimum_evidence_per_period=1,
        critical_entities=critical_entities,
        entity_synonyms=entity_synonyms if entity_synonyms is not None else {},
    )


class _FakeSessionCM:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def _fake_get_session_factory():
    """get_session_factory() → factory; factory() → async-CM."""
    return lambda: _FakeSessionCM()


def _wikidata_handler(
    *, search_hit: bool = True, labels: dict, aliases: dict, qid: str = "Q30",
):
    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "wbsearchentities" in url:
            if not search_hit:
                return httpx.Response(200, json={"search": []})
            return httpx.Response(
                200, json={"search": [{"id": qid, "label": "x"}]}
            )
        if "wbgetentities" in url:
            return httpx.Response(
                200,
                json={"entities": {qid: {"labels": labels, "aliases": aliases}}},
            )
        return httpx.Response(404)

    return handler


_PATCH_CACHE = (
    patch("app.providers.wikipedia._cache_get", AsyncMock(return_value=None)),
    patch("app.providers.wikipedia._cache_set", AsyncMock()),
)


# =============================================================================
# wikidata_aliases — parse / dedupe / exclude-entity / cap
# =============================================================================


@pytest.mark.asyncio
async def test_wikidata_aliases_parse_dedupe_exclude_entity():
    """labels{tr,en}+aliases{tr,en} → flat list; entity'nin kendisi +
    case-insensitive dupe çıkar (#863 zinciri reuse)."""
    handler = _wikidata_handler(
        labels={
            "tr": {"value": "Amerika Birleşik Devletleri"},
            "en": {"value": "United States"},
        },
        aliases={
            "tr": [{"value": "ABD"}, {"value": "Amerika"}, {"value": "abd"}],
            "en": [{"value": "USA"}, {"value": "US"}],
        },
    )
    provider = WikipediaProvider(transport=httpx.MockTransport(handler))
    with _PATCH_CACHE[0], _PATCH_CACHE[1]:
        out = await provider.wikidata_aliases("ABD", lang="tr")

    # "ABD" + "abd" (entity casefold) düşer; sıra korunur
    assert "ABD" not in out and "abd" not in out
    assert "Amerika Birleşik Devletleri" in out
    assert "United States" in out
    assert "Amerika" in out
    assert "USA" in out and "US" in out
    assert len(out) == len(set(o.casefold() for o in out))  # dupe yok


@pytest.mark.asyncio
async def test_wikidata_aliases_cap_limits_output():
    handler = _wikidata_handler(
        labels={"tr": {"value": "L1"}, "en": {"value": "L2"}},
        aliases={"tr": [{"value": f"a{i}"} for i in range(20)], "en": []},
    )
    provider = WikipediaProvider(transport=httpx.MockTransport(handler))
    with _PATCH_CACHE[0], _PATCH_CACHE[1]:
        out = await provider.wikidata_aliases("zzz", lang="tr", cap=5)
    assert len(out) == 5


@pytest.mark.asyncio
async def test_wikidata_aliases_empty_search_returns_empty():
    """Niş/yeni entity Wikidata'da yok → [] (retrieval no-op → regresyon
    YOK)."""
    handler = _wikidata_handler(
        search_hit=False, labels={}, aliases={},
    )
    provider = WikipediaProvider(transport=httpx.MockTransport(handler))
    with _PATCH_CACHE[0], _PATCH_CACHE[1]:
        out = await provider.wikidata_aliases("asdkjhqwe", lang="tr")
    assert out == []


@pytest.mark.asyncio
async def test_wikidata_aliases_http_error_graceful():
    """HTTP 5xx → [] (asla raise; #863 fail-silent deseni)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = WikipediaProvider(transport=httpx.MockTransport(handler))
    with _PATCH_CACHE[0], _PATCH_CACHE[1]:
        out = await provider.wikidata_aliases("Trump", lang="tr")
    assert out == []


@pytest.mark.asyncio
async def test_wikidata_aliases_cache_hit_skips_http():
    """Redis cache hit → HTTP yok (latency amorti)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("cache hit → HTTP çağrılmamalı")

    provider = WikipediaProvider(transport=httpx.MockTransport(handler))
    with (
        patch(
            "app.providers.wikipedia._cache_get",
            AsyncMock(return_value=["Amerika", "USA"]),
        ),
        patch("app.providers.wikipedia._cache_set", AsyncMock()),
    ):
        out = await provider.wikidata_aliases("ABD", lang="tr")
    assert out == ["Amerika", "USA"]


# =============================================================================
# QueryPlan.entity_synonyms + planner cache round-trip
# =============================================================================


def test_queryplan_entity_synonyms_default_empty():
    assert _mk_plan(["abd"]).entity_synonyms == {}


def test_plan_cache_dict_roundtrip_entity_synonyms():
    plan = _mk_plan(["abd"], {"abd": ["amerika", "amerika birleşik devletleri"]})
    d = _plan_to_cache_dict(plan)
    assert d["entity_synonyms"] == {
        "abd": ["amerika", "amerika birleşik devletleri"]
    }
    back = _plan_from_cache_dict(d)
    assert back is not None
    assert back.entity_synonyms == {
        "abd": ["amerika", "amerika birleşik devletleri"]
    }


def test_plan_from_cache_dict_legacy_missing_key():
    """fix-öncesi (24h TTL) cache kaydı bu key'i taşımaz → {} (graceful;
    flag ON ise plan_query canlı çözer)."""
    d = _plan_to_cache_dict(_mk_plan(["abd"]))
    d.pop("entity_synonyms", None)
    back = _plan_from_cache_dict(d)
    assert back is not None
    assert back.entity_synonyms == {}


# =============================================================================
# _attach_entity_synonyms — flag gate / idempotent / boş-CE
# =============================================================================


@pytest.mark.asyncio
async def test_attach_entity_synonyms_flag_off_noop():
    """flag OFF → entity_synonyms {} kalır (retrieval tam no-op)."""
    plan = _mk_plan(["abd", "çin"])
    with (
        patch("app.core.db.get_session_factory", _fake_get_session_factory),
        patch(
            "app.core.settings_store.settings_store.get_bool",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.providers.wikipedia.get_wikipedia_provider",
            AsyncMock(side_effect=AssertionError("flag OFF → provider yok")),
        ),
    ):
        await _attach_entity_synonyms(plan)
    assert plan.entity_synonyms == {}


@pytest.mark.asyncio
async def test_attach_entity_synonyms_flag_on_populates():
    """flag ON → bounded (≤2) entity için Wikidata eş-adları doldurulur."""
    plan = _mk_plan(["abd", "çin", "üçüncü"])

    fake_provider = AsyncMock()
    fake_provider.wikidata_aliases = AsyncMock(
        side_effect=lambda ent, lang="tr": {
            "abd": ["Amerika", "USA"],
            "çin": ["Çin Halk Cumhuriyeti"],
        }.get(ent, [])
    )
    with (
        patch("app.core.db.get_session_factory", _fake_get_session_factory),
        patch(
            "app.core.settings_store.settings_store.get_bool",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.providers.wikipedia.get_wikipedia_provider",
            AsyncMock(return_value=fake_provider),
        ),
    ):
        await _attach_entity_synonyms(plan)

    assert plan.entity_synonyms == {
        "abd": ["Amerika", "USA"],
        "çin": ["Çin Halk Cumhuriyeti"],
    }
    # bounded: 3. entity ("üçüncü") çözülmedi
    assert "üçüncü" not in plan.entity_synonyms
    assert fake_provider.wikidata_aliases.await_count == 2


@pytest.mark.asyncio
async def test_attach_entity_synonyms_idempotent_skips_refetch():
    """Zaten dolu (yeni cache hydrate) → tekrar Wikidata çağrısı YOK."""
    plan = _mk_plan(["abd"], {"abd": ["Amerika"]})
    with (
        patch("app.core.db.get_session_factory", _fake_get_session_factory),
        patch(
            "app.core.settings_store.settings_store.get_bool",
            AsyncMock(side_effect=AssertionError("idempotent → flag okunmamalı")),
        ),
    ):
        await _attach_entity_synonyms(plan)
    assert plan.entity_synonyms == {"abd": ["Amerika"]}


@pytest.mark.asyncio
async def test_attach_entity_synonyms_no_critical_entities_noop():
    plan = _mk_plan([])
    with patch(
        "app.core.settings_store.settings_store.get_bool",
        AsyncMock(side_effect=AssertionError("CE yok → flag okunmamalı")),
    ):
        await _attach_entity_synonyms(plan)
    assert plan.entity_synonyms == {}


# =============================================================================
# retrieval_cache._cache_key — boş synonyms BİREBİR key (no-op kanıtı)
# =============================================================================


def _ck(entity_synonyms):
    return _cache_key(
        norm_query="abd hürmüz",
        top_k=15,
        candidate_pool=60,
        since_hours=2160,
        timeframe_from=None,
        timeframe_to=None,
        critical_entities=["abd", "hürmüz"],
        entity_synonyms=entity_synonyms,
    )


def test_cache_key_empty_synonyms_identical_to_baseline():
    """flag OFF (None / {} / boş-değerli) → key DEĞİŞMEZ → eski cache
    kayıtlarıyla backward-compat + flag-OFF==baseline (no-op kanıtı)."""
    base = _ck(None)
    assert _ck({}) == base
    assert _ck({"abd": []}) == base


def test_cache_key_populated_synonyms_differs():
    """flag ON → ayrı key → flag-OFF kayıtlarıyla collision YOK
    (benchmark flag-ON gerçek SQL'i ölçer)."""
    base = _ck(None)
    assert _ck({"abd": ["amerika"]}) != base
    # sıralama-bağımsız (deterministik key)
    assert _ck({"abd": ["amerika", "usa"]}) == _ck({"abd": ["usa", "amerika"]})
