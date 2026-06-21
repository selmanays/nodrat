"""Sorgu-netleştirme üreteci (#1701) — 0-kaynak/anlaşılmayan sorgu niyet-anlama.

app_research_stream'de cited-only 0-kaynak reddinde (bland "bulamadım" yerine)
çağrılır: ucuz LLM (followup.py deseni) ile kullanıcının niyetini anlayıp kısa
açıklama + 2-3 öneri üretir. NADİR yol (0-kaynak) → maliyet ihmal edilebilir.
Best-effort: hata/timeout caller'da yutulur (ana akış sağlam). Citation-safe
(öneri/netleştirme, uydurma cevap yok — ayrı call, ana cevaba sızmaz).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.registry import registry


async def generate_clarification(
    db: AsyncSession,
    query: str,
    *,
    tier: str = "free",
) -> dict | None:
    """Ayrı, hafif LLM call → {message, suggestions}. Geçersiz/hata → None.

    NOT: caller flag-gate'ler (research.clarification.enabled) + dış try/except
    ile sarar (degrade). Prompt admin-tunable (prompts_store)."""
    from app.prompts.query_clarification import (
        SYSTEM_PROMPT as _SYS,
    )
    from app.prompts.query_clarification import (
        parse_clarification,
        render_user_payload,
    )
    from app.providers.base import Message as _PMsg
    from app.shared.runtime_config.prompts_store import prompts_store

    try:
        _sys = await prompts_store.get(db, "query_clarification", _SYS)
    except Exception:
        _sys = _SYS
    provider = registry.route_for_tier(operation="chat", tier=tier)
    res = await provider.generate_text(
        messages=[
            _PMsg(role="system", content=_sys),
            _PMsg(role="user", content=render_user_payload(query)),
        ],
        max_tokens=300,
        temperature=0.4,
    )
    # #1604 — best-effort cost log (akışı ASLA bozmaz; ayrı kısa session + commit).
    try:
        from app.core.db import get_session_factory
        from app.shared.observability.cost_tracker import track_provider_call

        _f = get_session_factory()
        async with _f() as _db_log:
            async with track_provider_call(
                db=_db_log, provider=provider.name, operation="clarification"
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
    return parse_clarification(res.text or "")
