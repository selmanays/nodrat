"""Araştırma kümeleme atayıcı — GECE batch (#1015 Pivot Faz 3).

Kullanıcı sorgularını (messages.role='user') GLOBAL kanonik araştırma
kümelerine (research_clusters) atar. "Tek sağlayıcı, çok dinleyici":
küme paylaşımlı, görünürlük message_clusters ⋈ messages ⋈ conversations
WHERE user_id=? ile türetilir (cross-user sızma yok).

AYRIM: `tasks.clustering.*` = haber-OLAY kümeleme (event_articles). BU
= araştırma kümesi (#1015). Karıştırma.

Hibrit atama (rev.12 §4/§7):
  1. Nadir-entity çapa: mesajdan n-gram → `entities` (haber korpusu)
     eşleşmesi → en nadir (df) entity → kanonik cluster_key → UPSERT
     global küme + üyelik. (S11: çapa YALNIZ korpus entity'si →
     özel-sorgu adı global küme MİNTLEMEZ.)
  2. Entity'siz → embedding-centroid fallback: query_embedding,
     yalnız MEVCUT aktif küme'ye bağlanır (yeni global küme yaratmaz);
     eşik altı → kümelenmemiş bırak ("bugünün sorguları"; UI seansı).
  3. S12: boş aktif küme → soft-deprecate (deprecated_at; user-tetikli
     değil).

Flag-gated: settings `research.clustering.enabled` (default FALSE →
no-op; #854 — DB override yoksa davranış byte-eş, deploy güvenli).
Idempotent: zaten message_clusters'ı olan mesaj atlanır + UNIQUE
(message_id, cluster_id). Cevap-üretim akışına DOKUNMAZ (additive).

Beat: tasks.research_clustering.assign — gece (celery_app.py).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.conversation_context import (
    cosine_similarity,
    deserialize_embedding,
)
from app.core.research_clustering import (
    canonical_cluster_key,
    query_grams,
    select_anchor,
)
from app.core.settings_store import settings_store
from app.models.conversation import Conversation, Message
from app.models.research_cluster import MessageCluster, ResearchCluster
from app.workers.celery_app import celery_app
from app.workers.tasks.sources import _get_session_factory, _run_async

logger = logging.getLogger(__name__)

_ENTITY_DF_SQL = sa.text(
    """
    SELECT entity_normalized, entity_type,
           COUNT(DISTINCT article_id) AS df
    FROM entities
    WHERE lower(entity_normalized) IN :grams
    GROUP BY entity_normalized, entity_type
    """
).bindparams(sa.bindparam("grams", expanding=True))


@celery_app.task(
    name="tasks.research_clustering.assign",
    queue="embedding_queue",
)
def run_cluster_assigner(batch: int | None = None) -> dict[str, Any]:
    """Gece araştırma-kümesi atama (flag-gated; default no-op)."""
    return _run_async(_cluster_assigner_async(batch))


async def _cluster_assigner_async(batch_override: int | None) -> dict[str, Any]:
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "status": "ok",
        "scanned": 0,
        "assigned_entity": 0,
        "assigned_fallback": 0,
        "unclustered": 0,
        "clusters_created": 0,
        "deprecated_empty": 0,
        "errors": 0,
    }

    async with factory() as db:
        enabled = await settings_store.get_bool(
            db, "research.clustering.enabled", False
        )
        if not enabled:
            logger.info("cluster_assigner: disabled, skipping")
            return {"status": "disabled", "scanned": 0}

        daily_max = (
            batch_override
            if batch_override is not None
            else await settings_store.get_int(
                db, "research.clustering.daily_max", 2000
            )
        )
        fb_min_cos = await settings_store.get_float(
            db, "research.clustering.fallback_min_cosine", 0.75
        )

        # Idempotent: message_clusters'ı OLMAYAN user mesajları (eski→yeni)
        rows_q = (
            select(Message, Conversation)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.role == "user",
                ~Message.id.in_(select(MessageCluster.message_id)),
            )
            .order_by(Message.created_at.asc())
            .limit(daily_max)
        )
        rows = list((await db.execute(rows_q)).all())
        summary["scanned"] = len(rows)

        for msg, conv in rows:
            try:
                assigned = await _assign_one(
                    db, msg, conv, fb_min_cos, summary
                )
                if assigned is None:
                    summary["unclustered"] += 1
            except Exception as exc:  # pragma: no cover — best-effort
                summary["errors"] += 1
                logger.warning(
                    "cluster_assigner: msg=%s atlandı: %s", msg.id, exc
                )
                await db.rollback()

        # S12 — boş aktif küme → soft-deprecate (user-tetikli DEĞİL)
        try:
            empty_q = (
                select(ResearchCluster.id)
                .where(
                    ResearchCluster.deprecated_at.is_(None),
                    ~ResearchCluster.id.in_(
                        select(MessageCluster.cluster_id)
                    ),
                )
            )
            empty_ids = [r[0] for r in (await db.execute(empty_q)).all()]
            if empty_ids:
                await db.execute(
                    sa.update(ResearchCluster)
                    .where(ResearchCluster.id.in_(empty_ids))
                    .values(deprecated_at=datetime.now(UTC))
                )
                await db.commit()
                summary["deprecated_empty"] = len(empty_ids)
        except Exception as exc:  # pragma: no cover
            await db.rollback()
            logger.warning("cluster_assigner: empty-deprecate atlandı: %s", exc)

    return summary


async def _assign_one(
    db, msg: Message, conv: Conversation, fb_min_cos: float,
    summary: dict[str, Any],
) -> str | None:
    """Tek mesajı ata. Dönüş: 'entity' | 'fallback' | None (unclustered)."""
    # 1) Nadir-entity çapa — yalnız haber-korpusu (`entities`) eşleşmesi
    grams = query_grams(msg.content or "")
    anchor = None
    if grams:
        rows = (
            await db.execute(_ENTITY_DF_SQL, {"grams": grams})
        ).all()
        cands = [(r[0], r[1], int(r[2])) for r in rows]
        anchor = select_anchor(cands)

    if anchor is not None:
        ent_norm, ent_type, _df = anchor
        key = canonical_cluster_key(ent_type, ent_norm)
        cluster = (
            await db.execute(
                select(ResearchCluster).where(
                    ResearchCluster.cluster_key == key,
                    ResearchCluster.deprecated_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if cluster is None:
            cluster = ResearchCluster(
                cluster_key=key,
                cluster_type=ent_type,
                canonical_name=ent_norm,
                centroid_embedding=msg.query_embedding,  # v1 temsil
            )
            db.add(cluster)
            await db.flush()
            summary["clusters_created"] += 1
        else:
            cluster.updated_at = datetime.now(UTC)
        await _add_membership(db, msg, conv, cluster.id, "entity")
        summary["assigned_entity"] += 1
        return "entity"

    # 2) Embedding-centroid fallback — YALNIZ mevcut küme'ye bağla
    #    (S11: yeni global küme MİNTLEMEZ; özel-sorgu adı sızmaz)
    emb = deserialize_embedding(msg.query_embedding)
    if emb is None:
        return None
    actives = (
        await db.execute(
            select(ResearchCluster).where(
                ResearchCluster.deprecated_at.is_(None),
                ResearchCluster.centroid_embedding.is_not(None),
            )
        )
    ).scalars().all()
    best_id, best_cos = None, -1.0
    for c in actives:
        c_emb = deserialize_embedding(c.centroid_embedding)
        if c_emb is None:
            continue
        cs = cosine_similarity(emb, c_emb)
        if cs > best_cos:
            best_cos, best_id = cs, c.id
    if best_id is not None and best_cos >= fb_min_cos:
        await _add_membership(db, msg, conv, best_id, "embedding_fallback")
        summary["assigned_fallback"] += 1
        return "fallback"
    return None  # kümelenmemiş ("bugünün sorguları" — UI seansı)


async def _add_membership(
    db, msg: Message, conv: Conversation, cluster_id, via: str
) -> None:
    """Üyelik satırı (idempotent — UNIQUE(message_id, cluster_id))."""
    db.add(
        MessageCluster(
            message_id=msg.id,
            cluster_id=cluster_id,
            user_id=conv.user_id,
            assigned_via=via,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()  # zaten atanmış — idempotent
