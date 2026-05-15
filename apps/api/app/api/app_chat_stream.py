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
import re
import uuid
from datetime import UTC, datetime, timedelta
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

# #851 — citation token (yapısal işaret: [1], [12], legacy [W1]). Cevapta
# citation VAR ama hiçbir tool kaynak üretmediyse → kanıtlı sahte (C1
# ihlali, bellekten cevap). Bu YAPISAL referans-bütünlüğü kontrolüdür —
# #819'daki "serbest metin ifade eşleştirme" anti-pattern'i DEĞİL.
_CITE_TOKEN_RE = re.compile(r"\[W?\d{1,3}\]")

# #854 — provider/tool çağrı latency tavanları. Provider default 60s
# (×retry) tek bir spike'ta tüm stream'i bloke ediyordu (conv 304bed5b
# condense 43s). Yardımcı/orkestrasyon adımları SIKI sınırlanır, zarif
# degrade edilir (Perplexity/ChatGPT deseni: hung upstream UI'ı asmaz).
_TOOL_ROUND_TIMEOUT_S = 30   # her agentic tur LLM kararı (tool-decision)
_TOOL_EXEC_TIMEOUT_S = 20    # tek tool yürütme (search_news/wikipedia)
MAX_TOOL_ROUNDS = 3          # agentic döngü max tur (admin-tunable, #848/#854)


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


async def _simulate_stream(text: str):
    """Non-streaming cevabı kelime gruplarıyla yield — akış hissi (#840).

    DeepSeek streaming+tools `<｜DSML｜tool_calls>` token bug'ı (#840)
    yüzünden tool-decision non-streaming. Tool çağrılmazsa cevap zaten
    üretilmiş; kelime gruplarıyla parça parça gönderilir (ekstra LLM
    call yok). Gerçek token streaming sadece tool path'inde (Aşama 2).
    """
    words = text.split(" ")
    group: list[str] = []
    for i, w in enumerate(words):
        group.append(w)
        if len(group) >= 4 or i == len(words) - 1:
            yield " ".join(group) + ("" if i == len(words) - 1 else " ")
            group = []
            await asyncio.sleep(0.018)  # akış hissi (~doğal hız)


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


async def _tracked_chat_generate(provider, *, user_id, totals: dict, **gen_kwargs):
    """`generate_text` + `provider_call_logs(operation='chat')` telemetri.

    #audit (2026-05-15): chat hattı HİÇ ölçülmüyordu — istek başına 3+ LLM
    çağrısı (condense / her agentic tur / forced-final) `track_provider_call`
    ile sarılmıyordu → token/maliyet/latency kör. Her çağrı KENDİ kısa
    session'ında loglanır + explicit commit; request `db` stream'den ÖNCE
    commit edildiği için kullanılamaz. `totals` record_usage için biriktirir.
    generate_text hata verirse track_provider_call success=False loglar +
    re-raise (mevcut çağrı-yeri degrade mantığı korunur); finally yine commit.
    """
    from app.core.cost_tracker import track_provider_call
    from app.core.db import get_session_factory

    prov_name = getattr(provider, "name", "unknown")
    factory = get_session_factory()
    async with factory() as _tdb:
        try:
            async with track_provider_call(
                db=_tdb, provider=prov_name, operation="chat", user_id=user_id,
            ) as _tr:
                res = await provider.generate_text(**gen_kwargs)
                _tr.record(
                    input_tokens=res.input_tokens,
                    output_tokens=res.output_tokens,
                    cached_tokens=getattr(res, "cached_input_tokens", 0),
                    model=res.model,
                    cost_usd=res.cost_usd,
                )
            totals["input_tokens"] += res.input_tokens or 0
            totals["output_tokens"] += res.output_tokens or 0
            totals["cached_tokens"] += getattr(res, "cached_input_tokens", 0) or 0
            if res.cost_usd is not None:
                totals["cost_usd"] += float(res.cost_usd)
            totals["model"] = res.model or totals.get("model")
            totals["provider"] = prov_name
            totals["calls"] = totals.get("calls", 0) + 1
            return res
        finally:
            try:
                await _tdb.commit()
            except Exception as _cexc:  # pragma: no cover
                logger.warning("chat telemetry commit failed: %s", _cexc)


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
    # Lazy imports — #845 agentic: planner/retrieval/confidence artık
    # search_news tool'unun İÇİNDE (kalite makinesi sarmalandı).
    from app.core.chat_tools import (
        CHAT_TOOL_DEFINITIONS,
        SEARCH_NEWS_TOOL,
        execute_search_news,
        execute_search_wikipedia,
    )
    from app.providers.base import Message as ProviderMessage
    from app.prompts.chat_answer import render_nodrat_agent_prompt

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
            # #854 — condense latency tavanı admin-tunable (constant fallback)
            _cond_to = 6
            try:
                from app.core.settings_store import settings_store
                _cond_to = await settings_store.get_int(
                    db, "chat.condense_timeout_s", 6,
                )
            except Exception:
                _cond_to = 6
            _cond_to = max(2, min(_cond_to, 20))
            # #854 — condense prompt admin-tunable (prompts_store; kod
            # default fallback → DB override yoksa davranış değişmez).
            _rw_tmpl = None
            try:
                from app.core.prompts_store import prompts_store
                from app.prompts.query_rewrite import REWRITE_SYSTEM_PROMPT
                _rw_tmpl = await prompts_store.get(
                    db, "chat_query_rewrite", REWRITE_SYSTEM_PROMPT,
                )
            except Exception:
                _rw_tmpl = None
            _t_rw = asyncio.get_event_loop().time()
            rewritten = await condense_followup_query(
                _rw_provider, _rw_ctx, payload.content,
                timeout_s=_cond_to,
                system_prompt=_rw_tmpl,
            )
            if rewritten and rewritten.strip():
                effective_query = rewritten.strip()
                yield _log_step(
                    "query_rewrite",
                    f"Bağlamlı sorgu: {effective_query[:80]}",
                    int((asyncio.get_event_loop().time() - _t_rw) * 1000),
                )

        # ---- #845: Agentic orkestrasyon — ön-retrieval KALDIRILDI ----
        # Eski mimari HER sorguda planner+retrieval+confidence çalıştırıp
        # sonra Wikipedia tool kararı veriyordu → "merhaba sen kimsin" bile
        # retrieval tetikliyordu; haber arşivi tool gibi konumlanmamıştı.
        # Yeni: LLM iki tool'u (search_news BİRİNCİL + search_wikipedia)
        # orkestre eder. Planner+embed+hybrid_search artık search_news
        # tool'unun İÇİNDE (kalite makinesi DEĞİŞMEDİ — sarmalandı). Meta/
        # selamlama/kimlik → LLM tool çağırmadan doğrudan yanıt. condense
        # (#833) korunur: effective_query bağlamlı standalone sorgu.
        query_class = "conversational"   # tool çalışırsa news_meta'dan güncellenir
        news_meta: dict[str, Any] = {}
        all_sources: list[dict[str, Any]] = []   # taranan tüm kaynaklar (collapsed)
        sources_used: list[dict[str, Any]] = []  # cevapta gerçekten cite edilen

        # #854 — agentic tunable'lar admin-tunable (settings_store; constant
        # fallback). Tek try-blok: DB hatası → güvenli default'lar.
        max_tool_rounds = MAX_TOOL_ROUNDS
        tool_round_timeout = _TOOL_ROUND_TIMEOUT_S
        tool_exec_timeout = _TOOL_EXEC_TIMEOUT_S
        try:
            from app.core.settings_store import settings_store
            content_top_k = await settings_store.get_int(
                db, "retrieval.content_top_k", 5,
            )
            max_tool_rounds = await settings_store.get_int(
                db, "chat.max_tool_rounds", MAX_TOOL_ROUNDS,
            )
            tool_round_timeout = await settings_store.get_int(
                db, "chat.tool_round_timeout_s", _TOOL_ROUND_TIMEOUT_S,
            )
            tool_exec_timeout = await settings_store.get_int(
                db, "chat.tool_exec_timeout_s", _TOOL_EXEC_TIMEOUT_S,
            )
        except Exception:
            content_top_k = 5
        content_top_k = max(3, min(content_top_k, 15))
        max_tool_rounds = max(1, min(max_tool_rounds, 6))
        tool_round_timeout = max(10, min(tool_round_timeout, 60))
        tool_exec_timeout = max(5, min(tool_exec_timeout, 45))
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

        # #845 — Agentic kullanıcı mesajı: SADECE soru + bağlam + (varsa)
        # ayar/stil + follow-up bağlamı. HABER CHUNK'LARI YOK — onları LLM
        # search_news tool'uyla kendisi getirir. condense (#833) sayesinde
        # effective_query bağlamlı standalone (follow-up'ta da doğru).
        gen_user_msg = (
            f"Soru: {effective_query}"
            + settings_block
            + style_block
            + followup_block
        )

        chat_provider = registry.route_for_tier(operation="chat", tier=user.tier)

        # wikipedia.enabled=False → sadece search_news sunulur (haber arşivi
        # her zaman birincil; Wikipedia opsiyonel ikincil tool).
        wikipedia_enabled = True
        try:
            from app.core.settings_store import settings_store
            wikipedia_enabled = await settings_store.get_bool(
                db, "wikipedia.enabled", True,
            )
        except Exception:
            wikipedia_enabled = True
        tools_arg = (
            CHAT_TOOL_DEFINITIONS if wikipedia_enabled else [SEARCH_NEWS_TOOL]
        )

        # #845 — Güncel tarih ENJEKTE (zaman bug fix). Eski mimaride answer
        # LLM'e tarih HİÇ verilmiyordu → model "bugünü" eğitim önbilgisinden
        # uyduruyordu ("Nisan 2025"). now UTC; TR yerel UTC+3.
        _now_tr = now + timedelta(hours=3)
        _tr_months = [
            "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
        ]
        _tr_days = [
            "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma",
            "Cumartesi", "Pazar",
        ]
        current_date_str = (
            f"{_now_tr.day} {_tr_months[_now_tr.month]} {_now_tr.year}, "
            f"{_tr_days[_now_tr.weekday()]}"
        )
        # #854 — Nodrat agent prompt admin-tunable (prompts_store; kod
        # default fallback → DB override yoksa davranış değişmez).
        _nodrat_tmpl = None
        try:
            from app.core.prompts_store import prompts_store
            from app.prompts.chat_answer import SYSTEM_PROMPT_NODRAT_AGENT
            _nodrat_tmpl = await prompts_store.get(
                db, "chat_nodrat_agent", SYSTEM_PROMPT_NODRAT_AGENT,
            )
        except Exception:
            _nodrat_tmpl = None
        sys_prompt = render_nodrat_agent_prompt(
            current_date_str, template=_nodrat_tmpl,
        )

        base_messages = [
            ProviderMessage(role="system", content=sys_prompt),
            ProviderMessage(role="user", content=gen_user_msg),
        ]

        accumulated = ""
        used_wikipedia = False

        # Per-request tool dispatch — search_news db/now/user closure ile
        # bind (#845). #851: cite_start ile GLOBAL benzersiz citation
        # (tek `[n]` namespace; multi-round'da aynı tool 2 kez çağrılsa
        # bile token çakışmaz — kaynak mis-attribution kökü çözüldü).
        async def _dispatch(name: str, args: dict[str, Any], cite_start: int):
            if name == "search_news":
                return await execute_search_news(
                    args, db=db, now=now, user=user,
                    query_vec_hint=query_vec, content_top_k=content_top_k,
                    cite_start=cite_start,
                )
            if name == "search_wikipedia":
                txt, srcs = await execute_search_wikipedia(
                    args, cite_start=cite_start,
                )
                return txt, srcs, {}
            return f"Bilinmeyen tool: {name}", [], {}

        # ---- #848 Çok-turlu agentic tool döngüsü ----
        # Tek-tur (Aşama1 tools → Aşama2 TOOLSUZ) LLM'i tuzağa
        # düşürüyordu: search_news alakasız dönünce search_wikipedia
        # çağıramayıp belleğe + sahte [W1] citation'a düşüyordu (C1
        # ihlali, conv 377ba71a). Gerçek agentic: her tur sonrası LLM
        # tool sonuçlarıyla TEKRAR karar verir (başka tool veya cevap).
        # Tool turları NON-streaming (#840 — DeepSeek streaming+tools
        # `<｜DSML｜tool_calls>` özel token bug'ı; non-streaming
        # generate_text yapısal tool_calls döndürür, #823-#835 kanıt).
        # Final cevap = LLM'in tool ÇAĞIRMADAN döndüğü tur metni →
        # _simulate_stream (ekstra LLM call yok, akış hissi). max_tool_rounds
        # admin-tunable (#854; default 3 = search_news→wikipedia→cevap).
        convo_messages = list(base_messages)
        final_text = ""
        tool_round = 0
        # #audit — chat LLM telemetri biriktirici (record_usage için)
        usage_totals: dict = {
            "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0,
            "cost_usd": 0.0, "model": None, "provider": None, "calls": 0,
        }
        cite_n = 0          # #851 — döngü boyunca global citation sayacı
        next_tool_choice = "auto"
        c1_forced_once = False   # #851 — C1 backstop en fazla 1 kez
        while tool_round < max_tool_rounds:
            try:
                decision = await _tracked_chat_generate(
                    chat_provider,
                    user_id=user.id,
                    totals=usage_totals,
                    messages=convo_messages,
                    max_tokens=1500,
                    temperature=0.7,
                    tools=tools_arg,
                    tool_choice=next_tool_choice,
                    timeout=tool_round_timeout,
                )
            except Exception as exc:
                logger.warning(
                    "chat tool-round %d failed: %s", tool_round, exc,
                )
                break
            next_tool_choice = "auto"
            tcs = decision.tool_calls
            if not tcs:
                candidate = decision.text or ""
                # #851 — C1 referans-bütünlüğü backstop: cevapta citation
                # token VAR ama hiçbir tool kaynak üretmemiş → LLM
                # substantive soruyu BELLEKTEN cevaplayıp sahte [n]
                # iliştirmiş (conv 2955ab58 "kurt russel hayatta mı" →
                # sahte [W1] + "— Nodrat"). Yapısal invariant (ifade
                # eşleştirme #819 DEĞİL). Bir kez tool_choice="required"
                # ile düzeltici tur zorla. Selamlama/kimlik (citation
                # YOK) etkilenmez — doğrudan servis edilir.
                if (
                    not all_sources
                    and not c1_forced_once
                    and _CITE_TOKEN_RE.search(candidate)
                ):
                    c1_forced_once = True
                    next_tool_choice = "required"
                    convo_messages.append(
                        ProviderMessage(
                            role="user",
                            content=(
                                "Var olmayan bir kaynak ([n]) gösterdin ama "
                                "hiçbir araç çağırmadın — bu sahte kaynaktır. "
                                "Bu soruyu yanıtlamak için MUTLAKA uygun "
                                "aracı çağır (güncel→search_news, sabit/"
                                "biyografik→search_wikipedia). Kaynak "
                                "bulunamazsa citation YAZMA."
                            ),
                        )
                    )
                    continue
                # LLM tool çağırmadı, citation yok → meşru konuşma cevabı
                # (selamlama/kimlik/meta) VEYA önceki turlarda grounding.
                final_text = candidate
                break
            tool_round += 1
            tool_names = ",".join(tc.name for tc in tcs)
            yield _log_step(
                "tool_use",
                f"Araç çağrılıyor: {tool_names}"
                + (f" (tur {tool_round})" if tool_round > 1 else ""),
            )
            convo_messages.append(
                ProviderMessage(
                    role="assistant", content="", tool_calls=tcs,
                )
            )
            for tc in tcs:
                try:
                    # #854 — tool yürütme latency tavanı (search_wikipedia
                    # Wikidata SPARQL / lang-fallback stack'lenebilir).
                    # Timeout → boş sonuç; LLM diğer tur'da toparlar.
                    tool_result, tc_sources, tc_meta = await asyncio.wait_for(
                        _dispatch(tc.name, tc.arguments, cite_n),
                        timeout=tool_exec_timeout,
                    )
                except (Exception, asyncio.TimeoutError) as _texc:
                    logger.warning("tool exec failed (%s): %s", tc.name, _texc)
                    tool_result, tc_sources, tc_meta = (
                        f"'{tc.name}' aracı zaman aşımına uğradı veya hata "
                        f"verdi; bu sonuç olmadan devam et.", [], {},
                    )
                if tc.name == "search_news" and tc_meta:
                    query_class = tc_meta.get("query_class") or query_class
                    news_meta = tc_meta
                if tc.name == "search_wikipedia" and tc_sources:
                    used_wikipedia = True
                cite_n += len(tc_sources)   # #851 global sayaç ilerlet
                all_sources.extend(tc_sources)
                for s in tc_sources:
                    yield _sse("source_discovered", s)
                convo_messages.append(
                    ProviderMessage(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tc.id,
                    )
                )
            # Döngü: LLM tool sonuçlarıyla TEKRAR karar verir — sonuç
            # yetersizse diğer tool'u çağırabilir (search_news↔wikipedia).

        # MAX tur dolduysa LLM hâlâ tool istiyordu → zorla cevap. #860:
        # explicit "ARTIK TOOL ÇAĞIRMA, eldeki sonuçlardan SADECE cevabı
        # yaz" talimatı + toolsuz çağrı. DeepSeek momentum'la yine DSML
        # basabilir (#857/#860) → generate_text adapter parse temizler;
        # yine de boş kalırsa scope-aware fallback (boş cevap servis etme).
        if not final_text:
            convo_messages.append(
                ProviderMessage(
                    role="user",
                    content=(
                        "Yeterli bilgi toplandı. ARTIK ARAÇ ÇAĞIRMA. "
                        "Yukarıdaki araç sonuçlarından kullanıcının "
                        "sorusuna SADECE nihai cevabı yaz (citation [n] "
                        "ile). Tool çağrısı / DSML üretme."
                    ),
                )
            )
            try:
                fb = await _tracked_chat_generate(
                    chat_provider,
                    user_id=user.id,
                    totals=usage_totals,
                    messages=convo_messages,
                    max_tokens=1500,
                    temperature=0.7,
                    timeout=tool_round_timeout,
                )
                final_text = fb.text or ""
            except Exception as exc:
                logger.warning("chat final answer failed: %s", exc)
                final_text = ""

        # #860 — SON GÜVENLİK AĞI: provider format varyasyonu parser'ı
        # atlatsa bile ham DSML markup ASLA kullanıcıya gitmez.
        from app.providers.deepseek import strip_dsml_markup
        final_text = strip_dsml_markup(final_text)
        if not final_text.strip():
            # Tüm turlar tool istedi, temiz cevap çıkmadı → dürüst
            # scope-aware (boş ekran / ham DSML yerine).
            final_text = (
                "Bu soruya kaynaklardan net bir yanıt oluşturamadım. "
                "Soruyu biraz daha belirginleştirir misin?"
            )

        # Final cevap simüle-stream (akış hissi; #840 DSML yok).
        accumulated = final_text
        if accumulated:
            async for piece in _simulate_stream(accumulated):
                yield _sse("chunk", {"delta": piece})

        # ---- #845 cited-only kaynaklar (#851: tek `[n]` namespace) ----
        # sources_used = cevapta GERÇEKTEN cite edilen ([n] accumulated'da
        # geçen; global benzersiz token → mis-attribution yok).
        # sources_considered = taranan tüm kaynaklar (UI'da collapsed).
        # Citation-marker tespiti display filtresidir — #819'daki "LLM
        # çıktısından KARAR çıkarma" anti-pattern'i DEĞİL.
        sources_used = [
            s for s in all_sources
            if s.get("cite") and s["cite"] in accumulated
        ]
        sources_considered = all_sources

        # ---- Step 6: Persist assistant message ----
        from app.core.db import get_session_factory
        factory = get_session_factory()
        async with factory() as persist_db:
            assistant_msg = Message(
                conversation_id=conv_id,
                role="assistant",
                content=accumulated,
                sources_used=sources_used,
                sources_considered=sources_considered or None,
                thinking_steps=thinking_log,
            )
            persist_db.add(assistant_msg)
            await persist_db.commit()
            await persist_db.refresh(assistant_msg)
            assistant_msg_id = assistant_msg.id

            # #audit — usage_events ledger (record_usage repo genelinde HİÇ
            # çağrılmıyordu → chat için billing/quota audit kördü). Mesaj
            # zaten commit'li; bu best-effort ek (hata mesajı kaybetmez).
            try:
                from app.core.quota import record_usage

                await record_usage(
                    persist_db,
                    user_id=user.id,
                    event_type="generation",
                    provider=usage_totals.get("provider"),
                    model=usage_totals.get("model"),
                    input_tokens=usage_totals["input_tokens"] or None,
                    output_tokens=usage_totals["output_tokens"] or None,
                    cost_usd=usage_totals["cost_usd"] or None,
                    metadata={
                        "conversation_id": str(conv_id),
                        "llm_calls": usage_totals.get("calls", 0),
                        "cached_tokens": usage_totals.get("cached_tokens", 0),
                    },
                )
                await persist_db.commit()
            except Exception as _uexc:  # pragma: no cover
                logger.warning("chat record_usage failed: %s", _uexc)

        yield _sse("done", {
            "conversation_id": str(conv_id),
            "user_message_id": str(user_msg_id),
            "assistant_message_id": str(assistant_msg_id),
            "is_followup": is_related,
            "similarity": round(similarity, 3),
            "query_class": query_class,
            "used_wikipedia": used_wikipedia,
            "sources_used_count": len(sources_used),
            "sources_considered_count": len(sources_considered),
        })

    except Exception as exc:
        logger.exception("chat stream failed: %s", exc)
        yield _sse("error", {
            "code": "STREAM_ERROR",
            "title": "Akış hatası",
            "reason": str(exc)[:200],
        })
        yield _sse("done", {"status": "failed"})
