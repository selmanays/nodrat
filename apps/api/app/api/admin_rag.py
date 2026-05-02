"""Admin RAG observability endpoints (#190).

docs/engineering/api-contracts.md §4 (admin endpoints)
Epic #189 — RAG observability dashboard backend.

Endpoints:
    GET  /admin/rag/health                 — feature flags + counts
    GET  /admin/rag/benchmark/history      — son N eval_runs
    POST /admin/rag/benchmark/run          — async benchmark trigger
    GET  /admin/rag/citation-stats         — son 100 generation aggregate
    GET  /admin/rag/rerank-stats           — provider_call_logs nim_rerank
    GET  /admin/rag/raptor/clusters        — weekly + children
    POST /admin/rag/raptor/trigger         — manuel weekly cluster build
    POST /admin/rag/inspect-query          — RRF + rerank skorlarını döndür

Auth: require_admin (super_admin) — sadece sistem yöneticisi erişebilir.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db
from app.core.deps import require_admin
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Pydantic schemas
# ============================================================================


class FeatureFlags(BaseModel):
    reranker_enabled: bool
    reranker_candidate_pool: int
    rerank_model: str
    use_local_embedding: bool


class HealthCounts(BaseModel):
    daily_cards: int
    weekly_cards: int
    daily_with_parent: int
    active_clusters: int
    last_24h_generations: int
    last_24h_insufficient: int


class HealthBeat(BaseModel):
    task: str
    last_seen: datetime | None = None


class RagHealthResponse(BaseModel):
    flags: FeatureFlags
    counts: HealthCounts
    last_eval: dict[str, Any] | None = None


class BenchmarkRunSummary(BaseModel):
    id: str
    golden_set: str
    started_at: datetime
    completed_at: datetime | None
    n_queries: int
    ndcg_10: float | None
    map_5: float | None
    mrr_10: float | None
    recall_20: float | None
    latency_ms_p50: float | None
    latency_ms_p95: float | None
    triggered_by: str | None


class BenchmarkHistoryResponse(BaseModel):
    runs: list[BenchmarkRunSummary]


class BenchmarkTriggerResponse(BaseModel):
    started: bool
    run_id: str | None = None
    message: str


class CitationStatsResponse(BaseModel):
    sample_size: int
    repairs_total: int
    repairs_avg_per_gen: float
    unsupported_warnings: int
    unsupported_avg_per_gen: float


class RerankStatsResponse(BaseModel):
    sample_size: int
    avg_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    last_call_at: datetime | None


class WeeklyClusterRow(BaseModel):
    id: str
    title: str
    summary: str
    importance: float | None
    daily_children_count: int
    children_titles: list[str] = Field(default_factory=list)
    updated_at: datetime


class RaptorClustersResponse(BaseModel):
    weekly: list[WeeklyClusterRow]


class RaptorTriggerResponse(BaseModel):
    daily_count: int
    cluster_count: int
    ok_count: int


class InspectRow(BaseModel):
    id: str
    title: str
    rrf_score: float | None = None
    rerank_score: float | None = None
    rrf_rank: int | None = None
    rerank_rank: int | None = None


class InspectQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=400)
    top_k: int = Field(10, ge=1, le=50)
    candidate_pool: int = Field(80, ge=10, le=200)
    # #202 — Query Planner ile zenginleştirme (kullanıcı yolundaki gibi)
    use_planner: bool = True


class InspectPlannerInfo(BaseModel):
    used: bool
    enriched_query: str | None = None
    keywords: list[str] = Field(default_factory=list)
    topic_query: str | None = None
    intent: str | None = None


class InspectQueryResponse(BaseModel):
    query: str
    levels: list[str]
    rows: list[InspectRow]
    rrf_only_top: list[InspectRow]
    reranked_top: list[InspectRow]
    planner: InspectPlannerInfo | None = None


# ============================================================================
# /admin/rag/health
# ============================================================================


@router.get(
    "/health",
    response_model=RagHealthResponse,
    summary="RAG feature health + counts",
)
async def rag_health(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RagHealthResponse:
    settings = get_settings()

    # Counts
    counts_row = (
        await db.execute(
            sa_text(
                """
                SELECT
                    (SELECT COUNT(*) FROM agenda_cards WHERE level='daily') AS daily_cards,
                    (SELECT COUNT(*) FROM agenda_cards WHERE level='weekly') AS weekly_cards,
                    (SELECT COUNT(*) FROM agenda_cards WHERE parent_card_id IS NOT NULL) AS daily_with_parent,
                    (SELECT COUNT(*) FROM event_clusters WHERE status IN ('active','developing')) AS active_clusters,
                    (SELECT COUNT(*) FROM generations WHERE created_at > NOW() - INTERVAL '24 hours') AS gen_24h,
                    (SELECT COUNT(*) FROM generations WHERE created_at > NOW() - INTERVAL '24 hours' AND status='insufficient_data') AS insufficient_24h
                """
            )
        )
    ).mappings().first()

    # Last eval
    last_eval_row = (
        await db.execute(
            sa_text(
                """
                SELECT id::text, golden_set, completed_at,
                       ndcg_10, map_5, mrr_10, recall_20,
                       latency_ms_p50, latency_ms_p95, n_queries
                FROM eval_runs
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        )
    ).mappings().first()

    last_eval: dict[str, Any] | None = None
    if last_eval_row:
        last_eval = {
            "id": last_eval_row["id"],
            "golden_set": last_eval_row["golden_set"],
            "completed_at": last_eval_row["completed_at"],
            "ndcg_10": float(last_eval_row["ndcg_10"]) if last_eval_row["ndcg_10"] else None,
            "map_5": float(last_eval_row["map_5"]) if last_eval_row["map_5"] else None,
            "mrr_10": float(last_eval_row["mrr_10"]) if last_eval_row["mrr_10"] else None,
            "recall_20": float(last_eval_row["recall_20"]) if last_eval_row["recall_20"] else None,
            "latency_ms_p50": float(last_eval_row["latency_ms_p50"]) if last_eval_row["latency_ms_p50"] else None,
            "latency_ms_p95": float(last_eval_row["latency_ms_p95"]) if last_eval_row["latency_ms_p95"] else None,
            "n_queries": last_eval_row["n_queries"],
        }

    return RagHealthResponse(
        flags=FeatureFlags(
            reranker_enabled=settings.reranker_enabled,
            reranker_candidate_pool=settings.reranker_candidate_pool,
            rerank_model=settings.nim_rerank_model,
            use_local_embedding=settings.use_local_embedding,
        ),
        counts=HealthCounts(
            daily_cards=counts_row["daily_cards"] or 0,
            weekly_cards=counts_row["weekly_cards"] or 0,
            daily_with_parent=counts_row["daily_with_parent"] or 0,
            active_clusters=counts_row["active_clusters"] or 0,
            last_24h_generations=counts_row["gen_24h"] or 0,
            last_24h_insufficient=counts_row["insufficient_24h"] or 0,
        ),
        last_eval=last_eval,
    )


# ============================================================================
# /admin/rag/benchmark
# ============================================================================


@router.get(
    "/benchmark/history",
    response_model=BenchmarkHistoryResponse,
    summary="Son N benchmark run",
)
async def benchmark_history(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
) -> BenchmarkHistoryResponse:
    rows = (
        await db.execute(
            sa_text(
                """
                SELECT id::text, golden_set, started_at, completed_at,
                       n_queries, ndcg_10, map_5, mrr_10, recall_20,
                       latency_ms_p50, latency_ms_p95, triggered_by
                FROM eval_runs
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": min(limit, 100)},
        )
    ).mappings().all()

    runs = [
        BenchmarkRunSummary(
            id=r["id"],
            golden_set=r["golden_set"],
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            n_queries=r["n_queries"],
            ndcg_10=float(r["ndcg_10"]) if r["ndcg_10"] is not None else None,
            map_5=float(r["map_5"]) if r["map_5"] is not None else None,
            mrr_10=float(r["mrr_10"]) if r["mrr_10"] is not None else None,
            recall_20=float(r["recall_20"]) if r["recall_20"] is not None else None,
            latency_ms_p50=float(r["latency_ms_p50"]) if r["latency_ms_p50"] is not None else None,
            latency_ms_p95=float(r["latency_ms_p95"]) if r["latency_ms_p95"] is not None else None,
            triggered_by=r["triggered_by"],
        )
        for r in rows
    ]
    return BenchmarkHistoryResponse(runs=runs)


@router.post(
    "/benchmark/run",
    response_model=BenchmarkTriggerResponse,
    summary="Manuel benchmark trigger (sync, blocking up to ~120s)",
)
async def benchmark_run(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    golden: str = "retrieval_golden_tr.yaml",
    top_k: int = 20,
) -> BenchmarkTriggerResponse:
    """Sync benchmark — kullanıcı butonun sonucunu beklesin (50 query × ~1.5s)."""
    try:
        from tests.eval.retrieval_benchmark import run_benchmark

        await run_benchmark(
            golden_name=golden,
            top_k=top_k,
            persist=True,
            triggered_by=f"admin:{user.email}",
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("admin benchmark trigger failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "BENCHMARK_FAILED", "title": str(exc)[:200]},
        ) from exc

    # Newest run id
    last = (
        await db.execute(
            sa_text(
                "SELECT id::text FROM eval_runs ORDER BY created_at DESC LIMIT 1"
            )
        )
    ).scalar_one_or_none()

    return BenchmarkTriggerResponse(
        started=True,
        run_id=last,
        message="Benchmark tamamlandı, eval_runs'a kaydedildi.",
    )


# ============================================================================
# /admin/rag/citation-stats
# ============================================================================


@router.get(
    "/citation-stats",
    response_model=CitationStatsResponse,
    summary="Son N generation citation aggregate",
)
async def citation_stats(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    sample: int = 100,
) -> CitationStatsResponse:
    rows = (
        await db.execute(
            sa_text(
                """
                SELECT
                    output_json->'_citation' AS cit,
                    warnings
                FROM generations
                WHERE status = 'completed'
                  AND output_json IS NOT NULL
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": min(sample, 500)},
        )
    ).mappings().all()

    total = len(rows)
    repairs = 0
    unsupported = 0
    for r in rows:
        cit = r["cit"] or {}
        if isinstance(cit, dict):
            repairs += int(cit.get("repairs", 0) or 0)
        warns = r["warnings"] or []
        if isinstance(warns, list):
            for w in warns:
                if "unsupported_claims" in str(w):
                    unsupported += 1

    return CitationStatsResponse(
        sample_size=total,
        repairs_total=repairs,
        repairs_avg_per_gen=round(repairs / total, 3) if total else 0.0,
        unsupported_warnings=unsupported,
        unsupported_avg_per_gen=round(unsupported / total, 3) if total else 0.0,
    )


# ============================================================================
# /admin/rag/rerank-stats
# ============================================================================


@router.get(
    "/rerank-stats",
    response_model=RerankStatsResponse,
    summary="Reranker call log aggregate",
)
async def rerank_stats(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: int = 24,
) -> RerankStatsResponse:
    rows = (
        await db.execute(
            sa_text(
                """
                SELECT latency_ms, created_at
                FROM provider_call_logs
                WHERE provider = 'nim_rerank'
                  AND created_at > NOW() - make_interval(hours => :hours)
                ORDER BY created_at DESC
                """
            ),
            {"hours": int(hours)},
        )
    ).mappings().all()

    if not rows:
        return RerankStatsResponse(
            sample_size=0,
            avg_latency_ms=None,
            p50_latency_ms=None,
            p95_latency_ms=None,
            last_call_at=None,
        )

    latencies = sorted(int(r["latency_ms"] or 0) for r in rows)
    avg = sum(latencies) / len(latencies)
    p50_idx = int(len(latencies) * 0.5)
    p95_idx = int(len(latencies) * 0.95)
    if p95_idx >= len(latencies):
        p95_idx = len(latencies) - 1

    return RerankStatsResponse(
        sample_size=len(rows),
        avg_latency_ms=round(avg, 2),
        p50_latency_ms=float(latencies[p50_idx]),
        p95_latency_ms=float(latencies[p95_idx]),
        last_call_at=rows[0]["created_at"],
    )


# ============================================================================
# /admin/rag/raptor
# ============================================================================


@router.get(
    "/raptor/clusters",
    response_model=RaptorClustersResponse,
    summary="RAPTOR weekly clusters + child daily titles",
)
async def raptor_clusters(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
) -> RaptorClustersResponse:
    weekly_rows = (
        await db.execute(
            sa_text(
                """
                SELECT id::text, title, summary, importance_score, updated_at
                FROM agenda_cards
                WHERE level = 'weekly'
                ORDER BY updated_at DESC
                LIMIT :limit
                """
            ),
            {"limit": min(limit, 100)},
        )
    ).mappings().all()

    weekly_ids = [w["id"] for w in weekly_rows]
    children_map: dict[str, list[str]] = {wid: [] for wid in weekly_ids}
    if weekly_ids:
        in_clause = ", ".join(f"'{wid}'::uuid" for wid in weekly_ids)
        child_rows = (
            await db.execute(
                sa_text(
                    f"""
                    SELECT id::text, title, parent_card_id::text AS parent_id
                    FROM agenda_cards
                    WHERE parent_card_id IN ({in_clause})
                    ORDER BY updated_at DESC
                    """
                )
            )
        ).mappings().all()
        for cr in child_rows:
            children_map.setdefault(cr["parent_id"], []).append(
                str(cr["title"])[:120]
            )

    out: list[WeeklyClusterRow] = []
    for w in weekly_rows:
        children = children_map.get(w["id"], [])
        out.append(
            WeeklyClusterRow(
                id=w["id"],
                title=w["title"][:200],
                summary=str(w["summary"])[:600],
                importance=float(w["importance_score"]) if w["importance_score"] else None,
                daily_children_count=len(children),
                children_titles=children[:10],
                updated_at=w["updated_at"],
            )
        )
    return RaptorClustersResponse(weekly=out)


class CountryBackfillResponse(BaseModel):
    status: str
    requested: int
    tagged: int
    skipped: int
    errors: int


@router.post(
    "/backfill-country",
    response_model=CountryBackfillResponse,
    summary="Country=NULL kartları toplu re-tag (#228)",
)
async def backfill_country(
    user: Annotated[User, Depends(require_admin)],
    batch: int = 50,
) -> CountryBackfillResponse:
    from app.workers.tasks.agenda import _backfill_country_async

    try:
        result = await _backfill_country_async(min(max(batch, 1), 200))
    except Exception as exc:  # pragma: no cover
        logger.exception("admin backfill_country failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "BACKFILL_FAILED", "title": str(exc)[:200]},
        ) from exc

    return CountryBackfillResponse(
        status=str(result.get("status", "unknown")),
        requested=int(result.get("requested", 0) or 0),
        tagged=int(result.get("tagged", 0) or 0),
        skipped=int(result.get("skipped", 0) or 0),
        errors=int(result.get("errors", 0) or 0),
    )


@router.post(
    "/raptor/trigger",
    response_model=RaptorTriggerResponse,
    summary="Manuel RAPTOR weekly cluster build",
)
async def raptor_trigger(
    user: Annotated[User, Depends(require_admin)],
) -> RaptorTriggerResponse:
    from app.workers.tasks.raptor import _build_weekly_summary_cards_async

    try:
        result = await _build_weekly_summary_cards_async()
    except Exception as exc:  # pragma: no cover
        logger.exception("admin raptor trigger failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "RAPTOR_FAILED", "title": str(exc)[:200]},
        ) from exc

    return RaptorTriggerResponse(
        daily_count=int(result.get("daily_count", 0) or 0),
        cluster_count=int(result.get("cluster_count", 0) or 0),
        ok_count=int(result.get("ok_count", 0) or 0),
    )


# ============================================================================
# /admin/rag/inspect-query
# ============================================================================


@router.post(
    "/inspect-query",
    response_model=InspectQueryResponse,
    summary="Query inspector — RRF vs Reranked top-K",
)
async def inspect_query(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: InspectQueryRequest,
) -> InspectQueryResponse:
    """RRF only ve rerank sonrası sıralamayı yan yana gösterir."""
    from app.core.retrieval import hybrid_search_agenda_cards
    from app.prompts.query_planner import plan_query as run_planner, QueryPlan
    from app.providers.registry import bootstrap_default_providers, registry

    bootstrap_default_providers()

    # #202 — Opsiyonel Query Planner (kullanıcı yolundaki davranışla eşleştir)
    planner_info = InspectPlannerInfo(used=False)
    effective_query = payload.query
    if payload.use_planner:
        try:
            plan = await run_planner(user_request=payload.query)
            if isinstance(plan, QueryPlan):
                kw = list(plan.keywords or [])[:5]
                topic = plan.topic_query or payload.query
                effective_query = (
                    f"{topic} {' '.join(kw)}".strip() if kw else topic
                )
                planner_info = InspectPlannerInfo(
                    used=True,
                    enriched_query=effective_query,
                    keywords=kw,
                    topic_query=topic,
                    intent=plan.intent,
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("inspect planner failed: %s", exc)

    # Embedding (enriched query kullan)
    query_vec: list[float] | None = None
    try:
        emb_provider = registry.route_for_tier(operation="embedding", tier="free")
        emb_result = await emb_provider.create_embedding([effective_query])
        if emb_result.vectors and len(emb_result.vectors[0]) == 1024:
            query_vec = list(emb_result.vectors[0])
    except Exception as exc:
        logger.warning("inspect embed failed: %s", exc)

    # RRF only (rerank=False)
    rrf_rows = await hybrid_search_agenda_cards(
        db,
        query_text=effective_query,
        query_vector=query_vec,
        top_k=payload.top_k,
        candidate_pool=payload.candidate_pool,
        rerank=False,
        levels=("daily", "weekly"),
    )

    # Rerank (rerank=True) — aynı pool üzerinde
    reranked_rows = await hybrid_search_agenda_cards(
        db,
        query_text=effective_query,
        query_vector=query_vec,
        top_k=payload.top_k,
        candidate_pool=payload.candidate_pool,
        rerank=True,
        levels=("daily", "weekly"),
    )

    rrf_index = {str(r["id"]): i for i, r in enumerate(rrf_rows, start=1)}
    rerank_index = {str(r["id"]): i for i, r in enumerate(reranked_rows, start=1)}

    rrf_only_top = [
        InspectRow(
            id=str(r["id"]),
            title=str(r.get("title") or "")[:200],
            rrf_score=float(r.get("_rrf_score") or 0.0),
            rrf_rank=rrf_index.get(str(r["id"])),
            rerank_rank=rerank_index.get(str(r["id"])),
        )
        for r in rrf_rows
    ]
    reranked_top = [
        InspectRow(
            id=str(r["id"]),
            title=str(r.get("title") or "")[:200],
            rrf_score=float(r.get("_rrf_score") or 0.0),
            rerank_score=float(r.get("_rerank_score") or 0.0),
            rrf_rank=rrf_index.get(str(r["id"])),
            rerank_rank=rerank_index.get(str(r["id"])),
        )
        for r in reranked_rows
    ]
    # Birleşik (id sırası rerank list'inden)
    rows = reranked_top
    return InspectQueryResponse(
        query=payload.query,
        levels=["daily", "weekly"],
        rows=rows,
        rrf_only_top=rrf_only_top,
        reranked_top=reranked_top,
        planner=planner_info,
    )
