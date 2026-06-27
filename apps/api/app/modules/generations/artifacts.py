"""Küme-bağlı artefakt oluşturma servisi — Faz 3.

Generation çıktısını küme-bağlı paylaşılabilir artefakt + ilk revizyon (seq=1,
intent='initial') olarak yazar. Stream-end best-effort hook (Faz 3 wire) bunu
çağırır; `cluster_id` NOT NULL → caller önce `cluster_resolver` ile küme çözer.

Revizyon endpoint'leri (quick-action / serbest-metin / revizyon-vs-yeni) = Faz 3b.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.generations.models import Artifact, ArtifactRevision


async def create_artifact_with_revision(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    cluster_id: uuid.UUID,
    content: str,
    artifact_type: str = "post",
    sources_used: list[Any] | None = None,
    effective_query: str | None = None,
    origin_message_id: uuid.UUID | None = None,
    origin: str = "interactive",
) -> uuid.UUID:
    """Artefakt + ilk revizyon yaz; head_revision işaretle. commit ETMEZ (caller).

    Dönüş: artifact_id. origin_message_id legacy mesaj köprüsü (mesaj silinse de
    artefakt kalır — SET NULL). İçerik immutable snapshot (revizyon zincirinin kökü).
    origin: 'interactive' (default; kullanıcı sorgusu) | 'automation' (#1785 oto-koşum).
    """
    art_id = uuid.uuid4()
    rev_id = uuid.uuid4()
    db.add(
        Artifact(
            id=art_id,
            user_id=user_id,
            cluster_id=cluster_id,
            artifact_type=artifact_type,
            origin=origin,
            origin_message_id=origin_message_id,
            head_revision_id=rev_id,
        )
    )
    await db.flush()
    db.add(
        ArtifactRevision(
            id=rev_id,
            artifact_id=art_id,
            revision_seq=1,
            revision_intent="initial",
            content=content,
            sources_used=sources_used,
            effective_query=effective_query,
        )
    )
    await db.flush()
    return art_id


# Revizyon niyetleri (Faz 3b). LLM quick-action'lar (3b-2) bu servisi içerik
# üreterek çağırır; serbest-metin/canvas direkt-edit içeriği doğrudan geçirir.
REVISION_INTENTS = frozenset(
    {
        "quick_shorter",
        "quick_rewrite",
        "quick_longer",
        "multi_share",
        "freetext",
        "edit",
        "system",
    }
)


async def add_revision(
    db: AsyncSession,
    *,
    artifact_id: uuid.UUID,
    content: str,
    revision_intent: str,
    sources_used: list[Any] | None = None,
) -> int:
    """Artefakta yeni revizyon ekle: seq = mevcut max + 1, parent = mevcut head.

    `head_revision_id` yeni revizyona güncellenir (canvas "en güncel" işaretçisi).
    commit ETMEZ (caller). Dönüş: yeni revision_seq. Revizyonu olmayan artefakt
    (initial olmadan) → ValueError. İçerik immutable (zincir kökten dallanır).
    """
    # FOR UPDATE — eşzamanlı add_revision'ları aynı artefakt için serialize eder
    # (revision_seq yarışı → UNIQUE çakışması yerine sıralı seq). Lock caller
    # commit'ine kadar tutulur.
    head = (
        await db.execute(
            select(ArtifactRevision)
            .where(ArtifactRevision.artifact_id == artifact_id)
            .order_by(ArtifactRevision.revision_seq.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if head is None:
        raise ValueError("artifact has no revisions")
    new_seq = head.revision_seq + 1
    rev_id = uuid.uuid4()
    db.add(
        ArtifactRevision(
            id=rev_id,
            artifact_id=artifact_id,
            revision_seq=new_seq,
            parent_revision_id=head.id,
            content=content,
            revision_intent=revision_intent,
            sources_used=sources_used,
        )
    )
    await db.flush()
    await db.execute(
        update(Artifact).where(Artifact.id == artifact_id).values(head_revision_id=rev_id)
    )
    return new_seq
