"""Paylaşılır non-streaming research çekirdeği (Faz 5.2a, #1785).

Founder kararı **B: paylaşılan bileşenler** — canlı SSE orkestratörü
(`_research_stream_body`, app/api) DEĞİŞMEZ; bu YENİ non-streaming çekirdek AYNI
invariant-taşıyan yapı-taşlarını çağırır:
- `SEARCH_NEWS_TOOL` + `execute_search_news` → retrieval KALİTE MAKİNESİ (planner +
  hybrid + RRF + critical_entities, prod-parite),
- `_tracked_chat_generate` → LLM + provider_call_logs cost-log + telemetri,
- `_cited_numbers` → cited-only filtresi (#1754: kaynaksız → artefakt yok),
- `_maybe_reframe_for_faithfulness` → RC3-B geriye-çıkarsama reframe paritesi
  (canlı yolla aynı flag; rekonstrüksiyon sızarsa → reframe → cited boşalır → artefakt yok).

Kompakt tek-tur-zorlamalı tool-loop (SSE `yield` YOK): system=Nodrat agent prompt +
user=Soru → LLM `search_news` çağırır → sonuç → atıflı cevap. İlk tur retrieval
ZORLANIR (otomasyon küme haberini ister; bellekten cevap engellenir). Cevaptaki `[n]`
atıflarına göre `sources_used` süzülür; hiç atıf yoksa `status='skipped_no_sources'`.

Bu modül ARTEFAKT YARATMAZ, kota/consent KONTROL ETMEZ, küme ÇÖZMEZ — bunlar çağırana
(Faz 5.2b otomasyon içerik işlemcisi) aittir. Saf "sorgu → (içerik, kaynaklar)".

import-linter: generations'ta yaşar; `automation → generations` izinli (17. contract).
Lazy import'lar (test source-path patch stabilitesi için — tracked_chat.py deseni).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_MAX_ROUNDS = 2  # tur1 retrieval (zorla) + tur2 cevap/ikinci-arama
TOOL_EXEC_TIMEOUT_S = 20.0  # execute_search_news yürütme tavanı (app_research_stream paritesi)


@dataclass
class ResearchRunResult:
    """research_runner çıktısı (artefakt değil — çağıran karar verir)."""

    status: str  # 'ok' | 'skipped_no_sources'
    content: str
    sources_used: list[dict[str, Any]]  # cevapta GERÇEKTEN atıf yapılan kaynaklar
    all_sources: list[dict[str, Any]]  # retrieval'ın getirdiği tüm kaynaklar
    usage: dict[str, Any]  # token/maliyet biriktirici (record_usage için)


def _current_date_str(now: datetime) -> str:
    """Nodrat agent prompt'a {current_date} enjeksiyonu (LLM zaman-farkındalığı)."""
    return now.strftime("%Y-%m-%d")


async def run_cluster_research(
    db: AsyncSession,
    *,
    user: Any,
    query: str,
    now: datetime,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> ResearchRunResult:
    """Verili sorgu için kaynaklı research yürüt (non-streaming).

    Canlı SSE yolundaki tool-loop'un SSE'siz, kompakt eşdeğeri; aynı tool + LLM +
    citation yapı-taşları. Artefakt/kota/consent çağırana bırakılır.
    """
    from app.core.research_tools import SEARCH_NEWS_TOOL, execute_search_news
    from app.modules.generations.citation import (
        _cited_numbers,
        _maybe_reframe_for_faithfulness,
    )
    from app.modules.generations.llm.tracked_chat import _tracked_chat_generate
    from app.prompts.research_answer import (
        SYSTEM_PROMPT_NODRAT_AGENT,
        render_nodrat_agent_prompt,
    )
    from app.providers.base import Message as ProviderMessage
    from app.providers.registry import registry
    from app.shared.runtime_config.prompts_store import prompts_store
    from app.shared.runtime_config.settings_store import settings_store

    tier = getattr(user, "tier", "free") or "free"
    user_id = getattr(user, "id", None)
    provider = registry.route_for_tier(operation="chat", tier=tier)

    # admin-tunable agent prompt (canlı yolla aynı kaynak: prompts_store override)
    try:
        tmpl = await prompts_store.get(db, "research_nodrat_agent", SYSTEM_PROMPT_NODRAT_AGENT)
    except Exception:
        tmpl = None
    sys_prompt = render_nodrat_agent_prompt(_current_date_str(now), template=tmpl)

    convo: list[ProviderMessage] = [
        ProviderMessage(role="system", content=sys_prompt),
        ProviderMessage(role="user", content=f"Soru: {query}"),
    ]

    totals: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cost_usd": 0.0,
        "model": None,
        "provider": None,
        "calls": 0,
    }
    all_sources: list[dict[str, Any]] = []
    cite_n = 0  # #851 global citation sayacı (tool çağrıları arası benzersiz [n])
    final_text = ""
    # Otomasyon: ilk tur retrieval ZORLA — bellekten/atıfsız cevap engellenir
    # (canlı yolun _force_followup_retrieval mantığının otomasyon karşılığı).
    next_choice = "required"
    rounds = 0

    while rounds < max_rounds:
        try:
            decision = await _tracked_chat_generate(
                provider,
                user_id=user_id,
                totals=totals,
                messages=convo,
                max_tokens=1500,
                temperature=0.7,
                tools=[SEARCH_NEWS_TOOL],
                tool_choice=next_choice,
                call_type="automation_research",
            )
        except Exception as exc:
            logger.warning("automation research tur %d başarısız: %s", rounds, exc)
            break
        next_choice = "auto"
        tcs = decision.tool_calls
        if not tcs:
            final_text = decision.text or ""
            break
        rounds += 1
        convo.append(ProviderMessage(role="assistant", content="", tool_calls=tcs))
        for tc in tcs:
            try:
                tool_result, tc_sources, _meta = await asyncio.wait_for(
                    execute_search_news(tc.arguments, db=db, now=now, user=user, cite_start=cite_n),
                    timeout=TOOL_EXEC_TIMEOUT_S,
                )
            except (TimeoutError, Exception) as exc:
                logger.warning("automation search_news başarısız: %s", exc)
                tool_result, tc_sources = ("Arama hata verdi; bu sonuç olmadan devam et.", [])
            cite_n += len(tc_sources)
            all_sources.extend(tc_sources)
            convo.append(ProviderMessage(role="tool", content=tool_result, tool_call_id=tc.id))

    # Max tur dolduysa ve hâlâ cevap yoksa → toolsuz zorla final (kaynak varsa).
    if not final_text and all_sources:
        try:
            convo.append(
                ProviderMessage(
                    role="user",
                    content=(
                        "Artık araç çağırma; eldeki kaynaklardan SADECE cevabı [n] "
                        "atıflarıyla yaz. Kaynaklar desteklemiyorsa açıkça söyle."
                    ),
                )
            )
            forced = await _tracked_chat_generate(
                provider,
                user_id=user_id,
                totals=totals,
                messages=convo,
                max_tokens=1500,
                temperature=0.5,
                call_type="automation_research_final",
            )
            final_text = forced.text or ""
        except Exception as exc:
            logger.warning("automation zorla-final başarısız: %s", exc)

    # faithfulness-reframe paritesi (canlı SSE yolu, app_research_stream.py:1334):
    # geriye-çıkarsama (rekonstrüksiyon) imleci sızmışsa cevabı sabit dürüst-kapsam
    # metniyle değiştir → [n] kalmaz → cited boşalır → status='skipped_no_sources'
    # → artefakt YOK (#1754 paritesi). Flag canlı yolla aynı (default True).
    try:
        _guard = await settings_store.get_bool(db, "research.faithfulness_guard_enabled", True)
    except Exception:
        _guard = True
    _reframe = _maybe_reframe_for_faithfulness(final_text, all_sources, _guard)
    if _reframe is not None:
        final_text = _reframe

    # cited-only (#1754): yalnız cevapta [n] ile atıf yapılan kaynaklar sayılır.
    cited = _cited_numbers(final_text)
    sources_used = [s for i, s in enumerate(all_sources, start=1) if i in cited]
    status = "ok" if sources_used else "skipped_no_sources"
    return ResearchRunResult(
        status=status,
        content=final_text,
        sources_used=sources_used,
        all_sources=all_sources,
        usage=totals,
    )
