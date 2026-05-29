"""Research conversations API (#793 S1 — Perplexity-style research UX).

Endpoint'ler:
    POST   /research/conversations              — boş conversation oluştur
    GET    /research/conversations              — sidebar list (user'ın conversations)
    GET    /research/conversations/{id}         — full thread (messages dahil)
    PATCH  /research/conversations/{id}         — title update
    DELETE /research/conversations/{id}         — archive (soft delete)

Streaming endpoint (POST /research/conversations/{id}/messages) S2'de eklenir
(app_research_stream.py — context-aware retrieval + source reuse).

docs/engineering/api-contracts.md §x güncellenir.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.user import User
from app.modules.accounts.deps import get_current_user
from app.modules.conversations.models import Conversation, Message

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
    sources_used: list[dict[str, Any]] | None = None
    sources_considered: list[dict[str, Any]] | None = None
    thinking_steps: list[dict[str, Any]] | None = None
    followup_suggestions: list[str] | None = None  # #961
    # S1C feedback fields
    halu_flagged_at: datetime | None = None
    user_action: str | None = None
    user_action_at: datetime | None = None
    sft_eligible: bool = False
    dpo_rejected: bool = False
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
    logger.info("research conversation created: user=%s id=%s", user.id, conv.id)
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
    count_q = select(func.count(Conversation.id)).where(Conversation.user_id == user.id)
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
        msg_count_map = dict(msg_count_rows)

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
                sources_used=m.sources_used,
                sources_considered=m.sources_considered,
                thinking_steps=m.thinking_steps,
                followup_suggestions=m.followup_suggestions,
                halu_flagged_at=m.halu_flagged_at,
                user_action=m.user_action,
                user_action_at=m.user_action_at,
                sft_eligible=m.sft_eligible,
                dpo_rejected=m.dpo_rejected,
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
    logger.info("research conversation archived: user=%s id=%s", user.id, conversation_id)


# ============================================================================
# Message feedback — halu flag + user action (#802 S1C)
# ============================================================================


class FlagHaluRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    chosen_content: str | None = Field(
        default=None,
        max_length=5000,
        description=(
            "DPO için kullanıcının önerdiği 'doğru cevap' (opsiyonel). "
            "Verilirse halu mesajı DPO rejected sample, chosen_content DPO chosen."
        ),
    )


class MessageActionRequest(BaseModel):
    action: Literal["copied", "posted", "edited", "none"]
    edit_distance: float | None = Field(default=None, ge=0.0, le=1.0)
    edited_content: str | None = Field(default=None, max_length=10000)


class MessageFeedbackResponse(BaseModel):
    id: uuid.UUID
    halu_flagged_at: datetime | None
    user_action: str | None
    user_action_at: datetime | None
    sft_eligible: bool
    sft_excluded_reason: str | None
    dpo_rejected: bool


async def _fetch_message_for_user(
    db: AsyncSession,
    msg_id: uuid.UUID,
    user: User,
) -> Message:
    """Mesajı çek + conversation ownership doğrula. Yoksa 404."""
    row = (
        await db.execute(
            select(Message, Conversation)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Message.id == msg_id, Conversation.user_id == user.id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return row[0]


async def _recompute_message_sft(db: AsyncSession, msg: Message, user: User) -> None:
    """Message için SFT eligibility recompute — generic utility kullanır."""
    from app.modules.sft.eligibility import recompute_sft_eligibility

    # Message için require_completed_status=False (role='assistant' zaten kontrol edildi)
    eligible, reason = recompute_sft_eligibility(
        msg,
        user,
        require_completed_status=False,
    )
    msg.sft_eligible = eligible
    msg.sft_excluded_reason = reason
    msg.sft_recomputed_at = datetime.now(UTC)


@router.post(
    "/messages/{message_id}/flag-halu",
    summary="Mesajı halüsinasyon olarak işaretle (DPO için saklanır)",
    response_model=MessageFeedbackResponse,
)
async def flag_message_halucination(
    message_id: Annotated[uuid.UUID, Path()],
    payload: FlagHaluRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageFeedbackResponse:
    """Halu bildirimi.

    - `halu_flagged_at`, `halu_flagged_by`, `halu_flagged_reason` set
    - `dpo_rejected=true` (eğer assistant mesajıysa — DPO training için)
    - `dpo_chosen_content` opsiyonel — kullanıcı "doğru cevap" önerdiyse
    - SFT eligibility recompute (halu_flagged → excluded)
    """
    msg = await _fetch_message_for_user(db, message_id, user)
    if msg.role != "assistant":
        raise HTTPException(
            status_code=400,
            detail="Halu flag yalnızca assistant mesajları için geçerlidir.",
        )

    msg.halu_flagged_at = datetime.now(UTC)
    msg.halu_flagged_by = user.id
    msg.halu_flagged_reason = (payload.reason or "").strip()[:500] or None
    msg.dpo_rejected = True
    if payload.chosen_content:
        msg.dpo_chosen_content = payload.chosen_content.strip()[:5000]

    await _recompute_message_sft(db, msg, user)
    await db.commit()
    await db.refresh(msg)

    logger.info(
        "message halu flagged: msg=%s by=%s reason_len=%d dpo_chosen=%s",
        message_id,
        user.id,
        len(msg.halu_flagged_reason or ""),
        bool(msg.dpo_chosen_content),
    )

    return MessageFeedbackResponse(
        id=msg.id,
        halu_flagged_at=msg.halu_flagged_at,
        user_action=msg.user_action,
        user_action_at=msg.user_action_at,
        sft_eligible=msg.sft_eligible,
        sft_excluded_reason=msg.sft_excluded_reason,
        dpo_rejected=msg.dpo_rejected,
    )


@router.post(
    "/messages/{message_id}/action",
    summary="Mesaj kullanıcı eylemi kaydet (copied/posted/edited/none)",
    response_model=MessageFeedbackResponse,
)
async def record_message_action(
    message_id: Annotated[uuid.UUID, Path()],
    payload: MessageActionRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageFeedbackResponse:
    """User action kaydı (SFT quality signal).

    - `copied` / `posted` → SFT positive signal (sft_eligible aday)
    - `edited` → edit_distance kaydı + edited_content (DPO için aday)
    - `none` → no-op (action geri al)
    """
    msg = await _fetch_message_for_user(db, message_id, user)
    if msg.role != "assistant":
        raise HTTPException(
            status_code=400,
            detail="Action yalnızca assistant mesajları için geçerlidir.",
        )

    now = datetime.now(UTC)
    msg.user_action = payload.action
    msg.user_action_at = now

    if payload.action == "edited":
        if payload.edited_content:
            msg.edited_content = payload.edited_content.strip()[:10000]
        if payload.edit_distance is not None:
            msg.edit_distance = Decimal(str(round(payload.edit_distance, 2)))

    await _recompute_message_sft(db, msg, user)
    await db.commit()
    await db.refresh(msg)

    logger.info(
        "message action: msg=%s by=%s action=%s edit_distance=%s",
        message_id,
        user.id,
        payload.action,
        msg.edit_distance,
    )

    return MessageFeedbackResponse(
        id=msg.id,
        halu_flagged_at=msg.halu_flagged_at,
        user_action=msg.user_action,
        user_action_at=msg.user_action_at,
        sft_eligible=msg.sft_eligible,
        sft_excluded_reason=msg.sft_excluded_reason,
        dpo_rejected=msg.dpo_rejected,
    )
