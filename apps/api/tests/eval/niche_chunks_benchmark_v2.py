"""Niche chunks recall benchmark V2 — PRODUCTION PARITY.

Eski niche_chunks_benchmark.py raw query ile hybrid_search_chunks'ı doğrudan
çağırır. Bu **production parity DEĞİL** — gerçek /app/generate-stream akışında:
  1. Planner çalışır (critical_entities çıkar)
  2. HyDE conditional (hypothetical doc)
  3. Multi-query batch embedding (raw + topic_query + hyde)
  4. Her embed için hybrid_search_chunks → RRF birleştirme
  5. Critical_entities filter + rescue
  6. Parent-doc retrieval

V2 benchmark bu **tam path**'i taklit eder. Recall ölçüm gerçeği daha iyi
yansıtır. Kullanım eski ile aynı:

    docker compose exec api python -m tests.eval.niche_chunks_benchmark_v2
    docker compose exec api python -m tests.eval.niche_chunks_benchmark_v2 \\
        --output /tmp/v2_results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.core.retrieval import hybrid_search_chunks
from app.providers.registry import bootstrap_default_providers, registry
from app.workers.tasks.sources import _get_session_factory
from app.prompts.query_planner import plan_query
from app.prompts.hyde import SYSTEM_PROMPT as HYDE_DEFAULT, render_hyde_prompt
from app.core.prompts_store import prompts_store
from app.providers.base import Message


logger = logging.getLogger(__name__)

GOLDEN_PATH = Path(__file__).parent / "golden_sets" / "niche_chunks_golden.yaml"


@dataclass
class V2Result:
    query_id: str
    text: str
    expected_article_id: str
    topic_query: str
    critical_entities: list[str]
    hyde_doc_len: int
    retrieved_article_ids: list[str] = field(default_factory=list)
    expected_rank: int = -1
    latency_ms: float = 0.0


async def _run_query(
    db_factory,
    embed_provider,
    chat_provider,
    *,
    query: str,
    expected_aid: str,
) -> V2Result:
    t0 = time.perf_counter()

    # 1) Planner
    plan_result = await plan_query(user_request=query, use_cache=False)
    topic = getattr(plan_result, "topic_query", query)
    critical_entities = getattr(plan_result, "critical_entities", None) or []

    # 2) HyDE
    hyde_doc = None
    try:
        async with db_factory() as db:
            hyde_template = await prompts_store.get(db, "hyde_doc", HYDE_DEFAULT)
        hyde_prompt = render_hyde_prompt(topic, template=hyde_template)
        hyde_resp = await chat_provider.generate_text(
            messages=[Message(role="user", content=hyde_prompt)],
            max_tokens=120,
            temperature=0.7,
            json_mode=False,
        )
        hyde_doc = (hyde_resp.text or "").strip()
    except Exception:
        hyde_doc = None

    # 3) Multi-query batch embedding
    variants = [query, topic]
    if hyde_doc:
        variants.append(hyde_doc[:500])
    emb_res = await embed_provider.create_embedding(variants)
    vectors = emb_res.vectors

    # 4) Multi-query retrieve + RRF combine
    combined_rrf: dict[str, float] = {}
    async with db_factory() as db:
        for i, vec in enumerate(vectors):
            chunks = await hybrid_search_chunks(
                db,
                query_text=variants[i],
                query_vector=vec,
                top_k=15,
                candidate_pool=60,
                since_hours=24 * 90,
                critical_entities=critical_entities or None,
                rerank=False,
            )
            for rank, c in enumerate(chunks[:15], start=1):
                aid = str(c.get("article_id"))
                # RRF: lower K = stronger stream weight; same K for all variants
                combined_rrf[aid] = combined_rrf.get(aid, 0.0) + 1.0 / (60 + rank)

    # 5) Sort
    sorted_aids = [
        aid for aid, _ in sorted(combined_rrf.items(), key=lambda x: x[1], reverse=True)
    ]
    rank = sorted_aids.index(expected_aid) + 1 if expected_aid in sorted_aids else -1
    latency = (time.perf_counter() - t0) * 1000

    return V2Result(
        query_id="",
        text=query,
        expected_article_id=expected_aid,
        topic_query=topic,
        critical_entities=critical_entities,
        hyde_doc_len=len(hyde_doc) if hyde_doc else 0,
        retrieved_article_ids=sorted_aids[:15],
        expected_rank=rank,
        latency_ms=latency,
    )


async def run_all(golden_path: Path) -> list[V2Result]:
    bootstrap_default_providers()
    factory = _get_session_factory()
    emb_provider = registry.route_for_tier(operation="embedding", tier="free")
    chat_provider = registry.route_for_tier(operation="chat", tier="free")

    with golden_path.open("r", encoding="utf-8") as f:
        golden = yaml.safe_load(f)

    results: list[V2Result] = []
    for q in golden["queries"]:
        qid = q["id"]
        text = q["text"]
        expected_aid = q["expected_article_id"]
        try:
            r = await _run_query(
                factory, emb_provider, chat_provider,
                query=text, expected_aid=expected_aid,
            )
            r.query_id = qid
            results.append(r)
            marker = "✅" if 0 < r.expected_rank <= 5 else ("🟡" if 0 < r.expected_rank <= 10 else "❌")
            print(
                f"{marker} {qid}: rank={'#'+str(r.expected_rank) if r.expected_rank>0 else 'NF'} "
                f"latency={r.latency_ms:.0f}ms ce={r.critical_entities} hyde={r.hyde_doc_len}",
                flush=True,
            )
        except Exception as exc:
            logger.error("query %s failed: %s", qid, exc)
            results.append(V2Result(
                query_id=qid, text=text, expected_article_id=expected_aid,
                topic_query="", critical_entities=[], hyde_doc_len=0,
            ))

    return results


def _summary(results: list[V2Result]) -> dict[str, float]:
    total = len(results)
    if total == 0:
        return {}
    recall_5 = sum(1 for r in results if 0 < r.expected_rank <= 5) / total
    recall_10 = sum(1 for r in results if 0 < r.expected_rank <= 10) / total
    mrr_10 = sum(
        (1.0 / r.expected_rank) for r in results if 0 < r.expected_rank <= 10
    ) / total
    avg_lat = sum(r.latency_ms for r in results) / total
    return {
        "total_queries": total,
        "recall@5": recall_5,
        "recall@10": recall_10,
        "mrr@10": mrr_10,
        "avg_latency_ms": avg_lat,
        "passed_recall5": sum(1 for r in results if 0 < r.expected_rank <= 5),
        "passed_recall10": sum(1 for r in results if 0 < r.expected_rank <= 10),
    }


async def main(output: str | None = None) -> None:
    print(f"=== Niche Chunks Recall V2 — PRODUCTION PARITY ===")
    print(f"Golden: {GOLDEN_PATH}")
    print(f"Path: planner → HyDE → multi-query embed → hybrid_search_chunks (RRF combine)\n")

    results = await run_all(GOLDEN_PATH)

    print("\n--- Summary ---")
    summary = _summary(results)
    for k, v in summary.items():
        if isinstance(v, float):
            print(f"  {k:20s} {v:.3f}")
        else:
            print(f"  {k:20s} {v}")

    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump({
                "summary": summary,
                "queries": [
                    {
                        "query_id": r.query_id,
                        "text": r.text,
                        "expected_article_id": r.expected_article_id,
                        "topic_query": r.topic_query,
                        "critical_entities": r.critical_entities,
                        "hyde_doc_len": r.hyde_doc_len,
                        "expected_rank": r.expected_rank,
                        "latency_ms": r.latency_ms,
                    }
                    for r in results
                ],
            }, f, ensure_ascii=False, indent=2)
        print(f"\nReport written to: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()
    asyncio.run(main(output=args.output))
