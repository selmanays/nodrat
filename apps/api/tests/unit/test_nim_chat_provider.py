"""NIM chat provider unit tests (#109).

NIM_API_KEY ile NIM endpoint üzerinden DeepSeek V4 Flash (ve diğer chat modelleri).
Network mock'lanır.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.providers.base import (
    Message,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderType,
)
from app.providers.nim_chat import (
    NIM_CHAT_DEFAULT_MODEL,
    NimChatProvider,
)


def _stub_response(
    *,
    text: str = "Selamlar, nasıl yardımcı olabilirim?",
    prompt_tokens: int = 12,
    completion_tokens: int = 8,
    model: str = NIM_CHAT_DEFAULT_MODEL,
) -> dict:
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _make_provider() -> NimChatProvider:
    return NimChatProvider(
        api_key="test-key",
        base_url="https://stub.test/v1",
    )


# ---------------------------------------------------------------------------
# Static
# ---------------------------------------------------------------------------


def test_static_attributes():
    p = _make_provider()
    assert p.name == "deepseek"  # registry routing key
    assert p.type == ProviderType.LLM
    assert p.supports_chat is True
    assert p.supports_embeddings is False
    # NIM free tier — cost zero
    assert p.cost_per_1m_input_tokens == 0.0
    assert p.cost_per_1m_output_tokens == 0.0


def test_default_model_deepseek():
    """Default model NIM CSV'de listelenmiş 'deepseek-v3.2' olmalı."""
    assert "deepseek" in NIM_CHAT_DEFAULT_MODEL
    assert "v3" in NIM_CHAT_DEFAULT_MODEL


def test_no_api_key_raises():
    with patch("app.providers.nim_chat.get_settings") as mock_settings:
        s = MagicMock()
        s.nim_api_key.get_secret_value.return_value = ""
        s.nim_base_url = "https://integrate.api.nvidia.com/v1"
        mock_settings.return_value = s

        with pytest.raises(ValueError, match="NIM_API_KEY"):
            NimChatProvider()


# ---------------------------------------------------------------------------
# generate_text — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_text_success_zero_cost():
    """200 OK → GenerationResult with text + tokens. NIM free tier → cost=0."""
    provider = _make_provider()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _stub_response()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await provider.generate_text(
            messages=[Message(role="user", content="Selam")],
            max_tokens=100,
        )

    assert result.text.startswith("Selamlar")
    assert result.input_tokens == 12
    assert result.output_tokens == 8
    # NIM free tier — cost 0
    assert result.cost_usd == 0.0


@pytest.mark.asyncio
async def test_generate_text_uses_nim_endpoint():
    """POST /v1/chat/completions NIM endpoint'ine atılmalı."""
    provider = _make_provider()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _stub_response()

    captured_url: list[str] = []

    async def fake_post(url, headers, json):  # type: ignore[no-untyped-def]
        captured_url.append(url)
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = fake_post
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await provider.generate_text(messages=[Message(role="user", content="x")])

    assert captured_url[0].endswith("/chat/completions")


@pytest.mark.asyncio
async def test_pii_redaction_user_only():
    """User mesajında PII redact, system mesajına dokunmaz."""
    provider = _make_provider()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _stub_response()

    captured_payload: dict = {}

    async def fake_post(url, headers, json):  # type: ignore[no-untyped-def]
        captured_payload.update(json)
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = fake_post
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await provider.generate_text(
            messages=[
                Message(role="system", content="Sistem promptu — info@nodrat.com"),
                Message(role="user", content="ali@example.com adresine yaz"),
            ],
        )

    sys_msg = captured_payload["messages"][0]["content"]
    user_msg = captured_payload["messages"][1]["content"]
    assert "info@nodrat.com" in sys_msg  # system redact edilmedi
    assert "ali@example.com" not in user_msg  # user redact edildi
    assert "[email_redacted]" in user_msg


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_rate_limit():
    provider = _make_provider()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "rate_limit_exceeded"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ProviderRateLimitError):
            await provider.generate_text(
                messages=[Message(role="user", content="x")],
            )


@pytest.mark.asyncio
async def test_502_server_error():
    provider = _make_provider()
    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = "Bad Gateway"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ProviderError, match="server error"):
            await provider.generate_text(
                messages=[Message(role="user", content="x")],
            )


@pytest.mark.asyncio
async def test_timeout():
    provider = _make_provider()

    async def raise_timeout(url, headers, json):  # type: ignore[no-untyped-def]
        raise httpx.TimeoutException("timeout")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = raise_timeout
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ProviderTimeoutError):
            await provider.generate_text(
                messages=[Message(role="user", content="x")],
            )


@pytest.mark.asyncio
async def test_empty_messages_raises():
    provider = _make_provider()
    with pytest.raises(ProviderError, match="messages"):
        await provider.generate_text(messages=[])


@pytest.mark.asyncio
async def test_empty_choices_raises():
    provider = _make_provider()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": []}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ProviderError, match="empty choices"):
            await provider.generate_text(
                messages=[Message(role="user", content="x")],
            )
