"""Unit — #619 PR-4A benchmark decompose+merge proxy helper.

`tests/eval/retrieval_benchmark.py`'a eklenen benchmark-içi merge helper'ının
deterministik testi. Bu helper BENCHMARK-only proxy — production retrieval/
orchestration'a SIZMAZ (prod PR-3 = 3b LLM-driven). DB-suz, saf.
"""

from __future__ import annotations

import pytest

from tests.eval.retrieval_benchmark import (
    _MERGE_FUNCS,
    _decompose_sub_queries,
    _merge_rank_rrf,
    _merge_rrf_max,
    _merge_rrf_sum,
    _merge_union_preserve_order,
)

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


# =============================================================================
# #619 PR-4D — alternatif merge stratejileri (saf, deterministik)
# =============================================================================


def test_merge_rrf_max_takes_highest():
    sub1 = [{"article_id": "A1", "_rrf_score": 0.3}, {"article_id": "A2", "_rrf_score": 0.5}]
    sub2 = [{"article_id": "A1", "_rrf_score": 0.4}]
    out = _merge_rrf_max([sub1, sub2], top_k=10)
    # A1 max(0.3,0.4)=0.4 · A2=0.5 → [A2, A1]
    assert out == ["A2", "A1"]


def test_merge_rank_rrf_position_based():
    # A1 iki alt-sorguda rank-1 (2/(60+1)) · A2 tek alt-sorguda rank-2 (1/(60+2))
    sub1 = [{"article_id": "A1", "_rrf_score": 0.9}, {"article_id": "A2", "_rrf_score": 0.1}]
    sub2 = [{"article_id": "A1", "_rrf_score": 0.05}]
    out = _merge_rank_rrf([sub1, sub2], top_k=10)
    assert out == ["A1", "A2"]


def test_merge_rank_rrf_ignores_score_scale():
    # rank-bazlı → düşük-skor rank-1 article, yüksek-skor rank-2'yi geçer (ölçek-bağımsız)
    sub = [{"article_id": "A1", "_rrf_score": 0.001}, {"article_id": "A2", "_rrf_score": 99.0}]
    out = _merge_rank_rrf([sub], top_k=10)
    assert out == ["A1", "A2"]  # rrf_sum olsaydı [A2, A1] olurdu


def test_merge_union_round_robin():
    sub1 = [{"article_id": "A1"}, {"article_id": "A2"}]
    sub2 = [{"article_id": "B1"}, {"article_id": "B2"}]
    out = _merge_union_preserve_order([sub1, sub2], top_k=10)
    # round-robin: i=0→A1,B1 · i=1→A2,B2
    assert out == ["A1", "B1", "A2", "B2"]


def test_merge_union_dedup():
    sub1 = [{"article_id": "A1"}, {"article_id": "A2"}]
    sub2 = [{"article_id": "A1"}, {"article_id": "B1"}]
    out = _merge_union_preserve_order([sub1, sub2], top_k=10)
    # i=0→A1 (sub2 A1 dedup) · i=1→A2,B1
    assert out == ["A1", "A2", "B1"]


def test_merge_union_top_k():
    sub = [{"article_id": f"A{i}"} for i in range(5)]
    out = _merge_union_preserve_order([sub], top_k=2)
    assert out == ["A0", "A1"]


def test_merge_dispatch_keys_and_default():
    assert set(_MERGE_FUNCS) == {"rrf_sum", "rrf_max", "rank_rrf", "union"}
    # default rrf_sum byte-identical (PR-4A _merge_rrf_sum)
    assert _MERGE_FUNCS["rrf_sum"] is _merge_rrf_sum
