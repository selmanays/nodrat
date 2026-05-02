"""NVIDIA NIM rerank provider (#181).

Endpoint: POST {base_url}/retrieval/nvidia/reranking (or model-specific)
Model:    nvidia/nv-rerankqa-mistral-4b-v3 (default)
Auth:     Authorization: Bearer {NIM_API_KEY}

Request:
    {
        "model": "...",
        "query": {"text": "..."},
        "passages": [{"text": "..."}, ...]
    }

Response:
    {
        "rankings": [
            {"index": 0, "logit": 1.234},
            {"index": 2, "logit": 0.987},
            ...
        ]
    }

NIM rerank free tier'a dahil (NIM_API_KEY ile aynı auth). RAGFlow esinlenmesi:
RRF top-K → cross-encoder rerank → final top-N.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import get_settings
from app.providers.base import (
    ModelProvider,
    ProviderError,
    ProviderHealth,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderType,
    RerankResult,
)


NIM_DEFAULT_RERANK_MODEL = "nvidia/rerank-qa-mistral-4b"
"""Multilingual cross-encoder, query×passage relevance score üretir.

Diğer NIM available alternatifler: nv-rerank-qa-mistral-4b:1
"""


class NimRerankProvider(ModelProvider):
    """NIM rerank API adapter."""

    name = "nim_rerank"
    type = ProviderType.RERANK

    supports_chat = False
    supports_embeddings = False
    supports_rerank = True
    supports_vision = False

    cost_per_1m_input_tokens = 0.0
    cost_per_1m_output_tokens = 0.0

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = NIM_DEFAULT_RERANK_MODEL,
        timeout: float = 15.0,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.nim_api_key.get_secret_value()
        # NIM rerank ayrı host — ai.api.nvidia.com tipik
        self._base_url = (
            base_url
            or getattr(settings, "nim_rerank_base_url", "https://ai.api.nvidia.com/v1")
        ).rstrip("/")
        self._default_model = default_model
        self._timeout = timeout

        if not self._api_key:
            raise ValueError("NIM_API_KEY env değişkeni gerekli (NimRerankProvider).")

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 10,
        model: str | None = None,
    ) -> list[RerankResult]:
        """Query × documents → relevance-sorted RerankResult list.

        Args:
            query: User query (sorgu metni)
            documents: Aday passage'lar (50 öneri max)
            top_k: Döndürülecek en üst N sonuç
            model: NIM model adı (None ise default)

        Returns:
            RerankResult listesi (logit-desc sıralı), score = logit raw
            (cross-provider normalize, 0-1 range için sigmoid uygulanabilir).
        """
        if not query or not documents:
            return []

        model_name = model or self._default_model
        # NIM endpoint: model adı path'in son segmenti olabiliyor; conservative
        # yaklaşım: /retrieval/nvidia/reranking + body'de model
        url = f"{self._base_url}/retrieval/nvidia/reranking"

        payload = {
            "model": model_name,
            "query": {"text": query[:4000]},
            "passages": [{"text": d[:4000]} for d in documents[:50]],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"NIM rerank timeout after {self._timeout}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"NIM rerank network error: {exc}") from exc

        latency_ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code == 429:
            raise ProviderRateLimitError(
                f"NIM rerank rate limit: {resp.text[:200]}"
            )
        if resp.status_code >= 500:
            raise ProviderError(
                f"NIM rerank 5xx ({resp.status_code}): {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise ProviderError(
                f"NIM rerank 4xx ({resp.status_code}): {resp.text[:200]}"
            )

        try:
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            raise ProviderError(f"NIM rerank invalid JSON: {exc}") from exc

        rankings = data.get("rankings", [])
        results: list[RerankResult] = []
        for r in rankings:
            try:
                idx = int(r["index"])
                score = float(r.get("logit", 0.0))
            except (KeyError, ValueError, TypeError):
                continue
            results.append(RerankResult(index=idx, score=score))

        # Score-desc sırala (NIM zaten sıralı döndürüyor ama emniyet)
        results.sort(key=lambda x: x.score, reverse=True)
        # latency'i raw_response yerine logger üzerinden raporlamak istersen
        _ = latency_ms
        return results[:top_k]

    async def healthcheck(self) -> ProviderHealth:
        """Tek probe rerank ile health."""
        try:
            await self.rerank("test", ["sample document"], top_k=1)
            return ProviderHealth(healthy=True)
        except Exception as exc:
            return ProviderHealth(healthy=False, error=str(exc)[:200])
