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
from dataclasses import dataclass
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


# #809 Faz 2 2A — hybrid_search_chunks dict çıktısını
# retrieval_confidence._ChunkLike Protocol'üne uyarlayan adapter.
@dataclass
class _ConfidenceChunk:
    semantic_score: float
    chunk_text: str
    source_id: str
    published_at: datetime | None


# ============================================================================
# Pydantic schemas
# ============================================================================


class ChatMessageCreate(BaseModel):
    """Yeni mesaj — payload (#803 S1D ile genişletildi).

    Form modu parametreleri sohbet'e taşındı:
    - output_type: x_post | x_thread | summary | analysis | headline | "" (Otomatik)
    - tone: tarafsız | eleştirel | mizahi | kurumsal | resmi | None (Otomatik)
    - length: short | medium | long | None (Otomatik)
    - max_posts: 1-10 | None (Otomatik)
    - style_profile_id: UUID | None (Pro+ paywall)
    - show_sources: bool (default true)
    """

    content: str = Field(min_length=1, max_length=5000)
    output_type: str = Field(default="x_post", max_length=32)
    tone: str | None = Field(default=None, max_length=32)
    length: str | None = Field(default=None, max_length=16)
    max_posts: int | None = Field(default=None, ge=1, le=10)
    style_profile_id: uuid.UUID | None = Field(default=None)
    show_sources: bool = Field(default=True)


# ============================================================================
# SSE helper
# ============================================================================


def _sse(event: str, data: dict | None = None) -> str:
    payload = json.dumps(data or {}, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def _resolve_style_block(
    db: AsyncSession, user: User, style_profile_id: uuid.UUID,
) -> str:
    """Style profile rules_json'u prompt'a uygun text blok'a çevir.

    Pro+ paywall: tier kontrolü yapılır; başarısızsa boş string döner.
    """
    from app.models.style_profile import StyleProfile

    # Pro tier check (gevşek — başarısızlık ölümcül değil)
    if user.tier not in ("pro", "agency_seat"):
        return ""

    sp = (await db.execute(
        select(StyleProfile).where(
            StyleProfile.id == style_profile_id,
            StyleProfile.user_id == user.id,
            StyleProfile.status == "ready",
        )
    )).scalar_one_or_none()

    if sp is None or not sp.rules_json:
        return ""

    rules = sp.rules_json
    if isinstance(rules, str):
        import json as _json
        try:
            rules = _json.loads(rules)
        except Exception:
            return ""

    if not isinstance(rules, dict) or not rules:
        return ""

    # Rules dict'i prompt'a okuma-dostu format'a çevir
    lines = ["\n\n## Stil profili (uy):"]
    for k, v in rules.items():
        if isinstance(v, (str, int, float, bool)):
            lines.append(f"- {k}: {v}")
        elif isinstance(v, list):
            lines.append(f"- {k}: {', '.join(str(x) for x in v[:5])}")
    return "\n".join(lines)


# ============================================================================
# Meta-query handler (#815 Faz 2 2C)
# ============================================================================


async def _recent_conversation_context(
    db: AsyncSession,
    conv_id: UUID,
    exclude_msg_id: UUID,
    *,
    last_n: int = 6,
) -> str:
    """Son N mesaj → context bloğu (content + assistant kaynak özeti).

    #829 fix: Follow-up sorular ("kaç yıl önce", "hangi tarihli haberde")
    önceki cevabın KAYNAKLARINI da görmeli. Eski kod sadece content
    iletiyordu; assistant mesajların sources_used (başlık + kaynak adı)
    özeti eklenmezse "konuşmada tarih yok" gibi yanlış cevaplar çıkıyordu.
    """
    rows = list((await db.execute(
        select(Message).where(
            Message.conversation_id == conv_id,
            Message.id != exclude_msg_id,
        ).order_by(Message.created_at.desc()).limit(last_n)
    )).scalars().all())
    rows.reverse()  # oldest-first (doğal okuma)

    lines: list[str] = []
    for m in rows:
        label = "Kullanıcı" if m.role == "user" else "Asistan"
        snippet = (m.content or "")[:500]
        lines.append(f"- {label}: {snippet}")
        # Assistant cevabın kaynak özeti — follow-up için kritik
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
                    "  (Bu cevabın kaynakları: "
                    + "; ".join(srcs) + ")"
                )
    return "\n".join(lines)


async def _stream_meta_query_answer(
    *,
    db: AsyncSession,
    conv_id: UUID,
    user_message: str,
    conv_summary: str | None,
    user: User,
    user_msg_id: UUID,
    similarity: float,
    is_related: bool,
    thinking_log: list[dict[str, Any]],
    sse: "callable",
) -> AsyncIterator[str]:
    """Meta-query: retrieval atla, conversation context'ten cevapla.

    Akış:
      1. Son 6 mesajı fetch et (user+assistant)
      2. System prompt + summary + son mesajlar + soru → LLM
      3. Stream chunks
      4. Persist (sources_used=[], thinking_steps=meta_query_handler)
    """
    from app.prompts.meta_query import SYSTEM_PROMPT_META_QUERY
    from app.providers.base import Message as ProviderMessage
    from app.providers.registry import bootstrap_default_providers, registry

    bootstrap_default_providers()

    # #829: ortak helper — content + assistant kaynak özeti
    recent_block = await _recent_conversation_context(
        db, conv_id, user_msg_id, last_n=6,
    )
    context_lines = []
    if conv_summary:
        context_lines.append(f"Konuşma özeti: {conv_summary}")
    if recent_block:
        context_lines.append("\nSon mesajlar:\n" + recent_block)
    context_block = "\n".join(context_lines)

    # #831 — meta-query handler artık tool-enabled. Eski kod "dead end"di:
    # conversation context'te cevap yoksa "bilgi yok" diyordu (örn. "ilk
    # bölümün adı ne" → önceki cevapta sadece tarih var → cevapsız). Oysa
    # bilgi Wikipedia'da. Çözüm: LLM'e search_wikipedia tool ver — context
    # yeterse context'ten, yoksa LLM tool çağırır. Mimari tutarlılık: tüm
    # generation tool-use, LLM karar verici (pattern/planner-accuracy değil).
    from app.core.chat_tools import CHAT_TOOL_DEFINITIONS, CHAT_TOOLS

    chat_provider = registry.route_for_tier(operation="chat", tier=user.tier)
    user_prompt = (
        f"{context_block}\n\nKullanıcı şimdi sordu: {user_message}\n\n"
        f"Önce yukarıdaki konuşma bağlamına bak — cevap (veya önceki "
        f"cevapların kaynak özetleri) orada varsa ondan yanıtla. Bağlamda "
        f"YOKSA ve evergreen factual bir detaysa (isim, tarih, sayı vb.) "
        f"search_wikipedia tool'unu çağır. Uydurma yapma."
    )

    wikipedia_enabled = True
    try:
        from app.core.settings_store import settings_store
        wikipedia_enabled = await settings_store.get_bool(
            db, "wikipedia.enabled", True,
        )
    except Exception:
        wikipedia_enabled = True
    tools_arg = CHAT_TOOL_DEFINITIONS if wikipedia_enabled else None

    base_messages = [
        ProviderMessage(role="system", content=SYSTEM_PROMPT_META_QUERY),
        ProviderMessage(role="user", content=user_prompt),
    ]
    accumulated = ""
    wiki_sources: list[dict[str, Any]] = []

    # Aşama 1: tool-decision (non-streaming)
    tool_decision = None
    try:
        tool_decision = await chat_provider.generate_text(
            messages=base_messages,
            max_tokens=600,
            temperature=0.5,
            tools=tools_arg,
            tool_choice="auto",
        )
    except Exception as exc:
        logger.warning("meta tool-decision failed: %s", exc)

    if tool_decision is not None and tool_decision.tool_calls:
        step = {
            "phase": "tool_use",
            "detail": "Konuşmada cevap yok — Wikipedia'ya başvuruluyor",
            "latency_ms": 0,
        }
        thinking_log.append(step)
        yield sse("thinking_step", step)
        convo = list(base_messages)
        convo.append(
            ProviderMessage(
                role="assistant",
                content=tool_decision.text or "",
                tool_calls=tool_decision.tool_calls,
            )
        )
        for tc in tool_decision.tool_calls:
            executor = CHAT_TOOLS.get(tc.name)
            if executor is None:
                tool_result = f"Bilinmeyen tool: {tc.name}"
            else:
                try:
                    tool_result, tc_sources = await executor(tc.arguments)
                    wiki_sources.extend(tc_sources)
                except Exception as _texc:
                    logger.warning("meta tool exec failed: %s", _texc)
                    tool_result = f"Tool hatası: {_texc}"
            convo.append(
                ProviderMessage(
                    role="tool", content=tool_result, tool_call_id=tc.id,
                )
            )
        for s in wiki_sources:
            yield sse("source_discovered", s)
        try:
            async for stream_chunk in chat_provider.generate_text_stream(
                messages=convo, max_tokens=900, temperature=0.5,
            ):
                delta = getattr(stream_chunk, "delta_text", None) or ""
                if not delta:
                    continue
                accumulated += delta
                yield sse("chunk", {"delta": delta})
        except Exception as exc:
            logger.warning("meta final stream failed: %s", exc)
            fb = await chat_provider.generate_text(
                messages=convo, max_tokens=900, temperature=0.5,
            )
            accumulated = fb.text
            yield sse("chunk", {"delta": accumulated})
    else:
        # Tool yok — context'ten cevap (tool_decision.text dolu)
        if tool_decision is not None and tool_decision.text:
            accumulated = tool_decision.text
            yield sse("chunk", {"delta": accumulated})
        else:
            try:
                async for stream_chunk in chat_provider.generate_text_stream(
                    messages=base_messages, max_tokens=600, temperature=0.5,
                ):
                    delta = getattr(stream_chunk, "delta_text", None) or ""
                    if not delta:
                        continue
                    accumulated += delta
                    yield sse("chunk", {"delta": delta})
            except Exception as exc:
                logger.warning("meta stream fallback failed: %s", exc)
                fb = await chat_provider.generate_text(
                    messages=base_messages, max_tokens=600, temperature=0.5,
                )
                accumulated = fb.text
                yield sse("chunk", {"delta": accumulated})

    # Persist — Wikipedia kullanıldıysa kaynaklar, yoksa boş
    from app.core.db import get_session_factory
    factory = get_session_factory()
    async with factory() as persist_db:
        meta_msg = Message(
            conversation_id=conv_id,
            role="assistant",
            content=accumulated,
            sources_used=wiki_sources,
            sources_considered=None,
            thinking_steps=thinking_log,
        )
        persist_db.add(meta_msg)
        await persist_db.commit()
        await persist_db.refresh(meta_msg)
        assistant_msg_id = meta_msg.id

    yield sse("done", {
        "conversation_id": str(conv_id),
        "user_message_id": str(user_msg_id),
        "assistant_message_id": str(assistant_msg_id),
        "is_followup": is_related,
        "similarity": round(similarity, 3),
        "query_class": "meta_query",
        "used_wikipedia": bool(wiki_sources),
        "confidence": None,
    })



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
    from app.core.chat_tools import (  # #822 tool-use
        CHAT_TOOL_DEFINITIONS,
        CHAT_TOOLS,
    )
    from app.core.retrieval import hybrid_search_chunks
    from app.core.retrieval_confidence import (  # #809 Faz 2 2A — telemetri
        compute_retrieval_confidence,
        load_thresholds_from_settings,
        load_weights_from_settings,
    )
    from app.providers.base import Message as ProviderMessage
    from app.prompts.query_planner import plan_query
    from app.prompts.content_generator import render_user_payload
    from app.prompts.chat_answer import (
        SYSTEM_PROMPT_CHAT_ANSWER,
        TOOL_USE_INSTRUCTION,
    )

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

        # ---- Step 1.5: Conversational query rewrite (#833) ----
        # #832 plan_input enrichment ÇALIŞMADI (production'da kanıtlandı):
        # planner SYSTEM_PROMPT preserve-first kuralı ad-hoc talimatı
        # ezdi, "ilk bölümün adı neydi" → Stargate bağlamı ignore →
        # "Daha 17 dizisi" çöpü. Çözüm: planner'dan ÖNCE izole condense
        # step (Perplexity/LangChain standardı). Multi-turn'de follow-up
        # → standalone arama sorgusu. is_related'a güvenmiyoruz (generic
        # "daha detaylı açıkla" embedding kaçırıyor); context VARSA hep.
        effective_query = payload.content
        _rw_ctx = await _recent_conversation_context(
            db, conv_id, user_msg_id, last_n=4,
        )
        if _rw_ctx:
            from app.prompts.query_rewrite import condense_followup_query

            _rw_provider = registry.route_for_tier(
                operation="chat", tier=user.tier,
            )
            _t_rw = asyncio.get_event_loop().time()
            rewritten = await condense_followup_query(
                _rw_provider, _rw_ctx, payload.content,
            )
            if rewritten and rewritten.strip():
                effective_query = rewritten.strip()
                yield _log_step(
                    "query_rewrite",
                    f"Bağlamlı sorgu: {effective_query[:80]}",
                    int((asyncio.get_event_loop().time() - _t_rw) * 1000),
                )

        # ---- Step 2: Query planner (standalone effective_query ile) ----
        t0 = asyncio.get_event_loop().time()
        plan_result = await plan_query(
            user_request=effective_query,
            current_time=now,
            user_locale=getattr(user, "locale", "tr-TR") or "tr-TR",
            user_tier=user.tier,
        )
        t_planner = int((asyncio.get_event_loop().time() - t0) * 1000)
        topic = getattr(plan_result, "topic_query", payload.content)
        critical_entities = getattr(plan_result, "critical_entities", None) or []
        early_query_class = getattr(plan_result, "query_class", "news_query")
        yield _log_step(
            "planner",
            f"Plan çıkarıldı: {topic[:80]}",
            t_planner,
        )

        # ---- Step 2.5 (#815 Faz 2 2C): Meta-query short-circuit ----
        # Konuşma kendisi hakkında sorgu → retrieval atlanır, conversation
        # context'ten cevap üretilir. Yeni kaynak/haber getirmez.
        if early_query_class == "meta_query":
            yield _log_step(
                "meta_query_handler",
                "Konuşma context'inden cevap (retrieval atlanır)",
            )
            # Conversation summary fetch (chat_stream sırasında refetch)
            conv_row = (await db.execute(
                select(Conversation).where(Conversation.id == conv_id)
            )).scalar_one_or_none()
            conv_summary = conv_row.summary if conv_row else None

            async for chunk in _stream_meta_query_answer(
                db=db,
                conv_id=conv_id,
                user_message=payload.content,
                conv_summary=conv_summary,
                user=user,
                user_msg_id=user_msg_id,
                similarity=similarity,
                is_related=is_related,
                thinking_log=thinking_log,
                sse=_sse,
            ):
                yield chunk
            return

        # #828 — #826 general_knowledge fast-path GERİ ALINDI. Fast-path
        # planner topic_query'sini ("stargate atlantis kaç sezondu") doğrudan
        # Wikipedia'ya gönderiyordu; soru kelimeleri ("kaç sezondu") full-text
        # search relevance'ı kirletip yanlış sayfa getiriyordu (Ronon Dex).
        # Tool-use path'te LLM soruyu temiz entity'ye çeviriyor ("Yıldız
        # Geçidi Atlantis") → doğru sayfa. Doğruluk > latency: general_knowledge
        # de normal tool-use akışına düşer (Step 3+ → Aşama 1 LLM query üretir).

        # ---- Step 3: Retrieve chunks (context-aware) ----
        # Eğer related: önceki kaynakları boost et + yeni retrieval combine
        # Eğer new topic: standart retrieval
        t0 = asyncio.get_event_loop().time()
        # #832 — Retrieval bağlamlı topic_query ile. Eski kod
        # query_text=payload.content (HAM) kullanıyordu; follow-up'ta
        # bağlam kayıp ("ilk bölümün adı neydi" → çöp). Planner artık
        # standalone topic_query üretiyor (plan_input zenginleştirildi);
        # retrieval de onu kullanmalı. topic ham mesajdan anlamlı
        # farklıysa (follow-up enrichment) yeni embedding al.
        retrieval_query = topic or payload.content
        retrieval_vec = query_vec
        if (
            topic
            and topic.strip().lower() != (payload.content or "").strip().lower()
        ):
            try:
                _emb = registry.route_for_tier(
                    operation="embedding", tier="free",
                )
                _re = await _emb.create_embedding([retrieval_query])
                if _re.vectors:
                    retrieval_vec = _re.vectors[0]
            except Exception as _ee:
                logger.warning("topic re-embed failed: %s", _ee)

        chunks = []
        if retrieval_vec is not None:
            chunks = await hybrid_search_chunks(
                db,
                query_text=retrieval_query,
                query_vector=retrieval_vec,
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

        # ---- Step 3.5 (#809 Faz 2 2A): Confidence Router ----
        # 5-signal fusion → score → routing decision.
        # 2A scope: telemetri + UI insufficiency signal hazır. Wikipedia
        # fallback short-circuit'i 2B'de wire edilir; meta_query bypass'ı 2C'de.
        query_class = getattr(plan_result, "query_class", "news_query")
        try:
            confidence_weights = await load_weights_from_settings(db)
            t_high, t_low = await load_thresholds_from_settings(db)
            # Dict chunks → Protocol-uyumlu basit shape (semantic + text + source_id + published_at)
            chunk_proto = [
                _ConfidenceChunk(
                    semantic_score=float(c.get("semantic_score") or 0.0),
                    chunk_text=str(c.get("chunk_text") or ""),
                    source_id=str(c.get("source_id") or c.get("article_id") or ""),
                    published_at=c.get("published_at"),
                )
                for c in chunks
            ]
            conf = compute_retrieval_confidence(
                plan_result, chunk_proto, weights=confidence_weights,
            )
        except Exception as _exc:
            logger.warning("confidence compute failed: %s", _exc)
            conf = None
            t_high, t_low = 0.70, 0.40

        # #822 — Confidence telemetri (SADECE observability; routing YOK).
        # Wikipedia tetikleme artık LLM tool-use ile (aşağıda). Confidence
        # admin /observability + done event için kalır, akışı yönlendirmez.
        if conf is not None:
            if conf.score >= t_high:
                layer_label = "Yüksek güven (haber arşivi)"
            elif conf.score >= t_low:
                layer_label = f"Orta güven ({','.join(conf.missing) or 'mixed'})"
            else:
                layer_label = "Düşük güven (LLM tool ile Wikipedia'ya başvurabilir)"
            yield _log_step(
                "confidence",
                f"query_class={query_class} score={conf.score:.2f} → {layer_label}",
            )
            yield _sse("confidence_score", {
                "score": conf.score,
                "query_class": query_class,
                "signals": {
                    "semantic": conf.semantic,
                    "source_count": conf.source_count,
                    "recency": conf.recency,
                    "entity_match": conf.entity_match,
                },
                "missing": conf.missing,
                "thresholds": {"t_high": t_high, "t_low": t_low},
            })

        # ---- Step 4: Sources discovered (haber kaynakları) ----
        # #829 fix: LLM'e verilen chunk sayısı = UI'da gösterilen kaynak
        # sayısı. Eski kod sources_used=chunks[:5] ama chunk_blocks=chunks[:10]
        # → LLM [1]-[10] cite ediyordu, UI [1]-[5] gösteriyordu, [6]-[10]
        # citation'lar "kayıp" görünüyordu. Tek top_k (content_top_k setting,
        # default 5, admin tunable) ikisinde de kullanılır.
        try:
            from app.core.settings_store import settings_store
            content_top_k = await settings_store.get_int(
                db, "retrieval.content_top_k", 5,
            )
        except Exception:
            content_top_k = 5
        content_top_k = max(3, min(content_top_k, 15))

        sources_used: list[dict[str, Any]] = []
        for c in chunks[:content_top_k]:
            src = {
                "source_type": "news",
                "article_id": str(c.get("article_id", "")),
                "chunk_id": str(c.get("chunk_id") or c.get("id") or ""),
                "title": c.get("article_title", "")[:200],
                "url": c.get("article_canonical_url") or c.get("url"),
                "source_name": c.get("source_name"),
            }
            sources_used.append(src)
            yield _sse("source_discovered", src)

        # ---- Step 5: Content generation (LLM tool-use) ----
        yield _log_step("generating", "Cevap yazılıyor (multi-source synthesis)...")

        # Chat user payload — minimal (chat-specific, X-post JSON yok)
        # Sadece kullanıcı sorusu + indeksli chunk listesi.
        # #829: chunk_blocks ve sources_used AYNI content_top_k → citation tutarlı.
        chunk_blocks = []
        for i, c in enumerate(chunks[:content_top_k], start=1):
            text = (c.get("chunk_text") or "")[:2500]
            title = (c.get("article_title") or "")[:200]
            source = c.get("source_name") or ""
            chunk_blocks.append(
                f"[{i}] {source} — {title}\n{text}"
            )
        # S1D (#803) — ChatSettings (output_type/tone/length/max_posts/style_profile)
        # generator prompt'a ek instruction olarak inject edilir.
        settings_block_parts: list[str] = []
        if payload.output_type and payload.output_type != "_auto":
            type_label = {
                "x_post": "X paylaşımı (kısa, tek post)",
                "x_thread": "X thread (numaralandırılmış post serisi)",
                "summary": "özet (paragraf)",
                "analysis": "analiz (detaylı yorum)",
                "headline": "başlık (1-2 satır)",
            }.get(payload.output_type, payload.output_type)
            settings_block_parts.append(f"- Çıktı türü: {type_label}")
        if payload.tone:
            settings_block_parts.append(f"- Ton: {payload.tone}")
        if payload.length:
            length_label = {
                "short": "kısa (1-2 cümle)",
                "medium": "orta (3-5 cümle)",
                "long": "uzun (1-2 paragraf)",
            }.get(payload.length, payload.length)
            settings_block_parts.append(f"- Uzunluk: {length_label}")
        if payload.max_posts:
            settings_block_parts.append(
                f"- Paylaşım adedi: {payload.max_posts} (X thread için maksimum)"
            )

        settings_block = ""
        if settings_block_parts:
            settings_block = (
                "\n\n## Kullanıcı tercihleri (uy):\n"
                + "\n".join(settings_block_parts)
            )

        # Style profile (Pro+ paywall — sadece resolved style profile rules)
        style_block = ""
        if payload.style_profile_id is not None:
            try:
                style_block = await _resolve_style_block(
                    db, user, payload.style_profile_id,
                )
            except Exception as _se:
                logger.warning("style profile resolve fail: %s", _se)

        # #829 fix: follow-up ise önceki konuşma + kaynak özetini ekle.
        # "kaç yıl önce" / "hangi tarihli haberde" gibi sorular önceki
        # cevabın bağlamını/kaynaklarını görmeli; eski kod sadece yeni
        # retrieval chunk'larını veriyordu → alakasız cevap.
        followup_block = ""
        if is_related:
            _ctx = await _recent_conversation_context(
                db, conv_id, user_msg_id, last_n=4,
            )
            if _ctx:
                followup_block = (
                    "\n\n## Önceki konuşma bağlamı (follow-up — kullanıcının "
                    "sorusu buna atıf olabilir):\n" + _ctx
                )

        gen_user_msg = (
            f"Soru: {payload.content}"
            + settings_block
            + style_block
            + followup_block
            + "\n\nVerilen kaynaklar:\n\n"
            + "\n\n---\n\n".join(chunk_blocks)
            + "\n\n"
            f"Yukarıdaki kaynakları kullanarak yukarıdaki kuralları izle ve "
            f"soruyu cevapla (citation [n] formatı ile). Soru önceki "
            f"konuşmaya atıfsa (örn. 'kaç yıl önce', 'o haber ne zamandı') "
            f"önceki bağlamı + kaynak özetlerini kullan."
        )

        # Chat provider + Wikipedia tool (#822 — LLM tool-use mimarisi)
        chat_provider = registry.route_for_tier(operation="chat", tier=user.tier)

        # #822 News-first STRICT (C2): news_query'de Wikipedia tool LLM'e
        # VERİLMEZ — "Trump bugün ne dedi?" haber kaynaklarından cevaplanır.
        # Diğer sınıflarda (general_knowledge/mixed/meta) LLM kaynak
        # yetersizse search_wikipedia tool'unu KENDİSİ çağırır.
        wikipedia_enabled = True
        try:
            from app.core.settings_store import settings_store
            wikipedia_enabled = await settings_store.get_bool(
                db, "wikipedia.enabled", True,
            )
        except Exception:
            wikipedia_enabled = True
        offer_tools = wikipedia_enabled and query_class != "news_query"
        tools_arg = CHAT_TOOL_DEFINITIONS if offer_tools else None

        # #822 KRİTİK — tool sunulduğunda sistem prompt'a tool talimatı
        # EKLENİR. Base prompt "kaynakta yoksa 'yok' de + Wikipedia
        # KULLANMA" diyor; bu tool ile çelişiyordu (LLM tool'u çağırmıyor,
        # refusal veriyordu — production'da gözlemlendi). TOOL_USE_INSTRUCTION
        # bu davranışı tool çağrısına yönlendirir, halüsinasyon korumasını
        # bozmadan.
        sys_prompt = SYSTEM_PROMPT_CHAT_ANSWER
        if offer_tools:
            sys_prompt = SYSTEM_PROMPT_CHAT_ANSWER + TOOL_USE_INSTRUCTION

        base_messages = [
            ProviderMessage(role="system", content=sys_prompt),
            ProviderMessage(role="user", content=gen_user_msg),
        ]

        accumulated = ""
        used_wikipedia = False

        # ---- Aşama 1: tool-decision (non-streaming) ----
        tool_decision = None
        try:
            tool_decision = await chat_provider.generate_text(
                messages=base_messages,
                max_tokens=1500,
                temperature=0.7,
                tools=tools_arg,
                tool_choice="auto",
            )
        except Exception as exc:
            logger.warning("chat tool-decision generate failed: %s", exc)

        if tool_decision is not None and tool_decision.tool_calls:
            # LLM kaynak yetersiz buldu, Wikipedia'ya başvurmak istiyor.
            yield _log_step(
                "tool_use",
                "Haber kaynakları yetersiz — Wikipedia'ya başvuruluyor",
            )
            convo_messages = list(base_messages)
            convo_messages.append(
                ProviderMessage(
                    role="assistant",
                    content=tool_decision.text or "",
                    tool_calls=tool_decision.tool_calls,
                )
            )
            wiki_sources: list[dict[str, Any]] = []
            for tc in tool_decision.tool_calls:
                executor = CHAT_TOOLS.get(tc.name)
                if executor is None:
                    tool_result = f"Bilinmeyen tool: {tc.name}"
                else:
                    try:
                        tool_result, tc_sources = await executor(tc.arguments)
                        wiki_sources.extend(tc_sources)
                    except Exception as _texc:
                        logger.warning(
                            "tool exec failed (%s): %s", tc.name, _texc,
                        )
                        tool_result = f"Tool hatası: {_texc}"
                convo_messages.append(
                    ProviderMessage(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tc.id,
                    )
                )
            if wiki_sources:
                used_wikipedia = True
                sources_used = wiki_sources
                for s in wiki_sources:
                    yield _sse("source_discovered", s)

            # ---- Aşama 2: final cevap (streaming, tool sonucuyla) ----
            try:
                async for stream_chunk in chat_provider.generate_text_stream(
                    messages=convo_messages,
                    max_tokens=1500,
                    temperature=0.7,
                ):
                    delta = getattr(stream_chunk, "delta_text", None) or ""
                    if not delta:
                        continue
                    accumulated += delta
                    yield _sse("chunk", {"delta": delta})
            except Exception as exc:
                logger.warning("chat final stream failed: %s", exc)
                fb = await chat_provider.generate_text(
                    messages=convo_messages,
                    max_tokens=1500,
                    temperature=0.7,
                )
                accumulated = fb.text
                yield _sse("chunk", {"delta": accumulated})
        else:
            # Tool çağrısı yok — LLM haber kaynaklarıyla cevap verdi.
            if tool_decision is not None and tool_decision.text:
                accumulated = tool_decision.text
                yield _sse("chunk", {"delta": accumulated})
            else:
                # tool_decision başarısız — streaming fallback (toolsuz)
                try:
                    async for stream_chunk in chat_provider.generate_text_stream(
                        messages=base_messages,
                        max_tokens=1500,
                        temperature=0.7,
                    ):
                        delta = getattr(stream_chunk, "delta_text", None) or ""
                        if not delta:
                            continue
                        accumulated += delta
                        yield _sse("chunk", {"delta": delta})
                except Exception as exc:
                    logger.warning("chat stream fallback failed: %s", exc)
                    fb = await chat_provider.generate_text(
                        messages=base_messages,
                        max_tokens=1500,
                        temperature=0.7,
                    )
                    accumulated = fb.text
                    yield _sse("chunk", {"delta": accumulated})

        # ---- Step 6: Persist assistant message ----
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

        # Telemetri — done event'a confidence + query_class (routing YOK).
        final_confidence = None
        if conf is not None:
            try:
                final_conf = compute_retrieval_confidence(
                    plan_result, chunk_proto,
                    weights=confidence_weights,
                    answer_text=accumulated,
                )
                final_confidence = {
                    "score": final_conf.score,
                    "citation_density": final_conf.citation_density,
                    "missing": final_conf.missing,
                }
            except Exception as _exc:
                logger.warning("post-gen confidence compute failed: %s", _exc)

        # #822 News-first STRICT telemetri: news_query'de tool verilmediği
        # için used_wikipedia=True olmamalı. Olursa contamination (bug işareti).
        if query_class == "news_query" and used_wikipedia:
            logger.error(
                "contamination: news_query Wikipedia kullandı conv=%s", conv_id,
            )
        elif query_class == "news_query":
            logger.info(
                "news_first_strict_ok: conv=%s wikipedia_used=False", conv_id,
            )

        yield _sse("done", {
            "conversation_id": str(conv_id),
            "user_message_id": str(user_msg_id),
            "assistant_message_id": str(assistant_msg_id),
            "is_followup": is_related,
            "similarity": round(similarity, 3),
            "query_class": query_class if conf is not None else None,
            "confidence": final_confidence,
            "used_wikipedia": used_wikipedia,
        })

    except Exception as exc:
        logger.exception("chat stream failed: %s", exc)
        yield _sse("error", {
            "code": "STREAM_ERROR",
            "title": "Akış hatası",
            "reason": str(exc)[:200],
        })
        yield _sse("done", {"status": "failed"})
