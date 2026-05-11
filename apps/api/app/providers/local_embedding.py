"""Local embedding — sentence-transformers + bge-m3 (#163).

Primary embedding provider (NIM bge-m3 kaldırıldıktan sonra). CPU üzerinde
inference, ~100ms / batch (16 chunk). Build-time model preload Dockerfile'da.

docs/engineering/architecture.md §0 (LLM stack — local embedding)
docs/strategy/unit-economics.md §4.2 (cost: $0)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config import get_settings
from app.providers.base import (
    EmbeddingResult,
    ModelProvider,
    ProviderError,
    ProviderHealth,
    ProviderType,
)


logger = logging.getLogger(__name__)


# Default model id (build-time preload Dockerfile'da yapılır).
LOCAL_MODEL_NAME = "BAAI/bge-m3"

# bge-m3 vector dimension (NIM ile uyumlu — pgvector schema değişmez).
LOCAL_EMBEDDING_DIM = 1024


class LocalBgeM3Provider(ModelProvider):
    """sentence-transformers ile bge-m3 yerel embedding (primary, #163).

    Container içinde model preload edilir (Dockerfile build-time).
    İlk request: ~2-3s (model RAM'e yüklenir).
    Sonraki request'ler: ~50-150ms / batch.

    Lazy load: instance oluşturulurken model değil, ilk create_embedding'de.
    """

    # Registry name — local_bge_m3 (UI grafiklerinde NIM'den ayrılmak için).
    # Tüm embedding çağrıları bu provider üzerinden — registry name 'local_bge_m3'.
    name = "local_bge_m3"
    type = ProviderType.EMBEDDING

    supports_chat = False
    supports_embeddings = True
    supports_rerank = False
    supports_vision = False

    cost_per_1m_input_tokens = 0.0
    cost_per_1m_output_tokens = 0.0

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.local_embedding_model or LOCAL_MODEL_NAME
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

        load_start = time.perf_counter()
        self._model = SentenceTransformer(self._model_name)
        load_ms = int((time.perf_counter() - load_start) * 1000)
        logger.info(
            "LocalBgeM3 model loaded: %s (%d ms, dim=%d)",
            self._model_name,
            load_ms,
            LOCAL_EMBEDDING_DIM,
        )

    async def create_embedding(
        self,
        texts: list[str],
        model: str | None = None,
        mode: str = "passage",  # #681 — interface uyumu için (bge-m3 ignore eder)
    ) -> EmbeddingResult:
        """CPU embedding oluştur.

        Note: sentence-transformers async değil; thread executor'da çalıştır
        ki event loop bloklanmasın.

        Args:
            mode: bge-m3 için ignore edilir (asymmetric değil). E5 alternatif
                provider için "query" / "passage" prefix ekleme. Interface
                compatibility (#681 Faz 7b).
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
        """Dummy embedding ile gerçek loaded check."""
        try:
            start = time.perf_counter()
            result = await self.create_embedding(["ping"])
            latency = int((time.perf_counter() - start) * 1000)
            if result.vectors and len(result.vectors[0]) == LOCAL_EMBEDDING_DIM:
                return ProviderHealth(healthy=True, latency_ms=latency)
            return ProviderHealth(
                healthy=False,
                latency_ms=latency,
                error=f"Unexpected vector dim: got {len(result.vectors[0]) if result.vectors else 0}",
            )
        except Exception as e:
            return ProviderHealth(healthy=False, error=str(e))


def build_local_provider() -> LocalBgeM3Provider | None:
    """Factory — embedding tek provider (#420). Init fail ederse None döner.

    #163 primary registration; #350 migration tamamlandı 2026-05-06;
    #420 ile NIM fallback kaldırıldı, artık koşulsuz kayıt.
    Init başarısız olursa None döner — registry _fallback bir başka candidate
    olmadığı için RuntimeError fırlatır (embedding broken durumu).
    """
    try:
        return LocalBgeM3Provider()
    except Exception as exc:
        logger.warning("LocalBgeM3 init failed: %s", exc)
        return None
