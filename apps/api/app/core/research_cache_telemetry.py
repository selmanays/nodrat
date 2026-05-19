"""Research prompt-cache segment telemetri yazıcısı (#981).

KURŞUNGEÇİRMEZ best-effort: bu modülün HİÇBİR fonksiyonu exception fırlatmaz
(tüm gövde try/except). Research akışı bu telemetri için ASLA kırılmaz. Runtime
flag `observability.research_cache_enabled` (default true) ile deploy'suz kapatılır.

KVKK: yalnız token SAYISI yazılır — mesaj/soru/doküman içeriği ASLA persist
edilmez. İzole tablo (`research_cache_telemetry`); billing ledger'a dokunmaz.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _approx_tokens(text: Any) -> int:
    """Kaba token tahmini (≈chars/4). Fatura DEĞİL — trend/atıf için.

    Ground truth provider'ın input/cached/output totalleri (ayrı kolon);
    Σsegment ≈ input drift'i kendisi izlenecek bir sinyal.
    """
    if not text:
        return 0
    try:
        return max(1, len(str(text)) // 4)
    except Exception:
        return 0


def classify_segments(messages: Any, tools: Any = None) -> dict[str, int]:
    """Mesaj dizisini kaba segmentlere ayır (v1: robust 5-kova).

    Fine msg1 alt-bölümü (static/history/question) v1'de YAPILMAZ — string
    delimiter parse'ı kırılgan; kolonlar şemada var (forward-compat), v1'de
    tüm user içeriği `seg_msg1_question`'a düşer. Asıl Senaryo-B sinyali
    (call_type + tools_present + cache hit/miss + total) tam yakalanır.
    """
    seg = {
        "seg_system": 0,
        "seg_tools_schema": 0,
        "seg_msg1_static": 0,
        "seg_msg1_history": 0,
        "seg_msg1_question": 0,
        "seg_rag_tool": 0,
        "seg_assistant_intermediate": 0,
    }
    try:
        for m in messages or []:
            role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
            content = getattr(m, "content", None)
            if content is None and isinstance(m, dict):
                content = m.get("content")
            tc = getattr(m, "tool_calls", None)
            if role == "system":
                seg["seg_system"] += _approx_tokens(content)
            elif role == "tool":
                seg["seg_rag_tool"] += _approx_tokens(content)
            elif role == "assistant":
                seg["seg_assistant_intermediate"] += _approx_tokens(content)
                if tc:
                    seg["seg_assistant_intermediate"] += _approx_tokens(str(tc))
            elif role == "user":
                seg["seg_msg1_question"] += _approx_tokens(content)
        if tools:
            seg["seg_tools_schema"] = _approx_tokens(str(tools))
    except Exception:  # pragma: no cover - bulletproof  # noqa: S110
        pass
    return seg


async def record_research_cache_telemetry(
    *,
    provider: str | None,
    model: str | None,
    call_type: str,
    conv_id: Any = None,
    user_id: Any = None,
    messages: Any = None,
    tools: Any = None,
    res: Any = None,
    call_seq: int | None = None,
    success: bool = True,
) -> None:
    """`research_cache_telemetry`'ye 1 satır yaz — best-effort, ASLA raise etmez.

    Kendi kısa session'ı (research akışının session'ına dokunmaz). Flag kapalıysa
    no-op. Herhangi bir hata → warning log + sessiz dönüş.
    """
    try:
        from app.core.db import get_session_factory
        from app.core.settings_store import settings_store
        from app.models.research_cache_telemetry import ResearchCacheTelemetry

        def _u(v: Any) -> UUID | None:
            if v is None or isinstance(v, UUID):
                return v
            try:
                return UUID(str(v))
            except Exception:
                return None

        factory = get_session_factory()
        async with factory() as db:
            try:
                enabled = await settings_store.get_bool(
                    db, "observability.research_cache_enabled", True
                )
            except Exception:
                enabled = True
            if not enabled:
                return

            seg = classify_segments(messages, tools)
            row = ResearchCacheTelemetry(
                user_id=_u(user_id),
                conversation_id=_u(conv_id),
                call_type=(call_type or "unknown")[:32],
                call_seq=call_seq,
                tools_present=bool(tools),
                model=(str(model)[:120] if model else None),
                input_tokens=getattr(res, "input_tokens", None),
                cached_tokens=getattr(res, "cached_input_tokens", None),
                output_tokens=getattr(res, "output_tokens", None),
                success=success,
                **seg,
            )
            db.add(row)
            await db.commit()
    except Exception as exc:  # pragma: no cover - bulletproof
        logger.warning("research_cache_telemetry write failed: %s", exc)
