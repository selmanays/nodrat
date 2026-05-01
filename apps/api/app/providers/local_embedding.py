"""Local embedding fallback — sentence-transformers + bge-m3.

NIM provider çalışmadığında veya rate-limit'e takıldığında devreye girer.
CPU üzerinde yavaş ama sınırsız + maliyet sıfır.

docs/strategy/unit-economics.md §4.2 (provider routing fallback)
"""

from __future__ import annotations

import time
from typing import Any

from app.providers.base import (
    EmbeddingResult,
    ModelProvider,
    ProviderError,
    ProviderHealth,
    ProviderType,
)


# Yerel model — sentence-transformers altyapısıyla bge-m3
LOCAL_MODEL_NAME = "BAAI/bge-m3"
"""Hugging Face model id. İlk çağrıda otomatik download (~2GB)."""

LOCAL_EMBEDDING_DIM = 1024


class LocalBgeM3Provider(ModelProvider):
    """sentence-transformers ile bge-m3 yerel embedding.

    İlk yükleme yavaş (model download); sonrası CPU inference.
    Production'da NIM rate-limit'e takılırsa fallback.

    Lazy load: instance oluşturulurken model değil, ilk create_embedding'de.
    """

    name = "local_bge_m3"
    type = ProviderType.EMBEDDING

    supports_chat = False
    supports_embeddings = True
    supports_rerank = False
    supports_vision = False

    cost_per_1m_input_tokens = 0.0
    cost_per_1m_output_tokens = 0.0

    def __init__(self, model_name: str = LOCAL_MODEL_NAME) -> None:
        self._model_name = model_name
        self._model: Any = None  # lazy load

    def _ensure_model_loaded(self) -> None:
        """Model'i ilk kullanımda yükle (memory + disk impact)."""
        if self._model is not None:
            return

        try:
            # Lazy import — sentence-transformers başlangıçta yüklenmemeli
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ProviderError(
                "sentence-transformers paketi yüklü değil. "
                "pip install sentence-transformers"
            ) from e

        self._model = SentenceTransformer(self._model_name)

    async def create_embedding(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> EmbeddingResult:
        """CPU embedding oluştur.

        Note: sentence-transformers async değil; thread executor'da çalıştır
        ki event loop bloklanmasın.
        """
        if not texts:
            return EmbeddingResult(vectors=[], model=self._model_name)

        self._ensure_model_loaded()

        start = time.perf_counter()

        # asyncio.to_thread (Python 3.9+) — event loop blocking yok
        import asyncio

        embeddings = await asyncio.to_thread(
            self._model.encode,
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        latency_ms = int((time.perf_counter() - start) * 1000)

        # numpy array → list[list[float]]
        vectors = embeddings.tolist()

        # Token sayısı yaklaşık (sentence-transformers tokenizer kullanır)
        # Ortalama: ~1.3 token per word, ~5 char per word
        approx_tokens = sum(max(1, len(t) // 4) for t in texts)

        return EmbeddingResult(
            vectors=vectors,
            model=self._model_name,
            input_tokens=approx_tokens,
            cost_usd=0.0,
            latency_ms=latency_ms,
        )

    async def healthcheck(self) -> ProviderHealth:
        """Model loaded mı kontrol — lazy load değilse loadla."""
        try:
            self._ensure_model_loaded()
            return ProviderHealth(healthy=True, latency_ms=0)
        except Exception as e:
            return ProviderHealth(healthy=False, error=str(e))


def build_local_provider() -> LocalBgeM3Provider:
    """Factory — local provider her zaman aktif (fallback)."""
    return LocalBgeM3Provider()
