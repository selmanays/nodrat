"""Score history snapshot helper (#765).

Niche chunks benchmark sonucundan otomatik snapshot JSON üretir. Kullanım:

    python -m tests.eval.niche_chunks_benchmark --output /tmp/run.json
    python -m tests.eval.score_history.snapshot \\
        --benchmark /tmp/run.json \\
        --label "step_1_microchunk-on" \\
        --baseline tests/eval/score_history/baseline_2026-05-13_pre-optimization.json \\
        --out tests/eval/score_history/step_1_2026-05-XX_microchunk-on.json

Bu script:
1. Benchmark JSON'undan per-query rank + summary metric'leri çıkartır
2. Baseline JSON ile delta hesaplar
3. Git HEAD SHA'yı kaydeder
4. Production state snapshot çağırması yapılır (manuel doldurulan alanlar)
5. Snapshot JSON'u yazar
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _git_head_sha() -> str:
    """Local git HEAD SHA (main branch tercih edilir)."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return "unknown"


def _ndcg10_binary(per_query_rank: dict[str, int]) -> float:
    """Binary NDCG@10 — expected article rank=N için 1/log2(N+1)."""
    scores: list[float] = []
    for rank in per_query_rank.values():
        if 0 < rank <= 10:
            actual = 1.0 / math.log2(rank + 1)
            ideal = 1.0 / math.log2(2)
            scores.append(actual / ideal)
        else:
            scores.append(0.0)
    return sum(scores) / len(scores) if scores else 0.0


def _extract_from_benchmark(bench_json: dict[str, Any]) -> dict[str, Any]:
    """niche_chunks_benchmark output JSON'undan summary + per-query rank çıkar."""
    summary = bench_json.get("summary", {})
    queries = bench_json.get("queries", [])
    per_query = {q["query_id"]: q["expected_rank"] for q in queries}
    return {
        "metrics": {
            "recall_at_5": float(summary.get("recall@5", 0.0)),
            "recall_at_10": float(summary.get("recall@10", 0.0)),
            "mrr_at_10": float(summary.get("mrr@10", 0.0)),
            "ndcg_at_10_approx": _ndcg10_binary(per_query),
            "avg_latency_ms": float(summary.get("avg_latency_ms", 0.0)),
            "passed_recall5": int(summary.get("passed_recall5", 0)),
            "passed_recall10": int(summary.get("passed_recall10", 0)),
        },
        "per_query_rank": per_query,
    }


def _delta(curr: dict[str, float], base: dict[str, float]) -> dict[str, float]:
    """Curr - base, sadece sayısal alan farkları."""
    out: dict[str, float] = {}
    for k, v in curr.items():
        if k in base and isinstance(v, (int, float)) and isinstance(base[k], (int, float)):
            out[k] = round(float(v) - float(base[k]), 4)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark → score history snapshot")
    parser.add_argument("--benchmark", type=Path, required=True, help="niche_chunks_benchmark JSON")
    parser.add_argument("--label", type=str, required=True, help="Deney etiketi")
    parser.add_argument("--baseline", type=Path, default=None, help="Karşılaştırılacak baseline JSON")
    parser.add_argument("--out", type=Path, required=True, help="Yazılacak snapshot JSON path")
    parser.add_argument(
        "--settings",
        type=str,
        default="{}",
        help="JSON string — active production settings snapshot",
    )
    args = parser.parse_args()

    with args.benchmark.open() as f:
        bench = json.load(f)

    extracted = _extract_from_benchmark(bench)

    snapshot: dict[str, Any] = {
        "snapshot_id": args.label,
        "label": args.label,
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "git_sha_main": _git_head_sha(),
        "production_state": {
            "active_settings": json.loads(args.settings) if args.settings else {},
        },
        "benchmark": {
            "script": "tests.eval.niche_chunks_benchmark",
            "golden_set": "tests/eval/golden_sets/niche_chunks_golden.yaml",
            "n_queries": len(extracted["per_query_rank"]),
        },
        **extracted,
    }

    if args.baseline:
        with args.baseline.open() as f:
            base = json.load(f)
        snapshot["delta_vs_baseline"] = {
            "baseline_id": base.get("snapshot_id"),
            "metrics_delta": _delta(extracted["metrics"], base.get("metrics", {})),
            "per_query_rank_delta": {
                qid: extracted["per_query_rank"].get(qid, -1) - base["per_query_rank"].get(qid, -1)
                for qid in extracted["per_query_rank"]
            },
        }

    args.out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    print(f"Snapshot written: {args.out}")
    if args.baseline:
        d = snapshot["delta_vs_baseline"]["metrics_delta"]
        print(f"Δ vs baseline: recall@5={d.get('recall_at_5'):+.4f}  mrr@10={d.get('mrr_at_10'):+.4f}  latency={d.get('avg_latency_ms'):+.0f}ms")


if __name__ == "__main__":
    main()
