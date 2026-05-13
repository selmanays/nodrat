"""Microchunks backfill — mevcut macros için micros üret (#767 Adım 1).

Strateji:
  - Mevcut article_chunks (chunk_level='macro') üzerinden geçer
  - Her macro için microchunk_text() ile alt-böl
  - INSERT chunk_level='micro' + parent_chunk_id=<macro.id>
  - Macros dokunulmaz (re-embed yok)
  - Micros embed task'ı toplu dispatch eder

Çalıştırma:
    docker compose exec -T api python scripts/backfill_microchunks.py
    docker compose exec -T api python scripts/backfill_microchunks.py --limit 100  # test

Süre tahmini (5,697 article × ~5 macro ≈ 11K macros → ~22K micros):
  - Chunker (CPU): ~5 dk
  - Embedding (bge-m3 lokal, batch 50): ~15 dk
  - Toplam: ~20 dk
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

from sqlalchemy import text as sa_text  # noqa: E402

from app.core.chunker import MicrochunkConfig, microchunk_text  # noqa: E402
from app.core.db import get_session_factory  # noqa: E402
from app.core.settings_store import settings_store  # noqa: E402

logger = logging.getLogger(__name__)


async def _backfill(limit: int | None = None) -> dict:
    """Tüm macros için micros üret."""
    factory = get_session_factory()
    summary = {"macros_processed": 0, "micros_inserted": 0, "errors": 0, "articles": 0}

    async with factory() as db:
        # Setting flag onaylı mı?
        flag = await settings_store.get_bool(db, "chunker.micro_enabled", False)
        if not flag:
            print("⚠️  chunker.micro_enabled=false — backfill atlanacak")
            return summary

        # Config
        m_target = await settings_store.get_int(db, "chunker.micro_target_tokens", 128)
        m_max = await settings_store.get_int(db, "chunker.micro_max_tokens", 200)
        m_min = await settings_store.get_int(db, "chunker.micro_min_tokens", 50)
        cfg = MicrochunkConfig(target_tokens=m_target, max_tokens=m_max, min_tokens=m_min)

        print(f"📐 Micro config: target={m_target}, max={m_max}, min={m_min}")

        # Stale micros sil (idempotent)
        deleted = await db.execute(
            sa_text("DELETE FROM article_chunks WHERE chunk_level='micro' RETURNING id")
        )
        deleted_count = len(deleted.all())
        await db.commit()
        print(f"🗑️  Stale micros silindi: {deleted_count}")

        # Macros'u oku
        q = """
            SELECT c.id, c.article_id, c.source_id, c.chunk_text, c.published_at,
                   a.title, a.subtitle
            FROM article_chunks c
            JOIN articles a ON a.id = c.article_id
            WHERE c.chunk_level = 'macro'
            ORDER BY c.article_id, c.chunk_index
        """
        if limit:
            q += f" LIMIT {int(limit)}"

        rows = (await db.execute(sa_text(q))).mappings().all()
        print(f"📊 Macros okundu: {len(rows)}")

        # Microchunk index namespace: 10000+ per article (overlap riski yok)
        per_article_idx: dict[str, int] = {}
        batch_inserts: list[dict] = []

        t0 = time.perf_counter()
        for r in rows:
            try:
                aid = str(r["article_id"])
                start_idx = per_article_idx.get(aid, 10000)

                micros = microchunk_text(
                    r["chunk_text"],
                    title=r["title"],
                    subtitle=r["subtitle"],
                    config=cfg,
                )

                for mch in micros:
                    batch_inserts.append({
                        "aid": aid,
                        "sid": str(r["source_id"]),
                        "idx": start_idx,
                        "ctext": mch.chunk_text,
                        "tcount": mch.token_count,
                        "pat": r["published_at"],
                        "parent": str(r["id"]),
                    })
                    start_idx += 1

                per_article_idx[aid] = start_idx
                summary["macros_processed"] += 1

                # Batch flush — her 500 rows
                if len(batch_inserts) >= 500:
                    await _flush_inserts(db, batch_inserts)
                    summary["micros_inserted"] += len(batch_inserts)
                    batch_inserts = []
                    if summary["macros_processed"] % 1000 == 0:
                        elapsed = time.perf_counter() - t0
                        rate = summary["macros_processed"] / elapsed
                        print(
                            f"  ⏳ {summary['macros_processed']}/{len(rows)} macros — "
                            f"{summary['micros_inserted']} micros — "
                            f"rate={rate:.1f}/s"
                        )
            except Exception as exc:
                logger.error("backfill error macro=%s: %s", r["id"], exc)
                summary["errors"] += 1

        # Final flush
        if batch_inserts:
            await _flush_inserts(db, batch_inserts)
            summary["micros_inserted"] += len(batch_inserts)

        summary["articles"] = len(per_article_idx)
        elapsed = time.perf_counter() - t0
        print(
            f"✅ Done in {elapsed:.1f}s: "
            f"{summary['macros_processed']} macros → {summary['micros_inserted']} micros "
            f"({summary['articles']} articles) errors={summary['errors']}"
        )

    return summary


async def _flush_inserts(db, batch: list[dict]) -> None:
    """Bulk INSERT micros (executemany)."""
    if not batch:
        return
    await db.execute(
        sa_text("""
            INSERT INTO article_chunks
                (article_id, source_id, chunk_index, chunk_text,
                 token_count, published_at, chunk_level, parent_chunk_id)
            VALUES (:aid, :sid, :idx, :ctext, :tcount, :pat,
                    'micro', :parent)
            ON CONFLICT (article_id, chunk_index) DO NOTHING
        """),
        batch,
    )
    await db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill microchunks from macros")
    parser.add_argument("--limit", type=int, default=None, help="Test için sınırla")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    summary = asyncio.run(_backfill(limit=args.limit))
    print(f"\n📊 Summary: {summary}")


if __name__ == "__main__":
    main()
