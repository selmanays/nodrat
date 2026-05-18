"""Embed pending chunks (#767 — micro backfill sonrası).

Tüm article_chunks WHERE embedding IS NULL — batch embedding ile doldur.
chunk_level filter yok (macros + micros aynı şekilde işlenir).

Çalıştırma:
    docker compose exec -T api python scripts/embed_pending_chunks.py
    docker compose exec -T api python scripts/embed_pending_chunks.py --batch-size 100

Süre: lokal bge-m3 (CPU) — ~50ms/batch 50 → 29K chunk × 50ms / 50 ≈ 30-90 saniye.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import get_session_factory
from app.providers.registry import bootstrap_default_providers, registry
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


async def _embed_pending(batch_size: int = 50) -> dict:
    """NULL embedding olan tüm chunks'u batch embed et."""
    bootstrap_default_providers()
    provider = registry.route_for_tier(operation="embedding", tier="free")

    factory = get_session_factory()
    summary = {"embedded": 0, "errors": 0, "batches": 0}

    t0 = time.perf_counter()

    async with factory() as db:
        # Pending count
        total_row = await db.execute(
            sa_text("SELECT COUNT(*) FROM article_chunks WHERE embedding IS NULL")
        )
        total = total_row.scalar()
        print(f"📊 Embed gerekli chunks: {total}")
        if total == 0:
            return summary

    # Cursor-style processing — batch by batch
    while True:
        async with factory() as db:
            rows = (
                (
                    await db.execute(
                        sa_text(f"""
                    SELECT id, chunk_text
                    FROM article_chunks
                    WHERE embedding IS NULL
                    ORDER BY created_at  -- önce eski (deterministik)
                    LIMIT {int(batch_size)}
                    """)  # noqa: S608
                    )
                )
                .mappings()
                .all()
            )

            if not rows:
                break

            texts = [r["chunk_text"] for r in rows]
            try:
                result = await provider.create_embedding(texts)
                vectors = result.vectors or []
                if len(vectors) != len(rows):
                    print(f"⚠️  vector count mismatch: {len(vectors)} vs {len(rows)}")
                    summary["errors"] += 1
                    continue

                # UPDATE — bind parameters per row
                for row, vec in zip(rows, vectors, strict=True):
                    # pgvector için string format gerek (e.g., '[0.1,0.2,...]')
                    vec_str = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
                    await db.execute(
                        sa_text("""
                            UPDATE article_chunks
                            SET embedding = CAST(:vec AS vector)
                            WHERE id = :id
                        """),
                        {"id": row["id"], "vec": vec_str},
                    )
                await db.commit()

                summary["embedded"] += len(rows)
                summary["batches"] += 1

                if summary["batches"] % 50 == 0:
                    elapsed = time.perf_counter() - t0
                    rate = summary["embedded"] / elapsed if elapsed > 0 else 0
                    print(
                        f"  ⏳ {summary['embedded']}/{total} — "
                        f"{summary['batches']} batches — "
                        f"rate={rate:.1f}/s"
                    )

            except Exception as exc:
                logger.error("batch embed failed: %s", exc)
                summary["errors"] += 1

    elapsed = time.perf_counter() - t0
    print(
        f"✅ Done in {elapsed:.1f}s: "
        f"{summary['embedded']} embedded, "
        f"{summary['batches']} batches, "
        f"errors={summary['errors']}"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed pending chunks (NULL embedding)")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    summary = asyncio.run(_embed_pending(batch_size=args.batch_size))
    print(f"\n📊 Summary: {summary}")


if __name__ == "__main__":
    main()
