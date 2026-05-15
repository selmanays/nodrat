"""Unit tests for chat_tools (#822 LLM tool-use Wikipedia)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.chat_tools import (
    CHAT_TOOL_DEFINITIONS,
    CHAT_TOOLS,
    SEARCH_WIKIPEDIA_TOOL,
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

    # Numaralı blok [W1][W2] (Wikidata None → sadece Wikipedia, offset 0)
    assert "[W1]" in result
    assert "[W2]" in result
    assert "Donald Trump" in result
    # Sources — source_type='wikipedia'
    assert len(sources) == 2
    assert all(s["source_type"] == "wikipedia" for s in sources)
    assert sources[0]["title"] == "Donald Trump"
    assert sources[0]["url"] == "https://tr.wikipedia.org/x"
    assert sources[0]["license"] == "CC BY-SA 4.0"


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
    """#827 — Wikidata fact varsa [W1] Wikidata, Wikipedia W2'den başlar."""

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

    # Wikidata [W1] başta — doğum tarihi ISO'dan kısaltılmış
    assert "[W1]" in result
    assert "Doğum tarihi: 1946-06-14" in result
    assert "Wikidata" in result
    # Wikipedia prose W2'ye kaydı (offset)
    assert "[W2]" in result
    assert sources[0]["source_name"] == "Wikidata"
    assert sources[0]["url"] == "https://www.wikidata.org/wiki/Q22686"
    assert sources[1]["title"] == "Donald Trump"


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
