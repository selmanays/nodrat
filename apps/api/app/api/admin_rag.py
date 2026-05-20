"""Admin RAG observability endpoints (#190).

docs/engineering/api-contracts.md §4 (admin endpoints)
Epic #189 — RAG observability dashboard backend.

> #854 KAPSAM NOTU: Bu izlence **RETRIEVAL katmanını** inceler
> (planner → hybrid_search_chunks → RRF → rerank). #845 agentic
> mimaride bu makine `search_news` tool'unun İÇİNDE sarmalı olarak
> AYNEN çalışır — yani inspect-query retrieval kalitesini hâlâ
> doğru ölçer. Research'in agentic ORKESTRASYON katmanı (LLM tool
> kararı, çok-tur döngü, search_wikipedia, condense) bunun
> ÜSTÜNDEdir ve buradan görünmez (tasarım gereği — retrieval
> debug aracı). Confidence router / meta_query / generate_text_stream
> #845'te kaldırıldı; izlence onları zaten kullanmıyor.

Endpoints:
    GET  /admin/rag/health                 — feature flags + counts
    GET  /admin/rag/benchmark/history      — son N eval_runs
    POST /admin/rag/benchmark/run          — async benchmark trigger
    GET  /admin/rag/citation-stats         — son 100 generation aggregate
    GET  /admin/rag/rerank-stats           — provider_call_logs nim_rerank
    GET  /admin/rag/raptor/clusters        — weekly + children
    POST /admin/rag/raptor/trigger         — manuel weekly cluster build
    POST /admin/rag/inspect-query          — RRF + rerank skorlarını döndür
    GET  /admin/rag/pipeline-comparison    — iki dönem arası LLM pipeline metrik karşılaştırması (#440)

Auth: require_admin (super_admin) — sadece sistem yöneticisi erişebilir.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db
from app.core.deps import require_admin
from app.core.settings_store import settings_store
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
    # #420 — use_local_embedding kaldırıldı (embedding artık tek provider:
    # local BAAI/bge-m3, NIM bge-m3 ekosistemden çıkarıldı).


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


class WarmUpInfo(BaseModel):
    """#696 (B6) — Cold start telemetri.

    PR-A #685 model warm-up startup'ta embedding + rerank model'i RAM'e yükler.
    Bu alan en son warm-up tamamlanma zamanı + süresi (process restart sonrası).
    """

    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float | None = None
    embedding_ms: float | None = None
    rerank_ms: float | None = None
    ok: bool = False


class RagHealthResponse(BaseModel):
    flags: FeatureFlags
    counts: HealthCounts
    last_eval: dict[str, Any] | None = None
    warm_up: WarmUpInfo | None = None  # #696 (B6)


class BenchmarkRunSummary(BaseModel):
    id: str
    golden_set: str
    started_at: datetime
    completed_at: datetime | None
    n_queries: int
    suite: str | None = None  # #712 B4 — chart suite-aware filtre
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
    # #742 (Faz 7c Aşama 1) — diagnostic answer extraction
    answer_span_candidates: list[str] = Field(default_factory=list)
    """Chunk içinde tespit edilen numerical span'lar (yüzde, miktar, skor, vb.).
    Telemetri amaçlı; Aşama 2'de query-side eşleştirme için kullanılır."""
    chunk_excerpt: str | None = None
    """Chunk text'inin ilk 300 char'ı (debug görünürlüğü). Cards path'inde title kullanılır."""
    article_id: str | None = None
    """Parent article id — chunks için chunk.article_id, cards için event_articles'tan ilk."""


class InspectQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=400)
    top_k: int = Field(10, ge=1, le=50)
    candidate_pool: int = Field(80, ge=10, le=200)
    # #202 — Query Planner ile zenginleştirme (kullanıcı yolundaki gibi)
    use_planner: bool = True
    # #696 — chunks (article chunks, NER + IDF) | cards (agenda, NER eklendi #714)
    # #718 — "production" suite: cards primary + chunks fallback (gerçek /api/generate akışı)
    suite: str = Field("production", pattern="^(cards|chunks|production)$")


class InspectPlannerInfo(BaseModel):
    used: bool
    enriched_query: str | None = None
    keywords: list[str] = Field(default_factory=list)
    topic_query: str | None = None
    intent: str | None = None


class InspectNerInfo(BaseModel):
    """#696 — NER pipeline telemetri (chunks suite'inde aktif).

    Mode'lar (PR #693 #691 Faz 6.1):
      - multi_and: 2+ rare entity (df<threshold) intersect → K=20 boost
      - multi_and_common: common entity AND intersect dar (<threshold) → K=20
      - single_rare: tek rare entity → K=30 (Faz 6 eski)
      - no_match: hiçbiri → boost yok
    """

    enabled: bool = False  # cards suite'te False
    query_entities: list[str] = Field(default_factory=list)
    df_map: dict[str, int] = Field(default_factory=dict)
    mode: str = "no_match"
    target_aids_count: int = 0
    target_aids_sample: list[str] = Field(default_factory=list)


class InspectTimeframeInfo(BaseModel):
    """#725 — Planner'dan çıkan timeframe SQL filter telemetri.

    Production /api/generate akışında planner.timeframes parse edilip
    hybrid_search_* çağrılarına `timeframe_from` + `timeframe_to` olarak
    geçer. Inspector bu davranışı simüle eder ki parity sağlansın.
    """

    enabled: bool = False
    timeframes: list[dict[str, str]] = Field(default_factory=list)
    """Planner'dan gelen label/from/to listesi."""
    effective_from: str | None = None
    """Retrieval SQL filter `timeframe_from` (en eski tarih)."""
    effective_to: str | None = None
    """Retrieval SQL filter `timeframe_to` (en geç tarih)."""
    span_days: float | None = None
    """En geniş timeframe'in span'i (gün)."""


class InspectSufficiencyInfo(BaseModel):
    """#725 — Sufficiency gate telemetri (tanı amaçlı, gate olarak DEĞİL).

    Production /api/generate akışında `check_sufficiency()` çağrılır ve
    `mode='current'` + `sufficient=False` ise erken çıkış (`insufficient_data`)
    yapılır. Inspector bu kontrolü çalıştırır ve sonucu gösterir ama erken
    çıkmaz — retrieval'ı tamamlar (tanı amaçlı).

    `would_have_exited=True` ise prod'da kullanıcı `insufficient_data` görür.
    """

    enabled: bool = False
    sufficient: bool = True
    mode: str = "current"
    """Plan mode'u (current/weekly/archive/comparison)."""
    counts_per_period: dict[str, int] = Field(default_factory=dict)
    min_evidence_per_period: int = 2
    reason: str | None = None
    would_have_exited: bool = False
    """mode='current' + sufficient=False ise True — prod'da bu sorgu fail eder."""


class InspectParentDocMerge(BaseModel):
    """#742 (Faz 7c Aşama 1) — parent doc merge görünürlüğü.

    Aynı article'dan birden fazla chunk top-K'de varsa cross-chunk merge
    için aday. Aşama 3'te bu gruplar LLM multi-chunk synthesis için
    kullanılacak.
    """

    article_id: str
    article_title: str | None = None
    chunk_count: int
    chunks: list[dict] = Field(default_factory=list)
    """List of {chunk_id, rank, excerpt} for chunks of this article in top-K."""


class InspectQueryResponse(BaseModel):
    query: str
    suite: str = "cards"  # #696
    levels: list[str]
    rows: list[InspectRow]
    rrf_only_top: list[InspectRow]
    reranked_top: list[InspectRow]
    planner: InspectPlannerInfo | None = None
    ner: InspectNerInfo | None = None  # #696 — chunks suite'inde dolu
    timeframe: InspectTimeframeInfo | None = None  # #725
    sufficiency: InspectSufficiencyInfo | None = None  # #725
    parent_doc_merge: list[InspectParentDocMerge] = Field(default_factory=list)
    """#742 (Faz 7c Aşama 1) — aynı article'dan 2+ chunk top-K'de varsa merge candidate."""


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
        (
            await db.execute(
                sa_text("""
                SELECT
                    (SELECT COUNT(*) FROM agenda_cards WHERE level='daily') AS daily_cards,
                    (SELECT COUNT(*) FROM agenda_cards WHERE level='weekly') AS weekly_cards,
                    (SELECT COUNT(*) FROM agenda_cards WHERE parent_card_id IS NOT NULL) AS daily_with_parent,
                    (SELECT COUNT(*) FROM event_clusters WHERE status IN ('active','developing')) AS active_clusters,
                    (SELECT COUNT(*) FROM messages WHERE created_at > NOW() - INTERVAL '24 hours' AND role='assistant') AS gen_24h,
                    -- #800/#845: `generations` DROP + insufficient_data status retired.
                    -- gen_24h = üretilen research cevabı; insufficient_24h artık
                    -- halü-flag'li mesaj sayısı (güncel kalite sinyali).
                    -- NOT: HealthCounts.last_24h_insufficient alan adı frontend
                    -- sözleşmesi için korundu (etiket güncellemesi frontend follow-up).
                    (SELECT COUNT(*) FROM messages WHERE created_at > NOW() - INTERVAL '24 hours' AND role='assistant' AND halu_flagged_at IS NOT NULL) AS insufficient_24h
                """)
            )
        )
        .mappings()
        .first()
    )

    # Last eval
    last_eval_row = (
        (
            await db.execute(
                sa_text("""
                SELECT id::text, golden_set, completed_at,
                       ndcg_10, map_5, mrr_10, recall_20,
                       latency_ms_p50, latency_ms_p95, n_queries
                FROM eval_runs
                ORDER BY created_at DESC
                LIMIT 1
                """)
            )
        )
        .mappings()
        .first()
    )

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
            "latency_ms_p50": (
                float(last_eval_row["latency_ms_p50"]) if last_eval_row["latency_ms_p50"] else None
            ),
            "latency_ms_p95": (
                float(last_eval_row["latency_ms_p95"]) if last_eval_row["latency_ms_p95"] else None
            ),
            "n_queries": last_eval_row["n_queries"],
        }

    # #758 (2026-05-12): Cross-encoder rerank kaldırıldı, `rerank.enabled` setting
    # ve `settings.reranker_enabled` config attr'ı silindi. Yeni opt-in flag
    # `retrieval.cross_encoder_enabled` (default False) — gelecekte yeni
    # reranker modeli denemek için altyapı. Production'da OFF kalıcı (3 model
    # eval fail history: #750 + #760).
    # `rerank.candidate_pool` setting key → `retrieval.candidate_pool` rename
    # edildi (#758 migration). settings.reranker_candidate_pool config attr
    # backward-compat olarak duruyor (50 default — RRF top-N).
    rerank_enabled = await settings_store.get_bool(db, "retrieval.cross_encoder_enabled", False)
    rerank_candidate_pool = await settings_store.get_int(
        db, "retrieval.candidate_pool", settings.reranker_candidate_pool
    )

    # #696 (B6) — Warm-up metrik (PR-A #685 cold start fix)
    from app.core import warmup_state

    warm_up = WarmUpInfo(
        started_at=warmup_state.STARTED_AT,
        completed_at=warmup_state.COMPLETED_AT,
        duration_ms=warmup_state.DURATION_MS,
        embedding_ms=warmup_state.EMBEDDING_MS,
        rerank_ms=warmup_state.RERANK_MS,
        ok=warmup_state.OK,
    )

    # #758: settings.nim_rerank_model silindi. Cross-encoder rerank kalıcı OFF —
    # 3 model fail history (NIM rerank, BAAI bge-reranker-v2-m3, Jina v2).
    # Aktif rerank katmanı LLM rerank (DeepSeek answer-aware, rerank.py).
    rerank_model_label = (
        "disabled (LLM rerank aktif)" if not rerank_enabled else "experimental cross-encoder"
    )

    return RagHealthResponse(
        flags=FeatureFlags(
            reranker_enabled=rerank_enabled,
            reranker_candidate_pool=rerank_candidate_pool,
            rerank_model=rerank_model_label,
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
        warm_up=warm_up,
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
        (
            await db.execute(
                sa_text("""
                SELECT id::text, golden_set, started_at, completed_at,
                       n_queries, ndcg_10, map_5, mrr_10, recall_20,
                       latency_ms_p50, latency_ms_p95, triggered_by, config_json
                FROM eval_runs
                ORDER BY created_at DESC
                LIMIT :limit
                """),
                {"limit": min(limit, 100)},
            )
        )
        .mappings()
        .all()
    )

    def _suite_from_config(cfg: Any) -> str | None:
        """#712 B4 — config_json içinden suite oku (eski koşumlarda None)."""
        if not cfg:
            return None
        try:
            if isinstance(cfg, str):
                import json as _json

                cfg = _json.loads(cfg)
            return cfg.get("suite") if isinstance(cfg, dict) else None
        except Exception:
            return None

    runs = [
        BenchmarkRunSummary(
            id=r["id"],
            golden_set=r["golden_set"],
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            n_queries=r["n_queries"],
            suite=_suite_from_config(r.get("config_json")),
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


# #700 — Background benchmark task durumu (in-process; basit)
# 55 sorgu × ~10s (chunks suite NER + LLM rerank) = ~5-10 dakika sürer.
# Caddy reverse proxy 120s timeout'a takılıyor → sync endpoint yetersizdi.
# Çözüm: asyncio.create_task ile arka planda koş, anında "started" yanıt;
# frontend history endpoint'i polling ile son sonucu görür.
_BENCHMARK_BG_STATE: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "completed_at": None,  # #712 B4 — son tamamlanma timestamp
    "triggered_by": None,
    "suite": None,
    "golden": None,
    "error": None,
}


async def _run_benchmark_background(
    *,
    golden: str,
    top_k: int,
    candidate_pool: int,
    suite: str,
    triggered_by: str,
) -> None:
    """asyncio.create_task hedefi — background koşum + state update."""
    from tests.eval.retrieval_benchmark import run_benchmark

    _BENCHMARK_BG_STATE["running"] = True
    _BENCHMARK_BG_STATE["started_at"] = datetime.now(UTC)
    _BENCHMARK_BG_STATE["completed_at"] = None
    _BENCHMARK_BG_STATE["triggered_by"] = triggered_by
    _BENCHMARK_BG_STATE["suite"] = suite
    _BENCHMARK_BG_STATE["golden"] = golden
    _BENCHMARK_BG_STATE["error"] = None
    try:
        await run_benchmark(
            golden_name=golden,
            top_k=top_k,
            candidate_pool=candidate_pool,
            persist=True,
            triggered_by=triggered_by,
            suite=suite,
        )
        logger.info(
            "background benchmark completed: golden=%s suite=%s triggered_by=%s",
            golden,
            suite,
            triggered_by,
        )
    except Exception as exc:
        logger.exception("background benchmark failed")
        _BENCHMARK_BG_STATE["error"] = str(exc)[:300]
    finally:
        _BENCHMARK_BG_STATE["running"] = False
        _BENCHMARK_BG_STATE["completed_at"] = datetime.now(UTC)


@router.get(
    "/benchmark/status",
    summary="#700 — Background benchmark koşum durumu",
)
async def benchmark_status(
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Polling endpoint — frontend bunu çağırıp running/done state'ini görür."""
    return dict(_BENCHMARK_BG_STATE)


@router.post(
    "/benchmark/run",
    response_model=BenchmarkTriggerResponse,
    summary="Manuel benchmark trigger (async background; #700)",
)
async def benchmark_run(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    golden: str = "retrieval_golden_tr.yaml",
    top_k: int = 20,
    candidate_pool: int = 50,
    suite: str = "chunks",
) -> BenchmarkTriggerResponse:
    """Async benchmark — anında "started" döner, arka planda koşar.

    #696 — `suite` default 'chunks' (production /api/generate/stream path'iyle aynı,
    NER + IDF + multi-entity AND dahil). Eski cards suite'i de korunur (`?suite=cards`).
    `candidate_pool` artık geçilir — admin endpoint'ten retrieval'a kadar.

    #700 — Background koşum (asyncio.create_task). Frontend `GET /benchmark/status`
    polling ile durum çeker; tamamlandığında `GET /benchmark/history` refresh eder.
    Caddy reverse proxy 120s timeout'a takılma sorunu giderildi.
    """
    if suite not in ("cards", "chunks"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SUITE", "title": "suite must be 'cards' or 'chunks'"},
        )

    # Concurrent koşumu engelle — aynı process içinde tek bir benchmark
    if _BENCHMARK_BG_STATE.get("running"):
        return BenchmarkTriggerResponse(
            started=False,
            run_id=None,
            message=(
                f"Halihazırda bir benchmark koşuyor "
                f"(suite={_BENCHMARK_BG_STATE.get('suite')}, "
                f"başlangıç={_BENCHMARK_BG_STATE.get('started_at')}). "
                "Bitmesini bekleyin."
            ),
        )

    import asyncio

    # RUF006: task ref'i module-level state'te tut → koşum bitmeden GC edilmesin
    _BENCHMARK_BG_STATE["task"] = asyncio.create_task(
        _run_benchmark_background(
            golden=golden,
            top_k=top_k,
            candidate_pool=candidate_pool,
            suite=suite,
            triggered_by=f"admin:{user.email}",
        )
    )

    # Halihazırdaki en yeni run id (önceki koşumdan kalan) — frontend hint
    last = (
        await db.execute(sa_text("SELECT id::text FROM eval_runs ORDER BY created_at DESC LIMIT 1"))
    ).scalar_one_or_none()

    return BenchmarkTriggerResponse(
        started=True,
        run_id=last,
        message=(
            f"Benchmark arka planda başlatıldı (suite={suite}, ~5-10dk). "
            "Durum için /admin/rag/benchmark/status, sonuç için /benchmark/history."
        ),
    )


# ============================================================================
# /admin/rag/ner-stats (#696 B5)
# ============================================================================


class NerStatsResponse(BaseModel):
    """#696 — NER pipeline mode dağılımı (process-lifetime).

    Bu telemetri in-memory (worker-local); container restart'ta sıfırlanır.
    Persistent storage gelecek bir sprint'te eklenecek (eval_runs benzeri).
    """

    total: int
    distribution: dict[str, int]
    ratios: dict[str, float]
    first_seen: datetime | None
    last_seen: datetime | None
    note: str = (
        "Process-lifetime counter; container restart'ta sıfırlanır. "
        "Mode'lar: multi_and (en güçlü) | multi_and_common | single_rare | no_match."
    )


@router.get(
    "/ner-stats",
    response_model=NerStatsResponse,
    summary="NER pipeline mode dağılımı (PR #693 #691 Faz 6.1 telemetri)",
)
async def ner_stats(
    user: Annotated[User, Depends(require_admin)],
) -> NerStatsResponse:
    from app.modules.entities import ner_stats as _ns

    snap = _ns.snapshot()
    return NerStatsResponse(
        total=snap["total"],
        distribution=snap["distribution"],
        ratios=snap["ratios"],
        first_seen=snap["first_seen"],
        last_seen=snap["last_seen"],
    )


# ============================================================================
# /admin/rag/ttft-stats (#739 — TTFT observability)
# ============================================================================


class TtftStatsResponse(BaseModel):
    """#739 — TTFT (Time-to-First-Token) observability stats.

    `generations.first_token_at` ile ölçülür (stream'da ilk SSE 'first_token').
    TTFT = first_token_at - created_at (ms). Eski rows NULL kalır.
    """

    window_hours: int
    sample_size: int
    """Bu window'da first_token_at dolu olan satır sayısı (completed stream)."""
    p50_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None
    avg_ms: float | None = None
    min_ms: float | None = None
    max_ms: float | None = None
    completed_total_ms_p50: float | None = None
    """Karşılaştırma için: full completion latency p50 (completed_at - created_at)."""


@router.get(
    "/ttft-stats",
    response_model=TtftStatsResponse,
    summary="TTFT (Time-to-First-Token) percentile dağılımı (#739)",
)
async def ttft_stats(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    window_hours: int = 24,
) -> TtftStatsResponse:
    """TTFT istatistikleri — #800/#845 sonrası RETIRED.

    `generations.first_token_at` ile ölçülüyordu; `generations` tablosu
    #800'de DROP edildi ve agentic mimari (#845) cevabı non-streaming
    üretip `_simulate_stream` ile yayınlıyor → gerçek "ilk token" kavramı
    yok. Endpoint 200 + boş örneklem döner (500 yerine); kavram retired.
    Güncel uçtan-uca latency provider_call_logs (operation='chat',
    PR-telemetry) üzerinden ele alınır.
    """
    return TtftStatsResponse(window_hours=window_hours, sample_size=0)


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
    # #800/#845 sonrası RETIRED. citation repair/unsupported metrikleri
    # `generations.output_json->'_citation'` + `warnings` üzerinden
    # hesaplanıyordu; `generations` tablosu #800'de DROP edildi. Agentic
    # mimaride citation provenance `messages.sources_used` (cited-only,
    # #851 tek `[n]`) — farklı şekil/semantik, ayrı bir metrik gerektirir.
    # 500 yerine 200 + sıfır örneklem döner; kavram retired (frontend
    # kartı kaldırma follow-up).
    _ = sample  # imza korunur; artık kullanılmıyor
    return CitationStatsResponse(
        sample_size=0,
        repairs_total=0,
        repairs_avg_per_gen=0.0,
        unsupported_warnings=0,
        unsupported_avg_per_gen=0.0,
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
    # #758 (2026-05-12): provider='nim_rerank' rows silindi (cross-encoder
    # cleanup migration). Aktif rerank katmanı LLM rerank (#756 telemetri
    # operation='llm_rerank' rows yazıyor). Bu endpoint LLM rerank latency
    # istatistiklerini gösterir.
    rows = (
        (
            await db.execute(
                sa_text("""
                SELECT latency_ms, created_at
                FROM provider_call_logs
                WHERE operation = 'llm_rerank'
                  AND created_at > NOW() - make_interval(hours => :hours)
                ORDER BY created_at DESC
                """),
                {"hours": int(hours)},
            )
        )
        .mappings()
        .all()
    )

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
        (
            await db.execute(
                sa_text("""
                SELECT id::text, title, summary, importance_score, updated_at
                FROM agenda_cards
                WHERE level = 'weekly'
                ORDER BY updated_at DESC
                LIMIT :limit
                """),
                {"limit": min(limit, 100)},
            )
        )
        .mappings()
        .all()
    )

    weekly_ids = [w["id"] for w in weekly_rows]
    children_map: dict[str, list[str]] = {wid: [] for wid in weekly_ids}
    if weekly_ids:
        in_clause = ", ".join(f"'{wid}'::uuid" for wid in weekly_ids)
        child_rows = (
            (
                await db.execute(
                    sa_text(f"""
                    SELECT id::text, title, parent_card_id::text AS parent_id
                    FROM agenda_cards
                    WHERE parent_card_id IN ({in_clause})
                    ORDER BY updated_at DESC
                    """)  # noqa: S608
                )
            )
            .mappings()
            .all()
        )
        for cr in child_rows:
            children_map.setdefault(cr["parent_id"], []).append(str(cr["title"])[:120])

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


class MissingChunksBackfillResponse(BaseModel):
    status: str
    requested: int
    dispatched: int
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
    "/backfill-missing-chunks",
    response_model=MissingChunksBackfillResponse,
    summary="cleaned ama chunks oluşmamış article'lar için chunk_article dispatch (#166)",
)
async def backfill_missing_chunks(
    user: Annotated[User, Depends(require_admin)],
    batch: int = 50,
) -> MissingChunksBackfillResponse:
    from app.workers.tasks.articles import _backfill_missing_chunks_async

    try:
        result = await _backfill_missing_chunks_async(min(max(batch, 1), 200))
    except Exception as exc:  # pragma: no cover
        logger.exception("admin backfill_missing_chunks failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "BACKFILL_FAILED", "title": str(exc)[:200]},
        ) from exc

    return MissingChunksBackfillResponse(
        status=str(result.get("status", "unknown")),
        requested=int(result.get("requested", 0) or 0),
        dispatched=int(result.get("dispatched", 0) or 0),
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
    """RRF only ve rerank sonrası sıralamayı yan yana gösterir.

    #696 — `suite` param ile chunks (prod path, NER + IDF dahil) veya cards
    (legacy agenda) seçilir. Chunks suite'inde NER mode/df_map/target_aids
    telemetrisi response'ta döner.
    """
    from app.core.data_sufficiency import check_sufficiency
    from app.core.rerank import _extract_entity_candidates
    from app.core.retrieval import (
        _ner_idf_match_aids,
        hybrid_search_agenda_cards,
        hybrid_search_chunks,
    )
    from app.prompts.query_planner import QueryPlan
    from app.prompts.query_planner import plan_query as run_planner
    from app.providers.registry import bootstrap_default_providers, registry

    bootstrap_default_providers()

    # #202 — Opsiyonel Query Planner (kullanıcı yolundaki davranışla eşleştir)
    # #712 B3 — Cards suite'inde planner enriched_query (topic + 5 keyword) cards
    # corpus için fazla geniş; topic + 1-2 keyword yeterli. Chunks suite'inde
    # mevcut davranış korunur (article corpus geniş).
    planner_info = InspectPlannerInfo(used=False)
    effective_query = payload.query
    plan: QueryPlan | None = None  # #725 — sonraki adımlarda timeframe + sufficiency için
    if payload.use_planner:
        try:
            _plan = await run_planner(user_request=payload.query)
            if isinstance(_plan, QueryPlan):
                plan = _plan
                kw_all = list(plan.keywords or [])[:5]
                # Cards suite: sadece topic + ilk keyword (corpus dar, pollution riski)
                kw = kw_all if payload.suite == "chunks" else kw_all[:1]
                topic = plan.topic_query or payload.query
                effective_query = f"{topic} {' '.join(kw)}".strip() if kw else topic
                planner_info = InspectPlannerInfo(
                    used=True,
                    enriched_query=effective_query,
                    keywords=kw,
                    topic_query=topic,
                    intent=plan.intent,
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("inspect planner failed: %s", exc)

    # #725 — Planner timeframes → SQL filter parametreleri (production parity)
    # app_generate.py:481-510 mantığı ile aynı: en geniş timeframe'den from/to,
    # span'a göre levels (daily/weekly/monthly).
    timeframe_info: InspectTimeframeInfo | None = None
    timeframe_from = None
    timeframe_to = None
    auto_levels: tuple[str, ...] = ("daily", "weekly")
    if plan is not None and plan.timeframes:
        try:
            from datetime import datetime as _dt

            spans_days: list[float] = []
            parsed_ranges: list[tuple] = []
            tf_list: list[dict[str, str]] = []
            for tf in plan.timeframes:
                tf_list.append(
                    {
                        "label": tf.label,
                        "from": tf.from_iso,
                        "to": tf.to_iso,
                    }
                )
                try:
                    a = _dt.fromisoformat(tf.from_iso.replace("Z", "+00:00"))
                    b = _dt.fromisoformat(tf.to_iso.replace("Z", "+00:00"))
                    spans_days.append(abs((b - a).total_seconds()) / 86400.0)
                    parsed_ranges.append((a, b))
                except Exception:  # noqa: S112
                    continue
            max_span = max(spans_days) if spans_days else 0.0
            if max_span >= 30:
                auto_levels = ("daily", "weekly", "monthly")
            elif max_span >= 6:
                auto_levels = ("daily", "weekly")
            else:
                auto_levels = ("daily",)
            if parsed_ranges:
                timeframe_from = min(r[0] for r in parsed_ranges)
                timeframe_to = max(r[1] for r in parsed_ranges)
            timeframe_info = InspectTimeframeInfo(
                enabled=True,
                timeframes=tf_list,
                effective_from=timeframe_from.isoformat() if timeframe_from else None,
                effective_to=timeframe_to.isoformat() if timeframe_to else None,
                span_days=max_span if max_span else None,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("inspect timeframe parse failed: %s", exc)

    # Embedding (enriched query kullan)
    query_vec: list[float] | None = None
    try:
        emb_provider = registry.route_for_tier(operation="embedding", tier="free")
        emb_result = await emb_provider.create_embedding([effective_query])
        if emb_result.vectors and len(emb_result.vectors[0]) == 1024:
            query_vec = list(emb_result.vectors[0])
    except Exception as exc:
        logger.warning("inspect embed failed: %s", exc)

    # #725 — Sufficiency telemetri (production parity).
    # Production /api/generate `mode='current'` + sufficient=False ise
    # `insufficient_data` ile erken çıkar (app_generate.py:355-392). Inspector
    # BURADA çıkmaz — telemetri olarak gösterir, retrieval'ı tamamlar (tanı amaçlı).
    sufficiency_info: InspectSufficiencyInfo | None = None
    if plan is not None and plan.timeframes:
        try:
            retrieval_plan_for_check = {
                "timeframes": [
                    {"label": tf.label, "from": tf.from_iso, "to": tf.to_iso}
                    for tf in plan.timeframes
                ],
                "mode": plan.mode,
                "topic_query": plan.topic_query,
            }
            _suf = await check_sufficiency(
                db,
                retrieval_plan=retrieval_plan_for_check,
                min_evidence_per_period=plan.minimum_evidence_per_period or 2,
            )
            _mode_lower = (plan.mode or "current").lower()
            sufficiency_info = InspectSufficiencyInfo(
                enabled=True,
                sufficient=_suf.sufficient,
                mode=_mode_lower,
                counts_per_period=_suf.counts_per_period,
                min_evidence_per_period=plan.minimum_evidence_per_period or 2,
                reason=_suf.reason,
                would_have_exited=(_mode_lower == "current" and not _suf.sufficient),
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("inspect sufficiency telemetry failed: %s", exc)

    # #696 + #718 — NER telemetri (cards + chunks her ikisinde aktif).
    # Önceki versiyon sadece chunks için doluyordu; cards path'ine NER eklendiği
    # için (#714) cards suite'inde de panel görünür olmalı.
    ner_info: InspectNerInfo | None = None
    if payload.suite in ("chunks", "cards", "production"):
        try:
            # cards/chunks normalize farklı; her ikisinde de norm_query/cleaned eşdeğeri olur
            from app.core.retrieval import normalize_tr_query

            _norm_for_ner = normalize_tr_query(effective_query)
            ents = _extract_entity_candidates(_norm_for_ner, min_len=3)
            target_aids, mode, df_map = await _ner_idf_match_aids(db, ents)
            ner_info = InspectNerInfo(
                enabled=True,
                query_entities=ents,
                df_map=df_map,
                mode=mode,
                target_aids_count=len(target_aids),
                target_aids_sample=list(target_aids)[:10],
            )
        except Exception as exc:
            logger.warning("inspect NER telemetry failed: %s", exc)
            ner_info = InspectNerInfo(enabled=True, mode="error")

    # Suite-aware retrieval
    # #718 — "production" suite gerçek /api/generate akışını birebir simüle eder:
    # cards PRIMARY → boşsa chunks FALLBACK (PR-E pattern app_generate.py:_search_with_fallback)
    # #725 — Production parity: planner.timeframes → timeframe_from/to SQL filter
    # ile birlikte (production'da olduğu gibi) geçiriyor.
    # #725 — Inspector production suite cards levels artık planner span'a göre
    # otomatik (`auto_levels`) — production parity.
    _cards_levels = auto_levels if payload.suite == "production" else ("daily", "weekly")
    if payload.suite == "production":
        # 1. Cards primary
        rrf_rows = await hybrid_search_agenda_cards(
            db,
            query_text=effective_query,
            query_vector=query_vec,
            top_k=payload.top_k,
            candidate_pool=payload.candidate_pool,
            rerank=False,
            levels=_cards_levels,
            timeframe_from=timeframe_from,  # #725
            timeframe_to=timeframe_to,
        )
        reranked_rows = await hybrid_search_agenda_cards(
            db,
            query_text=effective_query,
            query_vector=query_vec,
            top_k=payload.top_k,
            candidate_pool=payload.candidate_pool,
            rerank=True,
            levels=_cards_levels,
            timeframe_from=timeframe_from,  # #725
            timeframe_to=timeframe_to,
        )
        # 2. Yetersizse chunks fallback (PR-E mantığı: cards < threshold → chunks supplementary)
        cards_count = len(reranked_rows)
        if cards_count < 2:  # /generate'in cards yeterli threshold'u
            chunks_reranked = await hybrid_search_chunks(
                db,
                query_text=effective_query,
                query_vector=query_vec,
                top_k=payload.top_k,
                candidate_pool=payload.candidate_pool,
                since_hours=24 * 90,
                rerank=True,
                parent_doc_override=False,
                timeframe_from=timeframe_from,  # #725
                timeframe_to=timeframe_to,
            )
            # Chunks satırlarını cards formatına normalize et (UI tablosu için)
            for r in chunks_reranked:
                r.setdefault("id", r.get("chunk_id"))
                r.setdefault("title", r.get("article_title"))
            reranked_rows = (list(reranked_rows) + chunks_reranked)[: payload.top_k]
            rrf_rows = reranked_rows  # gerçek /generate'de aynı sırayla LLM'e gider
        _id_field = "id"
        _title_field = "title"
        levels_out = ["production"]
    elif payload.suite == "chunks":
        # #712 B1 — Inspector için parent_doc bypass: expanded chunks rerank'tan
        # geçmediği için _rerank_score=0 olur, debug görünümü temizliği için kapat.
        rrf_rows = await hybrid_search_chunks(
            db,
            query_text=effective_query,
            query_vector=query_vec,
            top_k=payload.top_k,
            candidate_pool=payload.candidate_pool,
            since_hours=24 * 90,
            rerank=False,
            parent_doc_override=False,
            timeframe_from=timeframe_from,  # #725
            timeframe_to=timeframe_to,
        )
        reranked_rows = await hybrid_search_chunks(
            db,
            query_text=effective_query,
            query_vector=query_vec,
            top_k=payload.top_k,
            candidate_pool=payload.candidate_pool,
            since_hours=24 * 90,
            rerank=True,
            parent_doc_override=False,
            timeframe_from=timeframe_from,  # #725
            timeframe_to=timeframe_to,
        )
        # chunks satırlarında "article_title" alanı; row id = chunk_id
        _id_field = "chunk_id"
        _title_field = "article_title"
        levels_out = ["chunks"]
    else:
        rrf_rows = await hybrid_search_agenda_cards(
            db,
            query_text=effective_query,
            query_vector=query_vec,
            top_k=payload.top_k,
            candidate_pool=payload.candidate_pool,
            rerank=False,
            levels=("daily", "weekly"),
            timeframe_from=timeframe_from,  # #725
            timeframe_to=timeframe_to,
        )
        reranked_rows = await hybrid_search_agenda_cards(
            db,
            query_text=effective_query,
            query_vector=query_vec,
            top_k=payload.top_k,
            candidate_pool=payload.candidate_pool,
            rerank=True,
            levels=("daily", "weekly"),
            timeframe_from=timeframe_from,  # #725
            timeframe_to=timeframe_to,
        )
        # #712 B3 — Cards+planner ON boş sonuç fallback: orijinal query ile retry
        # (enriched query cards corpus'unda fazla geniş olabilir)
        if not rrf_rows and payload.use_planner and effective_query != payload.query:
            logger.info("cards: planner enriched_query boş — orijinal query ile retry")
            # Orijinal query embed
            try:
                emb_result_orig = await emb_provider.create_embedding([payload.query])
                if emb_result_orig.vectors and len(emb_result_orig.vectors[0]) == 1024:
                    query_vec_orig = list(emb_result_orig.vectors[0])
                else:
                    query_vec_orig = query_vec
            except Exception:
                query_vec_orig = query_vec
            rrf_rows = await hybrid_search_agenda_cards(
                db,
                query_text=payload.query,
                query_vector=query_vec_orig,
                top_k=payload.top_k,
                candidate_pool=payload.candidate_pool,
                rerank=False,
                levels=("daily", "weekly"),
            )
            reranked_rows = await hybrid_search_agenda_cards(
                db,
                query_text=payload.query,
                query_vector=query_vec_orig,
                top_k=payload.top_k,
                candidate_pool=payload.candidate_pool,
                rerank=True,
                levels=("daily", "weekly"),
            )
        _id_field = "id"
        _title_field = "title"
        levels_out = ["daily", "weekly"]

    def _row_id(r: dict) -> str:
        return str(r.get(_id_field) or r.get("id") or "")

    rrf_index = {_row_id(r): i for i, r in enumerate(rrf_rows, start=1)}
    rerank_index = {_row_id(r): i for i, r in enumerate(reranked_rows, start=1)}

    def _f(v: Any) -> float | None:
        """#712 B1 — null-aware float (`or 0.0` 0 yerine gerçek None döner UI'da '—')."""
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # #718 — Dedupe: aynı title'lı cards UI'da tek satır (daily + weekly + farklı country
    # ayrı row olarak DB'de tutulur, debug görüntüsü kirletir). En yüksek skorlu olanı tut.
    def _dedupe_by_title(rows_in: list[dict]) -> list[dict]:
        seen: dict[str, dict] = {}
        for r in rows_in:
            t = str(r.get(_title_field) or r.get("title") or "")[:200].strip()
            if not t:
                seen[_row_id(r)] = r  # title yoksa id ile koru
                continue
            prev = seen.get(t)
            if prev is None:
                seen[t] = r
            else:
                # Yüksek rrf_score'u tut
                if float(r.get("_rrf_score") or 0) > float(prev.get("_rrf_score") or 0):
                    seen[t] = r
        return list(seen.values())

    rrf_rows_dedup = _dedupe_by_title(rrf_rows)
    reranked_rows_dedup = _dedupe_by_title(reranked_rows)

    # #742 (Faz 7c Aşama 1) — diagnostic helpers
    from app.core.answer_span import extract_numerical_spans

    def _row_text(r: dict) -> str:
        """Row'un chunk_text veya title text'ini al."""
        return str(
            r.get("chunk_text")
            or r.get("article_title")
            or r.get("title")
            or r.get("summary")
            or ""
        )

    def _row_excerpt(r: dict, n: int = 300) -> str:
        return _row_text(r)[:n]

    def _row_article_id(r: dict) -> str | None:
        # chunks suite'inde article_id field var; cards'ta event_id var ama
        # parent article farklı olabilir — şimdilik chunks için döndür.
        aid = r.get("article_id") or r.get("parent_article_id")
        return str(aid) if aid else None

    rrf_only_top = [
        InspectRow(
            id=_row_id(r),
            title=str(r.get(_title_field) or r.get("title") or "")[:200],
            rrf_score=_f(r.get("_rrf_score")),
            rrf_rank=rrf_index.get(_row_id(r)),
            rerank_rank=rerank_index.get(_row_id(r)),
            answer_span_candidates=extract_numerical_spans(_row_text(r)),
            chunk_excerpt=_row_excerpt(r),
            article_id=_row_article_id(r),
        )
        for r in rrf_rows_dedup
    ]
    reranked_top = [
        InspectRow(
            id=_row_id(r),
            title=str(r.get(_title_field) or r.get("title") or "")[:200],
            rrf_score=_f(r.get("_rrf_score")),
            rerank_score=_f(r.get("_rerank_score")),
            rrf_rank=rrf_index.get(_row_id(r)),
            rerank_rank=rerank_index.get(_row_id(r)),
            answer_span_candidates=extract_numerical_spans(_row_text(r)),
            chunk_excerpt=_row_excerpt(r),
            article_id=_row_article_id(r),
        )
        for r in reranked_rows_dedup
    ]
    rows = reranked_top

    # #742 — parent_doc_merge: aynı article'dan 2+ chunk varsa group
    parent_doc_merge: list[InspectParentDocMerge] = []
    if payload.suite in ("chunks", "production"):
        groups: dict[str, list[dict]] = {}
        for i, r in enumerate(reranked_rows_dedup):
            aid = _row_article_id(r)
            if not aid:
                continue
            groups.setdefault(aid, []).append({"row": r, "rank": i + 1})
        for aid, items in groups.items():
            if len(items) >= 2:
                parent_doc_merge.append(
                    InspectParentDocMerge(
                        article_id=aid,
                        article_title=str(
                            items[0]["row"].get("article_title")
                            or items[0]["row"].get("title")
                            or ""
                        )[:200],
                        chunk_count=len(items),
                        chunks=[
                            {
                                "chunk_id": _row_id(it["row"]),
                                "rank": it["rank"],
                                "excerpt": _row_excerpt(it["row"], 200),
                            }
                            for it in items
                        ],
                    )
                )
        parent_doc_merge.sort(key=lambda x: -x.chunk_count)

    return InspectQueryResponse(
        query=payload.query,
        suite=payload.suite,
        levels=levels_out,
        rows=rows,
        rrf_only_top=rrf_only_top,
        reranked_top=reranked_top,
        planner=planner_info,
        ner=ner_info,
        timeframe=timeframe_info,  # #725
        sufficiency=sufficiency_info,  # #725
        parent_doc_merge=parent_doc_merge,  # #742
    )


# =============================================================================
# #440 — Pipeline Comparison endpoint
# =============================================================================
#
# İki tarih aralığında LLM pipeline'ın performans metriklerini yan yana koyar:
# avg input/output tokens, latency P50/P95, cost/req, cache hit ratio,
# halü flag oranı ve insufficient_data oranı. Optimizasyon dalgalarının
# (örn. MVP-2.1 prompt cache ve top_k tuning) etkisini ölçmek için kullanılır.
#
# Default: son 7 gün (B) vs önceki 7 gün (A). Query parametreleriyle özel
# tarih aralıkları geçirilebilir.


class PeriodMetrics(BaseModel):
    """Tek bir tarih aralığı için agreged pipeline metrikleri."""

    period_start: datetime
    period_end: datetime
    sample_count: int = Field(description="provider_call_logs.operation='chat' satır sayısı")
    avg_input_tokens: float | None
    avg_output_tokens: float | None
    cache_hit_ratio: float | None = Field(
        default=None, description="sum(cached_tokens)/sum(input_tokens) — DeepSeek cache hit oranı"
    )
    avg_cost_usd_per_req: float | None
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    halu_flag_rate: float | None = Field(
        default=None,
        description="messages.halu_flagged_at NOT NULL / assistant cevap (#800/#845)",
    )
    insufficient_data_rate: float | None = Field(
        default=None,
        description="RETIRED (#845 — insufficient_data status yok); daima 0/None",
    )
    completed_generation_count: int = Field(
        description="Üretilen research cevabı sayısı (assistant message, #800)"
    )


class PipelineComparisonResponse(BaseModel):
    """Two-period pipeline metric comparison.

    `delta_pct` her metrik için (B - A) / A * 100. None değer veya A=0 → None.
    """

    period_a: PeriodMetrics = Field(description="Önceki dönem (referans / baseline)")
    period_b: PeriodMetrics = Field(description="Sonraki dönem (karşılaştırma)")
    delta_pct: dict[str, float | None]


# DeepSeek Content Generator + Query Planner çağrıları sadece research operation.
# Embedding (local_bge_m3, NIM) ve rerank (NIM) hariç tutulur — pipeline
# observability LLM çağrı katmanına odaklanır.
_PIPELINE_PROVIDER_METRICS_SQL = """
SELECT
    COUNT(*)::int                                    AS sample_count,
    AVG(input_tokens)::float                         AS avg_input_tokens,
    AVG(output_tokens)::float                        AS avg_output_tokens,
    SUM(COALESCE(cached_tokens, 0))::float           AS sum_cached,
    SUM(COALESCE(input_tokens, 0))::float            AS sum_input,
    AVG(cost_usd)::float                             AS avg_cost_usd,
    PERCENTILE_DISC(0.5)
        WITHIN GROUP (ORDER BY latency_ms)::int      AS p50_latency_ms,
    PERCENTILE_DISC(0.95)
        WITHIN GROUP (ORDER BY latency_ms)::int      AS p95_latency_ms
FROM provider_call_logs
WHERE created_at >= :start
  AND created_at <  :end
  AND operation = 'research'
  AND success = TRUE
"""

# #800/#845: `generations` DROP + insufficient_data status retired.
# Halü oranı artık `messages` (research assistant cevapları) üzerinden:
#   total      = üretilen research cevabı (assistant message)
#   halu_count = halü-flag'li (messages.halu_flagged_at NOT NULL) — güncel
#                kalite sinyali, gerçek veri
#   insuff_count = 0 (insufficient_data kavramı agentic mimaride yok)
_PIPELINE_GENERATION_QUALITY_SQL = """
SELECT
    COUNT(*) FILTER (WHERE role = 'assistant')::int          AS total,
    COUNT(*) FILTER (
        WHERE role = 'assistant' AND halu_flagged_at IS NOT NULL
    )::int                                                    AS halu_count,
    0::int                                                    AS insuff_count
FROM messages
WHERE created_at >= :start
  AND created_at <  :end
"""


async def _pipeline_period_metrics(
    db: AsyncSession,
    *,
    start: datetime,
    end: datetime,
) -> PeriodMetrics:
    prov_row = (
        await db.execute(sa_text(_PIPELINE_PROVIDER_METRICS_SQL), {"start": start, "end": end})
    ).one()
    gen_row = (
        await db.execute(sa_text(_PIPELINE_GENERATION_QUALITY_SQL), {"start": start, "end": end})
    ).one()

    sum_input = prov_row.sum_input or 0.0
    sum_cached = prov_row.sum_cached or 0.0
    cache_hit_ratio = (sum_cached / sum_input) if sum_input > 0 else None

    total_gen = gen_row.total or 0
    halu_rate = (gen_row.halu_count / total_gen) if total_gen > 0 else None
    insuff_rate = (gen_row.insuff_count / total_gen) if total_gen > 0 else None

    return PeriodMetrics(
        period_start=start,
        period_end=end,
        sample_count=prov_row.sample_count or 0,
        avg_input_tokens=prov_row.avg_input_tokens,
        avg_output_tokens=prov_row.avg_output_tokens,
        cache_hit_ratio=cache_hit_ratio,
        avg_cost_usd_per_req=prov_row.avg_cost_usd,
        p50_latency_ms=prov_row.p50_latency_ms,
        p95_latency_ms=prov_row.p95_latency_ms,
        halu_flag_rate=halu_rate,
        insufficient_data_rate=insuff_rate,
        completed_generation_count=total_gen,
    )


def _pipeline_delta_pct(a_val: float | None, b_val: float | None) -> float | None:
    """B/A yüzdesel değişim. None değer veya A=0 → None (zero-division koruması)."""
    if a_val is None or b_val is None or a_val == 0:
        return None
    return round(((b_val - a_val) / a_val) * 100, 2)


@router.get(
    "/pipeline-comparison",
    response_model=PipelineComparisonResponse,
    summary="İki dönem arası LLM pipeline metrik karşılaştırması",
)
async def pipeline_comparison(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_a: Annotated[
        datetime | None,
        Query(description="Dönem A başlangıcı (default: now - 14d)"),
    ] = None,
    to_a: Annotated[
        datetime | None,
        Query(description="Dönem A bitişi (default: now - 7d)"),
    ] = None,
    from_b: Annotated[
        datetime | None,
        Query(description="Dönem B başlangıcı (default: now - 7d)"),
    ] = None,
    to_b: Annotated[
        datetime | None,
        Query(description="Dönem B bitişi (default: now)"),
    ] = None,
) -> PipelineComparisonResponse:
    """Pipeline performans karşılaştırması — iki tarih aralığını yan yana koyar.

    Veri kaynakları:
        provider_call_logs (operation='chat')  → token, latency, cost, cache hit
        messages (role='assistant', #800/#845)  → halu_flag_rate
        (insufficient_data_rate RETIRED — agentic mimaride yok, daima 0/None)

    Default davranış: son 7 gün (B) vs önceki 7 gün (A). Periyodik
    optimizasyon kontrolü için tek başına çağrılabilir.

    Belirli bir dönüm noktasını ölçmek için (örn. bir prompt değişikliği
    deploy'u sonrası), tüm dört query parametresini deploy timestamp'i
    etrafında ayarla.

    Boş window (sample_count=0) durumunda metrikler null döner; ilgili
    delta_pct alanları da null.
    """
    now = datetime.now(UTC)

    # Default: son 7 gün vs önceki 7 gün
    period_b_end = to_b or now
    period_b_start = from_b or (period_b_end - timedelta(days=7))
    period_a_end = to_a or period_b_start
    period_a_start = from_a or (period_a_end - timedelta(days=7))

    # Naïve datetime'lara UTC ekle
    for label, dt in (
        ("from_a", period_a_start),
        ("to_a", period_a_end),
        ("from_b", period_b_start),
        ("to_b", period_b_end),
    ):
        if dt.tzinfo is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "TZ_REQUIRED", "title": f"{label} timezone bilgisi içermeli"},
            )

    if period_a_start >= period_a_end or period_b_start >= period_b_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_RANGE", "title": "Başlangıç < bitiş olmalı"},
        )

    period_a = await _pipeline_period_metrics(db, start=period_a_start, end=period_a_end)
    period_b = await _pipeline_period_metrics(db, start=period_b_start, end=period_b_end)

    delta_pct: dict[str, float | None] = {
        "avg_input_tokens": _pipeline_delta_pct(
            period_a.avg_input_tokens, period_b.avg_input_tokens
        ),
        "avg_output_tokens": _pipeline_delta_pct(
            period_a.avg_output_tokens, period_b.avg_output_tokens
        ),
        "cache_hit_ratio": _pipeline_delta_pct(period_a.cache_hit_ratio, period_b.cache_hit_ratio),
        "avg_cost_usd_per_req": _pipeline_delta_pct(
            period_a.avg_cost_usd_per_req, period_b.avg_cost_usd_per_req
        ),
        "p50_latency_ms": _pipeline_delta_pct(period_a.p50_latency_ms, period_b.p50_latency_ms),
        "p95_latency_ms": _pipeline_delta_pct(period_a.p95_latency_ms, period_b.p95_latency_ms),
        "halu_flag_rate": _pipeline_delta_pct(period_a.halu_flag_rate, period_b.halu_flag_rate),
    }

    return PipelineComparisonResponse(
        period_a=period_a,
        period_b=period_b,
        delta_pct=delta_pct,
    )


# ============================================================================
# /admin/rag/cache-telemetry  (#981/#982 — "Önbellek" sekmesi)
# Locked decision pipeline-observability-location: LLM/cache metriği
# /admin/rag SEKMESİ olarak gelir (yeni sayfa/observability AÇILMAZ).
# ============================================================================


class CacheCallTypeRow(BaseModel):
    call_type: str
    calls: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    miss_tokens: int
    cache_hit_ratio: float | None
    tools_present_rate: float | None


class CacheSegmentAvg(BaseModel):
    seg_system: float | None
    seg_tools_schema: float | None
    seg_msg1_question: float | None
    seg_rag_tool: float | None
    seg_assistant_intermediate: float | None


class CacheTelemetryResponse(BaseModel):
    window_hours: int
    total_calls: int
    overall_cache_hit_ratio: float | None
    total_input_tokens: int
    total_cached_tokens: int
    total_miss_tokens: int
    by_call_type: list[CacheCallTypeRow]
    segment_avg: CacheSegmentAvg


@router.get(
    "/cache-telemetry",
    response_model=CacheTelemetryResponse,
    summary="Research prompt-cache segment telemetri (#981/#982) — token-bazlı, fiyat-bağımsız",
)
async def cache_telemetry(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: int = 24,
    user_id: str | None = None,
) -> CacheTelemetryResponse:
    """research_cache_telemetry agregasyonu. Senaryo-B (#983) doğrulaması:
    call_type='forced_final' satırlarında tools_present_rate + cache_hit_ratio
    bakılır. $ VERİLMEZ (token-bazlı, fiyat-bağımsız — maliyet-yanılgısı dersi);
    gerçek $ provider_call_logs.cost_usd'de (ayrı, #990 sonrası doğru)."""
    hours = max(1, min(int(hours), 24 * 90))
    uid: str | None = None
    if user_id:
        from uuid import UUID

        try:
            uid = str(UUID(user_id))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="geçersiz user_id (uuid bekleniyor)",
            ) from None

    params = {"hours": hours, "uid": uid}
    rows = (
        (
            await db.execute(
                sa_text("""
                SELECT call_type,
                       count(*)                       AS calls,
                       COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                       COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens,
                       ROUND(AVG(CASE WHEN tools_present THEN 1.0 ELSE 0.0 END)::numeric, 3)
                                                       AS tools_present_rate
                FROM research_cache_telemetry
                WHERE created_at > NOW() - make_interval(hours => :hours)
                  AND (CAST(:uid AS uuid) IS NULL OR user_id = CAST(:uid AS uuid))
                GROUP BY call_type
                ORDER BY call_type
                """),
                params,
            )
        )
        .mappings()
        .all()
    )
    seg = (
        (
            await db.execute(
                sa_text("""
                SELECT ROUND(AVG(seg_system)::numeric, 1)                 AS seg_system,
                       ROUND(AVG(seg_tools_schema)::numeric, 1)           AS seg_tools_schema,
                       ROUND(AVG(seg_msg1_question)::numeric, 1)          AS seg_msg1_question,
                       ROUND(AVG(seg_rag_tool)::numeric, 1)               AS seg_rag_tool,
                       ROUND(AVG(seg_assistant_intermediate)::numeric, 1) AS seg_assistant_intermediate
                FROM research_cache_telemetry
                WHERE created_at > NOW() - make_interval(hours => :hours)
                  AND (CAST(:uid AS uuid) IS NULL OR user_id = CAST(:uid AS uuid))
                """),
                params,
            )
        )
        .mappings()
        .first()
    )

    def _ratio(cached: int, inp: int) -> float | None:
        return round(cached / inp, 4) if inp else None

    by_call_type: list[CacheCallTypeRow] = []
    t_in = t_cached = t_out = t_calls = 0
    for r in rows:
        inp = int(r["input_tokens"] or 0)
        cached = int(r["cached_tokens"] or 0)
        out = int(r["output_tokens"] or 0)
        n = int(r["calls"] or 0)
        t_in += inp
        t_cached += cached
        t_out += out
        t_calls += n
        by_call_type.append(
            CacheCallTypeRow(
                call_type=r["call_type"],
                calls=n,
                input_tokens=inp,
                cached_tokens=cached,
                output_tokens=out,
                miss_tokens=max(inp - cached, 0),
                cache_hit_ratio=_ratio(cached, inp),
                tools_present_rate=(
                    float(r["tools_present_rate"]) if r["tools_present_rate"] is not None else None
                ),
            )
        )

    return CacheTelemetryResponse(
        window_hours=hours,
        total_calls=t_calls,
        overall_cache_hit_ratio=_ratio(t_cached, t_in),
        total_input_tokens=t_in,
        total_cached_tokens=t_cached,
        total_miss_tokens=max(t_in - t_cached, 0),
        by_call_type=by_call_type,
        segment_avg=CacheSegmentAvg(
            seg_system=float(seg["seg_system"]) if seg and seg["seg_system"] is not None else None,
            seg_tools_schema=float(seg["seg_tools_schema"])
            if seg and seg["seg_tools_schema"] is not None
            else None,
            seg_msg1_question=float(seg["seg_msg1_question"])
            if seg and seg["seg_msg1_question"] is not None
            else None,
            seg_rag_tool=float(seg["seg_rag_tool"])
            if seg and seg["seg_rag_tool"] is not None
            else None,
            seg_assistant_intermediate=float(seg["seg_assistant_intermediate"])
            if seg and seg["seg_assistant_intermediate"] is not None
            else None,
        ),
    )
