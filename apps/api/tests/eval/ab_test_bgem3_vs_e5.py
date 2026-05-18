"""A/B test: bge-m3 vs intfloat/multilingual-e5-large (#681 Faz 7b).

Mevcut bge-m3 ile 11 ground-truth sorgu benchmark zaten var.
Bu script E5 modeli runtime'da yükler, aynı 9 test article için:
  1. Article chunks'larını e5 ile yeniden embed
  2. 11 sorguyu e5 query mode'la embed
  3. Manual cosine sim ile retrieval simulate
  4. Recall@5 / recall@10 / MRR ölç
  5. Mevcut bge-m3 sonucu ile head-to-head kıyas

Cost: e5 model 2.2GB download (HF, ~1-2 dk first-time), CPU inference
~50ms/chunk. Total ~5-10 dk test run.

Sonuç: e5 kazanırsa migration ZORUNLU (production'da chunks bge-m3 ile
embed edildi → mixed embeddings retrieval'da uyumsuz). Migration: 109K
chunks × yeniden embed ~3 saat background.

Kullanım:
    docker compose exec api python -m tests.eval.ab_test_bgem3_vs_e5
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path(__file__).parent / "golden_sets" / "niche_chunks_golden.yaml"


def _cosine_sim(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


async def _fetch_test_article_chunks(article_ids: list[str]) -> dict[str, list[dict]]:
    """Test article'ların tüm chunks'larını DB'den çek."""
    from app.workers.tasks.sources import _get_session_factory
    from sqlalchemy import text as sa_text

    factory = _get_session_factory()
    chunks_by_aid: dict[str, list[dict]] = {}

    async with factory() as db:
        aid_in = ", ".join(f"'{aid}'::uuid" for aid in article_ids)
        rows = (
            await db.execute(
                sa_text(
                    f"""
                    SELECT c.id::text AS chunk_id,
                           c.article_id::text AS article_id,
                           c.chunk_index,
                           c.chunk_text,
                           c.embedding::text AS embedding_text,
                           a.title AS title
                    FROM article_chunks c
                    JOIN articles a ON a.id = c.article_id
                    WHERE c.article_id IN ({aid_in})
                    ORDER BY c.article_id, c.chunk_index
                    """
                )
            )
        ).mappings().all()

    for r in rows:
        aid = r["article_id"]
        chunks_by_aid.setdefault(aid, []).append(dict(r))
    return chunks_by_aid


def _parse_pgvector(text: str | None) -> list[float] | None:
    if not text:
        return None
    s = text.strip("[] \n")
    try:
        return [float(x) for x in s.split(",") if x.strip()]
    except (ValueError, AttributeError):
        return None


async def benchmark_bge_m3(
    queries: list[dict], chunks_by_aid: dict[str, list[dict]]
) -> dict[str, Any]:
    """Bge-m3 baseline — DB'deki mevcut embeddings + provider'dan query embed."""
    from app.providers.registry import bootstrap_default_providers, registry

    bootstrap_default_providers()
    provider = registry.route_for_tier(operation="embedding", tier="free")
    logger.info("bge-m3 provider: %s", type(provider).__name__)

    results = []
    for q in queries:
        emb_result = await provider.create_embedding([q["text"]])
        qvec = emb_result.vectors[0] if emb_result.vectors else None
        if qvec is None:
            continue

        # All test article chunks ile cosine sim
        all_scored: list[tuple[str, str, float]] = []  # (chunk_id, article_id, sim)
        for aid, chunks in chunks_by_aid.items():
            for ch in chunks:
                emb = _parse_pgvector(ch.get("embedding_text"))
                if emb is None or len(emb) != 1024:
                    continue
                sim = _cosine_sim(qvec, emb)
                all_scored.append((ch["chunk_id"], aid, sim))

        all_scored.sort(key=lambda x: x[2], reverse=True)
        # Unique article_id sıralı
        seen_aids: set[str] = set()
        ranked_aids: list[str] = []
        for _, aid, _ in all_scored:
            if aid not in seen_aids:
                seen_aids.add(aid)
                ranked_aids.append(aid)

        target = q["expected_article_id"]
        rank = ranked_aids.index(target) + 1 if target in ranked_aids else -1
        results.append({"qid": q["id"], "text": q["text"], "target": target, "rank": rank})

    return {"results": results, "model": "bge-m3"}


async def benchmark_e5(
    queries: list[dict], chunks_by_aid: dict[str, list[dict]]
) -> dict[str, Any]:
    """E5 model: chunks + queries yeniden embed, recall ölç."""
    from app.providers.local_e5 import LocalE5Provider

    e5 = LocalE5Provider()
    logger.info("e5 provider initializing — model load ~2GB")

    # Tüm test chunks'ı e5 passage mode'la embed
    print("  e5 chunks embedding (~5sn)...")
    chunk_texts: list[str] = []
    chunk_meta: list[tuple[str, str]] = []  # (chunk_id, aid)
    for aid, chunks in chunks_by_aid.items():
        for ch in chunks:
            chunk_texts.append(ch["chunk_text"][:2000])  # truncate cost guard
            chunk_meta.append((ch["chunk_id"], aid))

    chunk_emb_result = await e5.create_embedding(chunk_texts, mode="passage")
    chunk_vecs: list[list[float]] = chunk_emb_result.vectors

    print(f"  e5 chunk embeddings: {len(chunk_vecs)} vectors")

    results = []
    for q in queries:
        # Query mode embed
        q_result = await e5.create_embedding([q["text"]], mode="query")
        qvec = q_result.vectors[0] if q_result.vectors else None
        if qvec is None:
            continue

        # Cosine sim with all chunks
        all_scored: list[tuple[str, str, float]] = []
        for i, (cid, aid) in enumerate(chunk_meta):
            sim = _cosine_sim(qvec, chunk_vecs[i])
            all_scored.append((cid, aid, sim))

        all_scored.sort(key=lambda x: x[2], reverse=True)
        seen_aids: set[str] = set()
        ranked_aids: list[str] = []
        for _, aid, _ in all_scored:
            if aid not in seen_aids:
                seen_aids.add(aid)
                ranked_aids.append(aid)

        target = q["expected_article_id"]
        rank = ranked_aids.index(target) + 1 if target in ranked_aids else -1
        results.append({"qid": q["id"], "text": q["text"], "target": target, "rank": rank})

    return {"results": results, "model": "e5-multilingual-large"}


def _summary(name: str, results: list[dict]) -> dict[str, float]:
    total = len(results)
    found = sum(1 for r in results if r["rank"] > 0)
    recall_5 = sum(1 for r in results if 0 < r["rank"] <= 5) / total
    recall_10 = sum(1 for r in results if 0 < r["rank"] <= 10) / total
    mrr = sum(1.0 / r["rank"] for r in results if r["rank"] > 0) / total
    print(f"\n=== {name} ===")
    print(f"  found / total: {found} / {total}")
    print(f"  recall@5:  {recall_5:.3f}")
    print(f"  recall@10: {recall_10:.3f}")
    print(f"  MRR:       {mrr:.3f}")
    for r in results:
        rank_str = f"#{r['rank']}" if r["rank"] > 0 else "❌ NOT FOUND"
        icon = "✅" if 0 < r["rank"] <= 5 else "❌"
        print(f"  {icon} {r['qid']}: {rank_str}  '{r['text'][:50]}'")
    return {"recall@5": recall_5, "recall@10": recall_10, "MRR": mrr}


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print("=== A/B Test: bge-m3 vs e5-multilingual-large (#681 Faz 7b) ===\n")

    # Load golden set
    with GOLDEN_PATH.open() as f:
        golden = yaml.safe_load(f)
    queries = golden["queries"]

    article_ids = list({q["expected_article_id"] for q in queries})
    print(f"Test article'lar: {len(article_ids)}, sorgular: {len(queries)}")

    # Fetch chunks once
    print("\nDB'den chunks fetch...")
    chunks_by_aid = await _fetch_test_article_chunks(article_ids)
    total_chunks = sum(len(v) for v in chunks_by_aid.values())
    print(f"  Total chunks: {total_chunks}")

    # bge-m3 baseline
    print("\n--- bge-m3 baseline ---")
    bge_start = time.perf_counter()
    bge_out = await benchmark_bge_m3(queries, chunks_by_aid)
    print(f"  Total time: {time.perf_counter() - bge_start:.1f}s")

    # e5 test
    print("\n--- e5 test ---")
    e5_start = time.perf_counter()
    e5_out = await benchmark_e5(queries, chunks_by_aid)
    print(f"  Total time: {time.perf_counter() - e5_start:.1f}s")

    # Summary
    bge_metrics = _summary("BGE-M3", bge_out["results"])
    e5_metrics = _summary("E5-MULTILINGUAL", e5_out["results"])

    print("\n=== KARŞILAŞTIRMA ===")
    print(f"  recall@5:  bge-m3 {bge_metrics['recall@5']:.3f} → e5 {e5_metrics['recall@5']:.3f}  "
          f"({'+' if e5_metrics['recall@5'] > bge_metrics['recall@5'] else ''}"
          f"{(e5_metrics['recall@5']-bge_metrics['recall@5'])*100:.1f}pp)")
    print(f"  recall@10: bge-m3 {bge_metrics['recall@10']:.3f} → e5 {e5_metrics['recall@10']:.3f}  "
          f"({'+' if e5_metrics['recall@10'] > bge_metrics['recall@10'] else ''}"
          f"{(e5_metrics['recall@10']-bge_metrics['recall@10'])*100:.1f}pp)")
    print(f"  MRR:       bge-m3 {bge_metrics['MRR']:.3f} → e5 {e5_metrics['MRR']:.3f}")

    delta_5 = e5_metrics["recall@5"] - bge_metrics["recall@5"]
    if delta_5 >= 0.05:
        print(f"\n✅ E5 KAZANDI (+{delta_5*100:.0f}pp recall@5) — migration önerilir")
    elif delta_5 >= 0:
        print(f"\n⚖️ E5 marjinal kazanım (+{delta_5*100:.0f}pp) — migration kararı kullanıcıya")
    else:
        print(f"\n❌ E5 kötüleştirdi ({delta_5*100:.1f}pp) — bge-m3 kalmalı")


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    asyncio.run(main())
