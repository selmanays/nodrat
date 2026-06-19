"""Maintenance tasks — pgvector binary quantization + re-embed backfill.

#221 quantize_chunks (embedding → embedding_binary) + reembed_chunks /
reembed_agenda_cards bakım task'ları.

NOT: Cold-tier raw_html retention (cold_tier_archive/restore) ve body_html_drop
#1634 ile KALDIRILDI — ham haber sayfaları saklanmıyor (URL'ler elde, gerekirse
yeniden çekilir). body_html artık kalıcı saklanır.

docs/engineering/architecture.md §5 (storage)
"""

from __future__ import annotations

import logging

from sqlalchemy import text as sa_text

from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


# ============================================================================
# #221 MVP-1.5 PR-6 — pgvector binary quantization backfill
# ============================================================================


async def _quantize_chunks_async(batch: int) -> dict:
    """article_chunks.embedding → embedding_binary backfill (idempotent)."""
    from app.core.embedding_binary import quantize_chunk_batch

    factory = _get_session_factory()
    async with factory() as db:
        result = await quantize_chunk_batch(db, batch=batch)
    result["status"] = "ok"
    logger.info(
        "quantize_chunks: updated=%d remaining=%d batch=%d",
        result["updated"],
        result["remaining"],
        batch,
    )
    return result


@celery_app.task(
    name="tasks.maintenance.quantize_chunks",
)
def quantize_chunks(batch: int = 500) -> dict:
    """NULL embedding_binary olan chunk'lar için binary_quantize().

    pgvector native fonksiyon; tek SQL'de batch UPDATE.
    Idempotent: zaten quantize edilmiş satırları atlar.

    Manuel one-shot: `quantize_chunks.apply_async(kwargs={"batch": 5000})`.
    Beat schedule: gerek yok — yeni chunk'lar embedding worker'da
    INSERT sırasında doldurulacak (sonraki PR), eski 2167 chunk için
    bir kez bu task çalıştırılır.
    """
    return _run_async(_quantize_chunks_async(batch))


# ============================================================================
# Re-embedding maintenance task (local BAAI/bge-m3 ile)
# ============================================================================
#
# Bu task article_chunks ve agenda_cards'ı LocalBgeM3Provider ile
# re-embed eder. Embedding model değişikliği veya migration durumlarında
# kullanılır. Provider'ı registry'i atlayarak direkt instance oluşturur.
# ============================================================================


async def _reembed_chunks_async(batch: int = 100) -> dict:
    """article_chunks'ı local bge-m3 ile re-embed et.

    Strategy:
      1. SELECT WHERE embedding_provider != 'local_bge_m3' (idempotent)
      2. LocalBgeM3Provider().create_embedding(batch_texts) — CPU
      3. UPDATE embedding + embedding_binary (binary_quantize) +
         embedding_provider = 'local_bge_m3'
      4. embedding_binary dual-write — search routing flag flip için hazır

    Idempotent: aynı task tekrar tekrar çağrılabilir, zaten taşınanı atlar.
    """
    from app.providers.local_embedding import LocalBgeM3Provider

    summary: dict = {"requested": batch, "reembedded": 0, "skipped": 0}
    provider = LocalBgeM3Provider()  # registry bypass — flag bağımsız

    factory = _get_session_factory()
    async with factory() as db:
        # Idempotent: settings'teki target embedding_model'a sahip olmayanları al
        from app.config import get_settings

        target_model = get_settings().local_embedding_model
        rows = (
            (
                await db.execute(
                    sa_text(
                        """
                    SELECT id::text AS id, chunk_text
                    FROM article_chunks
                    WHERE embedding IS NOT NULL
                      AND (embedding_model IS NULL
                           OR embedding_model != :target)
                    ORDER BY created_at DESC
                    LIMIT :batch
                    """
                    ),
                    {"batch": batch, "target": target_model},
                )
            )
            .mappings()
            .all()
        )

        if not rows:
            summary["status"] = "no_pending"
            return summary

        texts = [r["chunk_text"] for r in rows]
        emb_result = await provider.create_embedding(texts)

        if len(emb_result.vectors) != len(rows):
            summary["status"] = "vector_count_mismatch"
            return summary

        for row, vec in zip(rows, emb_result.vectors, strict=True):
            vec_str = "[" + ",".join(f"{v:.7f}" for v in vec) + "]"
            await db.execute(
                sa_text(
                    """
                    UPDATE article_chunks
                    SET embedding = (:vec)::vector,
                        embedding_binary = binary_quantize((:vec)::vector),
                        embedding_provider = 'local_bge_m3',
                        embedding_model = :model
                    WHERE id = :cid
                    """
                ),
                {
                    "vec": vec_str,
                    "model": emb_result.model,
                    "cid": row["id"],
                },
            )
            summary["reembedded"] += 1

        await db.commit()

        # Kalan sayı
        remaining = (
            await db.execute(
                sa_text(
                    """
                    SELECT COUNT(*) FROM article_chunks
                    WHERE embedding IS NOT NULL
                      AND (embedding_provider IS NULL
                           OR embedding_provider != 'local_bge_m3')
                    """
                )
            )
        ).scalar_one()
        summary["remaining"] = int(remaining)

    summary["status"] = "ok"
    logger.info(
        "reembed_chunks: reembedded=%d remaining=%d",
        summary["reembedded"],
        summary["remaining"],
    )
    return summary


async def _reembed_agenda_cards_async(batch: int = 100) -> dict:
    """agenda_cards.embedding'i local bge-m3 ile re-embed et.

    agenda_cards'da embedding_provider kolonu yok; tablonun tüm row'ları
    NIM ile yapıldı varsayımıyla, local provider ile yeniden embed
    + bir sentinel (örn. generated_by_model) kontrolü ile idempotent
    yapma — ya da sadece updated_at NOW() güncelleyerek 'taşındı' işaretle.

    Pragmatik: tek seferlik bir task; manuel one-shot çalıştırılır.
    Idempotent değil (her call tüm agenda_cards'ı tekrar embed eder),
    ama tek seferlik çalıştırıldığı için sorun yok.
    """
    from app.providers.local_embedding import LocalBgeM3Provider

    summary: dict = {"requested": batch, "reembedded": 0}
    provider = LocalBgeM3Provider()

    factory = _get_session_factory()
    async with factory() as db:
        # Idempotent restore: 'turkce-embed' sentinel'li olanları seç,
        # re-embed sırasında REPLACE ile sentinel'i kaldır.
        rows = (
            (
                await db.execute(
                    sa_text(
                        """
                    SELECT id::text AS id,
                           COALESCE(title, '') || E'\\n\\n' || COALESCE(summary, '') AS combined
                    FROM agenda_cards
                    WHERE embedding IS NOT NULL
                      AND generated_by_model LIKE '%turkce-embed%'
                    ORDER BY updated_at DESC
                    LIMIT :batch
                    """
                    ),
                    {"batch": batch},
                )
            )
            .mappings()
            .all()
        )

        if not rows:
            summary["status"] = "no_pending"
            return summary

        texts = [r["combined"][:4000] for r in rows]
        emb_result = await provider.create_embedding(texts)

        for row, vec in zip(rows, emb_result.vectors, strict=True):
            vec_str = "[" + ",".join(f"{v:.7f}" for v in vec) + "]"
            await db.execute(
                sa_text(
                    """
                    UPDATE agenda_cards
                    SET embedding = (:vec)::vector,
                        generated_by_model = REPLACE(
                            generated_by_model,
                            'turkce-embed',
                            'bge-m3-restored'
                        )
                    WHERE id = :id
                    """
                ),
                {"vec": vec_str, "id": row["id"]},
            )
            summary["reembedded"] += 1

        await db.commit()

    summary["status"] = "ok"
    logger.info("reembed_agenda_cards: reembedded=%d", summary["reembedded"])
    return summary


@celery_app.task(
    name="tasks.maintenance.reembed_chunks",
    queue="embedding_queue",
)
def reembed_chunks(batch: int = 100) -> dict:
    """Article chunks NIM → local bge-m3 re-embed.

    Manuel one-shot: `reembed_chunks.apply_async(kwargs={"batch": 5000})`.
    Idempotent: provider='local_bge_m3' olanlar atlanır.
    """
    return _run_async(_reembed_chunks_async(batch))


@celery_app.task(
    name="tasks.maintenance.reembed_agenda_cards",
    queue="embedding_queue",
)
def reembed_agenda_cards(batch: int = 100) -> dict:
    """Agenda cards NIM → local bge-m3 re-embed.

    Manuel one-shot. Idempotent değil (tek seferlik kullanım).
    """
    return _run_async(_reembed_agenda_cards_async(batch))
