"""Cross-encoder rerank eval A/B runner (#750 — B opsiyonu).

3 konfigürasyonu sıralı test eder ve sonuçları karşılaştırır:
  1. off:   rerank.enabled=false (baseline — production state)
  2. local: rerank.enabled=true  + local_bge_reranker PRIMARY (mevcut default)
  3. nim:   rerank.enabled=true  + local_bge_reranker bypass → NIM rerank fallback

Karar matrisi:
  - Eşik: NDCG@10 ≥ 0.90 VEYA recall@5 +5pp (>9/11)
  - Latency budget: rerank ek 200-500ms (TTFT etkisi)
  - Negatif → cross-encoder-rerank-disabled.md "permanent disabled" durumuna

Çalıştırma:
  docker compose exec -w /app api python scripts/eval_rerank_ab.py \\
    --output /tmp/rerank_ab.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Make project root importable
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.retrieval import hybrid_search_chunks
from app.core.settings_store import settings_store
from app.providers.registry import (
    bootstrap_default_providers,
    registry,
)
from app.workers.tasks.embedding import _get_session_factory

logger = logging.getLogger(__name__)

GOLDEN_PATH = ROOT / "tests" / "eval" / "golden_sets" / "niche_chunks_golden.yaml"


@dataclass
class QueryResult:
    query_id: str
    text: str
    expected_aid: str
    expected_rank: int  # -1 if not found
    latency_ms: float
    top_ids: list[str] = field(default_factory=list)

    @property
    def passed_recall5(self) -> bool:
        return 0 < self.expected_rank <= 5

    @property
    def passed_recall10(self) -> bool:
        return 0 < self.expected_rank <= 10

    @property
    def reciprocal_rank(self) -> float:
        return (1.0 / self.expected_rank) if 0 < self.expected_rank <= 10 else 0.0


@dataclass
class ConfigResult:
    mode: str  # "off" | "local" | "nim"
    queries: list[QueryResult]

    @property
    def recall5(self) -> float:
        if not self.queries:
            return 0.0
        return sum(1 for q in self.queries if q.passed_recall5) / len(self.queries)

    @property
    def recall10(self) -> float:
        if not self.queries:
            return 0.0
        return sum(1 for q in self.queries if q.passed_recall10) / len(self.queries)

    @property
    def mrr(self) -> float:
        if not self.queries:
            return 0.0
        return sum(q.reciprocal_rank for q in self.queries) / len(self.queries)

    @property
    def ndcg10(self) -> float:
        """NDCG@10 — binary relevance (1 if expected article in top-10).

        Ideal DCG: 1 / log2(2) = 1.0 (best position rank=1).
        Actual DCG: 1 / log2(rank+1) if rank<=10 else 0.
        NDCG = avg(actual_dcg / ideal_dcg) per query.
        """
        if not self.queries:
            return 0.0
        scores = []
        for q in self.queries:
            if 0 < q.expected_rank <= 10:
                # Binary relevance — only expected article counts
                actual = 1.0 / math.log2(q.expected_rank + 1)
                ideal = 1.0 / math.log2(2)  # rank=1
                scores.append(actual / ideal)
            else:
                scores.append(0.0)
        return sum(scores) / len(scores)

    @property
    def avg_latency_ms(self) -> float:
        if not self.queries:
            return 0.0
        return sum(q.latency_ms for q in self.queries) / len(self.queries)


async def _set_mode_off(db) -> None:
    """rerank.enabled=false."""
    await settings_store.set(db, key="rerank.enabled", value=False, type_="bool", group_name="rag")
    await db.commit()
    # Force L1 invalidation (own process)
    settings_store._l1_invalidate("rerank.enabled")


async def _set_mode_local(db) -> None:
    """rerank.enabled=true + local_bge_reranker primary (default)."""
    await settings_store.set(db, key="rerank.enabled", value=True, type_="bool", group_name="rag")
    await db.commit()
    settings_store._l1_invalidate("rerank.enabled")
    # Ensure local_bge_reranker registered (default state)
    bootstrap_default_providers()


async def _set_mode_nim(db) -> None:
    """rerank.enabled=true + local_bge_reranker bypass (registry pop)."""
    await settings_store.set(db, key="rerank.enabled", value=True, type_="bool", group_name="rag")
    await db.commit()
    settings_store._l1_invalidate("rerank.enabled")
    bootstrap_default_providers()
    # Pop local_bge_reranker so route_for_tier falls through to nim_rerank
    registry._providers.pop("local_bge_reranker", None)


async def _restore_default_registry(db) -> None:
    """Rebuild registry (NIM mode'dan sonra local'i geri getir)."""
    registry._providers.clear()
    bootstrap_default_providers()


async def _run_single_query(db, embed_provider, query_text: str, expected_aid: str) -> QueryResult:
    """Tek sorgu için hybrid_search_chunks koş, expected_rank ölç."""
    start = time.perf_counter()

    emb = await embed_provider.create_embedding([query_text])
    qvec = emb.vectors[0] if emb.vectors else None

    rows = await hybrid_search_chunks(
        db,
        query_text=query_text,
        query_vector=qvec,
        top_k=15,
        candidate_pool=60,
        since_hours=24 * 90,
        rerank=True,  # rerank.enabled setting kontrol eder
    )

    latency_ms = (time.perf_counter() - start) * 1000

    seen: set[str] = set()
    article_ids: list[str] = []
    for r in rows:
        aid = str(r.get("article_id"))
        if aid not in seen:
            seen.add(aid)
            article_ids.append(aid)

    rank = -1
    for i, aid in enumerate(article_ids, start=1):
        if aid == expected_aid:
            rank = i
            break

    return QueryResult(
        query_id="",  # caller doldurur
        text=query_text,
        expected_aid=expected_aid,
        expected_rank=rank,
        latency_ms=latency_ms,
        top_ids=article_ids[:10],
    )


async def _run_config(mode: str, golden: dict) -> ConfigResult:
    """Tek konfigürasyon için tüm golden sorguları koş."""
    factory = _get_session_factory()
    async with factory() as db:
        if mode == "off":
            await _set_mode_off(db)
        elif mode == "local":
            await _set_mode_local(db)
        elif mode == "nim":
            await _set_mode_nim(db)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        embed_provider = registry.route_for_tier(operation="embedding", tier="free")

        results: list[QueryResult] = []
        for q in golden["queries"]:
            qid = q["id"]
            try:
                r = await _run_single_query(db, embed_provider, q["text"], q["expected_article_id"])
                r.query_id = qid
                results.append(r)
                print(f"  {mode} {qid}: rank={r.expected_rank} ({r.latency_ms:.0f}ms)")
            except Exception as exc:
                logger.error("query %s failed: %s", qid, exc)
                results.append(
                    QueryResult(
                        query_id=qid,
                        text=q["text"],
                        expected_aid=q["expected_article_id"],
                        expected_rank=-1,
                        latency_ms=0.0,
                    )
                )
        return ConfigResult(mode=mode, queries=results)


async def _run_all() -> dict[str, ConfigResult]:
    """3 konfigürasyonu sıralı koş."""
    bootstrap_default_providers()

    with GOLDEN_PATH.open("r", encoding="utf-8") as f:
        golden = yaml.safe_load(f)

    results: dict[str, ConfigResult] = {}

    for mode in ("off", "local", "nim"):
        print(f"\n=== Mode: {mode} ===")
        results[mode] = await _run_config(mode, golden)

    # Restore default registry + setting (off, mevcut prod state)
    factory = _get_session_factory()
    async with factory() as db:
        await _set_mode_off(db)
        await _restore_default_registry(db)
    print("\n=== Restored to off (production baseline state) ===")

    return results


def _format_summary(results: dict[str, ConfigResult]) -> str:
    lines = ["", "=" * 70, "REZULTAT KARŞILAŞTIRMA", "=" * 70]
    lines.append(
        f"{'Mode':<8} {'recall@5':>10} {'recall@10':>10} {'mrr':>8} {'ndcg@10':>10} {'p95_lat':>10}"
    )
    lines.append("-" * 70)
    for mode in ("off", "local", "nim"):
        cr = results.get(mode)
        if cr is None:
            continue
        # p95 latency
        lats = sorted(q.latency_ms for q in cr.queries)
        p95 = lats[int(len(lats) * 0.95)] if lats else 0.0
        lines.append(
            f"{mode:<8} {cr.recall5:>9.3f}  {cr.recall10:>9.3f}  "
            f"{cr.mrr:>7.3f}  {cr.ndcg10:>9.3f}  {p95:>9.0f}ms"
        )
    lines.append("=" * 70)

    # Decision matrix
    off = results.get("off")
    local = results.get("local")
    nim = results.get("nim")
    if off and local and nim:
        lines.append("")
        lines.append("KARAR MATRİSİ:")
        for mode, cr in [("local", local), ("nim", nim)]:
            delta_r5 = cr.recall5 - off.recall5
            delta_ndcg = cr.ndcg10 - off.ndcg10
            lines.append(
                f"  {mode}: Δrecall@5={delta_r5:+.3f}, ΔNDCG@10={delta_ndcg:+.3f}, "
                f"NDCG@10={cr.ndcg10:.3f} {'✅' if cr.ndcg10 >= 0.90 else '❌'} (eşik 0.90)"
            )
        lines.append("")
        lines.append("Karar kuralı: NDCG@10 ≥ 0.90 VEYA recall@5 +5pp (>9/11=0.045)")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-encoder rerank A/B eval")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    results = asyncio.run(_run_all())

    summary = _format_summary(results)
    print(summary)

    if args.output:
        out_data = {
            "configs": {
                mode: {
                    "recall@5": cr.recall5,
                    "recall@10": cr.recall10,
                    "mrr": cr.mrr,
                    "ndcg@10": cr.ndcg10,
                    "avg_latency_ms": cr.avg_latency_ms,
                    "queries": [
                        {
                            "query_id": q.query_id,
                            "expected_rank": q.expected_rank,
                            "latency_ms": q.latency_ms,
                            "top_ids": q.top_ids,
                        }
                        for q in cr.queries
                    ],
                }
                for mode, cr in results.items()
            }
        }
        args.output.write_text(json.dumps(out_data, indent=2, ensure_ascii=False))
        print(f"\nReport written to: {args.output}")


if __name__ == "__main__":
    main()
