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

# MVP-1.1 #173: x_post + summary (cut-list revize, risk-register.md §4.5)
# Diğerleri MVP-2'de açılacak
VALID_OUTPUT_TYPES = {"x_post", "summary"}

# Tüm output type'lar (planner LLM bilgisi için)
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
            "source_based_briefing" | "multi_summary",
  "topic_query": "ana konu, kısa Türkçe (3-8 kelime)",
  "keywords": ["anahtar1", "anahtar2", "..."],
  "mode": "current" | "weekly" | "archive" | "comparison",
  "timeframes": [
    { "label": "string", "from": "ISO-8601", "to": "ISO-8601" }
  ],
  "output_type": "x_post" | "summary",
  "requested_count": 1-10 (kullanıcının istediği madde/post sayısı; default 1),
  "tone": "tarafsız" | "eleştirel" | "mizahi" | "kurumsal" | "aktivist" |
          "analitik" | "sade" | "sert ama kaynaklı" | null,
  "geographic_focus": "TR" | "US" | "DE" | "FR" | "GB" | "IL" | "PS" |
                      "RU" | "UA" | "SY" | "IR" | "GR" | "CY" | null,
  "constraints": ["string"],
  "needs_sources": true,
  "minimum_evidence_per_period": 3
}

INTENT VE OUTPUT_TYPE EŞLEMESİ (MVP-1.1 #173):

- "Son 5 önemli gelişmeyi özetle" / "bugünkü olayları sırala"
  → intent="multi_summary", output_type="summary", requested_count=5
  TEK KART içinde N madde halinde özet (NotebookLM-benzeri)

- "Tweet at" / "X paylaşımı üret" / "post yaz"
  → intent="current_content_generation", output_type="x_post", requested_count=1
  TEK X post (280 char)

- Sayı parsing:
  "Son 5 olayı" → requested_count=5
  "3 paylaşım üret" → requested_count=3
  "özetle" (sayı yok) → requested_count=5 default summary için
  "tweet" (sayı yok) → requested_count=1 default x_post için

GEOGRAPHIC_FOCUS (#209 — coğrafi context filter):
- "türkiye/türkiyedeki/yurtiçinde/ülkemizde/burada (Türkiye konteksti)" → "TR"
- "ABD'de/Amerika'da" → "US"
- "Almanya'da/Almanyadaki" → "DE"
- "Fransa'da" → "FR"
- "İsrail/Filistin/Gazze" → "IL" veya "PS"
- "Yunanistan/Kıbrıs" → "GR" / "CY"
- "Rusya/Ukrayna" → "RU" / "UA"
- "İran/Suriye" → "IR" / "SY"
- Coğrafi context yoksa → null
- Belirsizse (örn. "dünya gündemi") → null
- Türkiye dışı şehir adı geçiyorsa o ülke (örn. "Berlin'de" → "DE")

ÖNEMLİ: Sadece kullanıcı açıkça coğrafi belirtim yaptıysa doldur.
"son 1 saatteki gelişmeler" → null (coğrafi belirtim yok)
"son 1 saatteki türkiye gelişmeleri" → "TR"

KEYWORDS (ZORUNLU — boş bırakman YASAK):
- En az 3, en fazla 5 anahtar kelime DOLDUR
- topic_query'deki ana konunun parçalarını yaz: kelime kelime böl + eş anlamlı + üst kavram
- Boş array `[]` döndürürsen plan REDDEDİLİR
- Türkçe lower-case
- Örnek (TAM YANIT):
  request: "AGS sınavı başvurusu"
    → keywords: ["ags", "başvuru", "sınav", "meb", "akademi giriş sınavı"]
  request: "Bakan Fidan İran görüşmesi"
    → keywords: ["fidan", "iran", "diplomasi", "görüşme", "dışişleri"]
  request: "Türkiye-Fransa ilişkileri"
    → keywords: ["türkiye", "fransa", "ilişkiler", "diplomatik", "macron"]
  request: "En düşük emekli maaşı"
    → keywords: ["emekli", "maaş", "ssk", "bağ-kur", "zam"]
  request: "Son 5 önemli gelişmeyi özetle"
    → keywords: ["gündem", "haber", "gelişme", "olay", "günlük"]

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

    # #171 PR-E — query enrichment için planner'dan
    keywords: list[str] = field(default_factory=list)

    # #173 PR-F — kullanıcının istediği madde/post sayısı
    requested_count: int = 1

    # #209 — coğrafi context filter (ISO ülke kodu veya None)
    geographic_focus: str | None = None

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

    # Keywords (#171 — PR-E hybrid search enrichment)
    raw_keywords = data.get("keywords") or []
    keywords: list[str] = []
    if isinstance(raw_keywords, list):
        for kw in raw_keywords[:5]:  # max 5
            if isinstance(kw, str):
                cleaned = kw.strip().lower()
                if 1 <= len(cleaned) <= 60:
                    keywords.append(cleaned)

    # #175 — Fallback: planner keywords boş bıraktıysa topic_query'den derive et.
    # Hybrid retrieval sparse skoru için kelime kümesi şart; LLM keywords basamağı atlarsa
    # boş array döndürmeyelim, query parametrelerini düşmemiş gibi devam edelim.
    if not keywords and topic_query:
        warnings.append("planner_keywords_empty_fallback_topic_query")
        derived = [
            w for w in topic_query.lower().split()
            if 2 <= len(w) <= 60 and w not in {"ve", "ile", "için", "bir", "bu"}
        ]
        keywords = derived[:5]
    elif not keywords:
        warnings.append("planner_keywords_empty")

    # requested_count (#173 PR-F — kullanıcı sayısal isteği)
    raw_count = data.get("requested_count")
    requested_count = 1
    try:
        rc = int(raw_count) if raw_count is not None else 1
        requested_count = max(1, min(rc, 10))
    except (TypeError, ValueError):
        requested_count = 1

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

    # #209 — geographic_focus (ISO 2-char code veya null)
    geographic_focus = data.get("geographic_focus")
    if geographic_focus is not None:
        gf = str(geographic_focus).strip().upper()
        if len(gf) == 2 and gf.isalpha():
            geographic_focus = gf
        else:
            warnings.append(f"invalid geographic_focus '{geographic_focus}', set to None")
            geographic_focus = None

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
        keywords=keywords,
        requested_count=requested_count,
        mode=mode,  # type: ignore[arg-type]
        timeframes=timeframes,
        output_type=output_type,
        tone=tone,
        geographic_focus=geographic_focus,
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
            json_mode=True,  # #171 PR-E — DeepSeek deterministic JSON
        )
    except ProviderError as exc:
        return QueryPlanError(error="provider_error", reason=str(exc)[:300])

    return parse_response(result.text)
