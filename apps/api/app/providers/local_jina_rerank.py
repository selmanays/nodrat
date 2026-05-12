"""Local Jina Reranker v2 Base Multilingual provider (#760).

Model: jinaai/jina-reranker-v2-base-multilingual
  - ~560MB safetensors, 100+ dil destekli (Turkish dahil)
  - AutoModelForSequenceClassification + Tokenizer (transformers)
  - CPU inference (VPS Contabo Cloud VPS 40 — 12 vCPU / 47GB RAM)
  - Latency hedef: ~200-500ms top-15 query (CPU FP32)

Tarih:
  - #758 (2026-05-12): Önceki cross-encoder rerank (NIM mistral-4b + local
    bge-reranker-v2-m3) eval gate negatif → kalıcı disabled.
  - #760: Yeni model dene — Jina v2 multilingual (100+ dil Türkçe eval'li).
    Eval gate (NDCG@10 ≥ 0.90 VEYA recall@5 +5pp) → flip kararı.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.providers.base import (
    ModelProvider,
    ProviderHealth,
    ProviderType,
    RerankResult,
)

logger = logging.getLogger(__name__)


# Model id ENV ile override edilebilir (test/preview için).
_DEFAULT_MODEL = "jinaai/jina-reranker-v2-base-multilingual"


class LocalJinaRerankProvider(ModelProvider):
    """Local Jina Reranker v2 Base Multilingual (CPU on VPS).

    Lazy-loaded singleton (model first-use'da yüklenir). Cross-encoder
    pattern: `compute_score([query, passage])` çağrısı.
    """

    name = "local_jina_rerank"
    type = ProviderType.LOCAL
    supports_rerank = True
    cost_per_1m_input_tokens = 0.0
    cost_per_1m_output_tokens = 0.0

    def __init__(self, model_id: str = _DEFAULT_MODEL) -> None:
        self.model_id = model_id
        self._model = None  # Lazy load
        self._tokenizer = None

    def _ensure_loaded(self) -> None:
        """Model'i lazy yükle (process-local singleton)."""
        if self._model is not None:
            return

        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as exc:
            raise RuntimeError(
                "transformers package not installed — Jina rerank kullanılamaz"
            ) from exc

        logger.info("loading jina-reranker model: %s", self.model_id)
        t0 = time.perf_counter()
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, trust_remote_code=True
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.model_id, trust_remote_code=True, torch_dtype="auto"
        )
        self._model.eval()
        logger.info(
            "jina-reranker loaded in %.1fs (model=%s)",
            time.perf_counter() - t0, self.model_id,
        )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """Cross-encoder rerank: her [query, document] pair'i için skor.

        Returns top_k results sorted by score descending (index = original list pos).
        """
        if not documents:
            return []

        self._ensure_loaded()

        import torch

        # Pair construction
        pairs = [[query, doc] for doc in documents]

        # Tokenize batch
        with torch.no_grad():
            inputs = self._tokenizer(
                pairs,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=1024,  # Jina v2 max 1024 token
            )
            outputs = self._model(**inputs)
            scores = outputs.logits.squeeze(-1).float().cpu().numpy().tolist()

        # Top-K
        indexed = [
            RerankResult(index=i, score=float(s))
            for i, s in enumerate(scores)
        ]
        indexed.sort(key=lambda r: r.score, reverse=True)
        return indexed[:top_k]

    async def healthcheck(self) -> ProviderHealth:
        try:
            self._ensure_loaded()
            return ProviderHealth(healthy=True, latency_ms=0)
        except Exception as exc:
            return ProviderHealth(healthy=False, error=str(exc))


def build_local_jina_rerank_provider(
    *, model_id: str | None = None
) -> LocalJinaRerankProvider | None:
    """Factory — provider'ı oluştur. None döndürmek için bir koşul yok
    (CPU local, ENV gerek yok). model_id None ise default kullanılır.
    """
    return LocalJinaRerankProvider(model_id=model_id or _DEFAULT_MODEL)


__all__ = ["LocalJinaRerankProvider", "build_local_jina_rerank_provider"]
