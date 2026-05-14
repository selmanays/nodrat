"""Conversation context helpers — relatedness + token budget (#793 S2).

Embedding tabanlı follow-up tespiti:
- Yeni user query embed et (bge-m3)
- Conversation'daki son user message'ın embedding'i ile cosine similarity
- Threshold 0.65 üstü → RELATED (önceki kaynakları reuse aday)
- Altı → NEW TOPIC (fresh retrieval)

Token budget:
- Sustainable conversation history için son N mesaj raw + öncesi summarized
- DeepSeek 64K context içinde messages için ~8K budget
"""

from __future__ import annotations

import logging
import math
import struct
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message

logger = logging.getLogger(__name__)


# bge-m3 1024 dim × float32 = 4096 byte
EMBED_DIM = 1024
EMBED_BYTES = EMBED_DIM * 4

# Follow-up relatedness threshold (cosine similarity).
# 0.65: deneyim — Türkçe niş entity'lerde "Trump 6 Mayıs" vs "Trump 7 Mayıs"
# benzeri related, "Trump" vs "Karşıyaka" unrelated ayrımı için iyi denge.
# Settings ile runtime override edilebilir: chat.followup_relatedness_threshold
DEFAULT_RELATEDNESS_THRESHOLD = 0.65

# Conversation context — son N mesaj raw, öncesi summary.
# 3 mesaj çifti = ~6K token (typical Türkçe news query + 3-paragraf cevap).
# DEEPSEEK 64K içinde rahat.
DEFAULT_RECENT_MESSAGES = 3


def serialize_embedding(vector: list[float]) -> bytes:
    """list[float] → bytes (float32 array). 1024-dim için 4096 byte."""
    if len(vector) != EMBED_DIM:
        raise ValueError(f"Embedding dim must be {EMBED_DIM}, got {len(vector)}")
    return struct.pack(f"{EMBED_DIM}f", *vector)


def deserialize_embedding(raw: bytes | None) -> list[float] | None:
    """bytes → list[float]. None veya yanlış boyut → None."""
    if raw is None or len(raw) != EMBED_BYTES:
        return None
    try:
        return list(struct.unpack(f"{EMBED_DIM}f", raw))
    except struct.error:
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity — sıfır vektör koruması."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def get_recent_messages(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    limit: int = DEFAULT_RECENT_MESSAGES * 2,  # N çift = 2N mesaj
) -> list[Message]:
    """Conversation'ın son N mesajını çek (created_at ASC sıralı dön).

    User + assistant pair'lar zaman sıralı — context için doğru sıra.
    """
    rows = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(reversed(rows))


async def get_last_user_message(
    db: AsyncSession,
    conversation_id: UUID,
) -> Message | None:
    """Conversation'ın son user mesajı (en son sorulan soru)."""
    return (
        await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_last_assistant_message(
    db: AsyncSession,
    conversation_id: UUID,
) -> Message | None:
    """Conversation'ın son assistant mesajı (last_user için kaynaklar)."""
    return (
        await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "assistant",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def detect_followup_relatedness(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    new_query_embedding: list[float],
    threshold: float = DEFAULT_RELATEDNESS_THRESHOLD,
) -> tuple[bool, float, Message | None]:
    """Yeni query önceki user query ile related mi tespit et.

    Returns:
        (is_related, similarity_score, prev_user_message_or_None)
    """
    prev_user = await get_last_user_message(db, conversation_id)
    if prev_user is None or prev_user.query_embedding is None:
        return False, 0.0, None

    prev_embed = deserialize_embedding(prev_user.query_embedding)
    if prev_embed is None:
        return False, 0.0, prev_user

    sim = cosine_similarity(prev_embed, new_query_embedding)
    is_related = sim >= threshold
    return is_related, sim, prev_user


def build_context_messages(
    messages: list[Message],
    conversation_summary: str | None,
) -> list[dict[str, str]]:
    """Mesajları DeepSeek/OpenAI-format chat messages'a çevir.

    Format: [{role, content}, ...] — son N mesaj raw.
    summary varsa system message olarak başa eklenir.

    NOT: Yeni user message buraya dahil DEĞİL — caller ekler.
    """
    result: list[dict[str, str]] = []
    if conversation_summary:
        result.append({
            "role": "system",
            "content": f"Önceki konuşma özeti: {conversation_summary}",
        })
    for m in messages:
        result.append({
            "role": m.role,
            "content": m.content,
        })
    return result


__all__ = [
    "DEFAULT_RECENT_MESSAGES",
    "DEFAULT_RELATEDNESS_THRESHOLD",
    "EMBED_BYTES",
    "EMBED_DIM",
    "build_context_messages",
    "cosine_similarity",
    "deserialize_embedding",
    "detect_followup_relatedness",
    "get_last_assistant_message",
    "get_last_user_message",
    "get_recent_messages",
    "serialize_embedding",
]
