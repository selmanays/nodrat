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

            # #652 Faz 1 — RAGFlow-tier defaults (sentence-window):
            #   target 500→256, max 900→384, min 200→100, overlap 80→64
            # Niş bilgi recall sıçraması; mevcut 109K chunk re-chunk lazım.
            chunk_cfg = ChunkingConfig(
                target_tokens=await settings_store.get_int(
                    db, "chunker.target_tokens", 256
                ),
                max_tokens=await settings_store.get_int(
                    db, "chunker.max_tokens", 384
                ),
                min_tokens=await settings_store.get_int(
                    db, "chunker.min_tokens", 100
                ),
                overlap_tokens=await settings_store.get_int(
                    db, "chunker.overlap_tokens", 64
                ),
            )
        except Exception:  # pragma: no cover
            chunk_cfg = ChunkingConfig()

        # #661 Faz 5.1 — Semantic chunker feature flag (default ON)
        # Adjacent sentence cosine similarity ile semantic breakpoint
        # detection. Article başına 1 batch embedding call (cost guard).
        # Fallback: structural chunk_text (sentence-window only).
        try:
            from app.core.settings_store import settings_store

            use_semantic = await settings_store.get_bool(
                db, "chunker.semantic_enabled", True
            )
            semantic_target = await settings_store.get_int(
                db, "chunker.semantic_target_tokens", 400
            )
            semantic_max = await settings_store.get_int(
                db, "chunker.semantic_max_tokens", 800
            )
            semantic_min = await settings_store.get_int(
                db, "chunker.semantic_min_tokens", 150
            )
            semantic_percentile = await settings_store.get_int(
                db, "chunker.semantic_breakpoint_percentile", 25
            )
        except Exception:
            use_semantic = True
            semantic_target = 400
            semantic_max = 800
            semantic_min = 150
            semantic_percentile = 25

        if use_semantic:
            from app.core.semantic_chunker import (
                SemanticChunkConfig,
                semantic_chunk_text,
            )

            _ensure_providers()
            embed_provider = None
            try:
                embed_provider = registry.route_for_tier(
                    operation="embedding", tier="free"
                )
            except RuntimeError:
                embed_provider = None

            async def _embed_batch(texts: list[str]) -> list[list[float]]:
                """Tüm cümleler tek seferde embed — cost guard."""
                if not embed_provider:
                    return []
                result = await embed_provider.create_embedding(texts)
                return list(getattr(result, "vectors", None) or [])

            sem_cfg = SemanticChunkConfig(
                target_tokens=semantic_target,
                max_tokens=semantic_max,
                min_tokens=semantic_min,
                breakpoint_percentile=semantic_percentile,
            )
            try:
                chunks = await semantic_chunk_text(
                    article.clean_text,
                    title=article.title,
                    subtitle=article.subtitle,
                    embed_fn=_embed_batch if embed_provider else None,
                    config=sem_cfg,
                )
            except Exception as exc:
                logger.warning(
                    "semantic_chunk_text failed art=%s, fallback structural: %s",
                    article_id, exc,
                )
                chunks = chunk_text(
                    article.clean_text,
                    title=article.title,
                    subtitle=article.subtitle,
                    config=chunk_cfg,
                )
        else:
            # Faz 1 sentence-window fallback (test/rollback için)
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

        # #661 Faz 5.2 — article summary embedding zinciri
        try:
            embed_article_summary.apply_async(args=[str(article_id)])
            summary["summary_embed_dispatched"] = True
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "dispatch summary embed failed art=%s err=%s", article_id, exc
            )

        # #667 Faz 6 — NER entity extraction zinciri
        try:
            from app.workers.tasks.entities import extract_article_entities

            extract_article_entities.apply_async(args=[str(article_id)])
            summary["ner_dispatched"] = True
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "dispatch ner failed art=%s err=%s", article_id, exc
            )

        # #778 Faz 3 — Per-chunk keyword + question extraction (RagFlow pattern)
        # Async dispatch — chunks INSERT edildikten sonra keyword extraction
        # parallel olarak çalışır. BM25 retrieval'da yüksek ağırlık sağlar.
        try:
            extract_chunk_keywords.apply_async(args=[str(article_id)])
            summary["chunk_keywords_dispatched"] = True
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "dispatch chunk_keywords failed art=%s err=%s", article_id, exc
            )

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


# ============================================================================
# Article summary embedding (#661 Faz 5.2)
# Article ana teması için ayrı vector — sorgu önce article-level match
# (kategori/tema), sonra chunk-level (niş detay). İki-aşamalı retrieval.
# ============================================================================


async def _embed_article_summary_async(article_id: UUID) -> dict:
    """articles.summary_embedding column'unu doldur.

    Input formula: `title + " " + (subtitle or "") + " " + first_paragraph[:200]`
    Bu LangChain summary embedding pattern'i; haber ana temasını yakalar.
    """
    _ensure_providers()
    factory = _get_session_factory()
    from sqlalchemy import text as sa_text

    summary: dict[str, Any] = {
        "article_id": str(article_id),
        "status": "unknown",
    }

    try:
        provider = registry.route_for_tier(operation="embedding", tier="free")
    except RuntimeError as exc:
        summary["status"] = "no_provider"
        summary["error"] = str(exc)
        return summary

    async with factory() as db:
        row = (
            await db.execute(
                sa_text(
                    """
                    SELECT title, subtitle, clean_text, status
                    FROM articles WHERE id = :aid
                    """
                ),
                {"aid": str(article_id)},
            )
        ).mappings().first()

        if not row:
            summary["status"] = "not_found"
            return summary
        if row["status"] != "cleaned":
            summary["status"] = "skipped_not_cleaned"
            return summary
        if not (row["title"] or "").strip():
            summary["status"] = "skipped_no_title"
            return summary

        # Embed input: title + subtitle + ilk 200 char clean_text
        title = (row["title"] or "").strip()
        subtitle = (row["subtitle"] or "").strip()
        body_excerpt = (row["clean_text"] or "").strip()[:200]
        parts = [title]
        if subtitle:
            parts.append(subtitle)
        if body_excerpt:
            parts.append(body_excerpt)
        text_to_embed = " ".join(parts)

        try:
            result = await provider.create_embedding([text_to_embed])
            vectors = getattr(result, "vectors", None) or []
            if not vectors:
                summary["status"] = "embed_empty"
                return summary
            vec = vectors[0]
            vec_lit = "[" + ",".join(f"{v:.7f}" for v in vec) + "]"
            await db.execute(
                sa_text(
                    "UPDATE articles SET summary_embedding = :vec WHERE id = :aid"
                ),
                {"vec": vec_lit, "aid": str(article_id)},
            )
            await db.commit()
            summary["status"] = "embedded"
            summary["dim"] = len(vec)
            return summary
        except Exception as exc:
            await db.rollback()
            summary["status"] = "failed"
            summary["error"] = str(exc)
            return summary


@celery_app.task(
    name="tasks.embedding.embed_article_summary",
    bind=True,
    max_retries=2,
)
def embed_article_summary(self, article_id: str) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_embed_article_summary_async(UUID(article_id)))


async def _backfill_article_summaries_async(
    *, batch_size: int = 100, dry_run: bool = False
) -> dict:
    """Tüm cleaned article'lar için summary_embedding üret (NULL olanlar)."""
    factory = _get_session_factory()
    from sqlalchemy import text as sa_text

    summary: dict[str, Any] = {
        "status": "unknown",
        "dispatched": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }

    async with factory() as db:
        total = (
            await db.execute(
                sa_text(
                    """
                    SELECT COUNT(*) FROM articles
                    WHERE status = 'cleaned' AND summary_embedding IS NULL
                    """
                )
            )
        ).scalar() or 0
        summary["total_eligible"] = int(total)

        if dry_run or total == 0:
            summary["status"] = "dry_run" if dry_run else "no_eligible"
            return summary

        dispatched = 0
        offset = 0
        while True:
            rows = (
                await db.execute(
                    sa_text(
                        """
                        SELECT id::text AS aid
                        FROM articles
                        WHERE status = 'cleaned' AND summary_embedding IS NULL
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    {"limit": batch_size, "offset": offset},
                )
            ).mappings().all()

            if not rows:
                break

            for r in rows:
                try:
                    embed_article_summary.apply_async(args=[r["aid"]])
                    dispatched += 1
                except Exception as exc:
                    logger.warning(
                        "dispatch embed_article_summary failed aid=%s err=%s",
                        r["aid"], exc,
                    )
                    summary["skipped"] = int(summary["skipped"]) + 1

            offset += len(rows)

        summary["dispatched"] = dispatched
        summary["status"] = "dispatched"
        return summary


@celery_app.task(
    name="tasks.embedding.backfill_article_summaries",
    bind=True,
)
def backfill_article_summaries(  # type: ignore[no-untyped-def]
    self,
    batch_size: int = 100,
    dry_run: bool = False,
) -> dict:
    """#661 Faz 5.2 — tüm cleaned article'lar için summary_embedding üret."""
    return _run_async(
        _backfill_article_summaries_async(batch_size=batch_size, dry_run=dry_run)
    )


# ============================================================================
# Rechunk all (#652 Faz 1) — chunker rewrite migration
# ============================================================================


async def _rechunk_all_async(
    *,
    batch_size: int = 100,
    only_old_config: bool = True,
    dry_run: bool = False,
) -> dict:
    """Tüm cleaned article'ları yeni chunker config ile yeniden böl.

    #652 Faz 1: chunker default'lar 500/900/200/80 → 256/384/100/64 değişti.
    Mevcut 109K chunk eski config ile üretildi; yeni mimari için re-chunk
    gerek. Bu task batch dispatch yapar, embedding zinciri otomatik
    tetiklenir (chunk_article task → embed_article_chunks).

    Args:
        batch_size: Tek seferde dispatch edilecek article sayısı.
        only_old_config: True ise sadece avg_tokens > 256 olan article'lar
            (yeni config altında olanlar zaten doğru).
        dry_run: True ise sadece sayım, dispatch yok.

    Returns: {dispatched: int, total_eligible: int, skipped: int}
    """
    factory = _get_session_factory()
    from sqlalchemy import text as sa_text

    summary: dict[str, Any] = {
        "status": "unknown",
        "dispatched": 0,
        "total_eligible": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }

    async with factory() as db:
        # Eligible article'ları bul: cleaned + (only_old_config ise) eski
        # chunker ile üretilmiş (avg_tokens > 256, yeni hedef üstü)
        if only_old_config:
            count_sql = sa_text(
                """
                SELECT COUNT(DISTINCT a.id)
                FROM articles a
                WHERE a.status = 'cleaned'
                  AND a.clean_text IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM article_chunks c
                      WHERE c.article_id = a.id
                  )
                  AND (
                      SELECT AVG(c.token_count)
                      FROM article_chunks c
                      WHERE c.article_id = a.id
                  ) > 256
                """
            )
        else:
            count_sql = sa_text(
                """
                SELECT COUNT(*)
                FROM articles
                WHERE status = 'cleaned' AND clean_text IS NOT NULL
                """
            )

        total = (await db.execute(count_sql)).scalar() or 0
        summary["total_eligible"] = int(total)

        if dry_run or total == 0:
            summary["status"] = "dry_run" if dry_run else "no_eligible"
            return summary

        # Batch dispatch — chunk_article task chain'i embedding'i de tetikler
        # Her batch'te `batch_size` article, küçük article_id liste, async
        # background dispatch.
        dispatched = 0
        offset = 0
        while True:
            if only_old_config:
                rows_sql = sa_text(
                    """
                    SELECT a.id::text AS aid
                    FROM articles a
                    WHERE a.status = 'cleaned'
                      AND a.clean_text IS NOT NULL
                      AND EXISTS (
                          SELECT 1 FROM article_chunks c
                          WHERE c.article_id = a.id
                      )
                      AND (
                          SELECT AVG(c.token_count)
                          FROM article_chunks c
                          WHERE c.article_id = a.id
                      ) > 256
                    ORDER BY a.created_at ASC
                    LIMIT :limit OFFSET :offset
                    """
                )
            else:
                rows_sql = sa_text(
                    """
                    SELECT id::text AS aid
                    FROM articles
                    WHERE status = 'cleaned' AND clean_text IS NOT NULL
                    ORDER BY created_at ASC
                    LIMIT :limit OFFSET :offset
                    """
                )

            rows = (
                await db.execute(rows_sql, {"limit": batch_size, "offset": offset})
            ).mappings().all()

            if not rows:
                break

            for r in rows:
                try:
                    chunk_article.apply_async(args=[r["aid"]])
                    dispatched += 1
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        "rechunk dispatch failed aid=%s err=%s", r["aid"], exc
                    )
                    summary["skipped"] = int(summary["skipped"]) + 1

            offset += len(rows)
            logger.info(
                "rechunk_all progress: dispatched=%d / total=%d",
                dispatched, total,
            )

        summary["dispatched"] = dispatched
        summary["status"] = "dispatched"
        return summary


@celery_app.task(
    name="tasks.embedding.rechunk_all",
    bind=True,
)
def rechunk_all(  # type: ignore[no-untyped-def]
    self,
    batch_size: int = 100,
    only_old_config: bool = True,
    dry_run: bool = False,
) -> dict:
    """#652 Faz 1 — tüm cleaned article'ları yeni chunker config ile re-chunk.

    Admin panel /admin/rag/rechunk endpoint'inden tetiklenir veya manuel
    `celery -A app.workers.celery_app call tasks.embedding.rechunk_all`.

    NOT: Background long-running task. 109K article × ~3sn (chunk +
    embed dispatch) ≈ 1 saat. Embedding actual çalışması ayrı queue.
    """
    return _run_async(
        _rechunk_all_async(
            batch_size=batch_size,
            only_old_config=only_old_config,
            dry_run=dry_run,
        )
    )


# ============================================================================
# extract_chunk_keywords — #778 Faz 3 RagFlow adaptation
# ============================================================================


async def _extract_chunk_keywords_async(article_id: UUID) -> dict:
    """Article'ın tüm chunks'ları için keyword + question extract (LLM call).

    BM25 retrieval'da yüksek ağırlık sağlar (RagFlow pattern: question_kwd 6x,
    important_kwd 5x). NER'ın yakalamadığı discriminative kavramları çıkar.

    Cost: Admin /settings/llm-routing'te chunker keywords için provider
    seçilir (default DeepSeek, Gemma free alternatif).
    """
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "article_id": str(article_id),
        "status": "unknown",
    }

    from sqlalchemy import text as sa_text

    async with factory() as db:
        # Provider — #778 routing (default DeepSeek, admin'den Gemma seçilebilir)
        # NOT: 'ner' op_name'i kullanıyoruz — chunk keyword de aynı kategori
        from app.providers.registry import resolve_chat_provider

        try:
            provider = await resolve_chat_provider(db, op_name="ner", tier="free")
        except RuntimeError as exc:
            summary["status"] = "no_provider"
            summary["error"] = str(exc)
            return summary

        # Settings: feature flag + max keywords/questions per chunk
        from app.core.settings_store import settings_store
        enabled = await settings_store.get_bool(
            db, "chunker.keyword_extraction_enabled", True
        )
        if not enabled:
            summary["status"] = "skipped_disabled"
            return summary

        # Chunks fetch
        rows = (await db.execute(
            sa_text("""
                SELECT id::text, chunk_text, token_count
                FROM article_chunks
                WHERE article_id = :aid
                  AND (keywords IS NULL OR keywords_updated_at IS NULL)
                ORDER BY chunk_index
            """),
            {"aid": str(article_id)},
        )).mappings().all()

        if not rows:
            summary["status"] = "skipped_no_chunks_or_done"
            return summary

        # Load prompt — admin /prompts override aware
        from app.core.prompts_store import prompts_store
        from app.prompts.chunk_keywords import SYSTEM_PROMPT as DEFAULT_KEYWORDS_PROMPT
        system_prompt = await prompts_store.get(
            db, "chunk_keywords", DEFAULT_KEYWORDS_PROMPT
        )

        from app.providers.base import Message
        from app.core.cost_tracker import track_provider_call
        import json as _json

        success_count = 0
        failed_count = 0

        for r in rows:
            chunk_id = r["id"]
            chunk_text = r["chunk_text"][:3000]  # 3K char limit (LLM context)

            try:
                async with track_provider_call(
                    db=db,
                    provider=provider.name,
                    operation="chunk_keywords",
                ) as tracker:
                    result = await provider.generate_text(
                        messages=[
                            Message(role="system", content=system_prompt),
                            Message(role="user", content=chunk_text),
                        ],
                        max_tokens=250,
                        temperature=0.1,
                        json_mode=True,
                    )
                    tracker.record(
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cached_tokens=getattr(result, "cached_input_tokens", 0),
                        model=result.model,
                        cost_usd=float(result.cost_usd or 0),
                    )

                # Parse JSON — Gemma 4 CoT-style reasoning'i de handle eder
                # (response sonunda ```json ... ``` veya raw {...} olur).
                text = result.text.strip()
                json_text = text
                if "```" in text:
                    parts = text.split("```", 2)
                    if len(parts) >= 3:
                        inner = parts[1]
                        if inner.startswith(("json\n", "json\r")):
                            inner = inner[5:]
                        inner = inner.strip().rstrip("`").strip()
                        if inner.startswith(("{", "[")):
                            json_text = inner
                if not json_text.startswith(("{", "[")):
                    # Last balanced object scan (Gemma CoT fallback)
                    for opener, closer in (("{", "}"), ("[", "]")):
                        last_close = json_text.rfind(closer)
                        if last_close < 0:
                            continue
                        depth = 0
                        start = -1
                        for i in range(last_close, -1, -1):
                            if json_text[i] == closer:
                                depth += 1
                            elif json_text[i] == opener:
                                depth -= 1
                                if depth == 0:
                                    start = i
                                    break
                        if start >= 0:
                            json_text = json_text[start : last_close + 1]
                            break
                data = _json.loads(json_text)
                # Gemini/Gemma bazen [{...}] döner — tek dict'e indirge
                if isinstance(data, list) and data:
                    data = data[0]
                if not isinstance(data, dict):
                    data = {}
                keywords = data.get("keywords") or []
                questions = data.get("questions") or []

                # Validation: max 5 keywords, max 3 questions
                keywords = [
                    str(k).strip().lower()
                    for k in keywords[:5]
                    if isinstance(k, str) and 1 <= len(str(k).strip()) <= 80
                ]
                questions = [
                    str(q).strip()
                    for q in questions[:3]
                    if isinstance(q, str) and 5 <= len(str(q).strip()) <= 200
                ]

                # UPDATE chunk
                await db.execute(
                    sa_text("""
                        UPDATE article_chunks
                        SET keywords = :kw,
                            question_keywords = :qkw,
                            keywords_updated_at = NOW()
                        WHERE id = :cid
                    """),
                    {
                        "kw": keywords if keywords else None,
                        "qkw": questions if questions else None,
                        "cid": chunk_id,
                    },
                )
                await db.commit()
                success_count += 1
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "chunk_keywords extract failed chunk=%s err=%s",
                    chunk_id, exc,
                )
                failed_count += 1
                continue

        summary["status"] = "done"
        summary["chunks_processed"] = success_count
        summary["chunks_failed"] = failed_count
    return summary


@celery_app.task(
    name="tasks.embedding.extract_chunk_keywords",
    bind=True,
    max_retries=1,
)
def extract_chunk_keywords(self, article_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Wrapper for celery dispatch."""
    return _run_async(_extract_chunk_keywords_async(UUID(article_id)))
