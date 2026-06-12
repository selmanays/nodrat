"""Research message streaming — context-aware (#793 S2).

Endpoint: POST /research/conversations/{id}/messages

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
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Internal helpers (PR-B internal split — T6 #1085 P6).
# Pure SSE / streaming / telemetry helpers `_research_stream_helpers.py`'a
# taşındı (davranış değişmedi; pure refactor). Public surface re-export
# ile `app.api.app_research_stream` üzerinden korunur — caller'lar
# (test'ler dahil) etkilenmez.
from app.api._research_stream_context import _prepare_research_context
from app.core.db import get_db
from app.modules.accounts.deps import get_current_user
from app.modules.accounts.models import User
from app.modules.billing.services.quota import QuotaExceeded, enforce_quota
from app.modules.conversations.models import Conversation, Message
from app.modules.generations.citation import (
    _CITATION_GAP_NUDGE,
    _cite_to_int,
    _cited_numbers,
    _is_substantive,
    _maybe_reframe_for_faithfulness,
    _should_force_citation_gap_retry,
)
from app.modules.generations.followup import (
    _FOLLOWUP_ENABLED,
    _FOLLOWUP_TIMEOUT_S,
    _generate_followups,
)
from app.modules.generations.llm.tracked_chat import _tracked_chat_generate
from app.modules.generations.services.conversation_context import (
    detect_followup_relatedness,
    get_last_assistant_message,
    serialize_embedding,
)
from app.modules.generations.streaming.helpers import (
    _log_coverage_gap,
    _simulate_stream,
    _sse,
)
from app.providers.registry import bootstrap_default_providers, registry

# Re-export public + private surface for backward-compat (T6 P6 PR-B split).
# `__all__` ruff F401 unused-import'u önler.
__all__ = [
    "_log_coverage_gap",
    "_simulate_stream",
    "_sse",
]

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
_TOOL_ROUND_TIMEOUT_S = 30  # her agentic tur LLM kararı (tool-decision)
_TOOL_EXEC_TIMEOUT_S = 20  # tek tool yürütme (search_news/wikipedia)
MAX_TOOL_ROUNDS = 3  # agentic döngü max tur (admin-tunable, #848/#854)


# ============================================================================
# Pydantic schemas
# ============================================================================


class ResearchMessageCreate(BaseModel):
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


async def _resolve_style_block(
    db: AsyncSession,
    user: User,
    style_profile_id: uuid.UUID,
) -> str:
    """Style profile rules_json'u prompt'a uygun text blok'a çevir.

    Pro+ paywall: tier kontrolü yapılır; başarısızsa boş string döner.
    """
    # T8-6: facade import (not direct submodule path) — survives sys.modules
    # purge in test_module_init_lazy parametric tests. Direct path re-import
    # triggers duplicate Table registration when style_profiles.* package is
    # purged by earlier tests. Facade `app.models` caches the class binding.
    from app.models import StyleProfile

    # Pro tier check (gevşek — başarısızlık ölümcül değil)
    if user.tier not in ("pro", "agency_seat"):
        return ""

    sp = (
        await db.execute(
            select(StyleProfile).where(
                StyleProfile.id == style_profile_id,
                StyleProfile.user_id == user.id,
                StyleProfile.status == "ready",
            )
        )
    ).scalar_one_or_none()

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


# #1067 RC3-B v1 (LLM-verifier `_verify_primary_grounding` +
# `_parse_faithfulness_verdict` + `_FAITHFULNESS_VERIFIER_PROMPT`) prod'da
# 4/8 yanlış-pozitif yaptı (#1076 — agenda/aggregate/topic-partial
# /single-direct sınıflarında multi-claim modellemiyordu; NLP-
# faithfulness LLM-only judgment kanıtlı calibration-fragile). v2 (bu
# dosyanın başındaki `_has_reconstruction_marker` saf detektörü) ile
# YERİNE GEÇİRİLDİ: deterministik, cheap (LLM call YOK), 4 yanlış-
# pozitifte ZERO-fire. Detay: [[wiki:research-cited-only-hard-invariant]]
# (RC3-B v2 bölümü).


# ============================================================================
# Endpoint
# ============================================================================


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Yeni research mesajı (SSE streaming, context-aware) — #793 S2",
)
async def post_research_message(
    payload: ResearchMessageCreate,
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

    # 1b) Tek-tur invariantı (pivot: 1 conversation = 1 araştırma).
    # Backend-enforced no-thread: conversation'da ZATEN mesaj varsa yeni
    # mesaj kabul edilmez (client yeni araştırma oturumu açmalı). Frontend
    # (#1045) her sorguda yeni conversation açtığı için normal akışta
    # TETİKLENMEZ — bu, herhangi bir client için YAPISAL garanti (legacy
    # 4-mesajlı thread'lerin kökü tam buydu). Flag default-ON = pivot
    # standardı ("thread olmamalı"); runtime kapatılabilir (#854).
    from app.shared.runtime_config.settings_store import settings_store as _ss_guard

    if await _ss_guard.get_bool(db, "research.single_turn_enforced", True):
        _existing = await db.scalar(
            select(Message.id).where(Message.conversation_id == conv.id).limit(1)
        )
        if _existing is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "RESEARCH_ALREADY_COMPLETED",
                    "title": "Bu araştırma tamamlandı",
                    "message": (
                        "Her sorgu bağımsız bir araştırmadır. Yeni "
                        "sorgu için yeni araştırma oturumu açın."
                    ),
                },
            )

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
    query_embed_bytes = serialize_embedding(query_vec) if query_vec is not None else None

    # 4) Relatedness check (önceki user message ile)
    is_related = False
    similarity = 0.0
    prev_assistant_sources: list[dict] | None = None

    if query_vec is not None:
        is_related, similarity, _prev_user = await detect_followup_relatedness(
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
                    "research followup detected (sim=%.3f): %d prev sources available",
                    similarity,
                    len(prev_assistant_sources),
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
    msg_count = (await db.execute(select(Message).where(Message.conversation_id == conv.id))).all()
    if len(msg_count) == 1 and conv.title == "Yeni sohbet":
        conv.title = payload.content[:80].strip()

    await db.commit()

    user_msg_id = user_msg.id
    now = datetime.now(UTC)

    return StreamingResponse(
        _research_stream_body(
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
# Query decomposition wiring (#619)
# ============================================================================


def _parse_decomposition_allowlist(raw: str) -> frozenset[str]:
    """#619 PR-E — CSV user-id allowlist parse (canary gate). Saf, DB-suz, test edilebilir.

    Geçerli UUID token'ları canonical (lowercase) forma normalize edilip set'e alınır;
    boş / whitespace / geçersiz token SESSİZCE atlanır (asla raise etmez). Boş/None
    girdi → boş set (→ kimse allowlist'te, gate kapalı). Global-OFF + boş allowlist =
    byte-identical (decompose çağrılmaz).
    """
    out: set[str] = set()
    for tok in (raw or "").split(","):
        t = tok.strip()
        if not t:
            continue
        try:
            out.add(str(uuid.UUID(t)))  # canonical lowercase; geçersiz → ValueError
        except (ValueError, AttributeError, TypeError):
            continue  # invalid token → güvenli atla
    return frozenset(out)


def _resolve_decomposition_gate(
    *, global_enabled: bool, allowlist_raw: str, user_id: str
) -> tuple[bool, str]:
    """#619 PR-E — (enabled, cohort) hesapla. Saf, DB-suz, test edilebilir.

    - global ON → (True, "global") — tüm trafik (allowlist yok sayılır).
    - global OFF + user_id ∈ allowlist → (True, "allowlist") — canary.
    - global OFF + eşleşme yok → (False, "baseline") — decompose çağrılmaz (byte-identical).
    """
    if global_enabled:
        return True, "global"
    if user_id in _parse_decomposition_allowlist(allowlist_raw):
        return True, "allowlist"
    return False, "baseline"


def _decomposition_telemetry(result, duration_ms: int, *, cohort: str = "global") -> dict[str, Any]:
    """#619 PR-5 — PII-suz decomposition telemetry payload.

    Yalnız metrik (method / sub_query_count / llm_used / fallback_reason /
    duration_ms / cohort); query veya sub-query METNİ İÇERMEZ (PII/sensitive yok).
    #619 PR-E: ``cohort`` ∈ {baseline, allowlist, global} — yalnız canary kohort
    etiketi; user_id / email / PII İÇERMEZ.
    """
    return {
        "method": result.method,
        "sub_query_count": len(result.sub_queries),
        "llm_used": result.method == "llm",
        "fallback_reason": result.fallback_reason,
        "duration_ms": duration_ms,
        "cohort": cohort,
    }


def _search_telemetry_entry(
    tool_name: str,
    arguments: dict[str, Any] | None,
    meta: dict[str, Any] | None,
    *,
    round_no: int,
    source_count: int,
    error: bool = False,
) -> dict[str, Any]:
    """#1483 — PII-bilinçli search-arg telemetry kaydı (sabit key-set).

    ``query`` (LLM tool-call argümanı) ve ``topic`` (planner dönüşümü)
    ``redact()`` + 200-char truncate ile yazılır; user_id/email/raw-PII
    ASLA. Yalnız thinking_steps metadata'sına gider (DB+SSE, owner-only) —
    log-surface'e YAZILMAZ. ``error=True`` yalnız timeout/exception
    (0-sonuç başarılı arama ``error=False`` + ``source_count=0``).
    """
    from app.core.pii import redact

    def _clean(value: Any) -> str | None:
        if not value or not isinstance(value, str):
            return None
        return redact(value).text[:200]

    meta = meta or {}
    return {
        "tool": tool_name,
        "round": round_no,
        "query": _clean((arguments or {}).get("query")),
        "topic": _clean(meta.get("topic")),
        "query_class": meta.get("query_class"),
        "chunk_count": meta.get("chunk_count"),
        "source_count": source_count,
        "error": error,
    }


def _build_decomposition_hint(sub_queries: list[str]) -> str:
    """#619 — alt-sorgu planını LLM tool-loop'una bağlam hint'i olarak çevir.

    LLM-driven (3b): deterministik retrieval YOK; LLM'e her alt-sorguyu
    search_news ile ayrı arama talimatı verilir (mevcut tool-loop korunur).
    """
    lines = "\n".join(f"- {sq}" for sq in sub_queries)
    return (
        "Bu araştırma sorgusu şu alt konulara ayrıldı. Her birini "
        "search_news ile AYRI AYRI ara, sonra bulguları birleştirip tek "
        f"yanıtta sentezle:\n{lines}"
    )


async def _decompose_for_research(query: str, provider, *, enabled: bool):
    """#619 flag-gated query decomposition. Kapalı/hata/tek-konu → None.

    ``enabled`` False → ``None`` (byte-identical no-op). Aksi halde primitive
    ``decompose_query`` (heuristic + LLM-fallback); herhangi beklenmedik hata →
    ``None`` (graceful degrade, baseline akış). Dönen ``DecompositionResult``;
    caller ``is_decomposed`` kontrol eder.
    """
    if not enabled:
        return None
    try:
        from app.prompts.query_decomposition import decompose_query

        return await decompose_query(query, provider=provider, llm_enabled=True)
    except Exception as exc:
        logger.warning("query decomposition wiring failed: %s", exc)
        return None


# ============================================================================
# Stream body
# ============================================================================


async def _research_stream_body(
    *,
    db: AsyncSession,
    user: User,
    conv_id: UUID,
    user_msg_id: UUID,
    payload: ResearchMessageCreate,
    query_vec: list[float] | None,
    is_related: bool,
    similarity: float,
    prev_sources: list[dict] | None,
    now: datetime,
) -> AsyncIterator[str]:
    """Research streaming akışı — thinking_step events + content stream + persist."""
    # Lazy imports — #845 agentic: planner/retrieval/confidence artık
    # search_news tool'unun İÇİNDE (kalite makinesi sarmalandı).
    from app.core.research_tools import (
        RESEARCH_TOOL_DEFINITIONS,
        SEARCH_NEWS_TOOL,
        execute_search_news,
        execute_search_wikipedia,
    )
    from app.prompts.research_answer import render_nodrat_agent_prompt
    from app.providers.base import Message as ProviderMessage

    thinking_log: list[dict[str, Any]] = []

    def _log_step(phase: str, detail: str, latency_ms: int = 0, **extra: Any) -> str:
        """Thinking step kaydet + SSE event olarak yield.

        #619 PR-5: opsiyonel ``extra`` telemetry metadata. ``extra`` boş ise
        entry DEĞİŞMEZ → mevcut tüm çağrılar byte-identical.
        """
        entry = {"phase": phase, "detail": detail, "latency_ms": latency_ms}
        if extra:
            entry.update(extra)
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
        # Context/condense preparation → api/_research_stream_context.py
        # (T6 P6 PR-C+2 extraction; behavior-preserving). Helper yield
        # ÜRETMEZ; aşağıdaki L719 query_rewrite thinking_step orchestrator'da
        # KALIR (koşul = contextualized; detail = effective_query; latency =
        # rewrite_latency_ms). recent_context downstream cevap prompt'unda
        # (#854) kullanılır.
        _ctx = await _prepare_research_context(db, conv_id, user_msg_id, user, payload)
        effective_query = _ctx.effective_query
        _contextualized = _ctx.contextualized
        _rw_ctx = _ctx.recent_context
        if _contextualized:
            yield _log_step(
                "query_rewrite",
                f"Bağlamlı sorgu: {effective_query[:80]}",
                _ctx.rewrite_latency_ms,
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
        query_class = "conversational"  # tool çalışırsa news_meta'dan güncellenir
        all_sources: list[dict[str, Any]] = []  # taranan tüm kaynaklar (collapsed)
        sources_used: list[dict[str, Any]] = []  # cevapta gerçekten cite edilen

        # #854 — agentic tunable'lar admin-tunable (settings_store; constant
        # fallback). Tek try-blok: DB hatası → güvenli default'lar.
        max_tool_rounds = MAX_TOOL_ROUNDS
        tool_round_timeout = _TOOL_ROUND_TIMEOUT_S
        tool_exec_timeout = _TOOL_EXEC_TIMEOUT_S
        # #1058 — cited-only HARD guard + contextualized-takip force-
        # retrieval. Default-ON (escape hatch); flag-off = eski davranış.
        _cited_only_strict = True
        _force_followup_retrieval = True
        # #1067 RC3 — dolaylı/tepki-kaynağı rekonstrüksiyon backstop.
        # Default-ON (escape hatch); flag-off = eski davranış (byte-eş).
        _faithfulness_guard = True
        # #1483 — search-arg telemetry flag (default False → byte-identical)
        _search_arg_telemetry = False
        # #1484 — citation-gap guard flag (default False → byte-identical)
        _citation_gap_guard = False
        # #619 — query decomposition flag (default False → byte-identical)
        _query_decomposition_enabled = False
        # #619 PR-E — canary kohortu (telemetry; PII-suz): baseline | allowlist | global
        _decomp_cohort = "baseline"
        try:
            from app.shared.runtime_config.settings_store import settings_store

            content_top_k = await settings_store.get_int(
                db,
                "retrieval.content_top_k",
                5,
            )
            max_tool_rounds = await settings_store.get_int(
                db,
                "research.max_tool_rounds",
                MAX_TOOL_ROUNDS,
            )
            tool_round_timeout = await settings_store.get_int(
                db,
                "research.tool_round_timeout_s",
                _TOOL_ROUND_TIMEOUT_S,
            )
            tool_exec_timeout = await settings_store.get_int(
                db,
                "research.tool_exec_timeout_s",
                _TOOL_EXEC_TIMEOUT_S,
            )
            _cited_only_strict = await settings_store.get_bool(
                db, "research.cited_only_strict", True
            )
            _force_followup_retrieval = await settings_store.get_bool(
                db, "research.followup_force_retrieval", True
            )
            _faithfulness_guard = await settings_store.get_bool(
                db, "research.faithfulness_guard_enabled", True
            )
            # #1483 — gözlem-only: tool-call arama telemetrisi (redacted)
            _search_arg_telemetry = await settings_store.get_bool(
                db, "research.search_arg_telemetry_enabled", False
            )
            # #1484 — citation-gap guard (kaynak-var/citation-yok retry)
            _citation_gap_guard = await settings_store.get_bool(
                db, "research.citation_gap_guard_enabled", False
            )
            # #619 PR-E — global ON → tüm trafik (global); aksi user.id allowlist'te
            # ise canary (allowlist); global OFF + boş/eşleşmeyen allowlist → baseline
            # (decompose çağrılmaz = byte-identical). Alınan = prod-3b LLM-driven (union YOK).
            _query_decomposition_enabled, _decomp_cohort = _resolve_decomposition_gate(
                global_enabled=await settings_store.get_bool(
                    db, "research.query_decomposition_enabled", False
                ),
                allowlist_raw=await settings_store.get(
                    db, "research.query_decomposition_allowlist", ""
                ),
                user_id=str(user.id),
            )
        except Exception:
            content_top_k = 5
        content_top_k = max(3, min(content_top_k, 15))
        max_tool_rounds = max(1, min(max_tool_rounds, 6))
        tool_round_timeout = max(10, min(tool_round_timeout, 60))
        tool_exec_timeout = max(5, min(tool_exec_timeout, 45))
        # S1D (#803) — ResearchSettings (output_type/tone/length/max_posts/style_profile)
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
            settings_block = "\n\n## Kullanıcı tercihleri (uy):\n" + "\n".join(settings_block_parts)

        # Style profile (Pro+ paywall — sadece resolved style profile rules)
        style_block = ""
        if payload.style_profile_id is not None:
            try:
                style_block = await _resolve_style_block(
                    db,
                    user,
                    payload.style_profile_id,
                )
            except Exception as _se:
                logger.warning("style profile resolve fail: %s", _se)

        # #888 — Sohbet hafızası `is_related`'a GÖRE GATE EDİLMEZ (kök
        # mimari fix). Eski kod followup_block'u yalnız is_related
        # (embedding cosine vs ÖNCEKİ user mesajı, eşik 0.65) True iken
        # ekliyordu. Kısa/konu-evrilen follow-up'lar eşiği geçemez →
        # is_related=False → answer LLM HİÇBİR önceki turu görmez → kendi
        # 2 tur önceki olgusuyla çelişir, kullanıcı düzeltince bile
        # tekrarlar (prod conv aaa6ed44: 5467↔Ahi Evran/Burdur flip-flop;
        # her tur "Yeni konu — sıfırdan"). condense (#833) bu dersi ZATEN
        # almıştı (kod: "is_related'a güvenmiyoruz; context VARSA hep") —
        # answer LLM'e de AYNISI: bir sohbet asistanı her zaman son N
        # turu görmeli; konuşma hafızası retrieval-reuse heuristic'ine
        # TABİ DEĞİLDİR (ayrı endişeler). `_rw_ctx` zaten koşulsuz
        # hesaplandı (Step 1.5) — tekrar DB sorgusu YOK (DRY). Çerçeve
        # "zayıf atıf ipucu" değil OTORİTER: #884 proaktif-tutarlılık
        # kuralı ancak LLM önceki turları GÖRÜRSE bağlayıcı olur.
        followup_block = ""
        if _rw_ctx:
            followup_block = (
                "\n\n## Bu sohbetin geçmişi (sen bu konuşmanın "
                "tarafısın; AŞAĞIDA SENİN daha önce verdiğin cevaplar "
                "da var). Daha önce kaynakla kurduğun olgularla TUTARLI "
                "ol: yeni araç sonucu öncekiyle çelişiyorsa sessizce "
                "farklı söyleme — açıkça uzlaştır/belirt (proaktif "
                "tutarlılık). Kullanıcı önceki bir cevabındaki çelişkiyi "
                "işaret ediyorsa bu geçmişe bakarak düzelt.\n"
                "**Sohbet akıcılığı (KRİTİK):** Önceki turlarda ZATEN "
                "verdiğin bilgiyi (kimlik tanıtımı, selamlama, anlattığın "
                "haber/olay/açıklama) AYNEN TEKRARLAMA — kullanıcı bunu "
                "görmüş durumda. Kullanıcının O ANKİ sorusuna odaklan: "
                "yeni bir şey soruyorsa yalnız ona yanıt ver; "
                "'devamı/peki/başka/daha' tipi follow-up'ta önceki "
                "cevabı baştan anlatma, ÜZERİNE EKLE (yalnız yeni/eksik "
                "kısım). Selamlama/kimlik bir kez yapılır; sonraki "
                "turlarda doğrudan içeriğe geç. Akıcı, devam eden tek "
                "bir konuşma gibi yanıtla — her turu sıfırdan başlatma:\n" + _rw_ctx
            )

        # #845 — Agentic kullanıcı mesajı: SADECE soru + bağlam + (varsa)
        # ayar/stil + follow-up bağlamı. HABER CHUNK'LARI YOK — onları LLM
        # search_news tool'uyla kendisi getirir. condense (#833) sayesinde
        # effective_query bağlamlı standalone (follow-up'ta da doğru).
        gen_user_msg = f"Soru: {effective_query}" + settings_block + style_block + followup_block

        chat_provider = registry.route_for_tier(operation="chat", tier=user.tier)

        # wikipedia.enabled=False → sadece search_news sunulur (haber arşivi
        # her zaman birincil; Wikipedia opsiyonel ikincil tool).
        wikipedia_enabled = True
        try:
            from app.shared.runtime_config.settings_store import settings_store

            wikipedia_enabled = await settings_store.get_bool(
                db,
                "wikipedia.enabled",
                True,
            )
        except Exception:
            wikipedia_enabled = True
        tools_arg = RESEARCH_TOOL_DEFINITIONS if wikipedia_enabled else [SEARCH_NEWS_TOOL]

        # #845 — Güncel tarih ENJEKTE (zaman bug fix). Eski mimaride answer
        # LLM'e tarih HİÇ verilmiyordu → model "bugünü" eğitim önbilgisinden
        # uyduruyordu ("Nisan 2025"). now UTC; TR yerel UTC+3.
        _now_tr = now + timedelta(hours=3)
        _tr_months = [
            "",
            "Ocak",
            "Şubat",
            "Mart",
            "Nisan",
            "Mayıs",
            "Haziran",
            "Temmuz",
            "Ağustos",
            "Eylül",
            "Ekim",
            "Kasım",
            "Aralık",
        ]
        _tr_days = [
            "Pazartesi",
            "Salı",
            "Çarşamba",
            "Perşembe",
            "Cuma",
            "Cumartesi",
            "Pazar",
        ]
        current_date_str = (
            f"{_now_tr.day} {_tr_months[_now_tr.month]} {_now_tr.year}, "
            f"{_tr_days[_now_tr.weekday()]}"
        )
        # #854 — Nodrat agent prompt admin-tunable (prompts_store; kod
        # default fallback → DB override yoksa davranış değişmez).
        _nodrat_tmpl = None
        try:
            from app.prompts.research_answer import SYSTEM_PROMPT_NODRAT_AGENT
            from app.shared.runtime_config.prompts_store import prompts_store

            _nodrat_tmpl = await prompts_store.get(
                db,
                "research_nodrat_agent",
                SYSTEM_PROMPT_NODRAT_AGENT,
            )
        except Exception:
            _nodrat_tmpl = None
        sys_prompt = render_nodrat_agent_prompt(
            current_date_str,
            template=_nodrat_tmpl,
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
                    args,
                    db=db,
                    now=now,
                    user=user,
                    query_vec_hint=query_vec,
                    content_top_k=content_top_k,
                    cite_start=cite_start,
                )
            if name == "search_wikipedia":
                txt, srcs = await execute_search_wikipedia(
                    args,
                    cite_start=cite_start,
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
        # ---- #619 Query Decomposition (flag-gated; OFF → no-op = byte-identical) ----
        # Flag ON + çok-bileşenli sorgu → alt-sorgu planı LLM bağlamına hint
        # olarak eklenir (3b LLM-driven). Tool-loop / _dispatch / cite_n /
        # execute_search_news DOKUNULMAZ; LLM her alt-sorguyu kendi turunda arar.
        _decomp_t0 = time.monotonic()
        _decomp = await _decompose_for_research(
            effective_query, chat_provider, enabled=_query_decomposition_enabled
        )
        if _decomp is not None:
            _decomp_tele = _decomposition_telemetry(
                _decomp,
                int((time.monotonic() - _decomp_t0) * 1000),
                cohort=_decomp_cohort,
            )
            # #619 PR-5 telemetry — PII-suz (query/sub-query metni LOGLANMAZ);
            # single/fallback dahil HER flag-ON çağrıda emit (neden bölünmedi görünür).
            # #619 PR-F (Alt B): logger.warning (info DEĞİL) — app.* logger prod
            # effective level INFO'yu yutuyor (main.py explicit logging setup yok →
            # root WARNING; coverage_gap #1072 ile aynı kök) → warning prod-greppable.
            # Payload metrik-only (cohort/method/sub_query_count/llm_used/
            # fallback_reason/duration_ms) — PII (query/user_id/email) İÇERMEZ.
            logger.warning("query_decomposition %s", _decomp_tele)
            if _decomp.is_decomposed:
                yield _log_step(
                    "query_decomposition",
                    f"{len(_decomp.sub_queries)} alt sorguya ayrıldı: "
                    + " · ".join(_decomp.sub_queries),
                    _decomp_tele["duration_ms"],
                    method=_decomp_tele["method"],
                    sub_query_count=_decomp_tele["sub_query_count"],
                    llm_used=_decomp_tele["llm_used"],
                    fallback_reason=_decomp_tele["fallback_reason"],
                    cohort=_decomp_tele[
                        "cohort"
                    ],  # #619 PR-F (Alt A) — canary cohort DB-persist (PII-suz enum)
                )
                convo_messages.append(
                    ProviderMessage(
                        role="user",
                        content=_build_decomposition_hint(_decomp.sub_queries),
                    )
                )
        final_text = ""
        tool_round = 0
        # #audit — research LLM telemetri biriktirici (record_usage için)
        usage_totals: dict = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "cost_usd": 0.0,
            "model": None,
            "provider": None,
            "calls": 0,
        }
        cite_n = 0  # #851 — döngü boyunca global citation sayacı
        # Fix B′ (#1058): condense bağlamlı takip (örn. "nerede yaptı bu
        # açıklamayı") BELLEKTEN cevaplanamaz — ilk tur GERÇEK retrieval
        # zorlanır (tool_choice="required"); kanıtlı retrieval entity-
        # zengin contextualized sorguyla doğru makaleleri getirir.
        # 1. turdan sonra satır ~953 "auto"ya döner (mevcut akış).
        next_tool_choice = "required" if (_contextualized and _force_followup_retrieval) else "auto"
        c1_forced_once = False  # #851 — C1 backstop en fazla 1 kez
        citation_gap_forced_once = False  # #1484 — guard en fazla 1 kez (loop YOK)
        # #1059 — şeffaflık: Fix B′ devredeyse kullanıcı görsün (gözlem-
        # only; davranış #1058'de zaten var, burada yalnız _log_step).
        if next_tool_choice == "required" and _contextualized and _force_followup_retrieval:
            yield _log_step(
                "retrieval_forced",
                "Bağlamlı takip sorusu — kaynak araması zorunlu kılındı "
                "(bellekten yanıt engellendi)",
            )
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
                    conv_id=conv_id,
                    call_type="tool_round",
                    timeout=tool_round_timeout,
                )
            except Exception as exc:
                logger.warning(
                    "research tool-round %d failed: %s",
                    tool_round,
                    exc,
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
                # Fix A (#1058): sayısal [n] YANINDA — 0 kaynak + substantive
                # cevap da düzeltici-tur tetikler (uydurma "[Forbes Türkiye]"
                # gibi sayısal-olmayan sahte atıf `_CITE_TOKEN_RE`'yi
                # atlatıyordu; prod-audit conv 865e36e3).
                if (
                    not all_sources
                    and not c1_forced_once
                    and (
                        _CITE_TOKEN_RE.search(candidate)
                        or (_cited_only_strict and _is_substantive(candidate))
                    )
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
                    yield _log_step(
                        "grounding_retry",
                        "Kaynaksız taslak tespit edildi — düzeltici kaynak turu zorlandı",
                    )
                    continue
                # #1484 (S-2) — citation-gap guard: kaynak VAR ama substantive
                # cevapta hiç [n] yok → tek iki-çıkışlı dürüst-netleştirme
                # turu. C1 ile karşılıklı dışlayan (o `not all_sources`).
                # Kör "cite et" DEĞİL: kaynaklar desteklemiyorsa açıkça
                # söylemesi istenir; tool_choice="auto" kalır (model isterse
                # yeni arama da yapabilir); hard-refuse YOK.
                if _should_force_citation_gap_retry(
                    candidate,
                    all_sources,
                    citation_gap_guard=_citation_gap_guard,
                    forced_once=citation_gap_forced_once,
                ):
                    citation_gap_forced_once = True
                    convo_messages.append(ProviderMessage(role="user", content=_CITATION_GAP_NUDGE))
                    yield _log_step(
                        "citation_gap_retry",
                        "Kaynak bulundu ama cevapta atıf yok — dürüst-netleştirme turu zorlandı",
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
                    role="assistant",
                    content="",
                    tool_calls=tcs,
                )
            )
            _round_src_before = len(all_sources)  # #1059 — tur kazanımı
            _round_searches: list[dict[str, Any]] = []  # #1483 gözlem-only
            for tc in tcs:
                _tc_error = False
                try:
                    # #854 — tool yürütme latency tavanı (search_wikipedia
                    # Wikidata SPARQL / lang-fallback stack'lenebilir).
                    # Timeout → boş sonuç; LLM diğer tur'da toparlar.
                    tool_result, tc_sources, tc_meta = await asyncio.wait_for(
                        _dispatch(tc.name, tc.arguments, cite_n),
                        timeout=tool_exec_timeout,
                    )
                except (TimeoutError, Exception) as _texc:
                    logger.warning("tool exec failed (%s): %s", tc.name, _texc)
                    _tc_error = True
                    tool_result, tc_sources, tc_meta = (
                        f"'{tc.name}' aracı zaman aşımına uğradı veya hata "
                        f"verdi; bu sonuç olmadan devam et.",
                        [],
                        {},
                    )
                # #1483 — flag-gated arama telemetrisi (redacted; log'a YAZILMAZ)
                if _search_arg_telemetry:
                    _round_searches.append(
                        _search_telemetry_entry(
                            tc.name,
                            tc.arguments,
                            tc_meta,
                            round_no=tool_round,
                            source_count=len(tc_sources),
                            error=_tc_error,
                        )
                    )
                if tc.name == "search_news" and tc_meta:
                    query_class = tc_meta.get("query_class") or query_class
                if tc.name == "search_wikipedia" and tc_sources:
                    used_wikipedia = True
                cite_n += len(tc_sources)  # #851 global sayaç ilerlet
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
            # #1059 — şeffaflık: bu turda kaç kaynak bulundu (gözlem-only).
            _round_found = len(all_sources) - _round_src_before
            yield _log_step(
                "tool_result",
                f"{tool_names}: {_round_found} kaynak bulundu"
                if _round_found
                else f"{tool_names}: kaynak bulunamadı",
                # #1483 — flag OFF → kwargs boş → entry byte-identical
                **({"searches": _round_searches} if _round_searches else {}),
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
                # #983-revize — Kademe 1 (yaygın yol): tool_round'larla
                # AYNI request şekli (tools + tool_choice="auto"). Kontrollü
                # deney KANITLADI: tool_choice="none" → DeepSeek tools
                # şemasını prompt'a HİÇ koymuyor (none+tools == tools-yok:
                # input 8066 vs auto 8345; auto↔none switch cached=0) →
                # forced-final prefix'i tool_round'dan baştan farklı → cache
                # çöker (4608). "auto" + güçlü #860 nudge = kanıtlı doğal-
                # final deseni: model metin döndürür, prefix eşleşir.
                fb = await _tracked_chat_generate(
                    chat_provider,
                    user_id=user.id,
                    totals=usage_totals,
                    messages=convo_messages,
                    max_tokens=1500,
                    temperature=0.7,
                    tools=tools_arg,
                    tool_choice="auto",
                    conv_id=conv_id,
                    call_type="forced_final",
                    timeout=tool_round_timeout,
                )
                final_text = fb.text or ""
                # #983-revize — Kademe 2 (nadir güvenlik): model nudge'a
                # rağmen tool çağırıp metin döndürmediyse → TEK bounded
                # retry, tool_choice="none" + sert "tool YASAK". Cache
                # kaybı yalnız bu istisnada kabul (doğruluk > cache).
                # Döngü YOK — forced-final zaten döngü dışı tek atış.
                if not final_text.strip() and getattr(fb, "tool_calls", None):
                    convo_messages.append(
                        ProviderMessage(
                            role="user",
                            content=(
                                "Tool çağrısı YASAK — hiçbir araç çağırma. "
                                "Eldeki araç sonuçlarından SADECE nihai "
                                "metin cevabı yaz (citation [n] ile). "
                                "DSML / tool üretme."
                            ),
                        )
                    )
                    fb2 = await _tracked_chat_generate(
                        chat_provider,
                        user_id=user.id,
                        totals=usage_totals,
                        messages=convo_messages,
                        max_tokens=1500,
                        temperature=0.7,
                        tools=tools_arg,
                        tool_choice="none",
                        conv_id=conv_id,
                        call_type="forced_final_retry",
                        timeout=tool_round_timeout,
                    )
                    final_text = fb2.text or ""
            except Exception as exc:
                logger.warning("research final answer failed: %s", exc)
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

        # #1484 — gözlem-only: citation-gap retry zorlandı ama final cevap
        # hâlâ atıfsız → kapsama-boşluğu telemetrisi. Hard-refuse YOK
        # (kaynak mevcut; dürüst "kaynaklar desteklemiyor" cevabı meşru).
        if citation_gap_forced_once and not _CITE_TOKEN_RE.search(final_text):
            _log_coverage_gap("citation_gap", payload.content)

        # Fix A(b) cited-only HARD invariant (#1058 — prod-audit conv
        # 865e36e3): 0 GERÇEK retrieved kaynak + substantive cevap =
        # dayanaksız/halüsinasyon (uydurma "[Forbes Türkiye]" gibi).
        # ASLA servis edilmez → dürüst reddet. Kısa selamlama/kimlik/
        # meta (substantive değil) etkilenmez. Flag default-ON.
        if _cited_only_strict and not all_sources and _is_substantive(final_text):
            final_text = (
                "Bu soruya dayanak oluşturacak doğrulanabilir bir kaynak "
                "bulunamadı. Kaynaksız (dayanaksız) cevap vermiyorum — "
                "lütfen soruyu daha belirgin ya da farklı biçimde sor."
            )
            # #1059 — şeffaflık: #1058 hard-refuse tetiklendi (gözlem-only).
            yield _log_step(
                "cited_only_refused",
                "Doğrulanabilir kaynak bulunamadı — kaynaksız cevap reddedildi",
            )
            # #1067 RC2 — korpus-kapsama-boşluğu telemetri (0-kaynak).
            _log_coverage_gap("zero_source", payload.content)

        # RC3 (#1067 v2 — #1076) — dolaylı/tepki-kaynağı rekonstrüksiyon
        # YAPISAL marker-detect backstop. v1 LLM-verifier prod'da 4/8
        # yanlış-pozitif yapmıştı (agenda/aggregate/topic-partial/single-
        # direct sınıflarında multi-claim modellemiyordu — NLP-faithfulness
        # LLM-only judgment kanıtlı calibration-fragile). v2: deterministik
        # _has_reconstruction_marker — RC3-A prompt'a rağmen "anlaşıldığı
        # kadarıyla / tepkisinden anlaşıl…" SIZARSA reframe. 4 yanlış-
        # pozitifin hiçbirinde marker yoktu = false-positive-resistant;
        # Özel/Çelik orijinalinde marker VAR = true-positive korunur.
        # Cheap (LLM call YOK), saf, AST-test edilebilir.
        # #1058 ile karşılıklı dışlayan (o `not all_sources`, bu
        # `all_sources`). Flag-off → blok no-op (byte-eş).
        # RC3-B reframe KARARI saf helper'da (T6 P6 PR-C+4); yield +
        # `_log_coverage_gap` + `final_text` ataması orchestrator'da KALIR
        # (behavior-eş). Flag-off → helper None → blok no-op (byte-eş).
        _reframe = _maybe_reframe_for_faithfulness(final_text, all_sources, _faithfulness_guard)
        if _reframe is not None:
            final_text = _reframe
            yield _log_step(
                "faithfulness_reframed",
                "Geriye-çıkarsama imleci tespit edildi — dürüst "
                "kapsam-sınırı (rekonstrüksiyon engellendi)",
            )
            # #1067 RC2 — kapsama-boşluğu telemetri (marker-detect).
            _log_coverage_gap("reconstruction_marker", payload.content)

        # #1059 — şeffaflık: yanıt yazımı başlıyor (panelde etiket vardı,
        # hiç yayılmıyordu — gözlem-only).
        yield _log_step("generating", "Yanıt yazılıyor")

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
        _cited = _cited_numbers(accumulated)
        sources_used = [
            s for s in all_sources if s.get("cite") and _cite_to_int(s["cite"]) in _cited
        ]
        sources_considered = all_sources
        # #1059 — şeffaflık: cited-only atıf filtresi sonucu (gözlem-only;
        # filtre #845/#851'de zaten var, burada yalnız _log_step).
        if all_sources:
            yield _log_step(
                "citation_filter",
                f"Atıf doğrulama: {len(sources_used)}/{len(all_sources)} "
                "taranan kaynak cevapta kullanıldı",
            )

        # ---- Step 5.5: takip soruları (#961) ----
        # Substantive-gate: yalnız tool çağrılan turlar (all_sources
        # dolu) → greeting/kimlik/meta (research_answer §Karar md1, tool YOK
        # → all_sources boş) takip sorusu üretmez. Ana cevap zaten
        # stream edildi (accumulated); bu call kullanıcı okurken arkada
        # çalışır. Timeout/hata → degrade (followups=[], ana akış sağlam
        # — #854 yardımcı-call deseni). Cevap-içi "istersen" cümlesi YOK
        # (kullanıcı kararı; #851/#958 ton korunur — devam yalnız bu
        # sorularla, editoryal değil keşif yardımı).
        followups: list[str] = []
        if _FOLLOWUP_ENABLED and accumulated.strip() and sources_considered:
            try:
                followups = await asyncio.wait_for(
                    _generate_followups(
                        db,
                        payload.content,
                        accumulated,
                        user.tier,
                    ),
                    timeout=_FOLLOWUP_TIMEOUT_S,
                )
            except Exception as _fexc:  # asyncio.TimeoutError dahil
                logger.warning("research followup degraded (ana akış sağlam): %s", _fexc)
                followups = []

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
                followup_suggestions=followups or None,
                # #1013 (Faz 2a) — condense sonrası standalone sorgu
                # persist (L1 önkoşulu; SFT INPUT self-contained).
                # Rewrite yoksa payload.content'e eşittir (zararsız).
                effective_query=effective_query,
            )
            persist_db.add(assistant_msg)
            await persist_db.commit()
            await persist_db.refresh(assistant_msg)
            assistant_msg_id = assistant_msg.id

            # #audit — usage_events ledger (record_usage repo genelinde HİÇ
            # çağrılmıyordu → research için billing/quota audit kördü). Mesaj
            # zaten commit'li; bu best-effort ek (hata mesajı kaybetmez).
            try:
                from app.modules.billing.services.quota import record_usage

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
                logger.warning("research record_usage failed: %s", _uexc)

        # #961 — takip soruları done'dan ÖNCE (cevap zaten ekranda;
        # kullanıcı okurken altına düşer). Boşsa event yok (greeting/
        # meta veya degrade — sessiz, ana akış etkilenmez).
        if followups:
            yield _sse("followup_suggestions", {"questions": followups})

        yield _sse(
            "done",
            {
                "conversation_id": str(conv_id),
                "user_message_id": str(user_msg_id),
                "assistant_message_id": str(assistant_msg_id),
                "is_followup": is_related,
                "similarity": round(similarity, 3),
                "query_class": query_class,
                "used_wikipedia": used_wikipedia,
                "sources_used_count": len(sources_used),
                "sources_considered_count": len(sources_considered),
                "followup_count": len(followups),
            },
        )

    except Exception as exc:
        logger.exception("research stream failed: %s", exc)
        yield _sse(
            "error",
            {
                "code": "STREAM_ERROR",
                "title": "Akış hatası",
                "reason": str(exc)[:200],
            },
        )
        yield _sse("done", {"status": "failed"})
