"""Event clustering Celery tasks (#20).

Tasks:
    cluster_article(article_id)
        - Article'ın chunk_index=0 embedding'ini al
        - Aktif cluster'larda ara (cosine + title trigram)
        - Eşleşme var → event_articles INSERT, counters update
        - Yok → yeni event_cluster oluştur

    refresh_clusters()
        - Beat task: tüm aktif cluster'ların status + importance + freshness'ını güncelle
        - architecture.md §3.3 (event-clustering, saatlik)

docs/engineering/architecture.md §3 (event_queue)
docs/engineering/data-model.md §4.2, §4.3
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text as sa_text

from app.models.article import Article
from app.modules.clusters.clustering import (
    add_article_to_cluster,
    create_cluster,
    find_matching_cluster,
    refresh_cluster_statuses,
)
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _cluster_article_async(article_id: UUID) -> dict:
    """Article'ı uygun cluster'a ekle veya yeni cluster oluştur."""
    factory = _get_session_factory()
    summary: dict = {"article_id": str(article_id), "action": "unknown"}

    async with factory() as db:
        article = await db.get(Article, article_id)
        if article is None:
            summary["action"] = "skipped"
            summary["reason"] = "not_found"
            return summary
        if article.status != "cleaned":
            summary["action"] = "skipped"
            summary["reason"] = f"status={article.status}"
            return summary

        # chunk_index=0 embedding'ini al (title + lead context'i kapsar)
        chunk_row = (
            await db.execute(
                sa_text(
                    """
                    SELECT id, embedding::text AS emb_text
                    FROM article_chunks
                    WHERE article_id = :aid AND chunk_index = 0
                      AND embedding IS NOT NULL
                    LIMIT 1
                    """
                ),
                {"aid": str(article_id)},
            )
        ).first()

        if chunk_row is None:
            summary["action"] = "skipped"
            summary["reason"] = "no_embedding"
            return summary

        # Parse embedding text "[0.1,0.2,...]"
        emb_text = chunk_row.emb_text
        try:
            inner = emb_text.strip("[] \n")
            embedding = [float(x) for x in inner.split(",") if x.strip()]
            if not embedding:
                raise ValueError("empty")
        except (ValueError, AttributeError) as exc:
            summary["action"] = "skipped"
            summary["reason"] = f"embedding_parse_error: {exc}"
            return summary

        # 1) Eşleşen cluster ara
        match = await find_matching_cluster(
            db,
            article_embedding=embedding,
            article_title=article.title,
        )

        if match:
            cluster_id, sim = match
            inserted = await add_article_to_cluster(
                db,
                event_id=cluster_id,
                article_id=article.id,
                source_id=article.source_id,
                published_at=article.published_at,
                relationship_score=sim,
            )
            await db.commit()
            summary["action"] = "matched" if inserted else "duplicate"
            summary["event_id"] = str(cluster_id)
            summary["similarity"] = round(sim, 4)

            # #175 — Cluster büyüdükçe agenda refresh dispatch (UPSERT yapacak)
            # Yalnız "inserted" (gerçekten yeni article) durumunda — duplicate'lerde değil.
            if inserted:
                try:
                    # A1: string-bound send_task — clusters Python seviyesinde
                    # agenda task'ına bağlı değil; agenda generations'a taşınınca
                    # boundary contract ihlali doğurmaz.
                    celery_app.send_task(
                        "tasks.agenda.generate_agenda_card",
                        args=[str(cluster_id)],
                    )
                    summary["agenda_dispatched"] = True
                except Exception as exc:  # pragma: no cover
                    logger.exception(
                        "dispatch agenda refresh failed eid=%s err=%s",
                        cluster_id,
                        exc,
                    )
            return summary

        # 2) Yeni cluster oluştur
        cluster_id = await create_cluster(
            db,
            canonical_title=article.title,
            embedding=embedding,
            article_id=article.id,
            source_id=article.source_id,
            published_at=article.published_at,
        )
        await db.commit()
        summary["action"] = "created"
        summary["event_id"] = str(cluster_id)

        # Agenda card chain (yeni cluster için)
        # A1: string-bound send_task (see comment at site #1 above).
        try:
            celery_app.send_task(
                "tasks.agenda.generate_agenda_card",
                args=[str(cluster_id)],
            )
            summary["agenda_dispatched"] = True
        except Exception as exc:  # pragma: no cover
            logger.exception("dispatch agenda failed eid=%s err=%s", cluster_id, exc)

        return summary


@celery_app.task(name="tasks.clustering.cluster_article", bind=True, max_retries=2)
def cluster_article(self, article_id: str) -> dict:  # type: ignore[no-untyped-def]
    return _run_async(_cluster_article_async(UUID(article_id)))


async def _refresh_clusters_async() -> dict:
    factory = _get_session_factory()
    async with factory() as db:
        counts = await refresh_cluster_statuses(db)
        await db.commit()
        return counts


@celery_app.task(name="tasks.clustering.refresh_clusters", bind=True)
def refresh_clusters(self) -> dict:  # type: ignore[no-untyped-def]
    """Beat task: tüm cluster'ları status/importance/freshness refresh."""
    return _run_async(_refresh_clusters_async())
