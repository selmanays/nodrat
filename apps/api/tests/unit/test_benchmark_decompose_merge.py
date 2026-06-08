"""Unit — #619 PR-4A benchmark decompose+merge proxy helper.

`tests/eval/retrieval_benchmark.py`'a eklenen benchmark-içi merge helper'ının
deterministik testi. Bu helper BENCHMARK-only proxy — production retrieval/
orchestration'a SIZMAZ (prod PR-3 = 3b LLM-driven). DB-suz, saf.
"""

from __future__ import annotations

import pytest

from tests.eval.retrieval_benchmark import _decompose_sub_queries, _merge_rrf_sum

# =============================================================================
# _merge_rrf_sum (saf, deterministik)
# =============================================================================


def test_merge_sums_rrf_across_subqueries():
    # A1 iki alt-sorguda → _rrf_score toplanır → öne geçer
    sub1 = [{"article_id": "A1", "_rrf_score": 0.3}, {"article_id": "A2", "_rrf_score": 0.5}]
    sub2 = [{"article_id": "A1", "_rrf_score": 0.4}, {"article_id": "A3", "_rrf_score": 0.2}]
    out = _merge_rrf_sum([sub1, sub2], top_k=10)
    # A1: 0.3+0.4=0.7 · A2: 0.5 · A3: 0.2 → [A1, A2, A3]
    assert out == ["A1", "A2", "A3"]


def test_merge_respects_top_k():
    sub = [{"article_id": f"A{i}", "_rrf_score": 1.0 / i} for i in range(1, 6)]
    out = _merge_rrf_sum([sub], top_k=2)
    assert out == ["A1", "A2"]  # 1.0, 0.5 en yüksek


def test_merge_local_dedup_same_article_in_one_subquery():
    # Aynı alt-sorguda A1 iki chunk → sadece İLK sayılır (local dedup)
    sub = [{"article_id": "A1", "_rrf_score": 0.5}, {"article_id": "A1", "_rrf_score": 0.9}]
    out = _merge_rrf_sum([sub], top_k=10)
    assert out == ["A1"]


def test_merge_local_dedup_then_cross_subquery_sum():
    # A1: alt1 ilk-chunk(0.5, 0.9 atlanır) + alt2(0.3) = 0.8
    sub_a = [{"article_id": "A1", "_rrf_score": 0.5}, {"article_id": "A1", "_rrf_score": 0.9}]
    sub_b = [{"article_id": "A1", "_rrf_score": 0.3}]
    out = _merge_rrf_sum([sub_a, sub_b], top_k=10)
    assert out == ["A1"]


def test_merge_missing_rrf_score_treated_zero():
    sub = [{"article_id": "A1"}, {"article_id": "A2", "_rrf_score": 0.5}]
    out = _merge_rrf_sum([sub], top_k=10)
    assert out == ["A2", "A1"]  # A1 skor 0.0, A2 0.5


def test_merge_empty():
    assert _merge_rrf_sum([], top_k=10) == []
    assert _merge_rrf_sum([[]], top_k=10) == []


def test_merge_skips_empty_article_id():
    sub = [{"article_id": "", "_rrf_score": 0.9}, {"article_id": "A1", "_rrf_score": 0.5}]
    out = _merge_rrf_sum([sub], top_k=10)
    assert out == ["A1"]


# =============================================================================
# _decompose_sub_queries (heuristic mod — deterministik, provider-suz)
# =============================================================================


@pytest.mark.asyncio
async def test_decompose_heuristic_splits_multi_topic():
    out = await _decompose_sub_queries(
        "Türkiye ekonomisi ve faiz kararları son durum", mode="heuristic"
    )
    assert len(out) == 2


@pytest.mark.asyncio
async def test_decompose_single_topic_returns_original():
    # Bölünmez → [effective_query] (caller baseline retrieve eder)
    out = await _decompose_sub_queries("Türkiye ekonomisi son durum", mode="heuristic")
    assert out == ["Türkiye ekonomisi son durum"]
