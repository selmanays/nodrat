"""Unit tests for Wikipedia provider (#811 Faz 2 2E).

Network çağrıları httpx MockTransport ile mock'lanır. Redis cache test'te
mock_redis fixture via monkeypatch ile devre dışı (cache hit/miss isolated test).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.providers.wikipedia import (
    _WIKI_EXTRACT_CAP,
    DEFAULT_LANG_PRIORITY,
    WIKIDATA_FACTUAL_PROPS,
    WikiArticle,
    WikipediaProvider,
    _article_from_dict,
    _article_to_dict,
    _cache_key,
)

# =============================================================================
# Cache key tests
# =============================================================================


def test_cache_key_deterministic_per_day():
    """Aynı query+lang+kind+gün → aynı key."""
    k1 = _cache_key("Trump", "tr", "search")
    k2 = _cache_key("Trump", "tr", "search")
    assert k1 == k2
    # #973 — v1→v2 BİLİNÇLİ bump: _fetch_summary lead→tam-makale; eski
    # lead-only Redis girdileri 24h stale servis etmesin (deploy anında
    # geçerli; planner_cache #947 PROMPT_VERSION-in-key dersi).
    assert k1.startswith("wiki:v2:search:tr:")


def test_cache_key_different_kinds():
    """search vs wikidata farklı key namespace."""
    k1 = _cache_key("Trump", "tr", "search")
    k2 = _cache_key("Trump", "tr", "wikidata")
    assert k1 != k2


def test_cache_key_case_insensitive():
    """Query lower-cased — 'Trump' = 'trump'."""
    k1 = _cache_key("Trump", "tr", "search")
    k2 = _cache_key("trump", "tr", "search")
    assert k1 == k2


# =============================================================================
# WikiArticle serialization
# =============================================================================


def test_article_roundtrip():
    a = WikiArticle(
        title="Türkiye",
        summary="Anadolu ve Trakya'da kurulu ülke.",
        url="https://tr.wikipedia.org/wiki/T%C3%BCrkiye",
        page_id=3927,
        lang="tr",
    )
    d = _article_to_dict(a)
    b = _article_from_dict(d)
    assert b.title == a.title
    assert b.summary == a.summary
    assert b.url == a.url
    assert b.page_id == a.page_id
    assert b.license == "CC BY-SA 4.0"


def test_article_default_license():
    """License default CC BY-SA 4.0."""
    a = WikiArticle(title="x", summary="y", url="z", page_id=1)
    assert a.license == "CC BY-SA 4.0"


# =============================================================================
# Wikipedia search (mocked HTTP)
# =============================================================================


def _mock_search_response(titles: list[str]) -> dict:
    """Wikipedia query+list=search API response format (#824 — relevance-ranked)."""
    return {
        "query": {
            "search": [
                {"title": t, "snippet": f"snippet-{t}", "pageid": i}
                for i, t in enumerate(titles, start=1)
            ],
        },
    }


def _mock_extracts_response(title: str, extract: str = "Test özet") -> dict:
    """#973 — action=query&prop=extracts&explaintext format (tam makale)."""
    return {
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "title": title,
                    "extract": extract,
                },
            },
        },
    }


@pytest.mark.asyncio
async def test_search_returns_articles_with_summary():
    """opensearch → titles → summary fetch (mocked)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if "list=search" in str(request.url):
            return httpx.Response(
                200,
                json=_mock_search_response(["Çin"]),
            )
        if "prop=extracts" in str(request.url):
            return httpx.Response(
                200,
                json=_mock_extracts_response("Çin", "Çin Halk Cumhuriyeti, Asya'da bir ülkedir."),
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    provider = WikipediaProvider(transport=transport)

    # Cache bypass — _cache_get None döner
    with (
        patch("app.providers.wikipedia._cache_get", AsyncMock(return_value=None)),
        patch("app.providers.wikipedia._cache_set", AsyncMock()),
    ):
        results = await provider.search("Çin nüfusu", lang="tr")

    # En azından 1 sonuç döndü ve fields doğru
    assert len(results) >= 1
    assert results[0].title == "Çin"
    assert "Çin Halk Cumhuriyeti" in results[0].summary
    assert results[0].license == "CC BY-SA 4.0"


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty():
    provider = WikipediaProvider()
    result = await provider.search("", lang="tr")
    assert result == []


@pytest.mark.asyncio
async def test_search_lang_fallback_tr_to_en():
    """tr boş → en denenir."""
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "tr.wikipedia.org" in url and "list=search" in url:
            calls.append("tr_search")
            return httpx.Response(200, json=_mock_search_response([]))
        if "en.wikipedia.org" in url and "list=search" in url:
            calls.append("en_search")
            return httpx.Response(200, json=_mock_search_response(["China"]))
        if "prop=extracts" in url:
            return httpx.Response(
                200,
                json=_mock_extracts_response(
                    "China", "China, a country in Asia with a long history."
                ),
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    provider = WikipediaProvider(lang_priority=["tr", "en"], transport=transport)

    with (
        patch("app.providers.wikipedia._cache_get", AsyncMock(return_value=None)),
        patch("app.providers.wikipedia._cache_set", AsyncMock()),
    ):
        results = await provider.search("xyz", lang=None)

    assert "tr_search" in calls
    assert "en_search" in calls
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_cache_hit_skips_http():
    """Cache hit → HTTP çağrısı yapılmaz."""
    cached_articles = [
        _article_to_dict(
            WikiArticle(
                title="Cached",
                summary="cached summary",
                url="https://tr.wikipedia.org/wiki/Cached",
                page_id=99,
                lang="tr",
            )
        ),
    ]

    # HTTP istek gelirse handler raise eder → cache hit'te ulaşılmaması beklenir
    http_called = []

    async def handler(request: httpx.Request) -> httpx.Response:
        http_called.append(str(request.url))
        return httpx.Response(500, json={"error": "should not be called"})

    transport = httpx.MockTransport(handler)
    provider = WikipediaProvider(transport=transport)

    with (
        patch(
            "app.providers.wikipedia._cache_get",
            AsyncMock(return_value=cached_articles),
        ),
        patch("app.providers.wikipedia._cache_set", AsyncMock()) as mock_set,
    ):
        results = await provider.search("Cached query", lang="tr")

    assert len(results) == 1
    assert results[0].title == "Cached"
    # HTTP transport hiç çağrılmadı
    assert http_called == []
    # Cache set'i de çağırmadık (hit'te yeniden write yok)
    mock_set.assert_not_called()


# =============================================================================
# #973 — tam makale extract (lead-only DEĞİL)
# =============================================================================


@pytest.mark.asyncio
async def test_fetch_full_article_not_lead_only():
    """#973 — prod conv b66bf1c2: kanonik sayfa SEÇİLİYOR ama cevap
    lead'de değil gövdede ("Türkiye'de TRT 1 / 14 Nisan 2007"). Provider
    artık tam makaleyi çekmeli — lead'i AŞAN gövde-içi olgu görünür."""
    # lead + gövde; gövdede ancak full-extract ile görünecek olgu
    full = (
        "Yıldız Geçidi SG-1, 1997 yapımı bilimkurgu dizisidir.\n\n"
        "Yayın\n\nTürkiye'de ilk bölümü TRT 1 tarafından 14 Nisan 2007 "
        "tarihinde saat 23:35'te yayınlanmıştır."
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "list=search" in u:
            return httpx.Response(200, json=_mock_search_response(["Yıldız Geçidi SG-1"]))
        if "prop=extracts" in u:
            # explaintext + redirects param'ları geçiyor mu (kontrat)
            assert "explaintext=1" in u and "redirects=1" in u
            return httpx.Response(200, json=_mock_extracts_response("Yıldız Geçidi SG-1", full))
        return httpx.Response(404)

    provider = WikipediaProvider(transport=httpx.MockTransport(handler))
    with (
        patch("app.providers.wikipedia._cache_get", AsyncMock(return_value=None)),
        patch("app.providers.wikipedia._cache_set", AsyncMock()),
    ):
        res = await provider.search("Yıldız Geçidi SG-1", lang="tr")

    assert len(res) == 1
    s = res[0].summary
    # gövde-içi olgu (lead-only olsa GÖRÜNMEZDİ) artık metinde:
    assert "TRT 1" in s and "14 Nisan 2007" in s
    # url başlıktan kuruldu (REST content_urls yok)
    assert res[0].url == "https://tr.wikipedia.org/wiki/Y%C4%B1ld%C4%B1z_Ge%C3%A7idi_SG-1"


@pytest.mark.asyncio
async def test_extract_cap_truncates_long_article():
    """#973 — dev makale (50K+) context/maliyet patlatmasın: cap'te
    paragraf sınırında kesilir + '[…]' işareti."""
    long_extract = "paragraf bir.\n" * 5000  # _WIKI_EXTRACT_CAP'i aşar

    async def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "list=search" in u:
            return httpx.Response(200, json=_mock_search_response(["X"]))
        if "prop=extracts" in u:
            return httpx.Response(200, json=_mock_extracts_response("X", long_extract))
        return httpx.Response(404)

    provider = WikipediaProvider(transport=httpx.MockTransport(handler))
    with (
        patch("app.providers.wikipedia._cache_get", AsyncMock(return_value=None)),
        patch("app.providers.wikipedia._cache_set", AsyncMock()),
    ):
        res = await provider.search("X", lang="tr")

    assert len(res) == 1
    # cap + kısa kuyruk işareti; ham uzunluğun çok altında
    assert len(res[0].summary) <= _WIKI_EXTRACT_CAP + 8
    assert res[0].summary.endswith("[…]")
    assert len(long_extract) > _WIKI_EXTRACT_CAP  # gerçekten aşıyordu


@pytest.mark.asyncio
async def test_extract_missing_page_returns_none():
    """#973 — sayfa yoksa (pages '-1' / extract boş) → None; search
    çökmeden boş döner (geri uyum)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "list=search" in u:
            return httpx.Response(200, json=_mock_search_response(["Yok"]))
        if "prop=extracts" in u:
            return httpx.Response(
                200, json={"query": {"pages": {"-1": {"title": "Yok", "missing": ""}}}}
            )
        return httpx.Response(404)

    provider = WikipediaProvider(transport=httpx.MockTransport(handler))
    with (
        patch("app.providers.wikipedia._cache_get", AsyncMock(return_value=None)),
        patch("app.providers.wikipedia._cache_set", AsyncMock()),
    ):
        res = await provider.search("Yok", lang="tr")

    assert res == []  # missing → article None → sonuç boş (çökme yok)


# =============================================================================
# Wikidata SPARQL
# =============================================================================


@pytest.mark.asyncio
async def test_wikidata_factual_returns_properties():
    """#863 — wbsearchentities → Q-ID → wbgetentities (Action API, SPARQL
    DEĞİL) → properties. SPARQL endpoint flaky (400/502) olduğu için
    güvenilir Action API'ye geçildi."""

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "query.wikidata.org" in url:
            raise AssertionError("SPARQL artık kullanılmamalı (#863)")
        if "wbsearchentities" in url:
            return httpx.Response(
                200,
                json={
                    "search": [{"id": "Q22686", "label": "Donald Trump"}],
                },
            )
        if "wbgetentities" in url:
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q22686": {
                            "labels": {"en": {"value": "Donald Trump"}},
                            "claims": {
                                "P569": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {
                                                    "time": "+1946-06-14T00:00:00Z",
                                                },
                                            },
                                        },
                                    }
                                ],
                            },
                        },
                    },
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    provider = WikipediaProvider(transport=transport)

    with (
        patch("app.providers.wikipedia._cache_get", AsyncMock(return_value=None)),
        patch("app.providers.wikipedia._cache_set", AsyncMock()),
    ):
        fact = await provider.wikidata_factual("Trump", lang="tr")

    assert fact is not None
    assert fact.qid == "Q22686"
    assert fact.label == "Donald Trump"
    # "+1946-06-14T00:00:00Z" → "1946-06-14T00:00:00Z" (lstrip '+')
    assert fact.properties.get("P569", "").startswith("1946-06-14")


@pytest.mark.asyncio
async def test_wikidata_factual_with_explicit_qid_skips_search():
    """#863 — caller sitelink-QID geçince fuzzy wbsearchentities ATLANIR
    (deterministik; niteleyici-hassasiyet yok)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "wbsearchentities" in url:
            raise AssertionError("qid verildi → entity araması yapılmamalı")
        if "wbgetentities" in url:
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q431432": {
                            "labels": {"en": {"value": "Robert C. Cooper"}},
                            "claims": {
                                "P569": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {
                                                    "time": "+1968-10-14T00:00:00Z",
                                                }
                                            }
                                        },
                                    }
                                ],
                            },
                        },
                    },
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    provider = WikipediaProvider(transport=transport)
    with (
        patch("app.providers.wikipedia._cache_get", AsyncMock(return_value=None)),
        patch("app.providers.wikipedia._cache_set", AsyncMock()),
    ):
        fact = await provider.wikidata_factual(
            "Robert C. Cooper doğum tarihi",
            lang="tr",
            qid="Q431432",
        )
    assert fact is not None and fact.qid == "Q431432"
    assert fact.properties.get("P569", "").startswith("1968-10-14")


@pytest.mark.asyncio
async def test_wikidata_qid_for_title_sitelink():
    """#863 — Wikipedia sayfa başlığı → wikibase_item (deterministik QID)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if "pageprops" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "123": {
                                "title": "Robert C. Cooper",
                                "pageprops": {"wikibase_item": "Q431432"},
                            }
                        }
                    },
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    provider = WikipediaProvider(transport=transport)
    qid = await provider.wikidata_qid_for_title("Robert C. Cooper", "tr")
    assert qid == "Q431432"


@pytest.mark.asyncio
async def test_wikidata_no_results_returns_none():
    async def handler(request: httpx.Request) -> httpx.Response:
        if "wbsearchentities" in str(request.url):
            return httpx.Response(200, json={"search": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    provider = WikipediaProvider(transport=transport)

    with (
        patch("app.providers.wikipedia._cache_get", AsyncMock(return_value=None)),
        patch("app.providers.wikipedia._cache_set", AsyncMock()),
    ):
        fact = await provider.wikidata_factual("nonexistent_entity_xyz", lang="tr")

    assert fact is None


# =============================================================================
# Constants sanity
# =============================================================================


def test_default_lang_priority_includes_tr_and_en():
    assert "tr" in DEFAULT_LANG_PRIORITY
    assert "en" in DEFAULT_LANG_PRIORITY


def test_wikidata_factual_props_has_minimum_set():
    """En kritik 4 property — birth, death, population, founded."""
    assert "P569" in WIKIDATA_FACTUAL_PROPS  # birth_date
    assert "P570" in WIKIDATA_FACTUAL_PROPS  # death_date
    assert "P1082" in WIKIDATA_FACTUAL_PROPS  # population
    assert "P571" in WIKIDATA_FACTUAL_PROPS  # founded_date
