"""Unit tests for retrieval metric implementations (#179)."""

from __future__ import annotations

import math

from tests.eval.retrieval_benchmark import (
    average_precision_at_k,
    dcg_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


# ---------------------------------------------------------------------------
# DCG / NDCG
# ---------------------------------------------------------------------------


def test_dcg_perfect_order():
    rels = [3.0, 2.0, 1.0]
    # 7/log2(2) + 3/log2(3) + 1/log2(4) ≈ 7 + 1.893 + 0.5 = 9.393
    score = dcg_at_k(rels, 3)
    assert abs(score - (7 + 3 / math.log2(3) + 1 / math.log2(4))) < 1e-6


def test_ndcg_perfect_match():
    qrels = {"a": 1.0, "b": 1.0, "c": 1.0}
    retrieved = ["a", "b", "c"]
    assert ndcg_at_k(retrieved, qrels, 3) == 1.0


def test_ndcg_no_match():
    qrels = {"a": 1.0, "b": 1.0}
    retrieved = ["x", "y"]
    assert ndcg_at_k(retrieved, qrels, 5) == 0.0


def test_ndcg_partial_with_irrelevant_first():
    qrels = {"a": 1.0}
    retrieved = ["x", "a"]  # ilgili 2. sırada
    score = ndcg_at_k(retrieved, qrels, 5)
    # 1/log2(3) ≈ 0.6309
    assert 0.6 < score < 0.65


def test_ndcg_handles_empty_qrels():
    assert ndcg_at_k(["a"], {}, 5) == 0.0


# ---------------------------------------------------------------------------
# Precision@k
# ---------------------------------------------------------------------------


def test_precision_at_k_all_hits():
    qrels = {"a": 1.0, "b": 1.0, "c": 1.0}
    retrieved = ["a", "b", "c", "d", "e"]
    assert precision_at_k(retrieved, qrels, 3) == 1.0


def test_precision_at_k_partial():
    qrels = {"a": 1.0, "b": 1.0}
    retrieved = ["a", "x", "b", "y", "z"]
    assert precision_at_k(retrieved, qrels, 5) == 0.4


# ---------------------------------------------------------------------------
# AP@k / MRR
# ---------------------------------------------------------------------------


def test_average_precision_perfect():
    qrels = {"a": 1.0, "b": 1.0}
    retrieved = ["a", "b"]
    # AP = (1/1 + 2/2) / 2 = 1.0
    assert average_precision_at_k(retrieved, qrels, 5) == 1.0


def test_average_precision_with_gap():
    qrels = {"a": 1.0, "b": 1.0}
    retrieved = ["a", "x", "b"]
    # AP = (1/1 + 2/3) / 2 = 0.8333
    assert abs(average_precision_at_k(retrieved, qrels, 5) - (1 + 2 / 3) / 2) < 1e-6


def test_reciprocal_rank_first_position():
    qrels = {"a": 1.0}
    assert reciprocal_rank(["a", "b", "c"], qrels) == 1.0


def test_reciprocal_rank_third_position():
    qrels = {"a": 1.0}
    assert reciprocal_rank(["x", "y", "a"], qrels) == 1 / 3


def test_reciprocal_rank_no_match():
    qrels = {"a": 1.0}
    assert reciprocal_rank(["x", "y"], qrels) == 0.0


# ---------------------------------------------------------------------------
# Recall@k
# ---------------------------------------------------------------------------


def test_recall_at_k_full():
    qrels = {"a": 1.0, "b": 1.0}
    retrieved = ["a", "b", "x"]
    assert recall_at_k(retrieved, qrels, 5) == 1.0


def test_recall_at_k_half():
    qrels = {"a": 1.0, "b": 1.0}
    retrieved = ["a", "x", "y"]
    assert recall_at_k(retrieved, qrels, 5) == 0.5


def test_recall_no_relevant():
    assert recall_at_k(["x", "y"], {}, 5) == 0.0
