"""Agenda Card Generator prompt v1.0 (#21).

docs/engineering/prompt-contracts.md §3
PRD §2.6, §9.2, §12.4 (halüsinasyon korumaları)

Görev: Event cluster'a ait haberleri tek bir gündem kartına özetlemek.
Provider: DeepSeek V3 (default, free tier), Haiku 4.5 (Pro tier).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.json_utils import dumps as json_dumps

logger = logging.getLogger(__name__)


PROMPT_VERSION = "1.0.0"


# =============================================================================
# System prompt (prompt-contracts.md §3.3 birebir)
# =============================================================================


SYSTEM_PROMPT = """Sen Nodrat'ın Agenda Card Generator ajanısın. Görevin, aynı olaya
ait birden fazla haberin oluşturduğu bir cluster'ı tek bir
"gündem kartı"na özetlemektir.

ÇIKTI SADECE JSON. Markdown, kod bloğu, açıklama YOK.

ÇIKTI ŞEMASI:
{
  "title": "string (max 200 char, Türkçe)",
  "summary": "string (300-500 char, Türkçe)",
  "key_points": [
    "string (max 200 char each, en az 3 en fazla 5 madde)"
  ],
  "content_angles": [
    "string (kısa, üretim açıları, en fazla 5)"
  ],
  "timeline": [
    { "date": "ISO", "event": "string" }
  ],
  "source_refs": [
    { "source": "string", "title": "string", "url": "string", "published_at": "ISO" }
  ],
  "status": "developing" | "active" | "cooling" | "stale",
  "importance_score": 0.0-1.0,
  "freshness_score": 0.0-1.0
}

KESİN KURALLAR:

1. SADECE verilen articles dizisindeki bilgilere dayan.
   Bu liste dışında bilgi EKLEME, YORUM YAPMA.

2. Kaynakta olmayan kişi, kurum, tarih, sayı, alıntı UYDURMA.
   Bilmediğin bilgiyi yazma.

3. Her article SOURCE_REFS'e dahil edilmeli (yani article_count = source_refs.length).
   Eksik referans = kabul edilmez.

4. Direct quote 25 kelimeden uzun olamaz (FSEK).
   Her quote için kaynağı belirt.

5. timeline tarihleri ISO 8601 formatında.
   Yoksa boş array döndür [].

6. importance_score: source_count + article_count + recency'a göre.
   1 source / 1 article → 0.2 civarı
   3+ source / 5+ article → 0.7+

7. freshness_score: last_seen_at - current_time'a göre.
   Son 6 saat → 1.0
   Son 24 saat → 0.7
   Son 72 saat → 0.4

8. Status:
   - 'developing': son 72h içinde, article_count < 2
   - 'active': son 72h, article_count ≥ 2
   - 'cooling': 72h-7gün arası
   - 'stale': 7gün+ ama active değil

9. Özet ve key_points NOTRC bir tonda yaz. Yorum YOK.
   "X iddiaları" deniyor → "X yetkilileri açıkladı" değil
   Doğrulanmış: kaynaklar mutabık → "X gerçekleşti"
   Tartışmalı: kaynaklar farklı diyor → "raporlara göre"

10. content_angles: editör için fikir önerileri (2-5 madde).
    Her angle ayrı bir post fikri olmalı.

11. JSON dışında HİÇBİR şey döndürme. SADECE JSON.

12. Veriler yetersizse (article_count < 2 ve summary 200 char altı):
    {"error": "insufficient_data", "reason": "..."}
"""


# =============================================================================
# Input formatter
# =============================================================================


def render_user_payload(
    *,
    event_cluster: dict[str, Any],
    articles: list[dict[str, Any]],
    current_time: datetime | None = None,
    max_excerpt_chars: int = 1500,
) -> str:
    """Cluster + articles → user message JSON string.

    article.clean_text excerpt'lerini max_excerpt_chars'a kadar kırpar (cost guard).

    NOT: PII redaction provider adapter (DeepSeek) tarafında yapılır
        (deepseek.py user message'a redact uygular). Burada ekstra redact yok
        — clean_text zaten PII redacted (cleaning.py).
    """
    now_iso = (current_time or datetime.now(timezone.utc)).isoformat()

    sanitized_articles = []
    for a in articles[:20]:  # max 20 article (cost guard)
        text = a.get("clean_text") or ""
        if len(text) > max_excerpt_chars:
            text = text[:max_excerpt_chars] + "..."
        sanitized_articles.append(
            {
                "id": str(a.get("id", "")),
                "title": (a.get("title") or "")[:300],
                "subtitle": (a.get("subtitle") or "")[:200],
                "source_name": a.get("source_name"),
                "source_reliability": float(a.get("source_reliability") or 0.7),
                "published_at": (
                    a["published_at"].isoformat()
                    if isinstance(a.get("published_at"), datetime)
                    else a.get("published_at")
                ),
                "clean_text_excerpt": text,
                "url": a.get("canonical_url") or a.get("url"),
            }
        )

    payload = {
        "event_cluster": {
            "id": str(event_cluster.get("id", "")),
            "canonical_title": event_cluster.get("canonical_title", ""),
            "first_seen_at": (
                event_cluster["first_seen_at"].isoformat()
                if isinstance(event_cluster.get("first_seen_at"), datetime)
                else event_cluster.get("first_seen_at")
            ),
            "last_seen_at": (
                event_cluster["last_seen_at"].isoformat()
                if isinstance(event_cluster.get("last_seen_at"), datetime)
                else event_cluster.get("last_seen_at")
            ),
            "article_count": event_cluster.get("article_count", len(articles)),
            "source_count": event_cluster.get("source_count", 1),
        },
        "articles": sanitized_articles,
        "current_time": now_iso,
    }
    return json_dumps(payload)


# =============================================================================
# Output validator
# =============================================================================


@dataclass
class AgendaCardOutput:
    """Parse + validate edilmiş LLM çıktısı."""

    title: str
    summary: str
    key_points: list[str]
    content_angles: list[str]
    timeline: list[dict[str, Any]]
    source_refs: list[dict[str, Any]]
    status: str
    importance_score: float
    freshness_score: float

    warnings: list[str] = field(default_factory=list)
    """Validation sırasında çıkan uyarılar (soft)."""


@dataclass
class AgendaCardError:
    """LLM 'insufficient_data' veya parse error."""

    error: str
    reason: str


def parse_response(text: str) -> AgendaCardOutput | AgendaCardError:
    """LLM response → AgendaCardOutput.

    Markdown code fence varsa temizle (DeepSeek bazen kullanır).
    """
    cleaned = text.strip()

    # Markdown code fence temizliği
    if cleaned.startswith("```"):
        # ```json\n...\n```
        cleaned = cleaned.split("```", 2)
        if len(cleaned) >= 2:
            content = cleaned[1]
            if content.startswith("json\n"):
                content = content[5:]
            elif content.startswith("\n"):
                content = content[1:]
            cleaned = content.rstrip("`").strip()
        else:
            cleaned = text.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return AgendaCardError(
            error="json_parse_error", reason=f"Invalid JSON: {exc}"
        )

    if not isinstance(data, dict):
        return AgendaCardError(
            error="invalid_root", reason="Response not a JSON object"
        )

    # Insufficient data signal
    if data.get("error") == "insufficient_data":
        return AgendaCardError(
            error="insufficient_data",
            reason=str(data.get("reason", "LLM reported insufficient data"))[:300],
        )

    # Schema validation
    warnings: list[str] = []

    title = str(data.get("title", "")).strip()
    if not title:
        return AgendaCardError(error="missing_title", reason="title alanı boş")
    if len(title) > 500:
        warnings.append(f"title truncated from {len(title)} to 500")
        title = title[:500]

    summary = str(data.get("summary", "")).strip()
    if not summary or len(summary) < 50:
        return AgendaCardError(
            error="insufficient_summary",
            reason=f"summary too short: {len(summary)} chars",
        )
    if len(summary) > 2000:
        warnings.append(f"summary truncated from {len(summary)} to 2000")
        summary = summary[:2000]

    key_points = data.get("key_points", []) or []
    if not isinstance(key_points, list):
        warnings.append("key_points not list, replaced with []")
        key_points = []
    key_points = [str(kp).strip()[:300] for kp in key_points if kp]
    if len(key_points) < 3:
        warnings.append(f"key_points only {len(key_points)} items (expected 3+)")

    content_angles = data.get("content_angles", []) or []
    if not isinstance(content_angles, list):
        content_angles = []
    content_angles = [str(a).strip()[:200] for a in content_angles if a][:5]

    timeline = data.get("timeline", []) or []
    if not isinstance(timeline, list):
        timeline = []
    timeline = [
        t for t in timeline if isinstance(t, dict) and t.get("event")
    ][:20]

    source_refs = data.get("source_refs", []) or []
    if not isinstance(source_refs, list):
        source_refs = []
    source_refs = [
        s for s in source_refs if isinstance(s, dict) and s.get("source")
    ][:30]

    if not source_refs:
        warnings.append("source_refs empty (caller should add fallback)")

    status = data.get("status", "developing")
    if status not in ("developing", "active", "cooling", "stale", "archived"):
        warnings.append(f"invalid status '{status}', defaulting to 'developing'")
        status = "developing"

    try:
        importance = float(data.get("importance_score", 0.5))
        importance = max(0.0, min(1.0, importance))
    except (TypeError, ValueError):
        importance = 0.5
        warnings.append("invalid importance_score, defaulted to 0.5")

    try:
        freshness = float(data.get("freshness_score", 0.5))
        freshness = max(0.0, min(1.0, freshness))
    except (TypeError, ValueError):
        freshness = 0.5
        warnings.append("invalid freshness_score, defaulted to 0.5")

    return AgendaCardOutput(
        title=title,
        summary=summary,
        key_points=key_points,
        content_angles=content_angles,
        timeline=timeline,
        source_refs=source_refs,
        status=status,
        importance_score=importance,
        freshness_score=freshness,
        warnings=warnings,
    )
