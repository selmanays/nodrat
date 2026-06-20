"""Artefakt quick-action LLM revizyon üreteci — Faz 3b-2.

Mevcut artefakt head içeriğini intent'e göre LLM ile yeniden-şekillendirir
(kısalt / yeniden-yaz / uzat / X-thread). `followup.py::_generate_followups`
deseni: tek-atış `generate_text` + AYRI session'da best-effort cost-log
(#1604 — "her DeepSeek çağrısı loglanmalı"). Retrieval YOK; embedding'e
DOKUNMAZ (query_embedding HARD-STOP — revizyon yeniden-embed etmez).

followup.py'den FARK: hata YUTULMAZ. Quick-action kullanıcı-facing BİRİNCİL
aksiyon → generate_text fırlatırsa caller (endpoint) HTTP hatasına çevirir
(sessizce eski içeriği döndürmek yanıltıcı olur). Yalnız cost-log best-effort.

Provider: revizyon mekanik (mevcut metni yeniden-şekillendir) → ucuz model
yeter. `route_for_tier(operation="chat", tier="free")` deterministik olarak
ucuz DeepSeek v4-flash'a yönlendirir (maliyet kontrolü; pro kullanıcı için
pahalı modele gitmez — yardımcı aksiyon).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Revizyon = mekanik yeniden-şekillendirme → ucuz model deterministik seç.
_REVISION_TIER = "free"
_MAX_OUTPUT_TOKENS = 1400
_REVISION_TEMPERATURE = 0.3


async def generate_quick_action_revision(
    db: AsyncSession,
    *,
    head_content: str,
    sources_used: list | None,
    intent: str,
    user_id: uuid.UUID | None = None,
) -> str:
    """Intent'e göre mevcut head içeriğinin LLM revizyonunu üret → tek string.

    Hata fırlatır (caller yakalar). Cost-log best-effort (ayrı session, ana
    akışı bozmaz). commit ETMEZ (LLM çağrısı; DB yazımı caller'da add_revision).
    """
    from app.prompts.artifact_revision import SYSTEM_PROMPT, render_user_payload
    from app.providers.base import Message
    from app.providers.registry import registry
    from app.shared.runtime_config.prompts_store import prompts_store

    try:
        system = await prompts_store.get(db, "artifact_revision", SYSTEM_PROMPT)
    except Exception:
        system = SYSTEM_PROMPT

    provider = registry.route_for_tier(operation="chat", tier=_REVISION_TIER)
    res = await provider.generate_text(
        messages=[
            Message(role="system", content=system),
            Message(role="user", content=render_user_payload(head_content, sources_used, intent)),
        ],
        max_tokens=_MAX_OUTPUT_TOKENS,
        temperature=_REVISION_TEMPERATURE,
    )

    # #1604 — best-effort cost log (AYRI kısa session + explicit commit; caller
    # transaction'ına bağımlı değil; hata yutulur → ana akış ASLA bozulmaz).
    try:
        from app.core.db import get_session_factory
        from app.shared.observability.cost_tracker import track_provider_call

        _f = get_session_factory()
        async with _f() as _db_log:
            async with track_provider_call(
                db=_db_log,
                provider=provider.name,
                operation="artifact_revision",
                user_id=user_id,
            ) as _tr:
                _tr.record(
                    input_tokens=res.input_tokens,
                    output_tokens=res.output_tokens,
                    cached_tokens=getattr(res, "cached_input_tokens", 0),
                    model=res.model,
                    cost_usd=res.cost_usd,
                )
            await _db_log.commit()
    except Exception:  # noqa: S110 — best-effort cost log
        pass

    return (res.text or "").strip()
