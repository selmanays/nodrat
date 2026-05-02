"""Unit tests for rerank wrapper (#181)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.rerank import _build_passage, rerank_rows
from app.providers.base import RerankResult


# ---------------------------------------------------------------------------
# _build_passage
# ---------------------------------------------------------------------------


def test_build_passage_title_summary():
    row = {"title": "Emekli zammı", "summary": "Yüzde 10 oldu"}
    assert _build_passage(row) == "Emekli zammı\n\nYüzde 10 oldu"


def test_build_passage_chunk_fallback():
    row = {"article_title": "X", "chunk_text": "Y içeriği"}
    assert _build_passage(row) == "X\n\nY içeriği"


def test_build_passage_only_title():
    row = {"title": "Sadece başlık"}
    assert _build_passage(row) == "Sadece başlık"


def test_build_passage_truncates():
    row = {"title": "x" * 500, "summary": "y" * 800}
    out = _build_passage(row)
    # title 200 + \n\n + summary 600
    assert len(out) <= 800 + 2


# ---------------------------------------------------------------------------
# rerank_rows behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_disabled_passthrough():
    rows = [{"id": str(i), "title": f"t{i}"} for i in range(5)]
    with patch("app.config.get_settings") as gs:
        gs.return_value.reranker_enabled = False
        out = await rerank_rows(query="x", rows=rows, top_k=3)
    assert len(out) == 3
    assert out[0]["id"] == "0"  # original order


@pytest.mark.asyncio
async def test_rerank_empty_rows():
    out = await rerank_rows(query="test", rows=[], top_k=5)
    assert out == []


@pytest.mark.asyncio
async def test_rerank_empty_query():
    rows = [{"id": "1", "title": "x"}]
    out = await rerank_rows(query="", rows=rows, top_k=5)
    assert len(out) == 1


@pytest.mark.asyncio
async def test_rerank_no_provider_returns_original():
    rows = [{"id": str(i), "title": f"t{i}"} for i in range(3)]
    with patch("app.providers.registry.registry.route_for_tier") as route:
        route.side_effect = RuntimeError("no rerank provider")
        with patch("app.config.get_settings") as gs:
            gs.return_value.reranker_enabled = True
            out = await rerank_rows(query="q", rows=rows, top_k=2)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_rerank_reorders_by_score():
    """Reranker top score'u en üste taşımalı."""
    rows = [
        {"id": "a", "title": "low relevance"},
        {"id": "b", "title": "high relevance"},
        {"id": "c", "title": "medium"},
    ]

    class _FakeProvider:
        async def rerank(self, query, documents, top_k):
            # b en yüksek, c orta, a en düşük
            return [
                RerankResult(index=1, score=2.5),
                RerankResult(index=2, score=1.0),
                RerankResult(index=0, score=0.1),
            ]

    with patch("app.providers.registry.registry.route_for_tier") as route:
        route.return_value = _FakeProvider()
        with patch("app.config.get_settings") as gs:
            gs.return_value.reranker_enabled = True
            out = await rerank_rows(query="relevance", rows=rows, top_k=3)

    assert out[0]["id"] == "b"
    assert out[0]["_rerank_score"] == 2.5
    assert out[1]["id"] == "c"
    assert out[2]["id"] == "a"


@pytest.mark.asyncio
async def test_rerank_provider_error_fallback():
    rows = [{"id": "1", "title": "x"}, {"id": "2", "title": "y"}]

    class _BrokenProvider:
        async def rerank(self, query, documents, top_k):
            raise RuntimeError("provider down")

    with patch("app.providers.registry.registry.route_for_tier") as route:
        route.return_value = _BrokenProvider()
        with patch("app.config.get_settings") as gs:
            gs.return_value.reranker_enabled = True
            out = await rerank_rows(query="q", rows=rows, top_k=2)
    # Original sıra korunur, hata silent
    assert out[0]["id"] == "1"
