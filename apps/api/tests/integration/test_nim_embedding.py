"""NIM embedding adapter integration test (real API).

⚠️ Bu test gerçek NIM API'sine çağrı atar. CI'da NIM_API_KEY varsa çalışır,
   yoksa atlanır. Local'de .env'de NIM_API_KEY set olmalı.

docs/engineering/prompt-contracts.md §6 (eval framework)
"""

from __future__ import annotations

import os

import pytest

from app.providers.nim import (
    NIM_DEFAULT_MODEL,
    NIM_EMBEDDING_DIM,
    NimEmbeddingProvider,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("NIM_API_KEY"),
        reason="NIM_API_KEY env değişkeni yok — integration test atlanıyor",
    ),
]


@pytest.fixture
def provider() -> NimEmbeddingProvider:
    return NimEmbeddingProvider()


class TestNimRealAPI:
    """NIM API gerçek çağrılar."""

    @pytest.mark.asyncio
    async def test_healthcheck_returns_healthy(
        self, provider: NimEmbeddingProvider
    ) -> None:
        result = await provider.healthcheck()
        assert result.healthy is True
        assert result.latency_ms is not None
        assert result.latency_ms < 5000  # 5s tolerance

    @pytest.mark.asyncio
    async def test_single_text_embedding(
        self, provider: NimEmbeddingProvider
    ) -> None:
        result = await provider.create_embedding(["Test cümlesi."])
        assert len(result.vectors) == 1
        assert len(result.vectors[0]) == NIM_EMBEDDING_DIM
        assert result.model == NIM_DEFAULT_MODEL
        assert result.input_tokens > 0
        assert result.cost_usd == 0.0  # free tier
        assert result.latency_ms is not None

    @pytest.mark.asyncio
    async def test_batch_embedding(self, provider: NimEmbeddingProvider) -> None:
        texts = [
            "Bu Türkçe bir test cümlesidir.",
            "Ekonomi gündemiyle ilgili son gelişmeler.",
            "Yapay zeka regülasyonu üzerine bir değerlendirme.",
        ]
        result = await provider.create_embedding(texts)
        assert len(result.vectors) == 3
        for vec in result.vectors:
            assert len(vec) == NIM_EMBEDDING_DIM
        assert result.input_tokens > 5

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(
        self, provider: NimEmbeddingProvider
    ) -> None:
        result = await provider.create_embedding([])
        assert result.vectors == []
        assert result.input_tokens == 0

    @pytest.mark.asyncio
    async def test_long_text_truncated(self, provider: NimEmbeddingProvider) -> None:
        """truncate=END parametresi uzun metni keser, exception atmaz."""
        # ~3000 token (E5 modeli için 512 token sınırı var, kesilecek)
        long_text = "Bu bir Türkçe test cümlesidir. " * 500
        result = await provider.create_embedding([long_text])
        assert len(result.vectors) == 1
        assert len(result.vectors[0]) == NIM_EMBEDDING_DIM
