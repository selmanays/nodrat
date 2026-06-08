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
from datetime import UTC
from pathlib import Path
from typing import Any

import yaml
from app.core.retrieval import hybrid_search_agenda_cards, hybrid_search_chunks
from app.providers.registry import bootstrap_default_providers, registry
from app.shared.workers.db_session import _get_session_factory
from sqlalchemy import text as sa_text

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


def average_precision_at_k(retrieved: list[str], qrels: dict[str, float], k: int) -> float:
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
# #619 PR-4A — query decomposition proxy (benchmark-içi; production'a SIZMAZ)
# ---------------------------------------------------------------------------


def _merge_rrf_sum(per_subquery_rows: list[list[dict]], *, top_k: int) -> list[str]:
    """N alt-sorgu chunk-row listesini article-level ``_rrf_score`` SUM ile
    birleştir → top-K article_id (deterministik).

    BENCHMARK-İÇİ proxy merge — production retrieval/orchestration'a SIZMAZ.
    Prod PR-3 = 3b LLM-driven (LLM tool-loop merge); bu yalnız ölçüm aracıdır.
    Saf fonksiyon (DB-suz) → deterministik unit-test edilebilir.
    """
    merged: dict[str, float] = {}
    for rows in per_subquery_rows:
        seen_local: set[str] = set()
        for r in rows:
            aid = str(r.get("article_id", ""))
            if not aid or aid in seen_local:
                continue
            seen_local.add(aid)
            merged[aid] = merged.get(aid, 0.0) + float(r.get("_rrf_score", 0.0) or 0.0)
    return sorted(merged, key=lambda a: merged[a], reverse=True)[:top_k]


def _merge_rrf_max(per_subquery_rows: list[list[dict]], *, top_k: int) -> list[str]:
    """#619 PR-4D — article-level ``_rrf_score`` cross-query MAX (tek-güçlü alt-sorgu).

    Deterministik; konfirmasyon yerine en-iyi-tek-sinyal. Saf, DB-suz.
    """
    merged: dict[str, float] = {}
    for rows in per_subquery_rows:
        seen_local: set[str] = set()
        for r in rows:
            aid = str(r.get("article_id", ""))
            if not aid or aid in seen_local:
                continue
            seen_local.add(aid)
            merged[aid] = max(merged.get(aid, 0.0), float(r.get("_rrf_score", 0.0) or 0.0))
    return sorted(merged, key=lambda a: merged[a], reverse=True)[:top_k]


def _merge_rank_rrf(per_subquery_rows: list[list[dict]], *, top_k: int, k: int = 60) -> list[str]:
    """#619 PR-4D — KLASİK RRF: alt-sorgu RANK'ından ``Σ 1/(k+rank)`` (ölçek-bağımsız).

    `_rrf_score` mutlak-değerini değil pozisyonu kullanır → alt-sorgular arası
    dağılım farkına dayanıklı (rrf_sum'ın orijinal-relevance-kaybını azaltır).
    Öncelikli düzeltme adayı. Deterministik, saf, DB-suz.
    """
    merged: dict[str, float] = {}
    for rows in per_subquery_rows:
        seen_local: set[str] = set()
        rank = 0
        for r in rows:
            aid = str(r.get("article_id", ""))
            if not aid or aid in seen_local:
                continue
            seen_local.add(aid)
            rank += 1  # alt-sorgu-içi 1-based article rank
            merged[aid] = merged.get(aid, 0.0) + 1.0 / (k + rank)
    return sorted(merged, key=lambda a: merged[a], reverse=True)[:top_k]


def _merge_union_preserve_order(per_subquery_rows: list[list[dict]], *, top_k: int) -> list[str]:
    """#619 PR-4D — round-robin union: alt-sorgulardan sırayla ilk-görülen article
    (skor-bağımsız, dengeli interleave). Deterministik, saf, DB-suz.
    """
    out: list[str] = []
    seen: set[str] = set()
    # Her alt-sorgunun aynı rank pozisyonunu sırayla gez (round-robin)
    max_len = max((len(rows) for rows in per_subquery_rows), default=0)
    for i in range(max_len):
        for rows in per_subquery_rows:
            if i < len(rows):
                aid = str(rows[i].get("article_id", ""))
                if aid and aid not in seen:
                    seen.add(aid)
                    out.append(aid)
                    if len(out) >= top_k:
                        return out
    return out[:top_k]


# #619 PR-4D — merge stratejisi dispatch (deterministik; rerank_rows DAHİL DEĞİL,
# o LLM/non-det + prod-strateji değil benchmark-aracı — ayrı değerlendirilir).
_MERGE_FUNCS = {
    "rrf_sum": _merge_rrf_sum,
    "rrf_max": _merge_rrf_max,
    "rank_rrf": _merge_rank_rrf,
    "union": _merge_union_preserve_order,
}


async def _decompose_sub_queries(effective_query: str, *, mode: str) -> list[str]:
    """``decompose_query`` proxy çağrısı. ``mode='heuristic'`` deterministik;
    ``'llm'`` chat-provider (non-det, opsiyonel). Bölünmezse ``[effective_query]``.
    """
    from app.prompts.query_decomposition import decompose_query

    provider = None
    if mode == "llm":
        try:
            provider = registry.route_for_tier(operation="chat", tier="free")
        except RuntimeError:
            logger.warning("no chat provider — decompose llm falls back to heuristic-only")
    dr = await decompose_query(effective_query, provider=provider, llm_enabled=(mode == "llm"))
    return dr.sub_queries or [effective_query]


# ---------------------------------------------------------------------------
# Single-query evaluation
# ---------------------------------------------------------------------------


async def _map_card_ids_to_articles(db: Any, card_ids: list[str]) -> dict[str, list[str]]:
    """#696 — agenda_cards.id → article_id'ler mapping (chunks suite için).

    Mapping yolu: agenda_cards (card.event_id) → event_articles (article_id'ler).
    Bir card birden fazla article ile ilişkili olabilir (event = haber kümesi).
    """
    if not card_ids:
        return {}
    try:
        rows = (
            (
                await db.execute(
                    sa_text(
                        """
                    SELECT ac.id::text AS cid, ea.article_id::text AS aid
                    FROM agenda_cards ac
                    JOIN event_articles ea ON ea.event_id = ac.event_id
                    WHERE ac.id::text = ANY(:ids)
                    """
                    ),
                    {"ids": card_ids},
                )
            )
            .mappings()
            .all()
        )
        mapping: dict[str, list[str]] = {}
        for r in rows:
            mapping.setdefault(r["cid"], []).append(r["aid"])
        return mapping
    except Exception as exc:
        logger.warning("card→article mapping failed: %s", exc)
        return {}


async def evaluate_query(
    db: Any,
    *,
    query_id: str,
    query_text: str,
    relevant: list[dict],
    top_k: int,
    candidate_pool: int,
    use_planner: bool = False,
    suite: str = "cards",
    decompose: str = "off",
    merge: str = "rrf_sum",
    rerank: bool = True,
) -> QueryEval:
    """
    #696 — `suite` param ile retrieval path seçimi:
    - "cards" (default eski davranış): hybrid_search_agenda_cards — agenda card seviyesi
    - "chunks": hybrid_search_chunks — production /api/generate/stream ile aynı path
      (NER stream, parent-doc, IDF + multi-entity AND dahil)

    Chunks suite'inde qrels (card_id → relevance) önce article_id mapping ile
    çevrilir; chunks retrieval article_id döndürdüğü için skor karşılaştırması
    article düzeyinde yapılır.
    """
    qrels = {item["id"]: float(item.get("relevance", 1.0)) for item in relevant}

    t0 = time.perf_counter()

    # #240 — Query Planner enrichment (gerçek kullanıcı path'iyle aynı)
    effective_query = query_text
    geographic_focus = None
    if use_planner:
        try:
            from app.prompts.query_planner import QueryPlan
            from app.prompts.query_planner import plan_query as run_planner

            plan = await run_planner(user_request=query_text)
            if isinstance(plan, QueryPlan):
                kw = list(plan.keywords or [])[:5]
                topic = plan.topic_query or query_text
                effective_query = f"{topic} {' '.join(kw)}".strip() if kw else topic
                geographic_focus = getattr(plan, "geographic_focus", None)
        except Exception as exc:
            logger.warning("benchmark planner failed q=%s err=%s", query_id, exc)

    vec = await embed_query(effective_query)

    if suite == "chunks":
        # #696 — Production-faithful chunks path (NER + parent-doc dahil)
        # qrels card_id → article_id'ler çevir (event_articles üzerinden 1:N)
        article_qrels_map = await _map_card_ids_to_articles(db, list(qrels.keys()))
        chunks_qrels: dict[str, float] = {}
        for cid, rel in qrels.items():
            aids = article_qrels_map.get(cid, [])
            for aid in aids:
                # Aynı article birden fazla relevant card'a sahipse max relevance
                chunks_qrels[aid] = max(chunks_qrels.get(aid, 0.0), rel)
        qrels = chunks_qrels

        if decompose == "off":
            # Mevcut davranış AYNEN (byte-identical) — decompose kapalı
            rows = await hybrid_search_chunks(
                db,
                query_text=effective_query,
                query_vector=vec,
                top_k=top_k,
                candidate_pool=candidate_pool,
                since_hours=24 * 90,
                rerank=rerank,
            )
            # Aynı article'dan birden fazla chunk gelebilir → unique article order
            seen_aid: set[str] = set()
            retrieved_ids: list[str] = []
            for r in rows:
                aid = str(r.get("article_id", ""))
                if aid and aid not in seen_aid:
                    seen_aid.add(aid)
                    retrieved_ids.append(aid)
        else:
            # #619 PR-4A — decompose+merge proxy (her alt-sorgu ayrı retrieve,
            # _rrf_score SUM merge). Deterministik; prod 3b LLM-driven değil.
            sub_queries = await _decompose_sub_queries(effective_query, mode=decompose)
            per_sq_rows: list[list[dict]] = []
            for sq in sub_queries:
                sq_vec = vec if sq == effective_query else await embed_query(sq)
                sq_rows = await hybrid_search_chunks(
                    db,
                    query_text=sq,
                    query_vector=sq_vec,
                    top_k=top_k,
                    candidate_pool=candidate_pool,
                    since_hours=24 * 90,
                    rerank=rerank,
                )
                per_sq_rows.append(sq_rows)
            retrieved_ids = _MERGE_FUNCS[merge](per_sq_rows, top_k=top_k)
    else:
        # Cards suite — eski davranış (agenda_cards seviyesi)
        rows = await hybrid_search_agenda_cards(
            db,
            query_text=effective_query,
            query_vector=vec,
            top_k=top_k,
            candidate_pool=candidate_pool,
            geographic_focus=geographic_focus,
        )
        retrieved_ids = [str(r["id"]) for r in rows]

    latency_ms = (time.perf_counter() - t0) * 1000.0
    relevant_ids = sorted(qrels.keys(), key=lambda k: qrels[k], reverse=True)

    metrics = {
        "ndcg@10": ndcg_at_k(retrieved_ids, qrels, 10),
        "map@5": average_precision_at_k(retrieved_ids, qrels, 5),
        "mrr@10": reciprocal_rank(retrieved_ids[:10], qrels),
        "recall@5": recall_at_k(retrieved_ids, qrels, 5),
        "recall@10": recall_at_k(retrieved_ids, qrels, 10),
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
    use_planner: bool = False,
    suite: str = "cards",
    decompose: str = "off",
    merge: str = "rrf_sum",
    rerank: bool = True,
) -> BenchmarkReport:
    """Run benchmark; optionally persist to eval_runs table."""
    from datetime import datetime
    from decimal import Decimal

    bootstrap_default_providers()
    data = load_golden_set(golden_name)
    queries = data["queries"]

    factory = _get_session_factory()
    per_query: list[QueryEval] = []
    started_at = datetime.now(UTC)

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
                suite=suite,
                decompose=decompose,
                merge=merge,
                rerank=rerank,
            )
            per_query.append(qe)

    # Aggregate
    metric_keys = list(per_query[0].metrics.keys()) if per_query else []
    aggregate = {
        m: round(sum(qe.metrics[m] for qe in per_query) / max(len(per_query), 1), 4)
        for m in metric_keys
    }
    aggregate["latency_ms_p50"] = _percentile([qe.latency_ms for qe in per_query], 50)
    aggregate["latency_ms_p95"] = _percentile([qe.latency_ms for qe in per_query], 95)

    config = {
        "candidate_pool": candidate_pool,
        "min_semantic_score": 0.55,
        "min_text_score": 0.15,
        "rrf_k": 60,
        "suite": suite,  # #696 — chunks (prod path) veya cards
        "use_planner": use_planner,
        "decompose": decompose,  # #619 PR-4A — off | heuristic | llm
        "merge": merge,  # #619 PR-4D — rrf_sum | rrf_max | rank_rrf | union
        "rerank": rerank,  # #619 PR-4D — hybrid_search rerank on/off (determinizm)
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
        completed_at = datetime.now(UTC)

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

    fails = [qe for qe in report.per_query if qe.metrics.get("ndcg@10", 0.0) < 0.3]
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
        "--with-planner",
        action="store_true",
        help="Query Planner kullan (end-to-end user path benchmark)",
    )
    parser.add_argument(
        "--suite",
        choices=["cards", "chunks"],
        default="cards",
        help="cards (legacy, agenda card retrieval) | chunks (#696 — prod path, NER + IDF)",
    )
    parser.add_argument(
        "--decompose",
        choices=["off", "heuristic", "llm"],
        default="off",
        help="#619 PR-4A — query decomposition proxy (off=byte-identical; "
        "heuristic=deterministik; llm=chat-provider). Yalnız --suite chunks ile anlamlı.",
    )
    parser.add_argument(
        "--merge",
        choices=["rrf_sum", "rrf_max", "rank_rrf", "union"],
        default="rrf_sum",
        help="#619 PR-4D — decompose alt-sorgu merge stratejisi (default rrf_sum = "
        "byte-identical). rank_rrf = klasik RRF (ölçek-bağımsız). Yalnız --decompose != off ile etkili.",
    )
    parser.add_argument(
        "--rerank",
        choices=["on", "off"],
        default="on",
        help="#619 PR-4D — hybrid_search rerank (on=mevcut/byte-identical; "
        "off=deterministik retrieval, LLM-rerank devre dışı → merge karşılaştırması noise-suz).",
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
        use_planner=args.with_planner,
        suite=args.suite,
        decompose=args.decompose,
        merge=args.merge,
        rerank=(args.rerank == "on"),
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
