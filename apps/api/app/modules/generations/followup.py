"""generations followup question generation (P6.2b, Modular Monolith v2).

app/api/app_research_stream.py'den çıkarılan saf followup üreteci — ana cevap
akıtıldıktan sonra non-blocking 5 takip/keşif sorusu üretir. Behavior-eş.
`registry` module-level import; prompt/provider/prompts_store lazy (fonksiyon içi).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.registry import registry

# #961 — cevap-sonrası takip soruları. Kod-constant (MVP); admin-tunable
# settings (research.followup_enabled / research.followup_timeout_s) ayrı/ileride
# (#854 deseni — bu PR'ı şişirmemek için kapsam dışı).
_FOLLOWUP_ENABLED = True
_FOLLOWUP_TIMEOUT_S = 8.0


async def _generate_followups(
    db: AsyncSession,
    user_question: str,
    answer: str,
    tier: str,
) -> list[str]:
    """Ayrı, hafif, non-blocking LLM call → 5 takip/keşif sorusu.

    Ana cevap (final_text→_simulate_stream) AKITILDIKTAN sonra çağrılır;
    kullanıcı cevabı okurken arkada üretilir (görünür latency yok).
    Hata/timeout caller'da yutulur (degrade — ana akış sağlam, #854
    deseni). Çıktı satır-bazlı tolerant parse (JSON DEĞİL; #819/#840
    dersi — bu call ayrı, ham sızıntı ana cevaba giremez)."""
    from app.prompts.research_followup import (
        SYSTEM_PROMPT as _FU_SYS,
    )
    from app.prompts.research_followup import (
        parse_followups,
        render_user_payload,
    )
    from app.providers.base import Message as _PMsg
    from app.shared.runtime_config.prompts_store import prompts_store

    try:
        _sys = await prompts_store.get(db, "research_followup", _FU_SYS)
    except Exception:
        _sys = _FU_SYS
    provider = registry.route_for_tier(operation="chat", tier=tier)
    res = await provider.generate_text(
        messages=[
            _PMsg(role="system", content=_sys),
            _PMsg(
                role="user",
                content=render_user_payload(user_question, answer),
            ),
        ],
        max_tokens=240,
        temperature=0.5,
    )
    # #1604 — best-effort cost log (akışı ASLA bozmaz; kendi kısa session + commit,
    # caller transaction'ına bağımlı değil). NER #1533 ile aynı track_provider_call API.
    try:
        from app.core.db import get_session_factory
        from app.shared.observability.cost_tracker import track_provider_call

        _f = get_session_factory()
        async with _f() as _db_log:
            async with track_provider_call(
                db=_db_log, provider=provider.name, operation="followup"
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
    return parse_followups(res.text or "", limit=5)
