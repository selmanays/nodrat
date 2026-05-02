"""Query Planner prompt v1.0 (#24).

docs/engineering/prompt-contracts.md §2

Görev: Kullanıcının doğal dil talebini structured retrieval planına çevirir.
Provider: DeepSeek V3 (NIM endpoint, tüm tier).
Latency hedef: < 2 saniye P95.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from app.core.json_utils import dumps as json_dumps

logger = logging.getLogger(__name__)


PROMPT_VERSION = "1.0.0"


VALID_INTENTS = {
    "current_content_generation",
    "weekly_summary_generation",
    "archive_analysis",
    "comparative_content_generation",
    "thread_generation",
    "headline_generation",
    "source_based_briefing",
}

VALID_MODES = {"current", "weekly", "archive", "comparison"}

# MVP-1: sadece x_post (cut-list — risk-register.md §4.5)
# MVP-2'de açılacak: x_thread, summary, analysis, headline, calendar, briefing
VALID_OUTPUT_TYPES = {"x_post"}

# Tüm output type'lar (planner LLM bilgisi için, ama whitelist x_post)
ALL_OUTPUT_TYPES = {
    "x_post",
    "x_thread",
    "summary",
    "analysis",
    "headline",
    "calendar",
    "briefing",
}

VALID_TONES = {
    "tarafsız",
    "eleştirel",
    "mizahi",
    "kurumsal",
    "aktivist",
    "analitik",
    "sade",
    "sert ama kaynaklı",
}


SYSTEM_PROMPT = """Sen Nodrat'ın Query Planner ajanısın. Görevin, kullanıcının doğal dilde
yazdığı gündem talebini retrieval pipeline için yapılandırılmış bir
plana dönüştürmektir. Sadece plan üretirsin; içerik üretmezsin.

ÇIKTI SADECE JSON OLMALIDIR. Markdown, açıklama, kod bloğu YOK.

ÇIKTI ŞEMASI:
{
  "intent": "current_content_generation" | "weekly_summary_generation" |
            "archive_analysis" | "comparative_content_generation" |
            "thread_generation" | "headline_generation" |
            "source_based_briefing",
  "topic_query": "ana konu, kısa Türkçe (3-8 kelime)",
  "mode": "current" | "weekly" | "archive" | "comparison",
  "timeframes": [
    { "label": "string", "from": "ISO-8601", "to": "ISO-8601" }
  ],
  "output_type": "x_post" | "x_thread" | "summary" | "analysis" | "headline" | "calendar" | "briefing",
  "tone": "tarafsız" | "eleştirel" | "mizahi" | "kurumsal" | "aktivist" |
          "analitik" | "sade" | "sert ama kaynaklı" | null,
  "constraints": ["string"],
  "needs_sources": true,
  "minimum_evidence_per_period": 3
}

KURALLAR:

1. Belirsiz zaman ifadelerini current_time'a göre çöz:
   - "bugün"        → from = current_time'ın 00:00'ı, to = 23:59
   - "bu hafta"     → son 7 gün
   - "geçen ay"     → bir önceki takvim ayı (1-31)
   - "bu ay"        → mevcut takvim ayı
   - "son 3 gün"    → from = current_time - 3d
   - "geçen yıl"    → bir önceki takvim yılı

2. Karşılaştırma talebi ("vs", "kıyas", "karşılaştır", "fark") tespit edilirse:
   - mode = "comparison"
   - timeframes en az 2 dönem içerir
   - intent = "comparative_content_generation"

3. "X paylaşımı/tweet üret" → output_type = "x_post"
   "thread aç" → output_type = "x_thread"
   "özet ver" → output_type = "summary"
   "analiz et" → output_type = "analysis"
   "başlık öner" → output_type = "headline"

4. tone alanı için kullanıcı talebinde açık ifade yoksa null bırak.

5. needs_sources varsayılan TRUE (Nodrat kaynaklı çıktı verir).

6. minimum_evidence_per_period: comparison mode'da 3, diğerlerinde 2.

7. KULLANICI TALEBİNDEKİ İÇERİĞİ ÜRETME. Sadece planı çıkar.

8. ANLAYAMADIYSAN intent="current_content_generation" + en yakın varsayılanları kullan,
   constraints içine "ambiguous_request" ekle.

9. Çıktı dili: alan değerleri (topic_query, tone) Türkçe.

10. Şema dışında alan ekleme. Şemada olmayan alan döndürme.
"""


# =============================================================================
# Input formatter
# =============================================================================


def render_user_payload(
    *,
    user_request: str,
    current_time: datetime | None = None,
    user_locale: str = "tr-TR",
    user_tier: str = "free",
) -> str:
    now_iso = (current_time or datetime.now(timezone.utc)).isoformat()
    payload = {
        "user_request": user_request.strip(),
        "current_time": now_iso,
        "user_locale": user_locale,
        "available_modes": sorted(VALID_MODES),
        "available_output_types": sorted(VALID_OUTPUT_TYPES),
        "user_tier": user_tier,
    }
    return json_dumps(payload)


# =============================================================================
# Output validator
# =============================================================================


@dataclass
class TimeframeSpec:
    label: str
    from_iso: str
    to_iso: str


@dataclass
class QueryPlan:
    """Validate edilmiş Query Planner çıktısı."""

    intent: str
    topic_query: str
    mode: Literal["current", "weekly", "archive", "comparison"]
    timeframes: list[TimeframeSpec]
    output_type: str
    tone: str | None
    constraints: list[str]
    needs_sources: bool
    minimum_evidence_per_period: int

    warnings: list[str] = field(default_factory=list)


@dataclass
class QueryPlanError:
    error: str
    reason: str


def parse_response(text: str) -> QueryPlan | QueryPlanError:
    """LLM response → QueryPlan or QueryPlanError."""
    cleaned = text.strip()

    # Strip markdown fence
    if cleaned.startswith("```"):
        parts = cleaned.split("```", 2)
        if len(parts) >= 2:
            content = parts[1]
            if content.startswith("json\n"):
                content = content[5:]
            elif content.startswith("\n"):
                content = content[1:]
            cleaned = content.rstrip("`").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return QueryPlanError(
            error="json_parse_error", reason=f"Invalid JSON: {exc}"
        )

    if not isinstance(data, dict):
        return QueryPlanError(
            error="invalid_root", reason="Response not a JSON object"
        )

    warnings: list[str] = []

    # Intent
    intent = data.get("intent", "")
    if intent not in VALID_INTENTS:
        warnings.append(
            f"unknown intent '{intent}', defaulting to current_content_generation"
        )
        intent = "current_content_generation"

    # Topic query
    topic_query = str(data.get("topic_query", "")).strip()
    if not topic_query:
        return QueryPlanError(
            error="missing_topic_query",
            reason="topic_query alanı boş",
        )
    if len(topic_query) > 200:
        warnings.append(f"topic_query truncated from {len(topic_query)} to 200")
        topic_query = topic_query[:200]

    # Mode
    mode = data.get("mode", "current")
    if mode not in VALID_MODES:
        warnings.append(f"unknown mode '{mode}', defaulting to current")
        mode = "current"

    # Timeframes
    timeframes_raw = data.get("timeframes", []) or []
    if not isinstance(timeframes_raw, list):
        timeframes_raw = []
    timeframes: list[TimeframeSpec] = []
    for tf in timeframes_raw[:5]:  # max 5 timeframe
        if not isinstance(tf, dict):
            continue
        from_iso = tf.get("from", "")
        to_iso = tf.get("to", "")
        if from_iso and to_iso:
            timeframes.append(
                TimeframeSpec(
                    label=str(tf.get("label", ""))[:50],
                    from_iso=str(from_iso)[:50],
                    to_iso=str(to_iso)[:50],
                )
            )

    if mode == "comparison" and len(timeframes) < 2:
        warnings.append(
            f"comparison mode requires ≥2 timeframes, got {len(timeframes)}"
        )

    # Output type
    output_type = data.get("output_type", "x_post")
    if output_type not in VALID_OUTPUT_TYPES:
        warnings.append(
            f"unknown output_type '{output_type}', defaulting to x_post"
        )
        output_type = "x_post"

    # Tone
    tone = data.get("tone")
    if tone is not None and tone not in VALID_TONES:
        warnings.append(f"unknown tone '{tone}', set to None")
        tone = None

    # Constraints
    constraints = data.get("constraints", []) or []
    if not isinstance(constraints, list):
        constraints = []
    constraints = [str(c).strip()[:200] for c in constraints if c][:10]

    # Needs sources
    needs_sources = bool(data.get("needs_sources", True))

    # Min evidence
    try:
        min_ev = int(data.get("minimum_evidence_per_period", 2))
        min_ev = max(1, min(10, min_ev))
    except (TypeError, ValueError):
        min_ev = 2
        warnings.append("invalid minimum_evidence_per_period, defaulted to 2")

    return QueryPlan(
        intent=intent,
        topic_query=topic_query,
        mode=mode,  # type: ignore[arg-type]
        timeframes=timeframes,
        output_type=output_type,
        tone=tone,
        constraints=constraints,
        needs_sources=needs_sources,
        minimum_evidence_per_period=min_ev,
        warnings=warnings,
    )


# =============================================================================
# Public API
# =============================================================================


async def plan_query(
    *,
    user_request: str,
    current_time: datetime | None = None,
    user_locale: str = "tr-TR",
    user_tier: str = "free",
) -> QueryPlan | QueryPlanError:
    """Query planner çağrısı — DeepSeek V3 üzerinden.

    Cost tracking caller'da yapılır (track_provider_call ile sarın).
    """
    from app.providers.base import Message, ProviderError
    from app.providers.registry import bootstrap_default_providers, registry

    bootstrap_default_providers()

    try:
        provider = registry.route_for_tier(operation="chat", tier=user_tier)  # type: ignore[arg-type]
    except RuntimeError as exc:
        return QueryPlanError(
            error="no_provider", reason=f"No chat provider: {exc}"
        )

    user_message = render_user_payload(
        user_request=user_request,
        current_time=current_time,
        user_locale=user_locale,
        user_tier=user_tier,
    )

    try:
        result = await provider.generate_text(
            messages=[
                Message(role="system", content=SYSTEM_PROMPT),
                Message(role="user", content=user_message),
            ],
            max_tokens=512,
            temperature=0.1,  # düşük — deterministic plan
        )
    except ProviderError as exc:
        return QueryPlanError(error="provider_error", reason=str(exc)[:300])

    return parse_response(result.text)
