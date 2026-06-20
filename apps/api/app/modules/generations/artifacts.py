"""Küme-bağlı artefakt oluşturma servisi — Faz 3.

Generation çıktısını küme-bağlı paylaşılabilir artefakt + ilk revizyon (seq=1,
intent='initial') olarak yazar. Stream-end best-effort hook (Faz 3 wire) bunu
çağırır; `cluster_id` NOT NULL → caller önce `cluster_resolver` ile küme çözer.

Revizyon endpoint'leri (quick-action / serbest-metin / revizyon-vs-yeni) = Faz 3b.
"""

from __future__ import annotations

import uuid
from typing import Any

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
) -> uuid.UUID:
    """Artefakt + ilk revizyon yaz; head_revision işaretle. commit ETMEZ (caller).

    Dönüş: artifact_id. origin_message_id legacy mesaj köprüsü (mesaj silinse de
    artefakt kalır — SET NULL). İçerik immutable snapshot (revizyon zincirinin kökü).
    """
    art_id = uuid.uuid4()
    rev_id = uuid.uuid4()
    db.add(
        Artifact(
            id=art_id,
            user_id=user_id,
            cluster_id=cluster_id,
            artifact_type=artifact_type,
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
