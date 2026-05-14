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
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

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
    sources_used: list[dict[str, Any]] | None = None
    sources_considered: list[dict[str, Any]] | None = None
    thinking_steps: list[dict[str, Any]] | None = None
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
                sources_used=m.sources_used,
                sources_considered=m.sources_considered,
                thinking_steps=m.thinking_steps,
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
    logger.info("chat conversation archived: user=%s id=%s", user.id, conversation_id)


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
    db: AsyncSession, msg_id: uuid.UUID, user: User,
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
    from app.core.sft_eligibility import recompute_sft_eligibility

    # Message için require_completed_status=False (role='assistant' zaten kontrol edildi)
    eligible, reason = recompute_sft_eligibility(
        msg, user, require_completed_status=False,
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
        message_id, user.id, len(msg.halu_flagged_reason or ""),
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
        message_id, user.id, payload.action, msg.edit_distance,
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


# ============================================================================
# Wikipedia fallback CTA (#813 Faz 2 2B)
# ============================================================================


class WikipediaFallbackRequest(BaseModel):
    """Kullanıcının Wikipedia CTA'ya yanıtı.

    Stream daha önce `requires_user_consent` event ile durdu;
    stub assistant message (content="") oluşturuldu. Bu endpoint o
    mesajı günceller.
    """

    assistant_message_id: uuid.UUID
    accepted: bool


class WikipediaFallbackResponse(BaseModel):
    """Wikipedia kaynaklı cevap (accepted=true) veya kısa refusal (accepted=false)."""

    id: uuid.UUID
    content: str
    sources_used: list[dict[str, Any]]
    source_type: Literal["wikipedia", "none"]


@router.post(
    "/conversations/{conversation_id}/wikipedia-fallback",
    summary="Wikipedia fallback CTA yanıtı (#813 Faz 2 2B)",
    response_model=WikipediaFallbackResponse,
)
async def wikipedia_fallback(
    conversation_id: Annotated[uuid.UUID, Path()],
    payload: WikipediaFallbackRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WikipediaFallbackResponse:
    """Wikipedia onay CTA endpoint.

    accepted=True:
      1. Stub message + önceki user mesajını fetch
      2. Wikipedia search → max 3 article
      3. LLM ile cevap üret (Wikipedia kaynaklı, [W1] citation format)
      4. Mesajı update: content + sources_used (source_type='wikipedia')

    accepted=False:
      Mesajı update: kısa scope-aware refusal cevabı.
    """
    # 1. Conversation + message ownership
    conv = (await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    stub_msg = (await db.execute(
        select(Message).where(
            Message.id == payload.assistant_message_id,
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        )
    )).scalar_one_or_none()
    if stub_msg is None:
        raise HTTPException(status_code=404, detail="Stub message not found")
    if stub_msg.content:
        raise HTTPException(
            status_code=400,
            detail="Bu mesaj zaten içerik içeriyor — consent yanıtı verilemez.",
        )

    # consent_pending flag thinking_steps içinde olmalı (chat_stream tarafında set)
    pending_entries = [
        s for s in (stub_msg.thinking_steps or [])
        if isinstance(s, dict) and s.get("phase") == "consent_pending"
    ]
    if not pending_entries:
        raise HTTPException(
            status_code=400, detail="Mesajda consent_pending sinyali yok.",
        )

    topic_query = (
        pending_entries[0].get("topic_query") if pending_entries else None
    ) or ""

    if not payload.accepted:
        # Kısa scope-aware refusal
        refusal_text = (
            "Tamam, bu konuda Wikipedia'dan bakmıyorum. Güncel gündemle ilgili "
            "başka bir konuda yardım edebilirim."
        )
        stub_msg.content = refusal_text
        stub_msg.sources_used = []
        await db.commit()
        await db.refresh(stub_msg)
        return WikipediaFallbackResponse(
            id=stub_msg.id,
            content=refusal_text,
            sources_used=[],
            source_type="none",
        )

    # accepted=true → Wikipedia search + LLM cevap üret
    # Önce previous user message'ı fetch et (input query)
    prev_user = (await db.execute(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.role == "user",
            Message.created_at < stub_msg.created_at,
        ).order_by(Message.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    user_query = (prev_user.content if prev_user else topic_query) or ""

    # Wikipedia provider
    from app.providers.wikipedia import get_wikipedia_provider

    provider = await get_wikipedia_provider()
    articles = await provider.search(
        user_query or topic_query, lang=None, top_k=3,
    )

    if not articles:
        # Wikipedia da boş — refusal
        refusal_text = (
            "Bu konuda hem haber arşivimde hem de Wikipedia'da yeterli kaynak "
            "bulamadım. Başka bir açıdan bakmak ister misin?"
        )
        stub_msg.content = refusal_text
        stub_msg.sources_used = []
        await db.commit()
        await db.refresh(stub_msg)
        return WikipediaFallbackResponse(
            id=stub_msg.id,
            content=refusal_text,
            sources_used=[],
            source_type="none",
        )

    # LLM ile Wikipedia kaynaklı cevap üret
    from app.providers.base import Message as ProviderMessage
    from app.providers.registry import bootstrap_default_providers, registry

    bootstrap_default_providers()
    chat_provider = registry.route_for_tier(operation="chat", tier=user.tier)

    source_blocks = []
    sources_used = []
    for i, a in enumerate(articles, start=1):
        # 25 kelime quote cap (FSEK) — summary daha uzun olsa bile veriyoruz
        # ancak LLM prompt'taki kuralla kısa quote kısıtlanır.
        source_blocks.append(
            f"[W{i}] {a.title} ({a.lang}) — {a.url}\n{a.summary}"
        )
        sources_used.append({
            "source_type": "wikipedia",
            "source_name": f"Wikipedia ({a.lang.upper()})",
            "title": a.title,
            "url": a.url,
            "license": a.license,
        })

    sys_prompt = (
        "Sen Nodrat'ın bilgi asistanısın. Aşağıdaki Wikipedia kaynaklarını "
        "kullanarak kullanıcının sorusuna kısa ve kaynaklı cevap ver.\n\n"
        "KURALLAR:\n"
        "- Sadece verilen Wikipedia kaynaklarındaki bilgileri kullan\n"
        "- Her iddiayı [W1][W2] formatında citation ile bağla\n"
        "- 25 kelimeden uzun direct quote yapma (FSEK)\n"
        "- Kaynak yetersizse 'Wikipedia'da bu detay yok' de\n"
        "- Cevap dil: Türkçe, sade, akıcı"
    )
    user_msg = (
        f"Soru: {user_query}\n\n"
        f"Kaynaklar:\n\n"
        + "\n\n---\n\n".join(source_blocks)
        + "\n\nYukarıdaki Wikipedia kaynaklarını kullanarak cevap yaz."
    )

    try:
        result = await chat_provider.generate_text(
            messages=[
                ProviderMessage(role="system", content=sys_prompt),
                ProviderMessage(role="user", content=user_msg),
            ],
            max_tokens=1000,
            temperature=0.3,
        )
        answer_text = result.text.strip()
    except Exception as exc:
        logger.warning("wikipedia fallback LLM failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Cevap üretilemedi, lütfen tekrar deneyin.",
        ) from exc

    stub_msg.content = answer_text
    stub_msg.sources_used = sources_used
    # thinking_steps'e consent yanıt notu ekle
    new_thinking = list(stub_msg.thinking_steps or [])
    new_thinking.append({
        "phase": "consent_accepted",
        "source_type": "wikipedia",
        "article_count": len(articles),
    })
    stub_msg.thinking_steps = new_thinking
    await db.commit()
    await db.refresh(stub_msg)

    logger.info(
        "wikipedia fallback accepted: conv=%s msg=%s articles=%d",
        conversation_id, stub_msg.id, len(articles),
    )

    return WikipediaFallbackResponse(
        id=stub_msg.id,
        content=answer_text,
        sources_used=sources_used,
        source_type="wikipedia",
    )
