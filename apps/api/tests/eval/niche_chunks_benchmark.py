"""Niche chunks recall benchmark (#652 Faz 1 — RAGFlow-tier eval).

Founder feedback'ten 11 niş entity sorgusu. Her sorgu manuel doğrulanmış
expected_article_id ile eşleşiyor. Bu script hybrid_search_chunks'ı çağırıp
expected article'ın retrieve edilen top-K içinde olup olmadığını ölçer.

Metrikler:
  - recall@5: expected article ilk 5 chunk'ın article_id'sinde var mı?
  - recall@10: ilk 10 chunk'ta?
  - mrr@10: ilk hit'in tersi (1/rank)

Kullanım:
  docker compose exec -T api python -m tests.eval.niche_chunks_benchmark
  docker compose exec -T api python -m tests.eval.niche_chunks_benchmark \\
    --output /tmp/niche_recall.json

Çıktı: stdout summary (her sorgu + per-failure özet), opsiyonel JSON report.

Acceptance #652 Faz 1: Faz 1 sonrası ≥4/7 önceden başarısız vakanın recall@5'i
✅ olmalı.
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

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path(__file__).parent / "golden_sets" / "niche_chunks_golden.yaml"


@dataclass
class NicheResult:
    query_id: str
    text: str
    expected_article_id: str
    failure_reason: str | None
    retrieved_article_ids: list[str]
    expected_rank: int  # 1-indexed; -1 if not found
    latency_ms: float
    metrics: dict[str, float] = field(default_factory=dict)
    # #742 (Faz 7c Aşama 1) — diagnostic debug fields
    retrieved_chunk_excerpts: list[str] = field(default_factory=list)
    """Top-10 chunk'ların ilk 300 char'ı (fail analizi için)."""
    retrieved_answer_spans: list[list[str]] = field(default_factory=list)
    """Her chunk için extract_numerical_spans çıktısı (her chunk için ayrı liste)."""

    @property
    def is_baseline_pass(self) -> bool:
        """Baseline'da geçmiş sorgu mu? (failure_reason None ise evet)"""
        return self.failure_reason is None

    @property
    def passed_recall5(self) -> bool:
        return 0 < self.expected_rank <= 5

    @property
    def passed_recall10(self) -> bool:
        return 0 < self.expected_rank <= 10


async def _run_single_query(
    db, embed_provider, query_text: str, expected_article_id: str
) -> tuple[list[str], float, int, list[str], list[list[str]]]:
    """Tek sorgu çalıştır, (article_ids_top10, latency_ms, expected_rank,
    chunk_excerpts, answer_spans) döndür.

    #742 (Faz 7c Aşama 1): chunk_excerpts ve answer_spans diagnostic için eklendi.
    """
    from app.core.answer_span import extract_numerical_spans  # #742

    start = time.perf_counter()

    # Embed
    emb_result = await embed_provider.create_embedding([query_text])
    qvec = emb_result.vectors[0] if emb_result.vectors else None

    # Hybrid search chunks (90 gün, top_k 15)
    results = await hybrid_search_chunks(
        db,
        query_text=query_text,
        query_vector=qvec,
        top_k=15,
        candidate_pool=60,
        since_hours=24 * 90,
        rerank=True,
    )

    latency_ms = (time.perf_counter() - start) * 1000

    # Article-id sıralı liste (chunk içinde duplicate olabilir, unique sıralı)
    seen: set[str] = set()
    article_ids: list[str] = []
    chunk_excerpts: list[str] = []
    answer_spans: list[list[str]] = []
    for r in results[:10]:
        aid = str(r.get("article_id"))
        text = str(r.get("chunk_text") or r.get("article_title") or "")
        chunk_excerpts.append(text[:300])
        answer_spans.append(extract_numerical_spans(text))
        if aid not in seen:
            seen.add(aid)
            article_ids.append(aid)

    # Expected rank (1-indexed, -1 if not found)
    rank = -1
    for i, aid in enumerate(article_ids, start=1):
        if aid == expected_article_id:
            rank = i
            break

    return article_ids[:10], latency_ms, rank, chunk_excerpts, answer_spans


async def _run_benchmark(*, golden_path: Path) -> list[NicheResult]:
    """Tüm golden sorguları çalıştır."""
    bootstrap_default_providers()
    embed_provider = registry.route_for_tier(operation="embedding", tier="free")

    with golden_path.open("r", encoding="utf-8") as f:
        golden = yaml.safe_load(f)

    factory = _get_session_factory()
    results: list[NicheResult] = []

    async with factory() as db:
        for q in golden["queries"]:
            qid = q["id"]
            text = q["text"]
            expected_aid = q["expected_article_id"]
            failure_reason = q.get("failure_reason")

            try:
                (
                    article_ids,
                    latency_ms,
                    rank,
                    chunk_excerpts,
                    answer_spans,
                ) = await _run_single_query(
                    db, embed_provider, text, expected_aid
                )
            except Exception as exc:
                logger.error("query %s failed: %s", qid, exc)
                results.append(
                    NicheResult(
                        query_id=qid,
                        text=text,
                        expected_article_id=expected_aid,
                        failure_reason=failure_reason,
                        retrieved_article_ids=[],
                        expected_rank=-1,
                        latency_ms=0.0,
                    )
                )
                continue

            metrics = {
                "recall@5": 1.0 if 0 < rank <= 5 else 0.0,
                "recall@10": 1.0 if 0 < rank <= 10 else 0.0,
                "mrr@10": (1.0 / rank) if 0 < rank <= 10 else 0.0,
            }

            results.append(
                NicheResult(
                    query_id=qid,
                    text=text,
                    expected_article_id=expected_aid,
                    failure_reason=failure_reason,
                    retrieved_article_ids=article_ids,
                    expected_rank=rank,
                    latency_ms=latency_ms,
                    metrics=metrics,
                    retrieved_chunk_excerpts=chunk_excerpts,  # #742
                    retrieved_answer_spans=answer_spans,  # #742
                )
            )

    return results


def _format_result(r: NicheResult) -> str:
    icon = "✅" if r.passed_recall5 else "❌"
    rank_str = f"#{r.expected_rank}" if r.expected_rank > 0 else "❌ NOT IN TOP-10"
    baseline = " (baseline pass)" if r.is_baseline_pass else f" [{r.failure_reason}]"
    return (
        f"{icon} {r.query_id}: '{r.text[:60]}'\n"
        f"   expected={r.expected_article_id[:8]}.. rank={rank_str} "
        f"latency={r.latency_ms:.0f}ms{baseline}"
    )


def _summary_metrics(results: list[NicheResult]) -> dict[str, float]:
    total = len(results)
    if total == 0:
        return {}
    return {
        "total_queries": total,
        "recall@5": sum(r.metrics.get("recall@5", 0) for r in results) / total,
        "recall@10": sum(r.metrics.get("recall@10", 0) for r in results) / total,
        "mrr@10": sum(r.metrics.get("mrr@10", 0) for r in results) / total,
        "avg_latency_ms": sum(r.latency_ms for r in results) / total,
        "passed_recall5": sum(1 for r in results if r.passed_recall5),
        "passed_recall10": sum(1 for r in results if r.passed_recall10),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Niche chunks recall benchmark")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON output path (opsiyonel)",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=GOLDEN_PATH,
        help="Golden set yaml path",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    print("=== Niche Chunks Recall Benchmark (#652 Faz 1) ===")
    print(f"Golden: {args.golden}")
    print()

    results = asyncio.run(_run_benchmark(golden_path=args.golden))

    print("--- Per-query results ---")
    for r in results:
        print(_format_result(r))
    print()

    summary = _summary_metrics(results)
    print("--- Summary ---")
    for k, v in summary.items():
        if isinstance(v, float):
            print(f"  {k:20} {v:.3f}")
        else:
            print(f"  {k:20} {v}")
    print()

    # Pre/post baseline analysis
    pre_failures = [r for r in results if not r.is_baseline_pass]
    pre_pass = [r for r in results if r.is_baseline_pass]
    print(f"--- Pre-Faz-1 Failures ({len(pre_failures)}) ---")
    fixed = [r for r in pre_failures if r.passed_recall5]
    print(f"  Fixed (recall@5): {len(fixed)} / {len(pre_failures)}")
    for r in fixed:
        print(f"    ✅ {r.query_id}: {r.text[:60]}")
    still_broken = [r for r in pre_failures if not r.passed_recall5]
    if still_broken:
        print(f"  Still broken: {len(still_broken)}")
        for r in still_broken:
            print(f"    ❌ {r.query_id}: {r.text[:60]} [{r.failure_reason}]")

    if args.output:
        out_data = {
            "summary": summary,
            "queries": [
                {
                    "query_id": r.query_id,
                    "text": r.text,
                    "expected_article_id": r.expected_article_id,
                    "failure_reason": r.failure_reason,
                    "expected_rank": r.expected_rank,
                    "retrieved_article_ids": r.retrieved_article_ids,
                    "metrics": r.metrics,
                    "latency_ms": r.latency_ms,
                    # #742 (Faz 7c Aşama 1) — diagnostic fields
                    "retrieved_chunk_excerpts": r.retrieved_chunk_excerpts,
                    "retrieved_answer_spans": r.retrieved_answer_spans,
                }
                for r in results
            ],
        }
        args.output.write_text(json.dumps(out_data, indent=2, ensure_ascii=False))
        print(f"\nReport written to: {args.output}")


if __name__ == "__main__":
    main()
