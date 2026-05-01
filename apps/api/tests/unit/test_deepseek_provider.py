"""DeepSeek chat provider unit tests (#105).

Network mock'lanır — gerçek API key gerekmiyor.
Integration test (gerçek API çağrısı) ayrı dosyada (DEEPSEEK_API_KEY varsa).
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
from app.providers.deepseek import (
    DEEPSEEK_DEFAULT_MODEL,
    DeepSeekChatProvider,
)


def _stub_response(
    *,
    status_code: int = 200,
    text: str = "Selamlar, nasıl yardımcı olabilirim?",
    prompt_tokens: int = 12,
    completion_tokens: int = 8,
    model: str = DEEPSEEK_DEFAULT_MODEL,
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


def _make_provider() -> DeepSeekChatProvider:
    """Test için key stub'lı provider."""
    return DeepSeekChatProvider(api_key="test-key", base_url="https://stub.test")


# ---------------------------------------------------------------------------
# Static / class attribute checks
# ---------------------------------------------------------------------------


def test_provider_static_attributes():
    p = _make_provider()
    assert p.name == "deepseek_v3"
    assert p.type == ProviderType.LLM
    assert p.supports_chat is True
    assert p.supports_embeddings is False
    # Cost rates (unit-economics.md §4.2)
    assert p.cost_per_1m_input_tokens == 0.27
    assert p.cost_per_1m_output_tokens == 1.10


def test_base_url_appends_v1():
    p = DeepSeekChatProvider(api_key="x", base_url="https://api.deepseek.com")
    assert p._base_url == "https://api.deepseek.com/v1"

    p2 = DeepSeekChatProvider(api_key="x", base_url="https://api.deepseek.com/v1")
    assert p2._base_url == "https://api.deepseek.com/v1"


def test_no_api_key_raises():
    """Missing API key → ValueError."""
    from unittest.mock import patch as _patch

    with _patch(
        "app.providers.deepseek.get_settings"
    ) as mock_settings:
        s = MagicMock()
        s.deepseek_api_key.get_secret_value.return_value = ""
        s.deepseek_base_url = "https://api.deepseek.com"
        mock_settings.return_value = s

        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
            DeepSeekChatProvider()


# ---------------------------------------------------------------------------
# generate_text (success paths)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_text_success():
    """200 OK → GenerationResult with text + tokens + cost."""
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
    # 12 * 0.27/1M + 8 * 1.10/1M = 0.0000124
    assert result.cost_usd > 0
    assert result.cost_usd < 0.001
    assert result.model == DEEPSEEK_DEFAULT_MODEL
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_generate_text_pii_redaction_in_user_message():
    """User mesajında PII → redact, sistem mesajına dokunmaz."""
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
                Message(role="system", content="Sen yardımcı asistansın. info@nodrat.com."),
                Message(role="user", content="ali@example.com adresine yaz"),
            ],
        )

    # System message redact EDİLMEDİ
    sys_msg = captured_payload["messages"][0]["content"]
    assert "info@nodrat.com" in sys_msg
    # User message redact EDİLDİ
    user_msg = captured_payload["messages"][1]["content"]
    assert "ali@example.com" not in user_msg
    assert "[email_redacted]" in user_msg


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_text_429_rate_limit():
    provider = _make_provider()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = '{"error": "rate_limit_exceeded"}'

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
async def test_generate_text_500_server_error():
    provider = _make_provider()
    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = "<html>Bad Gateway</html>"

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
async def test_generate_text_timeout():
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
async def test_generate_text_empty_messages():
    provider = _make_provider()
    with pytest.raises(ProviderError, match="messages"):
        await provider.generate_text(messages=[])


@pytest.mark.asyncio
async def test_generate_text_empty_choices():
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
