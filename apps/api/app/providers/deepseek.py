"""DeepSeek native API chat provider (#163).

DeepSeek Chat Completions API (OpenAI-compatible).
NIM endpoint yerine direct API — daha hızlı (0.9-1.5s vs NIM 22-55s) ve cache desteği.

Models:
    - deepseek-v4-flash (V4 Flash — default, genel chat + reasoning)
        Eski 'deepseek-chat' adı kullanımdan kalktı; DeepSeek otomatik bu modele
        redirect ediyor. Açık ad ile referans verelim (#361).
    - deepseek-reasoner (R1 — reasoning-heavy, agenda card için kullanılabilir)

Pricing (2026 kampanya — %75 indirim, 2026-05-31 23:59 UTC'a kadar AKTİF):
    - input cache miss : $0.0675 / 1M token
    - input cache hit  : $0.0175 / 1M token  (4x ucuz)
    - output           : $0.275  / 1M token

docs/engineering/architecture.md §0 (LLM stack)
docs/strategy/unit-economics.md §4.2 (cost projection)
docs/legal/opinion-integration.md §3.5 (PII redaction LLM call öncesi şart)
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time
from collections.abc import AsyncIterator

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
    StreamChunk,
    ToolCall,
)


logger = logging.getLogger(__name__)


class _TransientHTTP(Exception):
    """Internal — 429 / 5xx retry signal."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"transient http {status}")
        self.status = status
        self.body = body


# Default chat model — deepseek-v4-flash. Default thinking mode aktif
# olduğundan payload'da "thinking": {"type": "disabled"} flag'i ile
# non-thinking mode'a zorlanır (response.content dolu, reasoning_content boş).
# api-docs.deepseek.com/guides/thinking_mode
# Eski model adı redirect ediyor ama explicit kullanmak audit/log netliği için doğru (#361).
DEEPSEEK_CHAT_DEFAULT_MODEL = "deepseek-v4-flash"


# Pricing (USD per 1M tokens).
# 2026 kampanya — %75 indirim 2026-05-31 23:59 UTC'a kadar AKTİF
# (settings.deepseek_campaign_discount). Bugün: 2026-05-07.
PRICE_INPUT_CACHE_MISS_PER_M = 0.27
PRICE_INPUT_CACHE_HIT_PER_M = 0.07
PRICE_OUTPUT_PER_M = 1.10


class DeepSeekProvider(ModelProvider):
    """DeepSeek native API chat provider (registry name='deepseek')."""

    type = ProviderType.LLM

    name = "deepseek"
    """Registry routing için sabit. NIM ile aynı isim — generation_log değişmez,
    backward-compatibility korunur."""

    supports_chat = True
    supports_embeddings = False
    supports_rerank = False
    supports_vision = False

    # Cache miss as base — runtime'da cache hit ile re-compute edilir
    cost_per_1m_input_tokens = PRICE_INPUT_CACHE_MISS_PER_M
    cost_per_1m_output_tokens = PRICE_OUTPUT_PER_M

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        """DeepSeek native API provider.

        Args:
            timeout: Per-request timeout (default 60s — DeepSeek 0.9-1.5s typical).
            max_retries: Transient hata (timeout/network/429/5xx) için retry sayısı.
        """
        settings = get_settings()
        self._api_key = (
            api_key
            or (settings.deepseek_api_key.get_secret_value() if settings.deepseek_api_key else "")
        )
        self._base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self._default_model = (
            default_model or settings.deepseek_chat_model or DEEPSEEK_CHAT_DEFAULT_MODEL
        )
        self._timeout = timeout
        self._max_retries = max_retries
        self._campaign_discount = float(settings.deepseek_campaign_discount)

        if not self._api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY env değişkeni gerekli (DeepSeekProvider)."
            )

    async def generate_text(
        self,
        messages: list[Message],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: int | None = None,
        json_mode: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> GenerationResult:
        """Chat completion (OpenAI-compatible).

        PII redaction USER mesajlarına uygulanır. System mesajı (bizim
        kontrolümüzdeki prompt) redact edilmez.

        #822 tool-use: `tools` verilirse OpenAI function calling formatında
        payload'a eklenir. LLM tool çağırırsa GenerationResult.tool_calls
        dolu döner. tool_call_id taşıyan 'tool' rolündeki mesajlar
        serialize edilir (multi-turn tool loop).
        """
        if not messages:
            raise ProviderError("messages list boş olamaz")

        chosen_model = model or self._default_model

        # PII redaction (KVKK / opinion-integration.md §3.5)
        # #822: tool/assistant mesajları redact edilmez (sistem üretimi);
        # sadece user content redact.
        sanitized: list[dict[str, Any]] = []
        total_redactions = 0
        for msg in messages:
            content = msg.content
            if msg.role == "user":
                redaction = redact(content)
                content = redaction.text
                total_redactions += redaction.total_redactions
            entry: dict[str, Any] = {"role": msg.role, "content": content}
            # #822 — assistant tool_calls serialize (OpenAI format)
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": _json.dumps(
                                tc.arguments, ensure_ascii=False
                            ),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            sanitized.append(entry)

        if total_redactions > 0:
            logger.info(
                "DeepSeek chat: PII redacted=%d in user messages (model=%s)",
                total_redactions,
                chosen_model,
            )

        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": sanitized,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            # DeepSeek v4-flash default thinking mode'da → response'da
            # reasoning_content dolu, content boş kalıyor. Non-thinking mode'a
            # zorla; tüm output content'te toplanır (api-docs/guides/thinking_mode).
            "thinking": {"type": "disabled"},
        }
        # #171 PR-E — DeepSeek JSON mode (deterministic JSON, parse error %90 azalır)
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        # #822 — tool-use (OpenAI-compatible function calling)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        request_timeout = timeout if timeout is not None else self._timeout

        # Retry: timeout/network/429/5xx
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
                if response.status_code == 429 or response.status_code >= 500:
                    transient_status = response.status_code
                    raise _TransientHTTP(response.status_code, response.text[:200])
                break  # success or 4xx-non-rate
            except (httpx.TimeoutException, httpx.RequestError, _TransientHTTP) as exc:
                last_error = exc
                if attempt < max_attempts:
                    backoff = 8.0 * attempt if transient_status == 429 else 2.0 * attempt
                    logger.warning(
                        "DeepSeek chat transient (attempt %d/%d): %s — retry %.1fs",
                        attempt,
                        max_attempts,
                        type(exc).__name__,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    response = None
                    continue
                if isinstance(exc, httpx.TimeoutException):
                    raise ProviderTimeoutError(
                        f"DeepSeek chat timeout after {request_timeout}s "
                        f"({max_attempts} attempts)"
                    ) from exc
                if isinstance(exc, _TransientHTTP) and exc.status == 429:
                    raise ProviderRateLimitError(
                        f"DeepSeek rate limit ({max_attempts} attempts): {exc.body}"
                    ) from exc
                if isinstance(exc, _TransientHTTP):
                    raise ProviderError(
                        f"DeepSeek server error ({exc.status}, "
                        f"{max_attempts} attempts): {exc.body}"
                    ) from exc
                raise ProviderError(
                    f"DeepSeek network error after {max_attempts} attempts: {exc}"
                ) from exc

        if response is None:
            raise ProviderError(
                f"DeepSeek chat unexpected state (last_error={last_error})"
            )

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code >= 400:
            raise ProviderError(
                f"DeepSeek chat client error ({response.status_code}): {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(f"DeepSeek invalid JSON: {exc}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("DeepSeek response empty choices")

        message = choices[0].get("message", {}) or {}
        text = message.get("content", "") or ""

        # #822 — tool_calls parse (OpenAI-compatible function calling)
        parsed_tool_calls: list[ToolCall] | None = None
        raw_tool_calls = message.get("tool_calls") or []
        if raw_tool_calls:
            parsed_tool_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {}) or {}
                raw_args = fn.get("arguments", "{}")
                try:
                    args = (
                        _json.loads(raw_args)
                        if isinstance(raw_args, str)
                        else (raw_args or {})
                    )
                except (ValueError, TypeError):
                    logger.warning(
                        "DeepSeek tool_call bad arguments JSON: %s",
                        str(raw_args)[:200],
                    )
                    args = {}
                parsed_tool_calls.append(
                    ToolCall(
                        id=str(tc.get("id") or ""),
                        name=str(fn.get("name") or ""),
                        arguments=args if isinstance(args, dict) else {},
                    )
                )

        if not text and not parsed_tool_calls:
            logger.warning("DeepSeek empty text for model=%s", chosen_model)

        # Token + cache parsing
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))

        # DeepSeek-specific: cache hit/miss breakdown
        cache_hit_tokens = int(
            usage.get("prompt_cache_hit_tokens")
            or usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        )
        cache_miss_tokens = max(input_tokens - cache_hit_tokens, 0)

        # Cost calculation (cache differential pricing × campaign discount)
        cost_usd = (
            cache_miss_tokens * PRICE_INPUT_CACHE_MISS_PER_M / 1_000_000
            + cache_hit_tokens * PRICE_INPUT_CACHE_HIT_PER_M / 1_000_000
            + output_tokens * PRICE_OUTPUT_PER_M / 1_000_000
        ) * self._campaign_discount

        # Returned model — API'nin response'unda gerçek model (V4-flash routing
        # gibi durumlar için)
        actual_model = data.get("model") or chosen_model

        if cache_hit_tokens > 0:
            logger.info(
                "DeepSeek cache hit: %d/%d tokens (%.1f%%, $%.6f saved)",
                cache_hit_tokens,
                input_tokens,
                100 * cache_hit_tokens / max(input_tokens, 1),
                cache_hit_tokens
                * (PRICE_INPUT_CACHE_MISS_PER_M - PRICE_INPUT_CACHE_HIT_PER_M)
                / 1_000_000
                * self._campaign_discount,
            )

        return GenerationResult(
            text=text,
            model=actual_model,
            tool_calls=parsed_tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cache_hit_tokens,
            cost_usd=round(cost_usd, 8),
            latency_ms=latency_ms,
            raw_response={"id": data.get("id"), "usage": usage},
        )

    async def generate_text_stream(
        self,
        messages: list[Message],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: int | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[StreamChunk]:
        """DeepSeek streaming chat completion (issue #527).

        SSE format (OpenAI-compatible):
            data: {"choices":[{"delta":{"content":"..."}}]}
            data: ...
            data: [DONE]

        Son chunk usage içerir (stream_options.include_usage=true ile).
        Her StreamChunk delta_text taşır; final chunk is_final=True ve usage
        + cost dolu.
        """
        if not messages:
            raise ProviderError("messages list boş olamaz")

        chosen_model = model or self._default_model

        # PII redaction (KVKK / opinion-integration.md §3.5)
        # #824 fix: tool message serialization (tool_calls + tool_call_id) —
        # generate_text ile aynı. Aşama 2 (tool sonrası final cevap) bu
        # mesajları streaming'e gönderir; eksikse DeepSeek 400 "missing
        # tool_call_id" → fallback non-streaming (TTFT bozulur).
        sanitized: list[dict[str, Any]] = []
        total_redactions = 0
        for msg in messages:
            content = msg.content
            if msg.role == "user":
                redaction = redact(content)
                content = redaction.text
                total_redactions += redaction.total_redactions
            entry: dict[str, Any] = {"role": msg.role, "content": content}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": _json.dumps(
                                tc.arguments, ensure_ascii=False
                            ),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            sanitized.append(entry)

        if total_redactions > 0:
            logger.info(
                "DeepSeek stream: PII redacted=%d in user messages (model=%s)",
                total_redactions,
                chosen_model,
            )

        payload = {
            "model": chosen_model,
            "messages": sanitized,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
            "thinking": {"type": "disabled"},
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        request_timeout = timeout if timeout is not None else self._timeout

        # Streaming için tek attempt — orta-stream başarısız olursa caller
        # restart etsin. Connection açma 429/5xx için pre-stream retry yapar.
        start = time.perf_counter()
        accumulated_input_tokens = 0
        accumulated_output_tokens = 0
        accumulated_cache_hit = 0
        actual_model = chosen_model

        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                    json=payload,
                ) as response:
                    if response.status_code == 429:
                        body = await response.aread()
                        raise ProviderRateLimitError(
                            f"DeepSeek rate limit: {body[:200].decode('utf-8', errors='replace')}"
                        )
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise ProviderError(
                            f"DeepSeek stream error ({response.status_code}): "
                            f"{body[:200].decode('utf-8', errors='replace')}"
                        )

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            continue
                        if not data_str:
                            continue
                        try:
                            event = _json.loads(data_str)
                        except ValueError:
                            logger.warning(
                                "DeepSeek stream: bad JSON in chunk: %s",
                                data_str[:100],
                            )
                            continue

                        actual_model = event.get("model") or actual_model

                        # Usage chunk — stream_options.include_usage=true ile son
                        # chunk'ta gelir. choices boş, usage dolu.
                        if event.get("usage"):
                            usage = event["usage"]
                            accumulated_input_tokens = int(
                                usage.get("prompt_tokens", 0)
                            )
                            accumulated_output_tokens = int(
                                usage.get("completion_tokens", 0)
                            )
                            accumulated_cache_hit = int(
                                usage.get("prompt_cache_hit_tokens")
                                or usage.get("prompt_tokens_details", {}).get(
                                    "cached_tokens", 0
                                )
                            )

                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {}) or {}
                        delta_content = delta.get("content") or ""
                        if delta_content:
                            yield StreamChunk(
                                delta_text=delta_content,
                                is_final=False,
                                raw_event=event,
                            )

        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"DeepSeek stream timeout after {request_timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"DeepSeek stream network error: {exc}") from exc

        # Final summary chunk — cost hesabı
        cache_miss = max(accumulated_input_tokens - accumulated_cache_hit, 0)
        cost_usd = (
            cache_miss * PRICE_INPUT_CACHE_MISS_PER_M / 1_000_000
            + accumulated_cache_hit * PRICE_INPUT_CACHE_HIT_PER_M / 1_000_000
            + accumulated_output_tokens * PRICE_OUTPUT_PER_M / 1_000_000
        ) * self._campaign_discount

        latency_ms = int((time.perf_counter() - start) * 1000)
        if accumulated_cache_hit > 0:
            logger.info(
                "DeepSeek stream cache hit: %d/%d tokens (latency %dms)",
                accumulated_cache_hit,
                accumulated_input_tokens,
                latency_ms,
            )

        yield StreamChunk(
            delta_text="",
            is_final=True,
            input_tokens=accumulated_input_tokens,
            output_tokens=accumulated_output_tokens,
            cached_input_tokens=accumulated_cache_hit,
            cost_usd=round(cost_usd, 8),
            model=actual_model,
        )

    async def healthcheck(self) -> ProviderHealth:
        """Lightweight ping — chat completion'a 'ping' gönder."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._default_model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                    },
                )
            latency = int((time.perf_counter() - start) * 1000)
            if response.status_code == 200:
                return ProviderHealth(healthy=True, latency_ms=latency)
            return ProviderHealth(
                healthy=False,
                latency_ms=latency,
                error=f"HTTP {response.status_code}",
            )
        except httpx.TimeoutException as exc:
            return ProviderHealth(healthy=False, error=f"timeout: {exc}")
        except httpx.RequestError as exc:
            return ProviderHealth(healthy=False, error=f"network: {exc}")


def build_deepseek_provider(timeout: float | None = None) -> DeepSeekProvider | None:
    """DEEPSEEK_API_KEY varsa DeepSeekProvider döner, yoksa None.

    Args:
        timeout: HTTP timeout (s). None ise class default (60s) kullanılır.
            Async bootstrap (#273) settings_store'dan okuyup geçirir.
    """
    settings = get_settings()
    if not settings.deepseek_api_key or not settings.deepseek_api_key.get_secret_value():
        logger.info("DEEPSEEK_API_KEY tanımlı değil — DeepSeekProvider skip")
        return None
    try:
        if timeout is not None:
            return DeepSeekProvider(timeout=timeout)
        return DeepSeekProvider()
    except ValueError:
        return None
