"""Local embedding — intfloat/multilingual-e5-large (#681 Faz 7b).

Alternative embedding provider to bge-m3. Türkçe için kalibre
(mc4-tr corpus training). 1024-dim → bge-m3 ile schema-compatible.

ASYMMETRIC RETRIEVAL PATTERN (KRİTİK):
e5 modelleri "query: " ve "passage: " prefix gerektirir. Yoksa retrieval
quality dramatic olarak düşer. Bu wrapper text tipine göre otomatik prefix
ekler:
  - mode="query" → "query: <text>" (sorgu vector'ü)
  - mode="passage" → "passage: <text>" (chunk vector'ü)

Default mode "passage" (chunk indexing için). Query embedding sırasında
caller `mode="query"` parametresi geçirir veya provider-level alternatif
metod `embed_query()` kullanır.

docs/engineering/architecture.md §0 (LLM stack — local embedding)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

from app.config import get_settings
from app.providers.base import (
    EmbeddingResult,
    ModelProvider,
    ProviderError,
    ProviderHealth,
    ProviderType,
)


logger = logging.getLogger(__name__)


# intfloat/multilingual-e5-large — 1024-dim, Türkçe kalibre
LOCAL_E5_MODEL_NAME = "intfloat/multilingual-e5-large"
LOCAL_E5_EMBEDDING_DIM = 1024


# E5 asymmetric retrieval prefixes (ZORUNLU — yoksa retrieval bozulur)
_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "


class LocalE5Provider(ModelProvider):
    """sentence-transformers ile intfloat/multilingual-e5-large.

    A/B test için bge-m3 alternative. Settings flag `embedding.provider`
    ile seçilir (default bge-m3). E5 multi-language modeli Türkçe için
    daha iyi kalibre (mc4-tr training).

    Asymmetric retrieval prefix ZORUNLU:
      - encode("query: Karşıyaka hakemleri") → sorgu vector'ü
      - encode("passage: ... maçın hakemleri ...") → chunk vector'ü
    Bu wrapper mode parametresi ile otomatik prefix ekler.
    """

    name = "local_e5_multilingual"
    type = ProviderType.EMBEDDING

    supports_chat = False
    supports_embeddings = True
    supports_rerank = False
    supports_vision = False

    cost_per_1m_input_tokens = 0.0
    cost_per_1m_output_tokens = 0.0

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        # E5 model adı override edilebilir (test için farklı e5 variant)
        self._model_name = (
            model_name
            or getattr(settings, "local_e5_model", None)
            or LOCAL_E5_MODEL_NAME
        )
        self._model: Any = None  # lazy load

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ProviderError(
                "sentence-transformers paketi yüklü değil. "
                "pip install sentence-transformers"
            ) from e

        load_start = time.perf_counter()
        self._model = SentenceTransformer(self._model_name)
        load_ms = int((time.perf_counter() - load_start) * 1000)
        logger.info(
            "LocalE5 model loaded: %s (%d ms, dim=%d)",
            self._model_name,
            load_ms,
            LOCAL_E5_EMBEDDING_DIM,
        )

    def _apply_prefix(
        self, texts: list[str], mode: Literal["query", "passage"]
    ) -> list[str]:
        """E5 asymmetric prefix ekle.

        Eğer text zaten prefix taşıyorsa double-prefix yapma.
        """
        prefix = _QUERY_PREFIX if mode == "query" else _PASSAGE_PREFIX
        out: list[str] = []
        for t in texts:
            s = t.lstrip()
            if s.startswith("query:") or s.startswith("passage:"):
                # Caller manuel prefix vermiş, dokunma
                out.append(t)
            else:
                out.append(prefix + t)
        return out

    async def create_embedding(
        self,
        texts: list[str],
        model: str | None = None,
        mode: Literal["query", "passage"] = "passage",
    ) -> EmbeddingResult:
        """E5 encoding — default passage prefix (chunk indexing için).

        Args:
            texts: Embedlenecek metinler
            model: Model adı override (yoksa instance default)
            mode: "query" veya "passage" — e5 asymmetric prefix
                Default "passage" (chunker + summary worker chunk metni embedler).
                Retrieval sorgusu için caller `mode="query"` geçirmeli.
        """
        if not texts:
            return EmbeddingResult(vectors=[], model=self._model_name)

        self._ensure_model_loaded()

        # Asymmetric prefix uygula
        prefixed_texts = self._apply_prefix(texts, mode=mode)

        start = time.perf_counter()
        embeddings = await asyncio.to_thread(
            self._model.encode,
            prefixed_texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)

        vectors = embeddings.tolist()
        approx_tokens = sum(max(1, len(t) // 4) for t in texts)

        return EmbeddingResult(
            vectors=vectors,
            model=self._model_name,
            input_tokens=approx_tokens,
            cost_usd=0.0,
            latency_ms=latency_ms,
        )

    async def embed_query(self, query: str) -> list[float] | None:
        """Convenience helper — sorgu embedding'i (e5 query prefix ile)."""
        result = await self.create_embedding([query], mode="query")
        return result.vectors[0] if result.vectors else None

    async def healthcheck(self) -> ProviderHealth:
        try:
            start = time.perf_counter()
            result = await self.create_embedding(["ping"], mode="passage")
            latency = int((time.perf_counter() - start) * 1000)
            if result.vectors and len(result.vectors[0]) == LOCAL_E5_EMBEDDING_DIM:
                return ProviderHealth(healthy=True, latency_ms=latency)
            return ProviderHealth(
                healthy=False,
                latency_ms=latency,
                error=f"Unexpected vector dim: got {len(result.vectors[0]) if result.vectors else 0}",
            )
        except Exception as e:
            return ProviderHealth(healthy=False, error=str(e))


def build_local_e5_provider() -> LocalE5Provider | None:
    """Factory — E5 alternative provider. Init fail ederse None döner."""
    try:
        return LocalE5Provider()
    except Exception as exc:
        logger.warning("LocalE5 init failed: %s", exc)
        return None
