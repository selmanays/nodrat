"""Smoke tests for admin RAG endpoints (#190).

Bu testler endpoint signature'larını ve schema'larını doğrular. Tam integration
test (DB + auth) integration suite kapsamında.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.api.admin_rag import (
    BenchmarkRunSummary,
    CitationStatsResponse,
    FeatureFlags,
    HealthCounts,
    InspectQueryRequest,
    InspectRow,
    RagHealthResponse,
    RaptorTriggerResponse,
    RerankStatsResponse,
    WeeklyClusterRow,
)


def test_feature_flags_required_fields():
    flags = FeatureFlags(
        reranker_enabled=True,
        reranker_candidate_pool=50,
        rerank_model="nvidia/rerank-qa-mistral-4b",
    )
    assert flags.reranker_enabled is True


def test_health_counts():
    c = HealthCounts(
        daily_cards=155,
        weekly_cards=4,
        daily_with_parent=8,
        active_clusters=120,
        last_24h_generations=12,
        last_24h_insufficient=2,
    )
    assert c.daily_cards == 155


def test_rag_health_response():
    health = RagHealthResponse(
        flags=FeatureFlags(
            reranker_enabled=True,
            reranker_candidate_pool=50,
            rerank_model="x",
        ),
        counts=HealthCounts(
            daily_cards=10,
            weekly_cards=2,
            daily_with_parent=4,
            active_clusters=8,
            last_24h_generations=1,
            last_24h_insufficient=0,
        ),
        last_eval=None,
    )
    assert health.last_eval is None


def test_benchmark_run_summary():
    r = BenchmarkRunSummary(
        id="abc",
        golden_set="retrieval_golden_tr.yaml",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        n_queries=50,
        ndcg_10=0.7123,
        map_5=0.6853,
        mrr_10=0.7400,
        recall_20=0.6973,
        latency_ms_p50=665.98,
        latency_ms_p95=843.94,
        triggered_by="cli",
    )
    assert r.ndcg_10 == 0.7123


def test_citation_stats_zero_division_guard():
    s = CitationStatsResponse(
        sample_size=0,
        repairs_total=0,
        repairs_avg_per_gen=0.0,
        unsupported_warnings=0,
        unsupported_avg_per_gen=0.0,
    )
    assert s.repairs_avg_per_gen == 0.0


def test_rerank_stats_no_data():
    s = RerankStatsResponse(
        sample_size=0,
        avg_latency_ms=None,
        p50_latency_ms=None,
        p95_latency_ms=None,
        last_call_at=None,
    )
    assert s.sample_size == 0


def test_weekly_cluster_row():
    w = WeeklyClusterRow(
        id="abc-123",
        title="Test",
        summary="özet",
        importance=0.7,
        daily_children_count=3,
        children_titles=["a", "b", "c"],
        updated_at=datetime.now(timezone.utc),
    )
    assert w.daily_children_count == 3


def test_inspect_query_request_validation():
    req = InspectQueryRequest(query="emekli maaşı", top_k=10)
    assert req.candidate_pool == 50  # default

    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InspectQueryRequest(query="x")  # min_length 2


def test_inspect_row_optional_scores():
    r = InspectRow(id="x", title="t")
    assert r.rrf_score is None
    assert r.rerank_score is None


def test_raptor_trigger_response():
    r = RaptorTriggerResponse(daily_count=155, cluster_count=4, ok_count=4)
    assert r.ok_count == 4
