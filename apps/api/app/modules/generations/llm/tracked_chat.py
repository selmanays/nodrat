"""generations LLM tracked-chat telemetry wrapper (P6.2c, Modular Monolith v2).

app/api/app_research_stream.py'den çıkarılan `_tracked_chat_generate` — her chat
LLM çağrısını `provider_call_logs(operation='chat')` telemetri + `record()` ile
sarar (token/maliyet/latency). Behavior-eş. Lazy import'lar (get_session_factory,
track_provider_call, research_cache_telemetry) fonksiyon içinde KALIR (test
source-path patch'leri stable).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def _tracked_chat_generate(
    provider, *, user_id, totals: dict, conv_id=None, call_type=None, **gen_kwargs
):
    """`generate_text` + `provider_call_logs(operation='chat')` telemetri.

    #audit (2026-05-15): research hattı HİÇ ölçülmüyordu — istek başına 3+ LLM
    çağrısı (condense / her agentic tur / forced-final) `track_provider_call`
    ile sarılmıyordu → token/maliyet/latency kör. Her çağrı KENDİ kısa
    session'ında loglanır + explicit commit; request `db` stream'den ÖNCE
    commit edildiği için kullanılamaz. `totals` record_usage için biriktirir.
    generate_text hata verirse track_provider_call success=False loglar +
    re-raise (mevcut çağrı-yeri degrade mantığı korunur); finally yine commit.
    """
    from app.core.db import get_session_factory
    from app.shared.observability.cost_tracker import track_provider_call

    prov_name = getattr(provider, "name", "unknown")
    factory = get_session_factory()
    async with factory() as _tdb:
        try:
            async with track_provider_call(
                db=_tdb,
                provider=prov_name,
                operation="chat",
                user_id=user_id,
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
            # #981 — prompt-cache segment telemetri (izole tablo, best-effort,
            # flag-gated). Çift-korumalı: helper kurşungeçirmez + bu try/except.
            # Research akışı bunun için ASLA kırılmaz.
            try:
                from app.modules.generations.services.research_cache_telemetry import (
                    record_research_cache_telemetry,
                )

                await record_research_cache_telemetry(
                    provider=prov_name,
                    model=res.model,
                    call_type=call_type or "unknown",
                    conv_id=conv_id,
                    user_id=user_id,
                    messages=gen_kwargs.get("messages"),
                    tools=gen_kwargs.get("tools"),
                    res=res,
                    call_seq=totals.get("calls"),
                    success=True,
                )
            except Exception as _texc:  # pragma: no cover
                logger.warning("research_cache_telemetry call failed: %s", _texc)
            return res
        finally:
            try:
                await _tdb.commit()
            except Exception as _cexc:  # pragma: no cover
                logger.warning("research telemetry commit failed: %s", _cexc)
