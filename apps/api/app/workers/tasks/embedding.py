"""Embedding worker (#19) — chunk article'ları → NIM embed → article_chunks.

Pipeline:
    article (status=cleaned) → chunk_text → article_chunks INSERT (embed=NULL)
    → article_chunks (embed=NULL) → embed via registry → UPDATE embedding column

Tasks:
    chunk_and_embed_article(article_id)
        - articles.clean_text → chunker.chunk_text
        - article_chunks INSERT (embed kısmı NULL — embed task ayrı)
        - embed_article_chunks task'ını chain dispatch

    embed_article_chunks(article_id, batch_size=50)
        - article_chunks WHERE article_id=X AND embedding IS NULL
        - registry.route_for_tier(operation='embedding') ile provider al
        - Batch (50) — local BAAI/bge-m3 (sentence-transformers, CPU on VPS).
        - UPDATE embedding column

docs/engineering/architecture.md §3.1 (embedding_queue)
docs/engineering/data-model.md §4.1 (article_chunks)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chunker import ChunkingConfig, chunk_text
from app.core.cost_tracker import estimate_cost_usd, track_provider_call
from app.providers.registry import registry, bootstrap_default_providers
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _get_session_factory, _run_async


logger = logging.getLogger(__name__)


# Provider bootstrap idempotent — worker process başına 1 kez
_PROVIDERS_BOOTSTRAPPED = False


def _ensure_providers() -> None:
    global _PROVIDERS_BOOTSTRAPPED
    if not _PROVIDERS_BOOTSTRAPPED:
        bootstrap_default_providers()
        _PROVIDERS_BOOTSTRAPPED = True


# Embedding batch size (local BAAI/bge-m3, sentence-transformers stable batch)
EMBED_BATCH_SIZE = 50


# ============================================================================
# chunk_and_embed_article — articles.clean_text → article_chunks INSERT
# ============================================================================


async def _chunk_article_async(article_id: UUID) -> dict:
    """Article cleaned_text'i chunk'la → article_chunks satırları üret."""
    factory = _get_session_factory()
    summary: dict[str, Any] = {"article_id": str(article_id), "status": "unknown"}

    # SQL doğrudan çalıştırarak ORM'i atlıyoruz çünkü article_chunks
    # ORM model henüz tanımlı değil (vector column için lazy raw SQL).
    from sqlalchemy import text as sa_text

    async with factory() as db:
        from app.models.article import Article

        article = await db.get(Article, article_id)
        if article is None:
            summary["status"] = "not_found"
            return summary
        if article.status != "cleaned":
            summary["status"] = "skipped"
            summary["reason"] = f"article not cleaned (status={article.status})"
            return summary
        if not article.clean_text or len(article.clean_text) < 100:
            summary["status"] = "skipped"
            summary["reason"] = "no_clean_text"
            return summary

        # Eski chunk'ları temizle (re-chunk idempotent)
        await db.execute(
            sa_text("DELETE FROM article_chunks WHERE article_id = :aid"),
            {"aid": str(article_id)},
        )

        # #271 — runtime chunker config override
        try:
            from app.core.settings_store import settings_store

            chunk_cfg = ChunkingConfig(
                target_tokens=await settings_store.get_int(
                    db, "chunker.target_tokens", 500
                ),
                max_tokens=await settings_store.get_int(
                    db, "chunker.max_tokens", 900
                ),
                min_tokens=await settings_store.get_int(
                    db, "chunker.min_tokens", 200
                ),
                overlap_tokens=await settings_store.get_int(
                    db, "chunker.overlap_tokens", 80
                ),
            )
        except Exception:  # pragma: no cover
            chunk_cfg = ChunkingConfig()

        # Chunk üret
        chunks = chunk_text(
            article.clean_text,
            title=article.title,
            subtitle=article.subtitle,
            config=chunk_cfg,
        )
        if not chunks:
            summary["status"] = "no_chunks"
            await db.commit()
            return summary

        # INSERT
        for ch in chunks:
            await db.execute(
                sa_text(
                    """
                    INSERT INTO article_chunks
                        (article_id, source_id, chunk_index, chunk_text,
                         token_count, published_at)
                    VALUES (:aid, :sid, :idx, :ctext, :tcount, :pat)
                    ON CONFLICT (article_id, chunk_index) DO UPDATE SET
                        chunk_text = EXCLUDED.chunk_text,
                        token_count = EXCLUDED.token_count
                    """
                ),
                {
                    "aid": str(article.id),
                    "sid": str(article.source_id),
                    "idx": ch.chunk_index,
                    "ctext": ch.chunk_text,
                    "tcount": ch.token_count,
                    "pat": article.published_at,
                },
            )
        await db.commit()

        summary["status"] = "chunked"
        summary["chunk_count"] = len(chunks)
        summary["total_tokens"] = sum(ch.token_count for ch in chunks)

        # Embed task chain
        try:
            embed_article_chunks.apply_async(args=[str(article_id)])
            summary["embed_dispatched"] = True
        except Exception as exc:  # pragma: no cover
            logger.exception("dispatch embed failed art=%s err=%s", article_id, exc)

        return summary


@celery_app.task(name="tasks.embedding.chunk_article", bind=True, max_retries=2)
def chunk_article(self, article_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Article'ı chunk'la (sync wrapper)."""
    return _run_async(_chunk_article_async(UUID(article_id)))


# ============================================================================
# embed_article_chunks — embedding column doldur
# ============================================================================


async def _embed_chunks_async(article_id: UUID, batch_size: int = EMBED_BATCH_SIZE) -> dict:
    """article_chunks WHERE embedding IS NULL → batch embed via registry."""
    _ensure_providers()
    factory = _get_session_factory()
    from sqlalchemy import text as sa_text

    summary: dict[str, Any] = {
        "article_id": str(article_id),
        "status": "unknown",
        "embedded": 0,
        "errors": 0,
    }

    # Provider seç (free tier defaults — NIM)
    try:
        provider = registry.route_for_tier(operation="embedding", tier="free")
    except RuntimeError as exc:
        summary["status"] = "no_provider"
        summary["error"] = str(exc)
        return summary

    async with factory() as db:
        # Pending chunk'ları al
        rows = (
            await db.execute(
                sa_text(
                    """
                    SELECT id, chunk_text
                    FROM article_chunks
                    WHERE article_id = :aid AND embedding IS NULL
                    ORDER BY chunk_index
                    LIMIT :batch
                    """
                ),
                {"aid": str(article_id), "batch": batch_size},
            )
        ).all()

        if not rows:
            summary["status"] = "all_embedded"
            return summary

        ids = [row[0] for row in rows]
        texts = [row[1] for row in rows]

        # Provider call — tracker insert'i caller commit'iyle yazılır
        try:
            async with track_provider_call(
                db=db,
                provider=provider.name,
                operation="embedding",
                article_id=article_id,
            ) as tracker:
                result = await provider.create_embedding(texts)
                tracker.record(
                    input_tokens=getattr(result, "token_count", None) or sum(
                        len(t.split()) for t in texts
                    ),
                    output_tokens=0,  # embedding output token sayılmaz
                    model=result.model,
                    cost_usd=estimate_cost_usd(
                        provider=provider.name,
                        input_tokens=getattr(result, "token_count", None),
                        output_tokens=0,
                        cost_per_1m_input=getattr(provider, "cost_per_1m_input_tokens", 0.0),
                        cost_per_1m_output=0.0,
                    ),
                )
        except Exception as exc:
            logger.exception("embed provider error art=%s err=%s", article_id, exc)
            summary["status"] = "provider_error"
            summary["error"] = str(exc)[:200]
            await db.commit()  # tracker'ın yazdığı failed log'u kaydet
            return summary

        if len(result.vectors) != len(ids):
            summary["status"] = "vector_count_mismatch"
            summary["expected"] = len(ids)
            summary["got"] = len(result.vectors)
            return summary

        # UPDATE — pgvector array literal: '[0.1,0.2,...]'
        # #221 — embedding_binary aynı UPDATE'te doldurulur (binary_quantize
        # native pgvector func'u, ekstra round-trip yok). Search routing
        # şimdilik hâlâ float32 kullanır; binary opt-in (sonraki PR).
        for chunk_id, vec in zip(ids, result.vectors, strict=True):
            vec_str = "[" + ",".join(f"{v:.7f}" for v in vec) + "]"
            await db.execute(
                sa_text(
                    """
                    UPDATE article_chunks
                    SET embedding = (:vec)::vector,
                        embedding_binary = binary_quantize((:vec)::vector),
                        embedding_model = :model,
                        embedding_provider = :provider
                    WHERE id = :cid
                    """
                ),
                {
                    "vec": vec_str,
                    "model": result.model or provider.name,
                    "provider": provider.name,
                    "cid": str(chunk_id),
                },
            )
            summary["embedded"] += 1

        await db.commit()

        # Hâlâ pending varsa kendini tekrar dispatch et (chain)
        remaining = (
            await db.execute(
                sa_text(
                    "SELECT COUNT(*) FROM article_chunks "
                    "WHERE article_id = :aid AND embedding IS NULL"
                ),
                {"aid": str(article_id)},
            )
        ).scalar() or 0

        summary["status"] = "embedded"
        summary["model"] = result.model
        summary["pending_remaining"] = remaining

        if remaining > 0:
            try:
                embed_article_chunks.apply_async(args=[str(article_id)])
                summary["next_batch_dispatched"] = True
            except Exception:
                pass
        else:
            # Tüm chunk'lar embed oldu → clustering chain
            try:
                from app.workers.tasks.clustering import cluster_article

                cluster_article.apply_async(args=[str(article_id)])
                summary["clustering_dispatched"] = True
            except Exception as exc:  # pragma: no cover
                logger.exception(
                    "dispatch cluster failed art=%s err=%s", article_id, exc
                )

        return summary


@celery_app.task(
    name="tasks.embedding.embed_chunks",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
)
def embed_article_chunks(self, article_id: str) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_embed_chunks_async(UUID(article_id)))
