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
import re
import struct
from datetime import UTC, datetime, timedelta
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


# =============================================================================
# F2b (#1014) — L1 zaman-pencereli görünmez bağlam (YALNIZ condense'i besler;
# asıl cevap prompt'una GİRMEZ). Flag-gated; default kapalı → davranış
# byte-eş (#854). 5-katman kirlilik-koruması (S5):
#   1+3  select_windowed_context: en-dar-pencere-önce cascade; ilgili
#        aday yoksa BOŞ → condense no-op → ham sorgu (standalone/taze
#        kirlenmez). 2: relatedness kapısı (cosine ≥ eşik, mevcut
#        cosine_similarity reuse). 4: l1_accept_rewrite (rewrite-drift
#        reddi — ham sorgudan kopuksa reddet). 5: saf birim testleri.
# =============================================================================


def format_context_block(rows: list[Message]) -> str:
    """Mesajları condense `history` string'ine çevir — `_recent_conversation
    _context` ile BİREBİR aynı format (condense sözleşmesi değişmez;
    legacy ve windowed yol aynı formatter'ı kullanır → drift yok).

    rows: oldest-first sıralı beklenir (caller `.reverse()` yapar).
    """
    lines: list[str] = []
    for m in rows:
        label = "Kullanıcı" if m.role == "user" else "Asistan"
        snippet = (m.content or "")[:500]
        lines.append(f"- {label}: {snippet}")
        if m.role == "assistant" and m.sources_used:
            srcs = []
            for s in (m.sources_used or [])[:8]:
                if not isinstance(s, dict):
                    continue
                title = (s.get("title") or "")[:120]
                sname = s.get("source_name") or ""
                if title or sname:
                    srcs.append(f"{sname} — {title}".strip(" —"))
            if srcs:
                lines.append(
                    "  (Bu cevabın kaynakları: " + "; ".join(srcs) + ")"
                )
    return "\n".join(lines)


async def select_windowed_context(
    db: AsyncSession,
    *,
    conv_id: UUID,
    user_id: UUID,
    exclude_msg_id: UUID,
    new_query_embedding: list[float] | None,
    user_scope: bool,
    windows_hours: tuple[int, ...] = (6, 24, 72),
    threshold: float = DEFAULT_RELATEDNESS_THRESHOLD,
    max_msgs: int = 8,
) -> list[Message]:
    """En-dar-pencere-önce cascade + relatedness kapısı.

    Gate 1+3: pencereler artan (6s→24s→3g); ilk, içinde ilgili (cosine
    ≥ threshold) bir user mesajı OLAN pencere kazanır. Hiçbiri yoksa
    BOŞ liste → caller condense'i boş history ile çağırır → condense
    None döner → ham sorgu (taze; standalone kirlenmez).
    Gate 2: relatedness mevcut cosine_similarity + deserialize reuse.
    Skop: user_scope=False → conversation içi; True → user+zaman
    (cross-conversation, kuzey yıldızı). Çıktı oldest-first.
    """
    if not new_query_embedding:
        return []
    now = datetime.now(UTC)
    for w in windows_hours:  # artan = en dar pencere önce
        cutoff = now - timedelta(hours=w)
        q = select(Message).where(
            Message.id != exclude_msg_id,
            Message.created_at >= cutoff,
        )
        if user_scope:
            q = q.join(
                Conversation, Conversation.id == Message.conversation_id
            ).where(Conversation.user_id == user_id)
        else:
            q = q.where(Message.conversation_id == conv_id)
        q = q.order_by(Message.created_at.desc()).limit(max_msgs)
        rows = list((await db.execute(q)).scalars().all())
        if not rows:
            continue
        related = False
        for m in rows:
            if m.role != "user" or m.query_embedding is None:
                continue
            emb = deserialize_embedding(m.query_embedding)
            if emb is None:
                continue
            if cosine_similarity(new_query_embedding, emb) >= threshold:
                related = True
                break
        if related:
            rows.reverse()  # oldest-first (format parity)
            return rows
    return []


_L1_WORD_RE = re.compile(r"[\wçğıöşüâîûÇĞİÖŞÜ]+", re.UNICODE)


def l1_accept_rewrite(raw: str, rewritten: str) -> bool:
    """Gate 4 — rewrite-drift reddi (saf; embedding çağrısı YOK).

    condense çıktısı ham sorguyla HİÇ ortak içerik-token'ı paylaşmıyorsa
    (≥3 harf) = konu tamamen kaymış → REDDET (caller ham sorguyu
    kullanır). Sinyal yetersizse (kısa) muhafazakâr: KABUL (mevcut
    davranışı bozma). Yalnız L1 açıkken uygulanır.
    """
    rt = {t.lower() for t in _L1_WORD_RE.findall(raw or "") if len(t) > 2}
    wt = {t.lower() for t in _L1_WORD_RE.findall(rewritten or "") if len(t) > 2}
    if not rt or not wt:
        return True
    return len(rt & wt) > 0


__all__ = [
    "DEFAULT_RECENT_MESSAGES",
    "DEFAULT_RELATEDNESS_THRESHOLD",
    "EMBED_BYTES",
    "EMBED_DIM",
    "build_context_messages",
    "cosine_similarity",
    "format_context_block",
    "l1_accept_rewrite",
    "select_windowed_context",
    "deserialize_embedding",
    "detect_followup_relatedness",
    "get_last_assistant_message",
    "get_last_user_message",
    "get_recent_messages",
    "serialize_embedding",
]
