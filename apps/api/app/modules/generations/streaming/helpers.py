"""Internal SSE + research stream pure helpers (T6 #1085 P6 PR-B internal split).

Pure helpers: SSE event formatting (`_sse`), async word-group streaming
(`_simulate_stream`), telemetry logging (`_log_coverage_gap`). Daha önce
`app.api.app_research_stream` (lines 136-150, 193-195, 248-263) içinde
inline'dı; pure refactor — davranış değişikliği YOK.

Public consumer: `app.api.app_research_stream` (re-export via top-level
import). Modül-dışı doğrudan import edilmez — stable API DEĞİL.

Refs:
- PR #1150 — SSE pure-helper characterization tests (regression safety-net)
- PR #1147/#1149/#1152 — extractor/retrieval internal split (pattern source)
- app.api.app_research_stream — public surface bu helper'ları import eder
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

logger = logging.getLogger(__name__)


def _log_coverage_gap(reason: str, question: str) -> None:
    """#1067 RC2 — korpus-kapsama-boşluğu telemetri sinyali.

    Yalnız observability (greppable `coverage_gap`); cevap/citation/akış
    DOKUNULMAZ, flag/şema yok (saf log). Ürün/ops hangi sorgu-konularının
    korpusta karşılığı olmadığını görür → kaynak-genişletme önceliği
    (RC2 kök-değil-davranış: korpus kodla tamamlanamaz, ölçülür).
    `reason`: zero_source | indirect:INDIRECT | indirect:UNSUPPORTED.

    #1072: `logger.warning` (info DEĞİL) — prod effective log level
    WARNING; `logger.info` sızıyordu → telemetri görünmezdi. Aksiyon-
    alınabilir ops/ürün sinyali (codebase precedent: degrade/telemetri
    logları warning); hata değil ama operatör görmeli."""
    with contextlib.suppress(Exception):  # telemetri ASLA akışı bozmaz
        logger.warning("coverage_gap reason=%s q=%r", reason, (question or "")[:160])


def _sse(event: str, data: dict | None = None) -> str:
    payload = json.dumps(data or {}, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


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
