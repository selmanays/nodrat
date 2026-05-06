"""Local cross-encoder rerank — sentence-transformers BGE-reranker-v2-m3 (#224 PR-9).

Cross-encoder modeli query×passage çiftleri üzerinde relevance score üretir.
NIM rerank'tan farklı olarak DB state etkilenmez — runtime-only rerank;
çıktı float[len(documents)]. Migration GEREK YOK (re-embed yok).

Tour 5'te keşfedilen reranker kalite sorunlarının (#251, #252, #254, #259,
#260) kalıcı çözümü hedefi: NIM rerank-qa-mistral-4b kısa Türkçe query'lerde
sürekli negatif logit veriyordu. BGE-reranker-v2-m3 multilingual fine-tuned,
Türkçe topic-relevance için NDCG@10 ≥ 0.90 hedef.

Latency: NIM ~250ms (network round-trip) → local CPU ~100-200ms (target).

Settings flag: USE_LOCAL_RERANK (default False — eval gate sonrası flip).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config import get_settings
from app.providers.base import (
    ModelProvider,
    ProviderError,
    ProviderHealth,
    ProviderType,
    RerankResult,
)


logger = logging.getLogger(__name__)


LOCAL_RERANK_MODEL_NAME = "BAAI/bge-reranker-v2-m3"


class LocalBgeRerankerProvider(ModelProvider):
    """sentence-transformers CrossEncoder ile bge-reranker-v2-m3 (#224 PR-9).

    İlk request: ~3-5s (model RAM'e yüklenir, ~568 MB FP32).
    Sonraki request'ler: ~100-200ms / batch (50 passage).

    Lazy load: instance oluşturulurken model değil, ilk rerank'te.
    """

    # Backward compat — provider_call_logs schema değişmez
    name = "nim_rerank"
    type = ProviderType.RERANK

    supports_chat = False
    supports_embeddings = False
    supports_rerank = True
    supports_vision = False

    cost_per_1m_input_tokens = 0.0
    cost_per_1m_output_tokens = 0.0

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self._model_name = (
            model_name
            or getattr(settings, "local_rerank_model", LOCAL_RERANK_MODEL_NAME)
        )
        self._model: Any = None  # lazy load

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return

        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise ProviderError(
                "sentence-transformers paketi yüklü değil. "
                "pip install sentence-transformers"
            ) from e

        load_start = time.perf_counter()
        self._model = CrossEncoder(self._model_name)
        load_ms = int((time.perf_counter() - load_start) * 1000)
        logger.info(
            "LocalBgeReranker model loaded: %s (%d ms)",
            self._model_name,
            load_ms,
        )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 10,
        model: str | None = None,
    ) -> list[RerankResult]:
        """Cross-encoder query × documents → relevance-sorted RerankResult.

        Args:
            query: Sorgu metni
            documents: Aday passage listesi
            top_k: Döndürülecek en üst N sonuç
            model: Override model (None ise default bge-reranker-v2-m3)

        Returns:
            list[RerankResult] — orijinal index + relevance score, descending.
        """
        if not documents:
            return []

        self._ensure_model_loaded()

        # CrossEncoder.predict pairs alır: [(q, d1), (q, d2), ...]
        pairs = [(query, d) for d in documents]

        import asyncio

        start = time.perf_counter()
        scores = await asyncio.to_thread(
            self._model.predict,
            pairs,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)

        # numpy float32 → list[(index, score)] sorted desc
        scored = [(i, float(s)) for i, s in enumerate(scores)]
        scored.sort(key=lambda x: x[1], reverse=True)

        results = [
            RerankResult(index=idx, score=score) for idx, score in scored[:top_k]
        ]

        logger.info(
            "LocalBgeReranker: query_len=%d n_docs=%d top_k=%d latency=%dms",
            len(query),
            len(documents),
            top_k,
            latency_ms,
        )

        return results

    async def healthcheck(self) -> ProviderHealth:
        try:
            start = time.perf_counter()
            results = await self.rerank("test", ["doc1", "doc2"])
            latency = int((time.perf_counter() - start) * 1000)
            if len(results) == 2:
                return ProviderHealth(healthy=True, latency_ms=latency)
            return ProviderHealth(
                healthy=False,
                latency_ms=latency,
                error=f"Unexpected result count: {len(results)}",
            )
        except Exception as e:
            return ProviderHealth(healthy=False, error=str(e))


def build_local_rerank_provider() -> LocalBgeRerankerProvider | None:
    """Factory — settings.use_local_rerank True ise aktif."""
    settings = get_settings()
    if not getattr(settings, "use_local_rerank", False):
        logger.info("USE_LOCAL_RERANK disabled in config — skip")
        return None
    try:
        return LocalBgeRerankerProvider()
    except Exception as exc:
        logger.warning("LocalBgeReranker init failed: %s", exc)
        return None
