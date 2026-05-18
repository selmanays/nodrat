"""Backfill agenda_cards.embedding (#169 PR-D).

Tek seferlik script — RAG entegrasyonu öncesi mevcut NULL embedding'leri
title + summary'den hesaplayıp DB'ye yazar.

Kullanım (production VPS):
    docker compose exec -T -w /app api python scripts/backfill_agenda_embeddings.py

Idempotent: NULL olanları seçer, var olanlara dokunmaz.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.config import get_settings
from app.providers.registry import bootstrap_default_providers, registry
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

logger = logging.getLogger("backfill_agenda")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    bootstrap_default_providers()
    provider = registry.route_for_tier(operation="embedding", tier="free")
    logger.info("Embedding provider: %s", provider.name)

    async with Session() as db:
        rows = (
            await db.execute(
                sa_text(
                    """
                    SELECT id, title, summary
                    FROM agenda_cards
                    WHERE embedding IS NULL
                    ORDER BY created_at DESC
                    """
                )
            )
        ).all()
        total = len(rows)
        logger.info("NULL embedding agenda_cards: %d", total)
        if not rows:
            logger.info("Nothing to backfill ✓")
            return

        # Batch process (her batch 16 kart)
        BATCH = 16
        embedded = 0
        failed = 0
        start = datetime.utcnow()

        for i in range(0, total, BATCH):
            batch = rows[i : i + BATCH]
            ids = [r[0] for r in batch]
            texts = [f"{r[1].strip()}\n\n{r[2].strip()}"[:4000] for r in batch]

            try:
                result = await provider.create_embedding(texts)
            except Exception as exc:
                logger.error("batch %d-%d failed: %s", i, i + len(batch), exc)
                failed += len(batch)
                continue

            if len(result.vectors) != len(ids):
                logger.error(
                    "batch %d vector count mismatch: %d != %d",
                    i,
                    len(result.vectors),
                    len(ids),
                )
                failed += len(batch)
                continue

            for aid, vec in zip(ids, result.vectors, strict=True):
                if len(vec) != 1024:
                    logger.warning(
                        "agenda %s vector dim != 1024 (got %d), skip",
                        aid,
                        len(vec),
                    )
                    failed += 1
                    continue
                vec_str = "[" + ",".join(f"{v:.7f}" for v in vec) + "]"
                await db.execute(
                    sa_text(
                        """
                        UPDATE agenda_cards
                        SET embedding = (:vec)::vector
                        WHERE id = :aid
                        """
                    ),
                    {"vec": vec_str, "aid": str(aid)},
                )
                embedded += 1

            await db.commit()
            logger.info(
                "batch %d/%d done — embedded=%d failed=%d",
                min(i + BATCH, total),
                total,
                embedded,
                failed,
            )

        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info(
            "DONE — embedded=%d/%d failed=%d (%.1fs)",
            embedded,
            total,
            failed,
            elapsed,
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
