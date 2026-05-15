"""Unit tests for chat_tools (#822 LLM tool-use Wikipedia)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.chat_tools import (
    CHAT_TOOL_DEFINITIONS,
    CHAT_TOOLS,
    SEARCH_NEWS_TOOL,
    SEARCH_WIKIPEDIA_TOOL,
    execute_search_news,
    execute_search_wikipedia,
)
from app.providers.base import GenerationResult, Message, ToolCall


# =============================================================================
# Tool definition shape (OpenAI-compatible)
# =============================================================================


def test_tool_definition_openai_shape():
    assert SEARCH_WIKIPEDIA_TOOL["type"] == "function"
    fn = SEARCH_WIKIPEDIA_TOOL["function"]
    assert fn["name"] == "search_wikipedia"
    assert "query" in fn["parameters"]["properties"]
    assert fn["parameters"]["required"] == ["query"]


def test_tool_registry_wired():
    assert "search_wikipedia" in CHAT_TOOLS
    assert CHAT_TOOLS["search_wikipedia"] is execute_search_wikipedia
    assert SEARCH_WIKIPEDIA_TOOL in CHAT_TOOL_DEFINITIONS


def test_news_tool_definition_and_priority():
    # #845 — search_news BİRİNCİL: tanım listesinde search_wikipedia'dan ÖNCE
    assert SEARCH_NEWS_TOOL["function"]["name"] == "search_news"
    names = [d["function"]["name"] for d in CHAT_TOOL_DEFINITIONS]
    assert names == ["search_news", "search_wikipedia"]
    assert "query" in SEARCH_NEWS_TOOL["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_execute_search_news_empty_query():
    txt, sources, meta = await execute_search_news(
        {"query": "  "}, db=None, now=None, user=None,
    )
    assert "Geçersiz" in txt
    assert sources == [] and meta == {}


@pytest.mark.asyncio
async def test_execute_search_news_contract():
    """#845 — (text, sources, meta) sözleşmesi: [n] bloklar, news cite token,
    source_type='news', meta.query_class."""

    class _Plan:
        topic_query = "Trump Çin ziyareti"
        critical_entities = ["trump"]
        query_class = "news_query"

    class _Emb:
        vectors = [[0.1, 0.2, 0.3]]

    class _Provider:
        async def create_embedding(self, _q):
            return _Emb()

    chunks = [
        {
            "article_id": "a1", "chunk_id": "c1",
            "article_title": "Trump Çin'i değerlendirdi",
            "chunk_text": "Trump görüşmeyi olumlu buldu.",
            "source_name": "Anadolu Ajansı",
            "article_canonical_url": "https://aa.com.tr/x",
        },
        {
            "article_id": "a2", "chunk_id": "c2",
            "article_title": "Boeing anlaşması",
            "chunk_text": "Çin daha fazla Boeing alacak.",
            "source_name": "Bloomberg HT",
            "url": "https://bloomberght.com/y",
        },
    ]

    with (
        patch(
            "app.prompts.query_planner.plan_query",
            AsyncMock(return_value=_Plan()),
        ),
        patch(
            "app.providers.registry.registry.route_for_tier",
            lambda **_kw: _Provider(),
        ),
        patch(
            "app.core.retrieval.hybrid_search_chunks",
            AsyncMock(return_value=chunks),
        ),
    ):
        txt, sources, meta = await execute_search_news(
            {"query": "Trump Çin son durum"},
            db=object(), now=None, user=None, content_top_k=5,
        )

    assert "[1]" in txt and "[2]" in txt
    assert "Anadolu Ajansı" in txt
    assert len(sources) == 2
    assert all(s["source_type"] == "news" for s in sources)
    assert sources[0]["cite"] == "[1]" and sources[1]["cite"] == "[2]"
    assert sources[0]["url"] == "https://aa.com.tr/x"
    assert meta["query_class"] == "news_query"
    assert meta["chunk_count"] == 2


# =============================================================================
# execute_search_wikipedia
# =============================================================================


@pytest.mark.asyncio
async def test_execute_empty_query():
    result, sources = await execute_search_wikipedia({"query": "  "})
    assert "Geçersiz" in result
    assert sources == []


@pytest.mark.asyncio
async def test_execute_no_results():
    fake_provider = AsyncMock()
    fake_provider.search = AsyncMock(return_value=[])
    fake_provider.wikidata_factual = AsyncMock(return_value=None)
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake_provider),
    ):
        result, sources = await execute_search_wikipedia({"query": "xyzqwerty"})
    assert "bulunamadı" in result.lower()
    assert sources == []


@pytest.mark.asyncio
async def test_execute_success_builds_numbered_sources():
    class _Art:
        def __init__(self, title, summary, url, lang, lic):
            self.title = title
            self.summary = summary
            self.url = url
            self.lang = lang
            self.license = lic

    arts = [
        _Art("Donald Trump", "ABD'nin 47. başkanı...", "https://tr.wikipedia.org/x", "tr", "CC BY-SA 4.0"),
        _Art("Trump Organization", "Şirket...", "https://tr.wikipedia.org/y", "tr", "CC BY-SA 4.0"),
    ]
    fake_provider = AsyncMock()
    fake_provider.search = AsyncMock(return_value=arts)
    fake_provider.wikidata_factual = AsyncMock(return_value=None)
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake_provider),
    ):
        result, sources = await execute_search_wikipedia(
            {"query": "Donald Trump"}
        )

    # #851 — tek `[n]` namespace (W prefix YOK), cite_start=0 → [1][2]
    assert "[1]" in result
    assert "[2]" in result
    assert "[W1]" not in result
    assert "Donald Trump" in result
    assert len(sources) == 2
    assert all(s["source_type"] == "wikipedia" for s in sources)
    assert sources[0]["title"] == "Donald Trump"
    assert sources[0]["url"] == "https://tr.wikipedia.org/x"
    assert sources[0]["cite"] == "[1]"
    assert sources[1]["cite"] == "[2]"


@pytest.mark.asyncio
async def test_execute_wikipedia_cite_start_offset():
    """#851 — cite_start ile global benzersiz citation (multi-round çakışma yok)."""

    class _Art:
        def __init__(self, t):
            self.title, self.summary = t, "özet..."
            self.url, self.lang, self.license = "https://tr.wp/" + t, "tr", "CC BY-SA 4.0"

    fake = AsyncMock()
    fake.search = AsyncMock(return_value=[_Art("A"), _Art("B")])
    fake.wikidata_factual = AsyncMock(return_value=None)
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake),
    ):
        result, sources = await execute_search_wikipedia(
            {"query": "x"}, cite_start=4,
        )
    assert "[5]" in result and "[6]" in result
    assert "[1]" not in result
    assert sources[0]["cite"] == "[5]" and sources[1]["cite"] == "[6]"


@pytest.mark.asyncio
async def test_execute_provider_exception_graceful():
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(side_effect=RuntimeError("network down")),
    ):
        result, sources = await execute_search_wikipedia({"query": "Trump"})
    assert "başarısız" in result.lower()
    assert sources == []


@pytest.mark.asyncio
async def test_execute_wikidata_fact_prepended():
    """#827/#851 — Wikidata fact varsa [1] Wikidata, Wikipedia [2] (tek namespace)."""

    class _Art:
        def __init__(self, title, summary, url, lang, lic):
            self.title, self.summary = title, summary
            self.url, self.lang, self.license = url, lang, lic

    class _Fact:
        qid = "Q22686"
        label = "Donald Trump"
        properties = {"P569": "1946-06-14T00:00:00Z", "P102": "Q29468"}

    arts = [_Art("Donald Trump", "ABD başkanı...", "https://tr.wp/x", "tr", "CC BY-SA 4.0")]
    fake_provider = AsyncMock()
    fake_provider.search = AsyncMock(return_value=arts)
    fake_provider.wikidata_factual = AsyncMock(return_value=_Fact())
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake_provider),
    ):
        result, sources = await execute_search_wikipedia({"query": "Trump yaşı"})

    # #851 — Wikidata [1] başta, Wikipedia [2] (tek `[n]` namespace, W YOK)
    assert "[1] Wikidata" in result
    assert "Doğum tarihi: 1946-06-14" in result
    assert "[W1]" not in result
    assert "[2]" in result
    assert sources[0]["source_name"] == "Wikidata"
    assert sources[0]["cite"] == "[1]"
    assert sources[0]["url"] == "https://www.wikidata.org/wiki/Q22686"
    assert sources[1]["title"] == "Donald Trump"
    assert sources[1]["cite"] == "[2]"


# =============================================================================
# Provider ToolCall / Message dataclass shape
# =============================================================================


def test_message_tool_fields_optional():
    m = Message(role="user", content="merhaba")
    assert m.tool_calls is None
    assert m.tool_call_id is None


def test_message_with_tool_calls():
    tc = ToolCall(id="call_1", name="search_wikipedia", arguments={"query": "x"})
    m = Message(role="assistant", content="", tool_calls=[tc])
    assert m.tool_calls[0].name == "search_wikipedia"
    assert m.tool_calls[0].arguments == {"query": "x"}


def test_tool_result_message():
    m = Message(role="tool", content="sonuç", tool_call_id="call_1")
    assert m.role == "tool"
    assert m.tool_call_id == "call_1"


def test_generation_result_tool_calls_default_none():
    gr = GenerationResult(text="hi", model="deepseek")
    assert gr.tool_calls is None


@pytest.mark.asyncio
async def test_execute_wikipedia_wikidata_uses_article_title_not_raw_query():
    """#863 — Wikidata wbsearchentities ENTITY araması niteleyiciyi
    kaldıramaz ("X doğum tarihi" → BOŞ). Fix: ham query yerine
    Wikipedia'nın çözdüğü kanonik sayfa başlığı Wikidata'ya gider.
    Aksi halde TÜM 'X kaç yaşında/doğum tarihi' soruları kırılır."""

    class _Art:
        def __init__(self, title):
            self.title, self.summary = title, "Kanadalı senarist..."
            self.url, self.lang, self.license = (
                "https://tr.wp/x", "tr", "CC BY-SA 4.0",
            )

    class _Fact:
        qid = "Q431432"
        label = "Robert C. Cooper"
        properties = {"P569": "1968-10-14T00:00:00Z"}

    captured: dict = {}

    async def _search(q, *, lang=None, top_k=3):
        return [_Art("Robert C. Cooper")]  # full-text niteliyiciye tolere

    async def _wikidata(q, *, lang="tr"):
        captured["wd_query"] = q
        return _Fact() if q == "Robert C. Cooper" else None

    fake = AsyncMock()
    fake.search = _search
    fake.wikidata_factual = _wikidata
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake),
    ):
        # LLM/condense niteliyici içeren query gönderse bile çalışmalı
        result, sources = await execute_search_wikipedia(
            {"query": "Robert C. Cooper doğum tarihi"}
        )

    # Wikidata, HAM query ile değil Wikipedia'nın çözdüğü başlıkla çağrıldı
    assert captured["wd_query"] == "Robert C. Cooper"
    assert "Doğum tarihi: 1968-10-14" in result
    assert any(s["source_name"] == "Wikidata" for s in sources)
