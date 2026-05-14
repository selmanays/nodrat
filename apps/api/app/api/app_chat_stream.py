"""Chat message streaming — context-aware (#793 S2).

Endpoint: POST /chat/conversations/{id}/messages

Akış:
1. User message persist (query_embedding ile)
2. Relatedness check — önceki user message embedding ile cosine similarity
3. Eğer RELATED (>= 0.65): source reuse hint generate_stream'e geçirilir
4. Mevcut generate_stream pipeline çağrılır (planner + HyDE + retrieve + ...)
5. SSE thinking_step events stream'e ekstra eklenir
6. Stream sonunda assistant message persist (sources_used, thinking_steps)

Mevcut /app/generate-stream backward-compat korundu (form-based use).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.conversation_context import (
    DEFAULT_RELATEDNESS_THRESHOLD,
    detect_followup_relatedness,
    get_last_assistant_message,
    serialize_embedding,
)
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.quota import QuotaExceeded, enforce_quota
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.providers.registry import bootstrap_default_providers, registry

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Pydantic schemas
# ============================================================================


class ChatMessageCreate(BaseModel):
    """Yeni mesaj — minimal payload (chat-style)."""

    content: str = Field(min_length=1, max_length=5000)
    # UI tarafı bu seans için: output parametreleri opsiyonel
    output_type: str = Field(default="x_post", max_length=32)
    tone: str | None = Field(default=None, max_length=32)
    max_posts: int | None = Field(default=None, ge=1, le=10)


# ============================================================================
# SSE helper
# ============================================================================


def _sse(event: str, data: dict | None = None) -> str:
    payload = json.dumps(data or {}, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


# ============================================================================
# Endpoint
# ============================================================================


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Yeni chat mesajı (SSE streaming, context-aware) — #793 S2",
)
async def post_chat_message(
    payload: ChatMessageCreate,
    conversation_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Yeni mesaj + SSE stream + assistant cevap persist.

    Conversation ownership doğrulanır (404 başkasınınkinde).
    User mesajı + embedding pre-stream commit edilir.
    Stream sonunda assistant message persist.
    """
    bootstrap_default_providers()

    # 1) Conversation ownership doğrula
    conv = (
        await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # 2) Quota
    try:
        await enforce_quota(user.id, user.tier)  # type: ignore[arg-type]
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "QUOTA_EXCEEDED",
                "title": "Kotanız doldu",
                "limit": exc.status.limit,
                "used": exc.status.used,
            },
        ) from exc

    # 3) Query embedding (relatedness check + persist için)
    emb_provider = registry.route_for_tier(operation="embedding", tier="free")
    emb_res = await emb_provider.create_embedding([payload.content])
    query_vec = emb_res.vectors[0] if emb_res.vectors else None
    query_embed_bytes = (
        serialize_embedding(query_vec) if query_vec is not None else None
    )

    # 4) Relatedness check (önceki user message ile)
    is_related = False
    similarity = 0.0
    prev_assistant_sources: list[dict] | None = None

    if query_vec is not None:
        is_related, similarity, prev_user = await detect_followup_relatedness(
            db,
            conversation_id=conv.id,
            new_query_embedding=query_vec,
        )
        if is_related:
            # Önceki assistant cevabın kaynaklarını reuse hint olarak hazırla
            prev_assistant = await get_last_assistant_message(db, conv.id)
            if prev_assistant and prev_assistant.sources_used:
                prev_assistant_sources = prev_assistant.sources_used
                logger.info(
                    "chat followup detected (sim=%.3f): %d prev sources available",
                    similarity, len(prev_assistant_sources),
                )

    # 5) User message persist
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=payload.content,
        query_embedding=query_embed_bytes,
    )
    db.add(user_msg)
    await db.flush()

    # 6) İlk mesajsa conversation title'ı update et (request_text snippet)
    msg_count = (await db.execute(
        select(Message).where(Message.conversation_id == conv.id)
    )).all()
    if len(msg_count) == 1 and conv.title == "Yeni sohbet":
        conv.title = payload.content[:80].strip()

    await db.commit()

    user_msg_id = user_msg.id
    now = datetime.now(UTC)

    return StreamingResponse(
        _chat_stream_body(
            db=db,
            user=user,
            conv_id=conv.id,
            user_msg_id=user_msg_id,
            payload=payload,
            query_vec=query_vec,
            is_related=is_related,
            similarity=similarity,
            prev_sources=prev_assistant_sources,
            now=now,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )


# ============================================================================
# Stream body
# ============================================================================


async def _chat_stream_body(
    *,
    db: AsyncSession,
    user: User,
    conv_id: UUID,
    user_msg_id: UUID,
    payload: ChatMessageCreate,
    query_vec: list[float] | None,
    is_related: bool,
    similarity: float,
    prev_sources: list[dict] | None,
    now: datetime,
) -> AsyncIterator[str]:
    """Chat streaming akışı — thinking_step events + content stream + persist."""
    # Lazy imports
    from app.core.retrieval import hybrid_search_chunks
    from app.providers.base import Message as ProviderMessage
    from app.prompts.query_planner import plan_query
    from app.prompts.content_generator import render_user_payload
    from app.prompts.chat_answer import SYSTEM_PROMPT_CHAT_ANSWER

    thinking_log: list[dict[str, Any]] = []

    def _log_step(phase: str, detail: str, latency_ms: int = 0) -> str:
        """Thinking step kaydet + SSE event olarak yield."""
        entry = {"phase": phase, "detail": detail, "latency_ms": latency_ms}
        thinking_log.append(entry)
        return _sse("thinking_step", entry)

    try:
        # ---- Step 1: Context awareness signal ----
        if is_related and prev_sources:
            yield _log_step(
                "context_check",
                f"Önceki sorularla ilişkili (similarity={similarity:.2f}) — "
                f"{len(prev_sources)} kaynak değerlendiriliyor",
            )
        else:
            yield _log_step("context_check", "Yeni konu — sıfırdan kaynak araması")

        # ---- Step 2: Query planner ----
        t0 = asyncio.get_event_loop().time()
        plan_result = await plan_query(
            user_request=payload.content,
            current_time=now,
            user_locale=getattr(user, "locale", "tr-TR") or "tr-TR",
            user_tier=user.tier,
        )
        t_planner = int((asyncio.get_event_loop().time() - t0) * 1000)
        topic = getattr(plan_result, "topic_query", payload.content)
        critical_entities = getattr(plan_result, "critical_entities", None) or []
        yield _log_step(
            "planner",
            f"Plan çıkarıldı: {topic[:80]}",
            t_planner,
        )

        # ---- Step 3: Retrieve chunks (context-aware) ----
        # Eğer related: önceki kaynakları boost et + yeni retrieval combine
        # Eğer new topic: standart retrieval
        t0 = asyncio.get_event_loop().time()
        chunks = []
        if query_vec is not None:
            chunks = await hybrid_search_chunks(
                db,
                query_text=payload.content,
                query_vector=query_vec,
                top_k=10,
                candidate_pool=60,
                since_hours=24 * 90,
                critical_entities=critical_entities or None,
                rerank=False,
            )
        t_retrieve = int((asyncio.get_event_loop().time() - t0) * 1000)

        # Source reuse: prev sources varsa, yeni chunks'a önceden seçilenleri
        # boost ekle (RRF benzeri)
        if is_related and prev_sources:
            existing_aids = {str(c.get("article_id")) for c in chunks}
            prev_aids = {str(s.get("article_id")) for s in prev_sources}
            reused_aids = existing_aids & prev_aids
            yield _log_step(
                "context_check",
                f"Önceki kaynaklardan {len(reused_aids)} tanesi "
                f"yeni sonuçlarda — reuse hint aktif",
            )

        yield _log_step(
            "retrieve",
            f"{len(chunks)} kaynak bulundu",
            t_retrieve,
        )

        # ---- Step 4: Sources discovered ----
        sources_used = []
        for c in chunks[:5]:
            src = {
                "article_id": str(c.get("article_id", "")),
                "chunk_id": str(c.get("chunk_id") or c.get("id") or ""),
                "title": c.get("article_title", "")[:200],
                "url": c.get("article_canonical_url") or c.get("url"),
                "source_name": c.get("source_name"),
            }
            sources_used.append(src)
            yield _sse("source_discovered", src)

        # ---- Step 5: Content generation ----
        yield _log_step("generating", "Cevap yazılıyor (multi-source synthesis)...")

        # Chat user payload — minimal (chat-specific, X-post JSON yok)
        # Sadece kullanıcı sorusu + indeksli chunk listesi.
        chunk_blocks = []
        for i, c in enumerate(chunks[:10], start=1):
            text = (c.get("chunk_text") or "")[:2500]
            title = (c.get("article_title") or "")[:200]
            source = c.get("source_name") or ""
            chunk_blocks.append(
                f"[{i}] {source} — {title}\n{text}"
            )
        gen_user_msg = (
            f"Soru: {payload.content}\n\n"
            f"Verilen kaynaklar:\n\n"
            + "\n\n---\n\n".join(chunk_blocks)
            + "\n\n"
            f"Yukarıdaki kaynakları kullanarak yukarıdaki kuralları izle ve "
            f"soruya tek yekpare yanıt yaz (citation [n] formatı ile)."
        )

        # Chat provider — yeni chat-specific prompt (plain text, multi-source)
        chat_provider = registry.route_for_tier(operation="chat", tier=user.tier)
        sys_prompt = SYSTEM_PROMPT_CHAT_ANSWER

        # Stream response
        accumulated = ""
        try:
            async for stream_chunk in chat_provider.generate_text_stream(
                messages=[
                    ProviderMessage(role="system", content=sys_prompt),
                    ProviderMessage(role="user", content=gen_user_msg),
                ],
                max_tokens=1500,
                temperature=0.7,
            ):
                if not stream_chunk:
                    continue
                accumulated += stream_chunk
                yield _sse("chunk", {"delta": stream_chunk})
        except Exception as exc:
            logger.warning("chat stream generation failed: %s", exc)
            # Fallback: non-streaming generate
            result = await chat_provider.generate_text(
                messages=[
                    ProviderMessage(role="system", content=sys_prompt),
                    ProviderMessage(role="user", content=gen_user_msg),
                ],
                max_tokens=1500,
                temperature=0.7,
            )
            accumulated = result.text
            yield _sse("chunk", {"delta": accumulated})

        # ---- Step 6: Persist assistant message ----
        # Yeni AsyncSession ile (stream sırasında orijinal session'ı kapatmamak için)
        from app.core.db import get_session_factory
        factory = get_session_factory()
        async with factory() as persist_db:
            assistant_msg = Message(
                conversation_id=conv_id,
                role="assistant",
                content=accumulated,
                sources_used=sources_used,
                sources_considered=None,
                thinking_steps=thinking_log,
            )
            persist_db.add(assistant_msg)
            await persist_db.commit()
            await persist_db.refresh(assistant_msg)
            assistant_msg_id = assistant_msg.id

        yield _sse("done", {
            "conversation_id": str(conv_id),
            "user_message_id": str(user_msg_id),
            "assistant_message_id": str(assistant_msg_id),
            "is_followup": is_related,
            "similarity": round(similarity, 3),
        })

    except Exception as exc:
        logger.exception("chat stream failed: %s", exc)
        yield _sse("error", {
            "code": "STREAM_ERROR",
            "title": "Akış hatası",
            "reason": str(exc)[:200],
        })
        yield _sse("done", {"status": "failed"})
