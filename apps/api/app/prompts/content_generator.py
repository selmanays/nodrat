"""Content Generator prompt v1.0 — X post variant (#25).

docs/engineering/prompt-contracts.md §4

Görev: Plan + agenda cards → X paylaşımları (max_posts adet)
Provider: DeepSeek V3 (free/starter), Haiku 4.5 (pro/agency) Faz 6+
Latency hedef: < 6s P95
Maliyet hedef: < $0.005 per generation
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

X_POST_MAX_CHARS = 280


SYSTEM_PROMPT_X_POST = """Sen Nodrat'ın İçerik Üretim ajanısın. Görevin, verilen gündem
kartlarına dayanarak {max_posts} adet X (Twitter) paylaşımı
üretmektir.

ÇIKTI SADECE JSON. Markdown, kod bloğu, açıklama YOK.

ÇIKTI ŞEMASI:
{{
  "posts": [
    {{
      "text": "string (max 280 char, Türkçe)",
      "angle": "string (paylaşımın hangi açıyı öne çıkardığı)",
      "char_count": number,
      "related_agenda_card_ids": ["uuid"]
    }}
  ],
  "summary": "string (opsiyonel, üretim özeti)",
  "sources": [
    {{ "title": "...", "source": "...", "url": "..." }}
  ],
  "warnings": ["string"]
}}

KESİN KURALLAR:

1. SADECE verilen agenda_cards ve supplementary_chunks içindeki
   bilgilere dayan. Bunlar dışında bilgi EKLEME.

2. Her post en az bir agenda_card'a referans vermeli
   (related_agenda_card_ids non-empty).

3. Kaynakta olmayan kişi, kurum, tarih, sayı, alıntı UYDURMA.
   Bilmediğin bilgiyi yazma.

4. Eski olayları "şu an oluyor" gibi sunma. Tarih bağlamı koru:
   - User payload'da `current_time` ISO-8601 verilir (BUGÜNÜN tarihi)
   - "2024'te" → geçmiş zaman
   - "Geçen hafta" → relative, agenda_card.timeline veya source_refs published_at'a göre
   - Olay current_time'dan 7+ gün önce ise "geçen hafta", 24h+ ise "dün/bugün başında"
   - SADECE current_time'a YAKIN olayları "şu an" olarak sun

5. Verified olmayan kişi etiketlerini "kesin" ifade etme.

6. Her post 280 karakteri AŞMAMALI. Char count kontrol et.

7. URL/link YERLEŞTİRME. Kaynaklar ayrı "sources" array'inde.

8. Hashtag minimum (1-2 max). Aşırı hashtag YOK.

9. Her post farklı bir angle olmalı. Aynı şeyi tekrar etmeyen
   çeşitlilik ({max_posts} kadar fikir).

10. Tone:
    - "tarafsız" → veri merkezli, yorumsuz
    - "eleştirel" → sert ama kaynaklı
    - "mizahi" → ironi, hakaret yok
    - "kurumsal" → soğukkanlı
    - "analitik" → veri ve karşılaştırma
    - "sade" → kısa, etkileyici cümle

11. style_profile verildiyse rules_json'daki sentence_length, tone,
    rhetorical_patterns'a uy. style_profile null ise tone'a göre standart.

12. AGENDA_CARDS YETERSİZSE (verilen kart sayısı < beklenen):
    {{ "posts": [], "warnings": ["insufficient_data"], "sources": [] }} döndür.

13. ⛔ ALAKA KONTROLÜ — MUTLAK KURAL (halüsinasyon koruması):

    İLK ADIM (içerik üretmeden ÖNCE) bu kontrolü yap:

    request_text → ana konu/varlık çıkar (örn. "Türkiye-Fransa ilişkileri")
    agenda_cards.title + summary → kapsadıkları konuyu çıkar

    EĞER agenda_cards request_text'in ANA KONUSUNU doğrudan kapsamıyorsa,
    HEMEN ŞUNU DÖNDÜR ve dur:

    {{
      "posts": [],
      "summary": "",
      "warnings": ["irrelevant_sources"],
      "sources": []
    }}

    YASAK DAVRANIŞLAR (kesinlikle yapma):
    ❌ "Kaynaklar konuyu kapsamıyor ama yine de özet üreteyim" — HAYIR
    ❌ "Yarım/ilgisiz bilgi de olsa cevap vereyim" — HAYIR
    ❌ "Genel/küresel bağlamda bahset" — HAYIR
    ❌ status=completed + warning ekleyip içerik döndürmek — HAYIR

    DOĞRU DAVRANIŞ:
    ✅ Alakasızsa posts=[] + warnings=["irrelevant_sources"] + DUR

    Örnekler:

    Örnek 1 (IRRELEVANT — boş döndür):
      request: "Türkiye-Fransa ilişkileri"
      cards: ["İran İHA üretimi", "BAE OPEC ayrılma", "Trump-Merz gerilimi"]
      → posts=[], warnings=["irrelevant_sources"]
      (Hiçbiri Türkiye-Fransa ilişkileri DEĞİL)

    Örnek 2 (IRRELEVANT — boş döndür):
      request: "deprem haberleri"
      cards: ["futbol maçı sonucu", "AGS sınav tarihi"]
      → posts=[], warnings=["irrelevant_sources"]

    Örnek 3 (ALAKALI — devam et):
      request: "Türkiye ekonomisi"
      cards: ["ihracat verileri", "enflasyon raporu"]
      → posts=[...] üret

    Örnek 4 (ALAKALI — devam et):
      request: "Süper Lig"
      cards: ["Galatasaray Fenerbahçe maçı", "Süper Lig hakem kararı"]
      → posts=[...] üret

14. FSEK uyumu: 25 kelimeden uzun direct quote yok.
"""


# =============================================================================
# Input formatter
# =============================================================================


def render_user_payload(
    *,
    request: str,
    retrieval_plan: dict[str, Any],
    agenda_cards: list[dict[str, Any]],
    supplementary_chunks: list[dict[str, Any]] | None = None,
    style_profile: dict[str, Any] | None = None,
    output_constraints: dict[str, Any] | None = None,
    max_excerpt_chars: int = 800,
) -> str:
    """Plan + agenda + chunks → user message JSON.

    NOT: Agenda card'ların full content'i gider. Supplementary chunks
    excerpt'lendir (cost guard).
    """
    sanitized_chunks = []
    for ch in (supplementary_chunks or [])[:10]:
        text = ch.get("chunk_text") or ""
        if len(text) > max_excerpt_chars:
            text = text[:max_excerpt_chars] + "..."
        sanitized_chunks.append(
            {
                "article_id": str(ch.get("article_id", "")),
                "chunk_text": text,
                "source_name": ch.get("source_name"),
                "url": ch.get("url") or ch.get("canonical_url"),
                "published_at": (
                    ch["published_at"].isoformat()
                    if isinstance(ch.get("published_at"), datetime)
                    else ch.get("published_at")
                ),
            }
        )

    sanitized_cards = []
    for c in agenda_cards[:10]:
        sanitized_cards.append(
            {
                "id": str(c.get("id", "")),
                "title": c.get("title", "")[:300],
                "summary": c.get("summary", "")[:1500],
                "key_points": c.get("key_points") or [],
                "content_angles": c.get("content_angles") or [],
                "source_refs": c.get("source_refs") or [],
                "status": c.get("status"),
                "importance_score": c.get("importance_score"),
                "freshness_score": c.get("freshness_score"),
            }
        )

    # #169 — current_time payload'a eklenir. LLM "bugün/dün" referanslarını
    # doğru tarihle ilişkilendirir, eski olayı "şu an" gibi sunmaz (Kural 4).
    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "current_time": now_iso,
        "request": request[:1000],
        "retrieval_plan": retrieval_plan,
        "agenda_cards": sanitized_cards,
        "supplementary_chunks": sanitized_chunks,
        "style_profile": style_profile,
        "output_constraints": output_constraints or {},
    }
    return json_dumps(payload)


SYSTEM_PROMPT_SUMMARY = """Sen Nodrat'ın İçerik Üretim ajanısın. Görevin, verilen gündem
kartlarına dayanarak {item_count} maddelik TEK BİR ÖZET içeriği üretmektir.
NotebookLM-benzeri çıktı: tek başlık + N madde + her madde için kaynak.

ÇIKTI SADECE JSON. Markdown, kod bloğu, açıklama YOK.

ÇIKTI ŞEMASI:
{{
  "summary_doc": {{
    "title": "string (genel başlık, 5-10 kelime Türkçe)",
    "items": [
      {{
        "event": "string (olay özeti, 1-3 cümle, max 280 char)",
        "source": "string (kaynak adı, örn. 'TRT Haber')",
        "date": "ISO-8601 veya 'bilinmiyor'",
        "agenda_card_id": "uuid (related agenda card)"
      }}
    ]
  }},
  "sources": [
    {{ "title": "...", "source": "...", "url": "..." }}
  ],
  "warnings": ["string"]
}}

KESİN KURALLAR:

1. SADECE verilen agenda_cards ve supplementary_chunks içindeki bilgilere dayan.
   UYDURMA YASAK.

2. {item_count} madde üret. Her madde farklı bir agenda card'a referans
   vermeli (related_agenda_card_ids non-empty her item için).

3. Maddeleri **ÖNEMSEME ve TARİH** sırasına göre sırala:
   - En önemli + en yeni → ilk sırada
   - importance_score + freshness_score birleşik
   - "son N olay" sorgusunda freshness ağırlıklı
   - "önemli N olay" sorgusunda importance ağırlıklı

4. Her madde için tarih:
   - agenda_card.timeline veya source_refs.published_at'a göre
   - current_time'a göre relative ifade kullanma; absolute tarih bağlamı ver
   - Bilinmiyorsa "bilinmiyor"

5. ⛔ ALAKA KONTROLÜ — MUTLAK KURAL (halüsinasyon koruması):
   request_text → ana konu/varlık çıkar
   agenda_cards → kapsadıkları konuları çıkar

   EĞER agenda_cards request_text'in ana konusunu kapsamıyorsa, HEMEN ŞUNU
   DÖNDÜR ve dur:

   {{
     "summary_doc": {{ "title": "", "items": [] }},
     "sources": [],
     "warnings": ["irrelevant_sources"]
   }}

6. Title kısa ve betimleyici (örn. "Bugünün 5 önemli gelişmesi",
   "Türkiye-Fransa ilişkilerinde son 3 olay", vb.).

7. Items.event 1-3 cümle. Detay için summary'den çek, alıntı YASAK
   (FSEK 25 kelime kuralı uygula).

8. AGENDA_CARDS YETERSİZSE (verilen kart sayısı < {item_count}):
   {{
     "summary_doc": {{ "title": "", "items": [] }},
     "sources": [],
     "warnings": ["insufficient_data"]
   }}
"""


def format_system_prompt(*, max_posts: int = 5, output_type: str = "x_post") -> str:
    """System prompt template'i output_type ve sayı ile doldur.

    Args:
        max_posts: x_post için adet, summary için item count
        output_type: "x_post" (default) veya "summary" (#173 PR-F)
    """
    if output_type == "summary":
        return SYSTEM_PROMPT_SUMMARY.format(item_count=max_posts)
    return SYSTEM_PROMPT_X_POST.format(max_posts=max_posts)


# =============================================================================
# Output validator
# =============================================================================


@dataclass
class XPost:
    text: str
    angle: str
    char_count: int
    related_agenda_card_ids: list[str]


@dataclass
class SummaryItem:
    """#173 PR-F — multi-item summary doc içindeki tek madde."""

    event: str
    source: str
    date: str
    agenda_card_id: str | None = None


@dataclass
class GeneratedXContent:
    posts: list[XPost]
    summary: str
    sources: list[dict[str, str]]
    warnings: list[str] = field(default_factory=list)

    # #173 PR-F — summary mode için multi-item
    summary_doc_title: str = ""
    summary_doc_items: list[SummaryItem] = field(default_factory=list)


@dataclass
class ContentGenError:
    error: str
    reason: str


def parse_x_post_response(text: str) -> GeneratedXContent | ContentGenError:
    """LLM response → GeneratedXContent or error."""
    cleaned = text.strip()

    # Markdown fence
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
        return ContentGenError(
            error="json_parse_error", reason=f"Invalid JSON: {exc}"
        )

    if not isinstance(data, dict):
        return ContentGenError(
            error="invalid_root", reason="Response not JSON object"
        )

    warnings: list[str] = list(data.get("warnings", []) or [])

    # Sources (her iki output_type için)
    sources_raw = data.get("sources", []) or []
    if not isinstance(sources_raw, list):
        sources_raw = []
    sources: list[dict[str, str]] = []
    for s in sources_raw[:30]:
        if not isinstance(s, dict):
            continue
        sources.append(
            {
                "title": str(s.get("title", ""))[:300],
                "source": str(s.get("source", ""))[:120],
                "url": str(s.get("url", ""))[:500],
            }
        )

    # #173 PR-F — Summary mode (multi-item bullet doc)
    summary_doc = data.get("summary_doc")
    summary_doc_title = ""
    summary_doc_items: list[SummaryItem] = []
    if isinstance(summary_doc, dict):
        summary_doc_title = str(summary_doc.get("title", "")).strip()[:200]
        raw_items = summary_doc.get("items", []) or []
        if isinstance(raw_items, list):
            for it in raw_items[:10]:
                if not isinstance(it, dict):
                    continue
                evt = str(it.get("event", "")).strip()
                if not evt:
                    continue
                if len(evt) > 500:
                    evt = evt[:500]
                summary_doc_items.append(
                    SummaryItem(
                        event=evt,
                        source=str(it.get("source", ""))[:120],
                        date=str(it.get("date", ""))[:40],
                        agenda_card_id=str(it.get("agenda_card_id", "")) or None,
                    )
                )

    # Summary mode: items var, posts boş olabilir
    if summary_doc_items:
        return GeneratedXContent(
            posts=[],
            summary=summary_doc_title,
            sources=sources,
            warnings=warnings,
            summary_doc_title=summary_doc_title,
            summary_doc_items=summary_doc_items,
        )

    # x_post mode (eski path)
    raw_posts = data.get("posts", []) or []
    if not isinstance(raw_posts, list):
        raw_posts = []

    posts: list[XPost] = []
    for p in raw_posts[:10]:  # cap at 10
        if not isinstance(p, dict):
            continue
        text_v = str(p.get("text", "")).strip()
        if not text_v:
            continue
        # Hard char cap
        if len(text_v) > X_POST_MAX_CHARS:
            warnings.append(
                f"post truncated from {len(text_v)} to {X_POST_MAX_CHARS}"
            )
            text_v = text_v[:X_POST_MAX_CHARS]

        angle = str(p.get("angle", "")).strip()[:200]
        related = p.get("related_agenda_card_ids", []) or []
        if not isinstance(related, list):
            related = []
        related = [str(r) for r in related if r][:5]
        if not related:
            warnings.append("post has empty related_agenda_card_ids")

        posts.append(
            XPost(
                text=text_v,
                angle=angle or "untagged",
                char_count=len(text_v),
                related_agenda_card_ids=related,
            )
        )

    if not posts:
        # insufficient_data signal
        if "insufficient_data" in warnings:
            return ContentGenError(
                error="insufficient_data",
                reason="LLM reported insufficient agenda cards",
            )
        # irrelevant_sources — #157 (LLM'in alaka kontrolü)
        if "irrelevant_sources" in warnings:
            return ContentGenError(
                error="insufficient_data",  # frontend tek state ile handle eder
                reason="Bulunan kaynaklar sorgu ile alakasız (LLM relevance check)",
            )
        return ContentGenError(
            error="empty_posts", reason="No valid posts in response"
        )

    summary = str(data.get("summary", "")).strip()[:1000]

    return GeneratedXContent(
        posts=posts,
        summary=summary,
        sources=sources,
        warnings=warnings,
    )
