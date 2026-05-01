"""DeepSeek V3 chat provider adapter (#105).

DeepSeek OpenAI-uyumlu Chat Completions API.

docs/engineering/architecture.md §4
docs/strategy/unit-economics.md §4.2 ($0.27/M input, $1.10/M output)

Endpoint: https://api.deepseek.com/v1/chat/completions
Model:    deepseek-chat (V3 default)

Auth:     Authorization: Bearer {DEEPSEEK_API_KEY}
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings
from app.core.pii import redact
from app.providers.base import (
    GenerationResult,
    Message,
    ModelProvider,
    ProviderError,
    ProviderHealth,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderType,
)


logger = logging.getLogger(__name__)


# Default model — DeepSeek V3 chat
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"

# Default endpoint (config'ten override edilebilir)
DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


class DeepSeekChatProvider(ModelProvider):
    """DeepSeek V3 chat completion adapter.

    NOT: Sistem promptu PII içermez (haber bağlamı). User message'a PII
    redaction uygulanır (KVKK uyumu — opinion-integration.md §3.5).
    """

    name = "deepseek_v3"
    type = ProviderType.LLM

    supports_chat = True
    supports_embeddings = False
    supports_rerank = False
    supports_vision = False

    # docs/strategy/unit-economics.md §4.2 (USD per 1M tokens)
    cost_per_1m_input_tokens = 0.27
    cost_per_1m_output_tokens = 1.10

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = DEEPSEEK_DEFAULT_MODEL,
        timeout: float = 60.0,
    ) -> None:
        settings = get_settings()
        self._api_key = (
            api_key
            if api_key
            else (
                settings.deepseek_api_key.get_secret_value()
                if settings.deepseek_api_key
                else None
            )
        )
        # Settings'te /v1 yok — adapter ekler
        configured_base = base_url or settings.deepseek_base_url
        configured_base = configured_base.rstrip("/")
        if not configured_base.endswith("/v1"):
            configured_base = f"{configured_base}/v1"
        self._base_url = configured_base
        self._default_model = default_model
        self._timeout = timeout

        if not self._api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY env değişkeni gerekli (DeepSeekChatProvider)."
            )

    async def generate_text(
        self,
        messages: list[Message],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: int | None = None,
    ) -> GenerationResult:
        """Chat completion — OpenAI uyumlu.

        Args:
            messages: system / user / assistant conversation
            model: deepseek-chat (default) | deepseek-reasoner
            max_tokens: response cap (default 1024)
            temperature: 0..2 (default 0.7)
            timeout: request timeout (default class-level)

        Returns:
            GenerationResult (text + model + tokens + cost + latency)

        Raises:
            ProviderRateLimitError (429)
            ProviderTimeoutError
            ProviderError (5xx, JSON parse)
        """
        if not messages:
            raise ProviderError("messages list boş olamaz")

        chosen_model = model or self._default_model

        # PII redaction: user role mesajlarına uygula (sistem promptu = bizim
        # control'umuzda, redaction'a gerek yok).
        sanitized: list[dict[str, str]] = []
        total_redactions = 0
        for msg in messages:
            content = msg.content
            if msg.role == "user":
                redaction = redact(content)
                content = redaction.text
                total_redactions += redaction.total_redactions
            sanitized.append({"role": msg.role, "content": content})

        if total_redactions > 0:
            logger.info(
                "DeepSeek call: PII redacted=%d in user messages",
                total_redactions,
            )

        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": sanitized,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        request_timeout = timeout if timeout is not None else self._timeout

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"DeepSeek timeout after {request_timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"DeepSeek network error: {exc}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code == 429:
            raise ProviderRateLimitError(
                f"DeepSeek rate limit: {response.text[:200]}"
            )
        if response.status_code >= 500:
            raise ProviderError(
                f"DeepSeek server error ({response.status_code}): {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"DeepSeek client error ({response.status_code}): {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(f"DeepSeek invalid JSON: {exc}") from exc

        # Extract response
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError("DeepSeek response empty choices")

        text = choices[0].get("message", {}).get("content", "") or ""
        if not text.strip():
            logger.warning("DeepSeek returned empty content (model=%s)", chosen_model)

        usage = data.get("usage", {}) or {}
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))

        cost_usd = (
            input_tokens * self.cost_per_1m_input_tokens / 1_000_000
            + output_tokens * self.cost_per_1m_output_tokens / 1_000_000
        )

        return GenerationResult(
            text=text,
            model=data.get("model", chosen_model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost_usd, 6),
            latency_ms=latency_ms,
            raw_response=data,
        )

    async def healthcheck(self) -> ProviderHealth:
        """Trivial chat ile API erişimi doğrula."""
        try:
            result = await self.generate_text(
                messages=[Message(role="user", content="ping")],
                max_tokens=8,
                temperature=0.0,
                timeout=10,
            )
            return ProviderHealth(healthy=True, latency_ms=result.latency_ms)
        except ProviderTimeoutError as exc:
            return ProviderHealth(healthy=False, error=f"timeout: {exc}")
        except ProviderError as exc:
            return ProviderHealth(healthy=False, error=str(exc)[:200])


def build_deepseek_provider() -> DeepSeekChatProvider | None:
    """Settings'tan DeepSeek provider inşa et — key yoksa None döner.

    Registry bootstrap'ı bu pattern'i kullanır (NIM gibi).
    """
    settings = get_settings()
    if not settings.deepseek_api_key:
        logger.info("DEEPSEEK_API_KEY tanımlı değil — DeepSeek provider skip edildi")
        return None
    if not settings.deepseek_api_key.get_secret_value():
        return None
    try:
        return DeepSeekChatProvider()
    except ValueError:
        return None
