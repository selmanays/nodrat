"""Tests for DeepSeekProvider.generate_text_stream (issue #527).

Mock httpx.AsyncClient ile stream chunk simülasyonu yapılır. Provider:
- delta_text taşıyan StreamChunk'ları yield eder
- son chunk is_final=True ve usage doldurulmuş gelir
- 4xx/5xx durumunda exception fırlatır
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.providers.base import (
    Message,
    ProviderError,
    StreamChunk,
)


@pytest.fixture(autouse=True)
def _patch_deepseek_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


def _make_sse_lines(deltas: list[str], usage: dict[str, int] | None = None) -> list[str]:
    """OpenAI-compatible SSE lines."""
    lines: list[str] = []
    for d in deltas:
        chunk = {
            "id": "chatcmpl-x",
            "model": "deepseek-v4-flash",
            "choices": [{"delta": {"content": d}, "finish_reason": None}],
        }
        lines.append(f"data: {json.dumps(chunk)}")
        lines.append("")
    if usage is not None:
        usage_chunk = {
            "id": "chatcmpl-x",
            "model": "deepseek-v4-flash",
            "choices": [],
            "usage": usage,
        }
        lines.append(f"data: {json.dumps(usage_chunk)}")
        lines.append("")
    lines.append("data: [DONE]")
    return lines


class _FakeResponse:
    def __init__(self, status_code: int, lines: list[str]):
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b""


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return None

    @asynccontextmanager
    async def stream(self, _method: str, _url: str, **_kwargs: Any):
        yield self._response


@pytest.mark.asyncio
async def test_stream_yields_deltas(monkeypatch):
    from app.providers import deepseek as ds_mod

    deltas = ['{"posts":', ' [{"text":"merhaba", "angle":"a"}]}']
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "prompt_cache_hit_tokens": 30,
    }
    response = _FakeResponse(200, _make_sse_lines(deltas, usage))

    def _client_factory(**_kwargs):
        return _FakeAsyncClient(response)

    monkeypatch.setattr(ds_mod.httpx, "AsyncClient", _client_factory)

    provider = ds_mod.DeepSeekProvider(api_key="test-key")
    chunks: list[StreamChunk] = []
    async for c in provider.generate_text_stream(
        messages=[Message(role="user", content="ping")],
        json_mode=True,
    ):
        chunks.append(c)

    # 2 delta + 1 final
    delta_chunks = [c for c in chunks if not c.is_final]
    final_chunks = [c for c in chunks if c.is_final]
    assert len(delta_chunks) == 2
    assert delta_chunks[0].delta_text == '{"posts":'
    assert delta_chunks[1].delta_text == ' [{"text":"merhaba", "angle":"a"}]}'

    assert len(final_chunks) == 1
    fc = final_chunks[0]
    assert fc.input_tokens == 100
    assert fc.output_tokens == 20
    assert fc.cached_input_tokens == 30
    assert fc.cost_usd > 0
    assert fc.model == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_stream_4xx_raises(monkeypatch):
    from app.providers import deepseek as ds_mod

    response = _FakeResponse(400, [])

    def _client_factory(**_kwargs):
        return _FakeAsyncClient(response)

    monkeypatch.setattr(ds_mod.httpx, "AsyncClient", _client_factory)

    provider = ds_mod.DeepSeekProvider(api_key="test-key")
    with pytest.raises(ProviderError):
        async for _ in provider.generate_text_stream(
            messages=[Message(role="user", content="x")]
        ):
            pass


@pytest.mark.asyncio
async def test_stream_pii_redacted_in_user_msgs(monkeypatch):
    """PII redaction user mesajına uygulanmalı, system'a değil."""
    from app.providers import deepseek as ds_mod

    captured: dict[str, Any] = {}

    class _Capturing(_FakeAsyncClient):
        @asynccontextmanager
        async def stream(self, method, url, **kwargs):  # type: ignore[override]
            captured["json"] = kwargs.get("json")
            yield self._response

    response = _FakeResponse(200, _make_sse_lines(["ok"], {"prompt_tokens": 1, "completion_tokens": 1}))
    monkeypatch.setattr(
        ds_mod.httpx,
        "AsyncClient",
        lambda **_kwargs: _Capturing(response),
    )

    provider = ds_mod.DeepSeekProvider(api_key="test-key")
    async for _ in provider.generate_text_stream(
        messages=[
            Message(role="system", content="You are an agent. user@example.com"),
            Message(role="user", content="My email is user@example.com"),
        ]
    ):
        pass

    payload = captured["json"]
    user_msg = next(m for m in payload["messages"] if m["role"] == "user")
    sys_msg = next(m for m in payload["messages"] if m["role"] == "system")
    # User redacted; system left alone (system is our prompt)
    assert "user@example.com" not in user_msg["content"]
    assert "user@example.com" in sys_msg["content"]


@pytest.mark.asyncio
async def test_stream_empty_messages_raises():
    from app.providers.deepseek import DeepSeekProvider

    provider = DeepSeekProvider(api_key="test-key")
    with pytest.raises(ProviderError):
        async for _ in provider.generate_text_stream(messages=[]):
            pass


# =============================================================================
# #857 — DSML-in-content tool-call normalize (provider quirk)
# =============================================================================


def test_parse_dsml_tool_calls_real_fullwidth():
    """DeepSeek ｜ (U+FF5C) DSML formatı → yapısal ToolCall, ham XML sızmaz."""
    from app.providers.deepseek import _parse_dsml_tool_calls

    t = (
        '<｜DSML｜tool_calls><｜DSML｜invoke name="search_wikipedia">'
        '<｜DSML｜parameter name="query" string="true">'
        'Stargate SG-1 creators writers</｜DSML｜parameter>'
        '</｜DSML｜invoke></｜DSML｜tool_calls>'
    )
    calls, cleaned = _parse_dsml_tool_calls(t)
    assert len(calls) == 1
    assert calls[0].name == "search_wikipedia"
    assert calls[0].arguments == {"query": "Stargate SG-1 creators writers"}
    assert cleaned == ""  # saf tool çağrısı → cevap metni yok


def test_parse_dsml_tool_calls_preserves_prose():
    from app.providers.deepseek import _parse_dsml_tool_calls

    t = (
        "Kısa açıklama. <｜DSML｜tool_calls><｜DSML｜invoke "
        'name="search_news"><｜DSML｜parameter name="query" '
        'string="true">CHP haber</｜DSML｜parameter></｜DSML｜invoke>'
        "</｜DSML｜tool_calls>"
    )
    calls, cleaned = _parse_dsml_tool_calls(t)
    assert calls and calls[0].name == "search_news"
    assert cleaned == "Kısa açıklama."


def test_parse_dsml_tool_calls_passthrough_normal_text():
    """Normal cevap (DSML yok) → değişmeden geçer, yanlış pozitif yok."""
    from app.providers.deepseek import _parse_dsml_tool_calls

    calls, cleaned = _parse_dsml_tool_calls("Normal cevap [1] kaynak metni.")
    assert calls == []
    assert cleaned == "Normal cevap [1] kaynak metni."


def test_parse_dsml_double_pipe_real_prod_format():
    """#860 — GERÇEK prod formatı ÇİFT ｜｜ (truncate kapanış). #857
    cleaner tek-｜ varsaymıştı → ham DSML sızdı. Bulletproof olmalı."""
    from app.providers.deepseek import (
        _parse_dsml_tool_calls,
        strip_dsml_markup,
    )

    real = (
        '<｜｜DSML｜｜tool_calls>\n<｜｜DSML｜｜invoke name="search_news">\n'
        '<｜｜DSML｜｜parameter name="query" string="true">'
        'Stargate Atlantis dizisi yönetmenleri kimler'
        '</｜｜DSML｜｜parameter>\n</｜｜DSML｜｜invoke>\n</｜｜DSML｜｜tool'
    )
    calls, cleaned = _parse_dsml_tool_calls(real)
    assert len(calls) == 1
    assert calls[0].name == "search_news"
    assert calls[0].arguments == {
        "query": "Stargate Atlantis dizisi yönetmenleri kimler"
    }
    assert cleaned == ""  # saf tool çağrısı
    # son güvenlik ağı: ham DSML markup tamamen sökülür
    assert strip_dsml_markup(real) == ""


def test_strip_dsml_markup_safety_net():
    """Parser kaçırsa bile kullanıcıya giden metinde DSML kalmaz."""
    from app.providers.deepseek import strip_dsml_markup

    assert strip_dsml_markup("Normal cevap [1] kaynak.") == (
        "Normal cevap [1] kaynak."
    )
    assert strip_dsml_markup(
        "Önsöz. <｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name=\"x\">"
    ) == "Önsöz."
