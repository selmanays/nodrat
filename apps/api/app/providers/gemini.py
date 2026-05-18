"""Google Gemini API chat provider (#778) — Gemma 4 modelleri ücretsiz tier.

Gemini API üzerinden Gemma 4 modellerine erişim. DeepSeek alternatifi olarak
admin /settings'ten per-operation seçilebilir (NER, planner, rerank, generation).

Models:
    - gemma-4-26b-a4b-it (default — MoE, 4B active params, hızlı)
    - gemma-4-31b-it (premium — 256K context, kalite ağırlıklı)

Pricing:
    Gemma modelleri free tier'da, 15 req/min limit (Gemini API).
    cost_usd alanı her zaman 0 — telemetri tutarlı kalır.

API contract (Gemini v1beta — generativelanguage.googleapis.com):
    POST /models/{model}:generateContent?key={api_key}
    body: contents (role/parts), generationConfig (temperature, maxOutputTokens,
          responseMimeType for JSON), systemInstruction (system prompt)
"""

from __future__ import annotations

import asyncio
import json as _json
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
    """Internal — 429 / 5xx retry signal."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"transient http {status}")
        self.status = status
        self.body = body


# Default model — Gemma 4 26B A4B IT (MoE, 4B active, hızlı; v1beta API'de
# generateContent destekli iki Gemma'dan biri). Free tier limit: 1.5K req/gün,
# 15 RPM. Bulk backfill için yetersiz (12K chunk), per-user request için yeter.
# NOT: Gemma 3 modelleri (1B/4B/12B/27B/2B) Google Console'da görünür ama
# v1beta `generateContent` ile çağrılamaz (404). Eklenirlerse fallback chain
# revisit edilmeli (ListModels ile çıkan tüm modelleri ekle).
GEMINI_DEFAULT_MODEL = "gemma-4-26b-a4b-it"

# Fallback cascade — daily quota exhausted (429) durumunda sıralı dener.
# Sadece v1beta'da `generateContent` destekli modeller buraya konur (ListModels
# ile doğrulandı, 2026-05-14). Her Gemma 4 model 1.5K/gün = toplam 3K free kapasite.
GEMINI_FALLBACK_MODELS: list[str] = [
    "gemma-4-26b-a4b-it",  # 1.5K/gün, 15 RPM — primary (MoE speed)
    "gemma-4-31b-it",  # 1.5K/gün, 15 RPM — secondary (256K context)
]

# Default base URL — Google Gemini API v1beta
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Ücretsiz tier — cost 0 (rate limit 15 req/min Gemini API'da)
PRICE_INPUT_PER_M = 0.0
PRICE_OUTPUT_PER_M = 0.0


class GeminiProvider(ModelProvider):
    """Google Gemini API chat provider (registry name='gemini').

    Gemma 4 modelleri için kullanılır. DeepSeek ile aynı interface — admin
    /settings'ten per-operation routing değiştirilebilir (#778).
    """

    type = ProviderType.LLM
    name = "gemini"
    supports_chat = True
    supports_embeddings = False
    supports_rerank = False
    supports_vision = False
    cost_per_1m_input_tokens = PRICE_INPUT_PER_M
    cost_per_1m_output_tokens = PRICE_OUTPUT_PER_M

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or (
            settings.google_api_key.get_secret_value() if settings.google_api_key else ""
        )
        self._base_url = (base_url or GEMINI_BASE_URL).rstrip("/")
        self._default_model = default_model or GEMINI_DEFAULT_MODEL
        self._timeout = timeout
        self._max_retries = max_retries

        if not self._api_key:
            raise ValueError("GOOGLE_API_KEY env değişkeni gerekli (GeminiProvider).")

    @staticmethod
    def _convert_messages(messages: list[Message]) -> tuple[str | None, list[dict]]:
        """OpenAI-style messages → Gemini contents + systemInstruction.

        Gemini API system prompt'u ayrı bir alanda alır (systemInstruction).
        User/assistant mesajları contents[] içinde role=user/model parts[text].
        """
        system_prompt: str | None = None
        contents: list[dict] = []
        for msg in messages:
            if msg.role == "system":
                # Gemini sadece tek systemInstruction kabul eder — birleştir
                system_prompt = f"{system_prompt}\n{msg.content}" if system_prompt else msg.content
                continue
            role = "model" if msg.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        return system_prompt, contents

    async def generate_text(
        self,
        messages: list[Message],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: int | None = None,
        json_mode: bool = False,
        tools: list[dict] | None = None,  # Gemini OpenAI-tool ignore — base
        tool_choice: str = "auto",  # sözleşmesi (LSP; chat→DeepSeek)
    ) -> GenerationResult:
        """Chat completion via Gemini API.

        PII redaction USER mesajlarına uygulanır (KVKK / opinion-integration.md §3.5).
        Gemini API key URL'de query param olarak gider (?key=...).
        """
        if not messages:
            raise ProviderError("messages list boş olamaz")

        # Caller verdiyse sadece o model — fallback yok. Aksi halde default
        # ile başla, 429 durumunda cascade chain üzerinden ilerle.
        if model:
            model_candidates = [model]
        else:
            # Default'u başa koy + chain'den geri kalanlar (dedup, sıra koru)
            seen = {self._default_model}
            model_candidates = [self._default_model]
            for m in GEMINI_FALLBACK_MODELS:
                if m not in seen:
                    model_candidates.append(m)
                    seen.add(m)

        chosen_model = model_candidates[0]

        # PII redaction (user messages only)
        sanitized: list[Message] = []
        total_redactions = 0
        for msg in messages:
            content = msg.content
            if msg.role == "user":
                redaction = redact(content)
                content = redaction.text
                total_redactions += redaction.total_redactions
            sanitized.append(Message(role=msg.role, content=content))

        if total_redactions > 0:
            logger.info(
                "Gemini chat: PII redacted=%d in user messages (model=%s)",
                total_redactions,
                chosen_model,
            )

        system_prompt, contents = self._convert_messages(sanitized)

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
            # NOT: Gemma 4 default'ta chain-of-thought ile JSON üretir (uzun
            # reasoning + sonda JSON). thinkingBudget=0 Gemini 2.x destekli
            # ama Gemma 4'te 400 INVALID_ARGUMENT — kaldırıldı. JSON çıkışı
            # caller'da extract edilir (robust JSON parser).

        request_timeout = timeout if timeout is not None else self._timeout
        t0 = time.perf_counter()
        last_exc: Exception | None = None

        # Outer loop: model cascade (429 daily-quota → next model)
        for model_idx, current_model in enumerate(model_candidates):
            chosen_model = current_model
            url = f"{self._base_url}/models/{chosen_model}:generateContent?key={self._api_key}"

            attempt = 0
            quota_exhausted = False

            while attempt <= self._max_retries:
                try:
                    async with httpx.AsyncClient(timeout=request_timeout) as client:
                        resp = await client.post(url, json=payload)

                    if resp.status_code == 429:
                        raise _TransientHTTP(429, resp.text[:300])
                    if resp.status_code >= 500:
                        raise _TransientHTTP(resp.status_code, resp.text[:300])
                    if resp.status_code >= 400:
                        body_excerpt = resp.text[:300]
                        raise ProviderError(f"Gemini API {resp.status_code}: {body_excerpt}")

                    data = resp.json()
                    latency_ms = int((time.perf_counter() - t0) * 1000)

                    # Parse response
                    candidates = data.get("candidates", [])
                    if not candidates:
                        # Gemini may return empty if blocked by safety filters
                        block_reason = data.get("promptFeedback", {}).get("blockReason", "unknown")
                        raise ProviderError(f"Gemini empty response (block_reason={block_reason})")

                    content_parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in content_parts)

                    usage = data.get("usageMetadata", {}) or {}
                    input_tokens = int(usage.get("promptTokenCount", 0))
                    output_tokens = int(usage.get("candidatesTokenCount", 0))

                    # Gemma ücretsiz — cost 0
                    cost_usd = 0.0

                    if model_idx > 0:
                        logger.info(
                            "Gemini cascade success: fell back to %s (idx=%d)",
                            chosen_model,
                            model_idx,
                        )

                    return GenerationResult(
                        text=text,
                        model=chosen_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cached_input_tokens=0,
                        cost_usd=cost_usd,
                        latency_ms=latency_ms,
                        raw_response=data,
                    )

                except _TransientHTTP as exc:
                    last_exc = exc
                    attempt += 1
                    # 429 + body içinde "PerDay"/"daily" → quota exhausted, cascade
                    body_lc = (exc.body or "").lower()
                    is_daily_quota = exc.status == 429 and (
                        "perday" in body_lc
                        or "daily" in body_lc
                        or ("quota" in body_lc and "minute" not in body_lc)
                    )
                    if attempt > self._max_retries or is_daily_quota:
                        if exc.status == 429:
                            quota_exhausted = True
                            logger.warning(
                                "Gemini %s rate/quota exhausted (status=429, daily=%s), "
                                "attempting cascade",
                                chosen_model,
                                is_daily_quota,
                            )
                            break  # break inner retry loop, try next model
                        raise ProviderError(
                            f"Gemini {exc.status} after {self._max_retries} retries: {exc.body}"
                        ) from exc
                    # Per-minute rate limit → exponential backoff retry same model
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                except httpx.TimeoutException as exc:
                    last_exc = exc
                    attempt += 1
                    if attempt > self._max_retries:
                        raise ProviderTimeoutError(
                            f"Gemini timeout after {self._max_retries} retries"
                        ) from exc
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                except (httpx.RequestError, httpx.NetworkError) as exc:
                    last_exc = exc
                    attempt += 1
                    if attempt > self._max_retries:
                        raise ProviderError(f"Gemini network error: {exc}") from exc
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue

            # while exited without return/raise → quota exhausted; for moves to next model
            if not quota_exhausted:
                break  # non-429 issue, don't cascade

        # All models exhausted — raise rate limit error
        raise ProviderRateLimitError(
            f"Gemini all models exhausted (tried {len(model_candidates)} models): {last_exc}"
        ) from (last_exc if isinstance(last_exc, Exception) else None)

    async def generate_structured_json(
        self,
        messages: list[Message],
        schema: dict,
        model: str | None = None,
        max_tokens: int = 1024,
        timeout: int = 30,
    ) -> dict:
        """JSON output via responseMimeType=application/json + parse."""
        result = await self.generate_text(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=0.1,
            timeout=timeout,
            json_mode=True,
        )
        try:
            return _json.loads(result.text.strip())
        except _json.JSONDecodeError as exc:
            raise ProviderError(
                f"Gemini structured JSON parse fail: {exc}; text={result.text[:200]}"
            ) from exc

    async def healthcheck(self) -> ProviderHealth:
        """Basic health probe — minimal prompt."""
        try:
            t0 = time.perf_counter()
            await self.generate_text(
                messages=[Message(role="user", content="ok")],
                max_tokens=5,
                temperature=0.0,
                timeout=15,
            )
            return ProviderHealth(
                healthy=True,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        except Exception as exc:
            return ProviderHealth(healthy=False, error=str(exc)[:200])


def build_gemini_provider(
    *, api_key: str | None = None, default_model: str | None = None, timeout: float = 60.0
) -> GeminiProvider | None:
    """Factory — ENV / settings'tan parametre okur, GOOGLE_API_KEY yoksa None."""
    settings = get_settings()
    key = api_key or (settings.google_api_key.get_secret_value() if settings.google_api_key else "")
    if not key:
        return None
    return GeminiProvider(api_key=key, default_model=default_model, timeout=timeout)


__all__ = [
    "GEMINI_DEFAULT_MODEL",
    "GeminiProvider",
    "build_gemini_provider",
]
