"""Unit tests for rerank wrapper (#181, #251)."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

import pytest

from app.core.rerank import _build_passage, rerank_rows
from app.providers.base import RerankResult


def _patches(
    *,
    reranker_enabled: bool = True,
    min_combined: float = 0.0,
    fake_provider=None,
):
    """Helper: tüm mock patch'leri tek context'te aç.

    Returns: ExitStack — caller `with _patches(...) as stack:` ile kullanır.
    """
    stack = ExitStack()
    gs = stack.enter_context(patch("app.core.rerank.get_settings"))
    gsf = stack.enter_context(patch("app.core.db.get_session_factory"))
    gs.return_value.reranker_enabled = reranker_enabled
    gs.return_value.rerank_min_combined_score = min_combined
    gsf.side_effect = RuntimeError("test: no db")
    if fake_provider is not None:
        route = stack.enter_context(
            patch("app.providers.registry.registry.route_for_tier")
        )
        route.return_value = fake_provider
    return stack


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
    assert len(out) <= 800 + 2


# ---------------------------------------------------------------------------
# rerank_rows behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_disabled_passthrough():
    rows = [{"id": str(i), "title": f"t{i}"} for i in range(5)]
    with _patches(reranker_enabled=False):
        out = await rerank_rows(query="x", rows=rows, top_k=3)
    assert len(out) == 3
    assert out[0]["id"] == "0"


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
    with _patches() as stack:
        route = stack.enter_context(
            patch("app.providers.registry.registry.route_for_tier")
        )
        route.side_effect = RuntimeError("no rerank provider")
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
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            return [
                RerankResult(index=1, score=2.5),
                RerankResult(index=2, score=1.0),
                RerankResult(index=0, score=0.1),
            ]

    with _patches(fake_provider=_FakeProvider()):
        out = await rerank_rows(query="relevance", rows=rows, top_k=3)

    assert out[0]["id"] == "b"
    assert out[0]["_rerank_score"] == 2.5
    assert out[1]["id"] == "c"
    assert out[2]["id"] == "a"


@pytest.mark.asyncio
async def test_rerank_negative_logit_ignores_importance():
    """#251 — logit ≤ 0 olan kart, yüksek importance'a rağmen tepeye çıkmamalı.

    Eski formül: 0.65*sigmoid(-16) + 0.35*0.85 = 0.298 (yanlış)
    Yeni formül: sigmoid(-16) ≈ 0 (importance bonus YOK).
    """
    rows = [
        {"id": "alaka_yok_imp_yuksek", "title": "alakasız", "importance_score": 0.85},
        {"id": "alaka_var", "title": "alakalı", "importance_score": 0.40},
    ]

    class _FakeProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            return [
                RerankResult(index=0, score=-16.0),
                RerankResult(index=1, score=2.5),
            ]

    with _patches(min_combined=-1.0, fake_provider=_FakeProvider()):
        out = await rerank_rows(query="alakalı sorgu", rows=rows, top_k=5)

    assert len(out) == 2, "drop yok, ikisi de gelmeli"
    assert out[0]["id"] == "alaka_var", "alakalı kart üstte"
    assert out[1]["id"] == "alaka_yok_imp_yuksek"
    assert out[1]["_combined_score"] < 0.001, (
        f"importance ignore edilmiyor: combined={out[1]['_combined_score']}"
    )


@pytest.mark.asyncio
async def test_rerank_drops_below_min_combined():
    """#251 — combined_score < min_combined kartlar drop edilir."""
    rows = [
        {"id": "iyi", "title": "x", "importance_score": 0.80},
        {"id": "kotu", "title": "y", "importance_score": 0.85},
    ]

    class _FakeProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            return [
                RerankResult(index=0, score=3.0),
                RerankResult(index=1, score=-10.0),
            ]

    with _patches(min_combined=0.20, fake_provider=_FakeProvider()):
        out = await rerank_rows(query="q", rows=rows, top_k=5)

    assert len(out) == 1, "min_combined altındaki kart drop edilmeli"
    assert out[0]["id"] == "iyi"


@pytest.mark.asyncio
async def test_rerank_drops_all_below_threshold_returns_empty():
    """#251 — tüm kartlar threshold altındaysa boş liste; caller insufficient_data."""
    rows = [
        {"id": "1", "title": "a"},
        {"id": "2", "title": "b"},
    ]

    class _FakeProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            return [
                RerankResult(index=0, score=-15.0),
                RerankResult(index=1, score=-12.0),
            ]

    with _patches(min_combined=0.20, fake_provider=_FakeProvider()):
        out = await rerank_rows(query="q", rows=rows, top_k=5)

    assert out == []


@pytest.mark.asyncio
async def test_rerank_provider_error_fallback():
    rows = [{"id": "1", "title": "x"}, {"id": "2", "title": "y"}]

    class _BrokenProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            raise RuntimeError("provider down")

    with _patches(fake_provider=_BrokenProvider()):
        out = await rerank_rows(query="q", rows=rows, top_k=2)
    assert out[0]["id"] == "1"
