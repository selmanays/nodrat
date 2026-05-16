"""#904 — schema.org JSON-LD Tier-0 extractor + cascade entegrasyon testleri.

Kök neden: content_quality `<p>`-sayım gate'i `<div>`-CMS / JSON-LD-gövdeli
siteleri (Habertürk/Fotomaç) terminal archived'a atıyordu. Tier-0 generic
JSON-LD `articleBody` parser bunları per-site selector OLMADAN kurtarır.
"""

from __future__ import annotations

import json

from app.core.extractor import extract_article, extract_structured_tier
from app.core.structured_data import parse_jsonld

LONG_BODY = (
    "Antalya'da deniz kaplumbağaları bu yıl erken yumurta bırakmaya başladı. "
    "Uzmanlar iklim değişikliğinin üreme takvimini öne çektiğini belirtiyor. "
) * 6  # > 200 char


def _html(jsonld: object, body_html: str = "<div>içerik</div>") -> str:
    blob = json.dumps(jsonld, ensure_ascii=False)
    return (
        "<html><head><title>Test</title>"
        f'<script type="application/ld+json">{blob}</script>'
        f"</head><body>{body_html}</body></html>"
    )


def test_newsarticle_articlebody_found():
    html = _html(
        {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "Antalya'da kaplumbağalar erken yumurtladı",
            "articleBody": LONG_BODY,
            "datePublished": "2026-05-15T08:30:00+03:00",
            "author": {"@type": "Person", "name": "AA Muhabiri"},
            "image": {"@type": "ImageObject", "url": "https://x/t.jpg"},
        }
    )
    sd = parse_jsonld(html)
    assert sd.found
    assert sd.title.startswith("Antalya")
    assert len(sd.clean_text) >= 200
    assert sd.author == "AA Muhabiri"
    assert sd.published_raw == "2026-05-15T08:30:00+03:00"
    assert sd.image_url == "https://x/t.jpg"
    assert sd.schema_type == "newsarticle"


def test_graph_and_longest_body_wins():
    html = _html(
        {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebPage", "name": "yan sayfa"},
                {"@type": "NewsArticle", "headline": "kısa", "articleBody": "x"},
                {
                    "@type": ["Article", "NewsArticle"],
                    "headline": "Asıl haber",
                    "articleBody": LONG_BODY,
                },
            ],
        }
    )
    sd = parse_jsonld(html)
    assert sd.found
    assert sd.title == "Asıl haber"
    assert len(sd.clean_text) >= 200


def test_value_wrapper_and_type_url():
    html = _html(
        {
            "@type": "http://schema.org/ReportageNewsArticle",
            "headline": {"@value": "Wrapped başlık"},
            "articleBody": {"@value": LONG_BODY},
        }
    )
    sd = parse_jsonld(html)
    assert sd.found
    assert sd.title == "Wrapped başlık"
    assert sd.schema_type == "reportagenewsarticle"


def test_short_body_not_found():
    html = _html(
        {"@type": "NewsArticle", "headline": "h", "articleBody": "çok kısa özet"}
    )
    sd = parse_jsonld(html)
    assert not sd.found  # min_body_len altı → caller density'ye düşer


def test_malformed_script_skipped_good_one_used():
    good = json.dumps(
        {"@type": "NewsArticle", "headline": "İyi", "articleBody": LONG_BODY},
        ensure_ascii=False,
    )
    html = (
        "<html><head>"
        '<script type="application/ld+json">{ bozuk json,, }</script>'
        f'<script type="application/ld+json">{good}</script>'
        "</head><body></body></html>"
    )
    sd = parse_jsonld(html)
    assert sd.found
    assert sd.title == "İyi"


def test_no_jsonld_not_found():
    sd = parse_jsonld("<html><body><p>hiç jsonld yok</p></body></html>")
    assert not sd.found


def test_array_root_payload():
    blob = json.dumps(
        [
            {"@type": "BreadcrumbList"},
            {"@type": "NewsArticle", "headline": "Dizi", "articleBody": LONG_BODY},
        ],
        ensure_ascii=False,
    )
    html = (
        "<html><head>"
        f'<script type="application/ld+json">{blob}</script>'
        "</head><body></body></html>"
    )
    sd = parse_jsonld(html)
    assert sd.found and sd.title == "Dizi"


# ---- Cascade entegrasyon (#904 — Habertürk/Fotomaç vakası) ----------------


def test_cascade_picks_structured_tier_div_body():
    """`<div>`-gövdeli sayfa (eski thin_content false-positive) — Tier-0
    JSON-LD ile başarılı, terminal archived DEĞİL."""
    html = _html(
        {
            "@type": "NewsArticle",
            "headline": "Habertürk vakası",
            "articleBody": LONG_BODY,
            "datePublished": "2026-05-15",
        },
        body_html="<div class='news-content'>JS ile gelir</div>",  # <p> YOK
    )
    structured = extract_structured_tier(html, url="https://haberturk.com/x")
    assert structured.successful
    assert structured.extraction_confidence >= 0.6
    assert structured.strategy_used == "structured_data"

    result = extract_article(html, url="https://haberturk.com/x")
    assert result.successful
    assert result.strategy_used == "structured_data"
    assert len(result.clean_text) >= 200


def test_cascade_falls_through_when_jsonld_short():
    """AA vakası — JSON-LD yalnız kısa özet; Tier-0 .successful değil →
    trafilatura/fallback kademesine düşülür (içerik <p>/article'da)."""
    long_para = "<p>" + ("Gerçek gövde cümlesi burada uzun uzun yer alır. " * 10) + "</p>"
    html = _html(
        {"@type": "NewsArticle", "headline": "AA", "articleBody": "76 char özet"},
        body_html=f"<article><h1>AA başlık</h1>{long_para}</article>",
    )
    structured = extract_structured_tier(html, url="https://aa.com.tr/x")
    assert not structured.found if False else not structured.successful
    # extract_article Tier-0'ı atlayıp density/fallback ile başarılı olmalı
    result = extract_article(html, url="https://aa.com.tr/x")
    assert result.strategy_used in ("trafilatura", "fallback")
    assert len(result.clean_text) >= 200
