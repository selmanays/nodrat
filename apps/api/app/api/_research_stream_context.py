"""Research stream — conversation context + condense preparation (#833).

Extracted from `app_research_stream.py` `_research_stream_body` (Step 1.5) in
T6 P6 PR-C+2 (behavior-preserving). Holds the recent-conversation-context
fetch + L1 windowed-context decision + conversational query rewrite (condense),
i.e. everything that produces the standalone `effective_query` BEFORE the
agentic tool-loop.

Why a sibling module: this block is DB + settings_store + prompts_store +
provider-routing + research-tools dependent — distinct cohesion from the pure
SSE/format helpers in `_research_stream_helpers.py`. Extraction collapses ~6
orchestrator dependencies into one mockable helper, enabling future 2nd-yield
orchestration tests at low mock count (PR-C+3).

Invariants preserved (byte-for-byte logic):
- `_recent_conversation_context` moved verbatim (17 async-helper tests follow).
- The L719 `query_rewrite` thinking_step yield STAYS in `_research_stream_body`
  (this helper yields nothing); it returns `contextualized` (yield condition),
  `effective_query` (yield detail) and `rewrite_latency_ms` (yield latency).
- `recent_context` (legacy `_rw_ctx`) is returned because the answer-prompt
  (#854) consumes it downstream.

Dependencies (NOT extracted): provider `registry`, `settings_store`,
`prompts_store`, `condense_followup_query` (lazy, as in the original).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.modules.conversations.models import Message
from app.modules.generations.services.conversation_context import (
    format_context_block,
    l1_accept_rewrite,
    select_windowed_context,
)
from app.providers.registry import registry

if TYPE_CHECKING:
    from app.api.app_research_stream import ResearchMessageCreate


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
    rows = list(
        (
            await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conv_id,
                    Message.id != exclude_msg_id,
                )
                .order_by(Message.created_at.desc())
                .limit(last_n)
            )
        )
        .scalars()
        .all()
    )
    rows.reverse()  # oldest-first (doğal okuma)
    # F2b (#1014) — formatter ortak: legacy ve windowed yol AYNI string
    # formatını üretir → condense `history` sözleşmesi birebir korunur.
    return format_context_block(rows)


@dataclass
class ResearchContextResult:
    """`_research_stream_body` Step 1.5 (condense) çıktısı.

    L719 `query_rewrite` yield orchestrator'da kalır; bu sonuç ona yield
    koşulunu (`contextualized`), detail'i (`effective_query[:80]`) ve
    latency'yi (`rewrite_latency_ms`, condense yapılmadıysa 0) sağlar.
    `recent_context` (legacy `_rw_ctx`) downstream cevap prompt'unda (#854)
    kullanılır.
    """

    effective_query: str
    contextualized: bool
    recent_context: str
    rewrite_latency_ms: int


async def _prepare_research_context(
    db: AsyncSession,
    conv_id: UUID,
    user_msg_id: UUID,
    user: User,
    payload: ResearchMessageCreate,
) -> ResearchContextResult:
    """Step 1.5: Conversational query rewrite (#833) — yield ÜRETMEZ.

    #832 plan_input enrichment ÇALIŞMADI (production'da kanıtlandı):
    planner SYSTEM_PROMPT preserve-first kuralı ad-hoc talimatı ezdi,
    "ilk bölümün adı neydi" → Stargate bağlamı ignore → "Daha 17 dizisi"
    çöpü. Çözüm: planner'dan ÖNCE izole condense step (Perplexity/LangChain
    standardı). Multi-turn'de follow-up → standalone arama sorgusu.
    is_related'a güvenmiyoruz (generic "daha detaylı açıkla" embedding
    kaçırıyor); context VARSA hep.

    `_research_stream_body` bu sonuca göre L719 `query_rewrite` thinking_step'i
    `contextualized` True iken kendisi yield eder (PR-C+2 extraction; davranış
    byte-eş).
    """
    effective_query = payload.content
    # condense L1/önceki-bağlamla yeniden yazdıysa True → bu takip
    # bellekten cevaplanamaz, GERÇEK retrieval zorlanır (Fix B′).
    _contextualized = False
    rewrite_latency_ms = 0
    _rw_ctx = await _recent_conversation_context(
        db,
        conv_id,
        user_msg_id,
        last_n=4,
    )
    # F2b (#1014) — L1 zaman-pencereli görünmez bağlam. Flag default
    # KAPALI → yukarıdaki legacy _rw_ctx AYNEN (byte-eş, #854).
    # Açıkken: en-dar-pencere-önce + relatedness kapısı; ilgili yoksa
    # BOŞ → condense None → ham sorgu (standalone/taze KİRLENMEZ).
    # Yalnız condense'i besler; asıl cevap prompt'una GİRMEZ.
    _l1_on = False
    try:
        from app.shared.runtime_config.settings_store import settings_store as _ss

        _l1_on = await _ss.get_bool(
            db,
            "research.l1_windowed_context_enabled",
            False,
        )
    except Exception:
        _l1_on = False
    if _l1_on:
        try:
            # Pivot-sonrası doğru default: her conv tek-mesaj
            # (#1045/#1048) → conversation-scope ölü; L1 ancak
            # user-scope ile çalışır (settings_store.get registry
            # default'u OKUMAZ → call-site default belirleyici).
            _uscope = await _ss.get_bool(db, "research.l1_user_scope", True)
            _maxm = await _ss.get_int(db, "research.l1_window_max_msgs", 8)
            # COSINE YOK (kanıtlı kök neden): belirsiz takip kendine
            # benzeyen önceki belirsiz takibe yakın, atıf yaptığı
            # içerikli sorguya değil. select_windowed_context artık
            # S5 Gate-1 (standalone-yeterlilik) + recency-anchored
            # içerikli araştırma çapası kullanır (ham metin yeter).
            _win = await select_windowed_context(
                db,
                conv_id=conv_id,
                user_id=user.id,
                exclude_msg_id=user_msg_id,
                new_query_text=payload.content,
                user_scope=_uscope,
                windows_hours=(6, 24, 72),
                max_msgs=_maxm,
            )
            _rw_ctx = format_context_block(_win) if _win else ""
        except Exception:  # noqa: S110
            pass  # herhangi hata → legacy _rw_ctx korunur (güvenli)
    if _rw_ctx:
        from app.prompts.query_rewrite import condense_followup_query

        _rw_provider = registry.route_for_tier(
            operation="chat",
            tier=user.tier,
        )
        # #854 — condense latency tavanı admin-tunable (constant fallback)
        _cond_to = 6
        try:
            from app.shared.runtime_config.settings_store import settings_store

            _cond_to = await settings_store.get_int(
                db,
                "research.condense_timeout_s",
                6,
            )
        except Exception:
            _cond_to = 6
        _cond_to = max(2, min(_cond_to, 20))
        # #854 — condense prompt admin-tunable (prompts_store; kod
        # default fallback → DB override yoksa davranış değişmez).
        _rw_tmpl = None
        try:
            from app.prompts.query_rewrite import REWRITE_SYSTEM_PROMPT
            from app.shared.runtime_config.prompts_store import prompts_store

            _rw_tmpl = await prompts_store.get(
                db,
                "research_query_rewrite",
                REWRITE_SYSTEM_PROMPT,
            )
        except Exception:
            _rw_tmpl = None
        _t_rw = asyncio.get_event_loop().time()
        rewritten = await condense_followup_query(
            _rw_provider,
            _rw_ctx,
            payload.content,
            timeout_s=_cond_to,
            system_prompt=_rw_tmpl,
        )
        # Gate 4 (S5) — L1 açıkken rewrite-drift reddi: condense çıktısı
        # ham sorgudan tamamen kopuksa ham'a düş. L1 KAPALIYKEN koşul
        # eski hâliyle birebir (davranış değişmez).
        if (
            rewritten
            and rewritten.strip()
            and ((not _l1_on) or l1_accept_rewrite(payload.content, rewritten))
        ):
            effective_query = rewritten.strip()
            _contextualized = True
            rewrite_latency_ms = int((asyncio.get_event_loop().time() - _t_rw) * 1000)
    return ResearchContextResult(
        effective_query=effective_query,
        contextualized=_contextualized,
        recent_context=_rw_ctx,
        rewrite_latency_ms=rewrite_latency_ms,
    )
