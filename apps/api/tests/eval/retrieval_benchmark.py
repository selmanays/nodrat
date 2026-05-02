"""Retrieval quality benchmark — NDCG@10 / MAP@5 / MRR@10 / Recall@20 (#179).

Türkçe golden set üzerinden mevcut hybrid_search_agenda_cards() pipeline'ının
ölçüsünü çıkarır. PR-B/C/D iyileştirmelerinin etkisini sayısal kıyaslamak için.

Kullanım:
    python -m tests.eval.retrieval_benchmark
    python -m tests.eval.retrieval_benchmark --golden retrieval_golden_tr.yaml
    python -m tests.eval.retrieval_benchmark --output report.json --top-k 20

Production (Docker compose):
    docker compose exec -T api python -m tests.eval.retrieval_benchmark

Output: stdout summary + opsiyonel JSON report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.retrieval import hybrid_search_agenda_cards
from app.providers.registry import bootstrap_default_providers, registry
from app.workers.tasks.sources import _get_session_factory


logger = logging.getLogger(__name__)

GOLDEN_DIR = Path(__file__).parent / "golden_sets"


@dataclass
class QueryEval:
    """Tek query'nin değerlendirme sonucu."""

    query_id: str
    query_text: str
    relevant_ids: list[str]  # gold qrels (sıralı, relevance-desc)
    retrieved_ids: list[str]  # run sonucu (sıralı, score-desc)
    latency_ms: float
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    """Tüm benchmark çıktısı."""

    golden_set: str
    n_queries: int
    top_k: int
    aggregate_metrics: dict[str, float]
    per_query: list[QueryEval]
    config: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Metric implementasyonları (ranx olmadan minimal)
# ---------------------------------------------------------------------------


def dcg_at_k(relevances: list[float], k: int) -> float:
    """Discounted Cumulative Gain @ k.

    DCG = sum_{i=1..k} (2^rel_i - 1) / log2(i + 1)
    """
    import math

    score = 0.0
    for i, rel in enumerate(relevances[:k], start=1):
        score += (2.0**rel - 1.0) / math.log2(i + 1)
    return score


def ndcg_at_k(retrieved: list[str], qrels: dict[str, float], k: int) -> float:
    """Normalized DCG @ k."""
    rels = [qrels.get(rid, 0.0) for rid in retrieved[:k]]
    ideal_rels = sorted(qrels.values(), reverse=True)[:k]
    ideal_dcg = dcg_at_k(ideal_rels, k)
    if ideal_dcg == 0.0:
        return 0.0
    return dcg_at_k(rels, k) / ideal_dcg


def precision_at_k(retrieved: list[str], qrels: dict[str, float], k: int) -> float:
    if not retrieved:
        return 0.0
    hits = sum(1 for rid in retrieved[:k] if qrels.get(rid, 0.0) > 0)
    return hits / k


def average_precision_at_k(
    retrieved: list[str], qrels: dict[str, float], k: int
) -> float:
    """AP@k — precision sum / number of relevant items."""
    relevant_count = sum(1 for v in qrels.values() if v > 0)
    if relevant_count == 0:
        return 0.0
    score = 0.0
    hits = 0
    for i, rid in enumerate(retrieved[:k], start=1):
        if qrels.get(rid, 0.0) > 0:
            hits += 1
            score += hits / i
    return score / min(relevant_count, k)


def reciprocal_rank(retrieved: list[str], qrels: dict[str, float]) -> float:
    """MRR — 1 / first relevant item rank."""
    for i, rid in enumerate(retrieved, start=1):
        if qrels.get(rid, 0.0) > 0:
            return 1.0 / i
    return 0.0


def recall_at_k(retrieved: list[str], qrels: dict[str, float], k: int) -> float:
    relevant_count = sum(1 for v in qrels.values() if v > 0)
    if relevant_count == 0:
        return 0.0
    hits = sum(1 for rid in retrieved[:k] if qrels.get(rid, 0.0) > 0)
    return hits / relevant_count


# ---------------------------------------------------------------------------
# Golden set loader
# ---------------------------------------------------------------------------


def load_golden_set(name: str) -> dict[str, Any]:
    """Load golden set YAML and validate minimal schema."""
    path = GOLDEN_DIR / name if not name.startswith("/") else Path(name)
    if not path.exists():
        raise FileNotFoundError(f"golden set not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if "queries" not in data or not isinstance(data["queries"], list):
        raise ValueError("golden set missing 'queries' list")
    return data


# ---------------------------------------------------------------------------
# Embed helper
# ---------------------------------------------------------------------------


async def embed_query(text: str) -> list[float] | None:
    """Try to embed via registered embedding provider. None on failure."""
    try:
        provider = registry.route_for_tier(operation="embedding", tier="free")
    except RuntimeError:
        logger.warning("no embedding provider — sparse-only retrieval")
        return None

    try:
        result = await provider.create_embedding([text])
    except Exception as exc:
        logger.warning("embed_query failed: %s", exc)
        return None

    if not result.vectors or len(result.vectors[0]) != 1024:
        logger.warning(
            "unexpected embedding dim: %s",
            len(result.vectors[0]) if result.vectors else 0,
        )
        return None

    return list(result.vectors[0])


# ---------------------------------------------------------------------------
# Single-query evaluation
# ---------------------------------------------------------------------------


async def evaluate_query(
    db: Any,
    *,
    query_id: str,
    query_text: str,
    relevant: list[dict],
    top_k: int,
    candidate_pool: int,
    use_planner: bool = True,
) -> QueryEval:
    qrels = {item["id"]: float(item.get("relevance", 1.0)) for item in relevant}
    relevant_ids = sorted(qrels.keys(), key=lambda k: qrels[k], reverse=True)

    t0 = time.perf_counter()

    # #240 — Query Planner enrichment (gerçek kullanıcı path'iyle aynı)
    effective_query = query_text
    geographic_focus = None
    if use_planner:
        try:
            from app.prompts.query_planner import plan_query as run_planner, QueryPlan

            plan = await run_planner(user_request=query_text)
            if isinstance(plan, QueryPlan):
                kw = list(plan.keywords or [])[:5]
                topic = plan.topic_query or query_text
                effective_query = (
                    f"{topic} {' '.join(kw)}".strip() if kw else topic
                )
                geographic_focus = getattr(plan, "geographic_focus", None)
        except Exception as exc:
            logger.warning("benchmark planner failed q=%s err=%s", query_id, exc)

    vec = await embed_query(effective_query)
    rows = await hybrid_search_agenda_cards(
        db,
        query_text=effective_query,
        query_vector=vec,
        top_k=top_k,
        candidate_pool=candidate_pool,
        geographic_focus=geographic_focus,
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0

    retrieved_ids = [str(r["id"]) for r in rows]

    metrics = {
        "ndcg@10": ndcg_at_k(retrieved_ids, qrels, 10),
        "map@5": average_precision_at_k(retrieved_ids, qrels, 5),
        "mrr@10": reciprocal_rank(retrieved_ids[:10], qrels),
        "recall@20": recall_at_k(retrieved_ids, qrels, 20),
        "p@5": precision_at_k(retrieved_ids, qrels, 5),
    }

    return QueryEval(
        query_id=query_id,
        query_text=query_text,
        relevant_ids=relevant_ids,
        retrieved_ids=retrieved_ids,
        latency_ms=latency_ms,
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


async def run_benchmark(
    *,
    golden_name: str,
    top_k: int = 20,
    candidate_pool: int = 50,
    persist: bool = False,
    triggered_by: str | None = None,
    use_planner: bool = True,
) -> BenchmarkReport:
    """Run benchmark; optionally persist to eval_runs table."""
    from datetime import datetime, timezone
    from decimal import Decimal

    bootstrap_default_providers()
    data = load_golden_set(golden_name)
    queries = data["queries"]

    factory = _get_session_factory()
    per_query: list[QueryEval] = []
    started_at = datetime.now(timezone.utc)

    async with factory() as db:
        for q in queries:
            qe = await evaluate_query(
                db,
                query_id=q["id"],
                query_text=q["text"],
                relevant=q.get("relevant", []),
                top_k=top_k,
                candidate_pool=candidate_pool,
                use_planner=use_planner,
            )
            per_query.append(qe)

    # Aggregate
    metric_keys = list(per_query[0].metrics.keys()) if per_query else []
    aggregate = {
        m: round(sum(qe.metrics[m] for qe in per_query) / max(len(per_query), 1), 4)
        for m in metric_keys
    }
    aggregate["latency_ms_p50"] = _percentile(
        [qe.latency_ms for qe in per_query], 50
    )
    aggregate["latency_ms_p95"] = _percentile(
        [qe.latency_ms for qe in per_query], 95
    )

    config = {
        "candidate_pool": candidate_pool,
        "min_semantic_score": 0.55,
        "min_text_score": 0.15,
        "rrf_k": 60,
    }
    report = BenchmarkReport(
        golden_set=golden_name,
        n_queries=len(per_query),
        top_k=top_k,
        aggregate_metrics=aggregate,
        per_query=per_query,
        config=config,
    )

    # #190 — DB persist (admin observability dashboard için)
    if persist:
        completed_at = datetime.now(timezone.utc)

        def _decimal(key: str) -> Decimal | None:
            val = aggregate.get(key)
            if val is None:
                return None
            try:
                return Decimal(str(val))
            except Exception:
                return None

        async with factory() as db:
            await db.execute(
                __import__("sqlalchemy").text(
                    """
                    INSERT INTO eval_runs (
                        golden_set, started_at, completed_at,
                        n_queries, top_k,
                        ndcg_10, map_5, mrr_10, recall_20, p_5,
                        latency_ms_p50, latency_ms_p95,
                        config_json, triggered_by
                    ) VALUES (
                        :golden, :start, :end,
                        :nq, :tk,
                        :ndcg, :map5, :mrr, :rec, :p5,
                        :p50, :p95,
                        CAST(:cfg AS jsonb), :trig
                    )
                    """
                ),
                {
                    "golden": golden_name,
                    "start": started_at,
                    "end": completed_at,
                    "nq": len(per_query),
                    "tk": top_k,
                    "ndcg": _decimal("ndcg@10"),
                    "map5": _decimal("map@5"),
                    "mrr": _decimal("mrr@10"),
                    "rec": _decimal("recall@20"),
                    "p5": _decimal("p@5"),
                    "p50": _decimal("latency_ms_p50"),
                    "p95": _decimal("latency_ms_p95"),
                    "cfg": __import__("json").dumps(config),
                    "trig": triggered_by or "cli",
                },
            )
            await db.commit()

    return report


def _percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * (p / 100.0))
    if idx >= len(sorted_v):
        idx = len(sorted_v) - 1
    return round(sorted_v[idx], 2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_summary(report: BenchmarkReport) -> str:
    lines = [
        f"Golden set : {report.golden_set}",
        f"Queries    : {report.n_queries}",
        f"Top-K      : {report.top_k}",
        "",
        "Aggregate metrics:",
    ]
    for m, v in report.aggregate_metrics.items():
        lines.append(f"  {m:<18} {v}")

    fails = [
        qe for qe in report.per_query
        if qe.metrics.get("ndcg@10", 0.0) < 0.3
    ]
    if fails:
        lines.append("")
        lines.append(f"Worst-performing queries (NDCG@10 < 0.3): {len(fails)}")
        for qe in fails[:10]:
            lines.append(
                f"  {qe.query_id} '{qe.query_text[:50]}'  "
                f"NDCG@10={qe.metrics['ndcg@10']:.3f}  "
                f"MRR={qe.metrics['mrr@10']:.3f}"
            )
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default="retrieval_golden_tr.yaml")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--pool", type=int, default=50)
    parser.add_argument("--output", help="optional JSON report path")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="DB'ye eval_runs row yaz (#190 admin dashboard için)",
    )
    parser.add_argument(
        "--no-planner",
        action="store_true",
        help="Query Planner'ı bypass et — raw query mode (eski davranış)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    report = await run_benchmark(
        golden_name=args.golden,
        top_k=args.top_k,
        candidate_pool=args.pool,
        persist=args.persist,
        triggered_by="cli",
        use_planner=not args.no_planner,
    )

    print(_format_summary(report))

    if args.output:
        Path(args.output).write_text(
            json.dumps(
                {
                    "golden_set": report.golden_set,
                    "n_queries": report.n_queries,
                    "top_k": report.top_k,
                    "aggregate_metrics": report.aggregate_metrics,
                    "config": report.config,
                    "per_query": [asdict(qe) for qe in report.per_query],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nReport written to: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
