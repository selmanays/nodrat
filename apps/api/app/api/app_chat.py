"""Chat conversations API (#793 S1 — Perplexity-style chat UX).

Endpoint'ler:
    POST   /chat/conversations              — boş conversation oluştur
    GET    /chat/conversations              — sidebar list (user'ın conversations)
    GET    /chat/conversations/{id}         — full thread (messages dahil)
    PATCH  /chat/conversations/{id}         — title update
    DELETE /chat/conversations/{id}         — archive (soft delete)

Streaming endpoint (POST /chat/conversations/{id}/messages) S2'de eklenir
(app_chat_stream.py — context-aware retrieval + source reuse).

docs/engineering/api-contracts.md §x güncellenir.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.conversation import Conversation, Message
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Pydantic schemas
# ============================================================================


class ConversationCreate(BaseModel):
    """Yeni conversation isteği — title opsiyonel (ilk mesajdan auto-gen)."""

    title: str | None = Field(default=None, max_length=200)


class ConversationItem(BaseModel):
    """Sidebar list item — preview snippet dahil."""

    id: uuid.UUID
    title: str
    summary: str | None = None
    message_count: int = 0
    last_answer_snippet: str | None = None
    archived: bool = False
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationItem]
    total: int


class MessageItem(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    generation_id: uuid.UUID | None = None
    sources_used: list[dict[str, Any]] | None = None
    sources_considered: list[dict[str, Any]] | None = None
    thinking_steps: list[dict[str, Any]] | None = None
    created_at: datetime


class ConversationThread(BaseModel):
    id: uuid.UUID
    title: str
    summary: str | None = None
    archived: bool = False
    created_at: datetime
    updated_at: datetime
    messages: list[MessageItem]


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/conversations",
    summary="Yeni conversation oluştur",
    response_model=ConversationItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationItem:
    """Yeni boş conversation oluştur. Title verilmediyse 'Yeni sohbet'.

    İlk mesaj geldiğinde title auto-update edilir (POST /messages içinde).
    """
    title = (payload.title or "Yeni sohbet").strip()[:200] or "Yeni sohbet"
    conv = Conversation(user_id=user.id, title=title)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    logger.info("chat conversation created: user=%s id=%s", user.id, conv.id)
    return ConversationItem(
        id=conv.id,
        title=conv.title,
        summary=conv.summary,
        message_count=0,
        last_answer_snippet=None,
        archived=conv.archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get(
    "/conversations",
    summary="User'ın conversations — sidebar list",
    response_model=ConversationList,
)
async def list_conversations(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_archived: Annotated[bool, Query(description="Archive olanları da göster")] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationList:
    """Sidebar için conversation listesi. updated_at DESC sıralı.

    Her item için:
    - message_count: toplam mesaj sayısı
    - last_answer_snippet: son assistant cevabının ilk 200 char (preview)
    """
    from sqlalchemy import func

    # Conversations query
    query = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if not include_archived:
        query = query.where(Conversation.archived == False)  # noqa: E712

    convs = (await db.execute(query)).scalars().all()

    # Total count
    count_q = select(func.count(Conversation.id)).where(
        Conversation.user_id == user.id
    )
    if not include_archived:
        count_q = count_q.where(Conversation.archived == False)  # noqa: E712
    total = (await db.execute(count_q)).scalar_one()

    # Bulk fetch: message counts + last assistant snippet per conversation
    items: list[ConversationItem] = []
    if convs:
        conv_ids = [c.id for c in convs]

        # message count per conv
        msg_count_rows = (
            await db.execute(
                select(Message.conversation_id, func.count(Message.id))
                .where(Message.conversation_id.in_(conv_ids))
                .group_by(Message.conversation_id)
            )
        ).all()
        msg_count_map = {cid: cnt for cid, cnt in msg_count_rows}

        # last assistant message per conv (window function)
        # Simple yaklaşım: her conversation için ayrı query (N+1 — küçük N için OK)
        snippet_map: dict[uuid.UUID, str | None] = {}
        for cid in conv_ids:
            last_assistant = (
                await db.execute(
                    select(Message.content)
                    .where(
                        Message.conversation_id == cid,
                        Message.role == "assistant",
                    )
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            snippet_map[cid] = (last_assistant or "")[:200] if last_assistant else None

        for c in convs:
            items.append(
                ConversationItem(
                    id=c.id,
                    title=c.title,
                    summary=c.summary,
                    message_count=msg_count_map.get(c.id, 0),
                    last_answer_snippet=snippet_map.get(c.id),
                    archived=c.archived,
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                )
            )

    return ConversationList(items=items, total=total)


@router.get(
    "/conversations/{conversation_id}",
    summary="Conversation tam thread — messages dahil",
    response_model=ConversationThread,
)
async def get_conversation(
    conversation_id: Annotated[uuid.UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationThread:
    """Conversation detay sayfası — tüm mesajlar created_at ASC."""
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

    msgs = (
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    return ConversationThread(
        id=conv.id,
        title=conv.title,
        summary=conv.summary,
        archived=conv.archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageItem(
                id=m.id,
                role=m.role,
                content=m.content,
                generation_id=m.generation_id,
                sources_used=m.sources_used,
                sources_considered=m.sources_considered,
                thinking_steps=m.thinking_steps,
                created_at=m.created_at,
            )
            for m in msgs
        ],
    )


@router.patch(
    "/conversations/{conversation_id}",
    summary="Conversation title güncelle",
    response_model=ConversationItem,
)
async def update_conversation_title(
    conversation_id: Annotated[uuid.UUID, Path()],
    payload: ConversationUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationItem:
    """Conversation title manuel rename."""
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

    conv.title = payload.title.strip()[:200]
    await db.commit()
    await db.refresh(conv)

    return ConversationItem(
        id=conv.id,
        title=conv.title,
        summary=conv.summary,
        message_count=0,  # patch endpoint count bilgisi içermez
        last_answer_snippet=None,
        archived=conv.archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.delete(
    "/conversations/{conversation_id}",
    summary="Conversation arşivle (soft delete)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_conversation(
    conversation_id: Annotated[uuid.UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Conversation'ı arşivle. Veriler korunur (KVKK m.11 — soft delete).

    Hard delete admin path'ten (ileri tarih).
    """
    result = await db.execute(
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        .values(archived=True)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.commit()
    logger.info("chat conversation archived: user=%s id=%s", user.id, conversation_id)
