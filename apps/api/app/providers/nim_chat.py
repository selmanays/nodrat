"""NIM chat provider — DeepSeek V3 (ve diğer NIM chat modelleri) için adapter.

NVIDIA NIM ücretsiz tier'da çok sayıda chat modeli host'lar:
  - deepseek-v3.2 (default, agentic + reasoning)
  - deepseek-v3.1-terminus (function calling)
  - mistral-large-3-675b-instruct (multimodal)
  - kimi-k2-instruct (coding + reasoning)
  - mistral-medium-3-instruct (kurumsal genel amaçlı)
  - mistral-nemotron (function calling)
  - glm-4.7 (tool calling + UI)

Hepsi NIM_API_KEY ile çağrılır → /v1/chat/completions (OpenAI-compatible).

docs/engineering/architecture.md §4
docs/strategy/unit-economics.md §4.2 (free tier)
"""

from __future__ import annotations

import asyncio
import logging
import time

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


class _TransientHTTP(Exception):
    """Internal — 429 / 5xx retry signal (#147 #155)."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"transient http {status}")
        self.status = status
        self.body = body


# Default chat model — DeepSeek V3.1-terminus (NIM tarafında stabil yanıtlar).
# 2026-05-02: deepseek-v3.2 NIM'de 502 dönüyor (geçici); v3.1-terminus
# 200 OK + Türkçe yanıt veriyor. v4-flash timeout. Stabil olan terminus.
NIM_CHAT_DEFAULT_MODEL = "deepseek-ai/deepseek-v3.1-terminus"


class NimChatProvider(ModelProvider):
    """NIM ücretsiz tier üzerinden DeepSeek V3 (ve diğer chat modelleri).

    PII redaction: User mesajları üzerinde otomatik (opinion-integration.md §3.5).
    System prompt redact edilmez (bizim kontrolümüzde).

    NOT: registry'de name='deepseek_v3' olarak kayıtlı (route_for_tier uyumu).
    """

    name = "deepseek_v3"  # registry routing için sabit (deepseek-v3.2 modeli NIM'den)
    type = ProviderType.LLM

    supports_chat = True
    supports_embeddings = False
    supports_rerank = False
    supports_vision = False

    # NIM ücretsiz tier — gerçek maliyet $0
    cost_per_1m_input_tokens = 0.0
    cost_per_1m_output_tokens = 0.0

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        """NIM chat provider.

        Args:
            timeout: Per-request timeout (default 120s — NIM occasional 30-60s
                latency observed in prod, 60s buffer çok sıkı, kullanıcı için
                kötü UX). #147 fix.
            max_retries: Transient hata (timeout/network) için retry sayısı
                (default 1 — toplam 2 deneme).
        """
        settings = get_settings()
        self._api_key = api_key or settings.nim_api_key.get_secret_value()
        self._base_url = (base_url or settings.nim_base_url).rstrip("/")
        # NIM URL zaten /v1 ile bitiyor (config'te öyle)
        # Default model: env (NIM_CHAT_MODEL) > settings > module constant
        self._default_model = (
            default_model
            or settings.nim_chat_model
            or NIM_CHAT_DEFAULT_MODEL
        )
        self._timeout = timeout
        self._max_retries = max_retries

        if not self._api_key:
            raise ValueError(
                "NIM_API_KEY env değişkeni gerekli (NimChatProvider)."
            )

    async def generate_text(
        self,
        messages: list[Message],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: int | None = None,
        json_mode: bool = False,  # NIM ignore — DeepSeek-only feature (#171)
    ) -> GenerationResult:
        """Chat completion (OpenAI-uyumlu).

        PII redaction USER mesajlarına uygulanır. System mesajı (bizim
        kontrolümüzdeki prompt) redact edilmez.
        """
        if not messages:
            raise ProviderError("messages list boş olamaz")

        chosen_model = model or self._default_model

        # PII redaction (KVKK / opinion-integration.md §3.5)
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
                "NIM chat: PII redacted=%d in user messages (model=%s)",
                total_redactions,
                chosen_model,
            )

        payload = {
            "model": chosen_model,
            "messages": sanitized,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        request_timeout = timeout if timeout is not None else self._timeout

        # Transient hata (timeout/network/429/5xx) retry — #147 + #155 fix.
        # NIM occasional 30-60s latency + rate limit cooldown (1-5 dk).
        attempt = 0
        max_attempts = self._max_retries + 1
        last_error: Exception | None = None
        response: httpx.Response | None = None

        start = time.perf_counter()
        while attempt < max_attempts:
            attempt += 1
            transient_status: int | None = None
            try:
                async with httpx.AsyncClient(timeout=request_timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json=payload,
                    )
                # 429 / 5xx transient — retry kapsamında
                if response.status_code == 429 or response.status_code >= 500:
                    transient_status = response.status_code
                    raise _TransientHTTP(response.status_code, response.text[:200])
                break  # success (2xx/4xx-non-rate)
            except (httpx.TimeoutException, httpx.RequestError, _TransientHTTP) as exc:
                last_error = exc
                if attempt < max_attempts:
                    # 429 için daha uzun backoff (rate limit cooldown)
                    if transient_status == 429:
                        backoff = 8.0 * attempt  # 8s, 16s, ...
                    else:
                        backoff = 2.0 * attempt  # 2s, 4s, ...
                    logger.warning(
                        "NIM chat transient error (attempt %d/%d): %s — retry in %.1fs",
                        attempt,
                        max_attempts,
                        type(exc).__name__,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    response = None  # reset for next iteration
                    continue
                # Tüm denemeler tükendi
                if isinstance(exc, httpx.TimeoutException):
                    raise ProviderTimeoutError(
                        f"NIM chat timeout after {request_timeout}s "
                        f"({max_attempts} attempts)"
                    ) from exc
                if isinstance(exc, _TransientHTTP) and exc.status == 429:
                    raise ProviderRateLimitError(
                        f"NIM chat rate limit ({max_attempts} attempts): {exc.body}"
                    ) from exc
                if isinstance(exc, _TransientHTTP):
                    raise ProviderError(
                        f"NIM chat server error ({exc.status}, "
                        f"{max_attempts} attempts): {exc.body}"
                    ) from exc
                raise ProviderError(
                    f"NIM chat network error after {max_attempts} attempts: {exc}"
                ) from exc

        if response is None:
            # Defensive — should never happen, loop ya success ya raise eder
            raise ProviderError(
                f"NIM chat unexpected state (last_error={last_error})"
            )

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code >= 400:
            raise ProviderError(
                f"NIM chat client error ({response.status_code}): {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(f"NIM chat invalid JSON: {exc}") from exc

        choices = data.get("choices", [])
        if not choices:
            raise ProviderError("NIM chat response empty choices")

        text = choices[0].get("message", {}).get("content", "") or ""
        if not text.strip():
            logger.warning(
                "NIM chat returned empty content (model=%s)", chosen_model
            )

        usage = data.get("usage", {}) or {}
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))

        # NIM free tier — cost 0
        cost_usd = 0.0

        return GenerationResult(
            text=text,
            model=data.get("model", chosen_model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            raw_response=data,
        )

    async def healthcheck(self) -> ProviderHealth:
        """Trivial 'ping' chat ile doğrula."""
        try:
            result = await self.generate_text(
                messages=[Message(role="user", content="ping")],
                max_tokens=4,
                temperature=0.0,
                timeout=10,
            )
            return ProviderHealth(healthy=True, latency_ms=result.latency_ms)
        except ProviderTimeoutError as exc:
            return ProviderHealth(healthy=False, error=f"timeout: {exc}")
        except ProviderError as exc:
            return ProviderHealth(healthy=False, error=str(exc)[:200])


def build_nim_chat_provider() -> NimChatProvider | None:
    """NIM_API_KEY varsa NimChatProvider döner, yoksa None.

    Registry bootstrap'ı bu pattern'i kullanır (NIM embedding gibi).
    """
    settings = get_settings()
    if not settings.nim_api_key or not settings.nim_api_key.get_secret_value():
        logger.info("NIM_API_KEY tanımlı değil — NimChatProvider skip")
        return None
    try:
        return NimChatProvider()
    except ValueError:
        return None
