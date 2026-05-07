"""NVIDIA NIM provider — embedding adapter (Issue #6).

Default model: nvidia/nv-embedqa-e5-v5 (1024-dim, NIM stable)
Backup: baai/bge-m3 (NIM bazen 500 hatası veriyor; local fallback'e geç)

API docs: https://docs.api.nvidia.com/nim/reference/embeddings

Ücretlendirme: NIM free tier (developer hesap, rate limit'li)
docs/strategy/unit-economics.md §1.3
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import get_settings
from app.providers.base import (
    EmbeddingResult,
    ModelProvider,
    ProviderError,
    ProviderHealth,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderType,
)


# NIM embedding modelleri — bu sürümde aktif default
NIM_DEFAULT_MODEL = "nvidia/nv-embedqa-e5-v5"
"""1024-dim, multilingual, NIM stable.

bge-m3 NIM'de bazen 500 hatası veriyor; bu yüzden default değiştirildi.
Local fallback olarak sentence-transformers ile bge-m3 hala kullanılabilir.
"""

NIM_EMBEDDING_DIM = 1024
"""pgvector article_chunks.embedding ile uyumlu (data-model.md §4.1)."""


class NimEmbeddingProvider(ModelProvider):
    """NVIDIA NIM Embedding API adapter.

    Endpoint: POST {base_url}/embeddings
    Auth:     Authorization: Bearer {NIM_API_KEY}
    """

    name = "nim_bge_m3"  # registry name (legacy; aslında nv-embedqa-e5-v5 kullanıyor)
    type = ProviderType.EMBEDDING

    supports_chat = False
    supports_embeddings = True
    supports_rerank = False
    supports_vision = False

    # Free tier — gerçek maliyet sıfır (ama NV usage tracking için tutulur)
    cost_per_1m_input_tokens = 0.0
    cost_per_1m_output_tokens = 0.0

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = NIM_DEFAULT_MODEL,
        timeout: float = 30.0,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.nim_api_key.get_secret_value()
        self._base_url = (base_url or settings.nim_base_url).rstrip("/")
        self._default_model = default_model
        self._timeout = timeout

        if not self._api_key:
            raise ValueError(
                "NIM_API_KEY env değişkeni gerekli (NimEmbeddingProvider)."
            )

    async def create_embedding(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> EmbeddingResult:
        """Batch embedding oluştur.

        Args:
            texts: Embed edilecek metinler (max ~512 token per text)
            model: NIM model adı; None ise default kullanılır

        Returns:
            EmbeddingResult: vectors + token count + latency

        Raises:
            ProviderError: API hatası
            ProviderRateLimitError: 429
            ProviderTimeoutError: timeout
        """
        if not texts:
            return EmbeddingResult(vectors=[], model=model or self._default_model)

        chosen_model = model or self._default_model

        payload = {
            "input": texts,
            "model": chosen_model,
            "encoding_format": "float",
            "input_type": "passage",  # NV-Embed modelleri için
            "truncate": "END",  # Uzun metinleri sondan kes (haber içeriği için)
        }

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"NIM embedding timeout: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"NIM HTTP error: {e}") from e

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code == 429:
            raise ProviderRateLimitError(
                f"NIM rate limit (429). Retry-After: {response.headers.get('Retry-After')}"
            )

        if response.status_code >= 500:
            raise ProviderError(
                f"NIM server error ({response.status_code}): {response.text[:200]}"
            )

        if response.status_code != 200:
            raise ProviderError(
                f"NIM error ({response.status_code}): {response.text[:200]}"
            )

        data = response.json()

        if "data" not in data:
            raise ProviderError(f"NIM unexpected response: {data}")

        vectors = [item["embedding"] for item in data["data"]]
        usage = data.get("usage", {})

        return EmbeddingResult(
            vectors=vectors,
            model=chosen_model,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            cost_usd=0.0,  # NIM free tier
            latency_ms=latency_ms,
        )

    async def healthcheck(self) -> ProviderHealth:
        """NIM /models endpoint ile basit ping.

        Returns:
            ProviderHealth: healthy + latency
        """
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
            latency_ms = int((time.perf_counter() - start) * 1000)

            if response.status_code == 200:
                return ProviderHealth(healthy=True, latency_ms=latency_ms)
            return ProviderHealth(
                healthy=False,
                latency_ms=latency_ms,
                error=f"HTTP {response.status_code}",
            )
        except Exception as e:
            return ProviderHealth(healthy=False, error=str(e))


def build_nim_provider(timeout: float | None = None) -> NimEmbeddingProvider | None:
    """Factory — config'den NIM provider oluştur.

    None döner: NIM_API_KEY yoksa veya boşsa.

    Args:
        timeout: HTTP timeout (s). None ise class default (30s) kullanılır.
            Async bootstrap (#273) settings_store'dan okuyup geçirir.
    """
    settings = get_settings()
    if not settings.nim_api_key.get_secret_value():
        return None
    if timeout is not None:
        return NimEmbeddingProvider(timeout=timeout)
    return NimEmbeddingProvider()
