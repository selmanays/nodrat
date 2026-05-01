"""Detail extractor unit tests — 3 kademeli strateji.

Sentetik HTML fixtures ile test:
  - Strategy 1 (selectors) — admin tanımlı CSS selectors
  - Strategy 2 (trafilatura) — gerçekçi haber HTML
  - Strategy 3 (fallback) — sadece OG meta + h1 + p
  - HTML sanitization (XSS guard)
  - extraction_confidence skoru
  - main_image_url relative→absolute
"""

from __future__ import annotations

from app.core.extractor import (
    MIN_TEXT_LENGTH,
    ExtractedArticle,
    _parse_iso_date,
    _resolve_image_url,
    _to_clean_text,
    extract_article,
    extract_fallback,
    extract_with_selectors,
    extract_with_trafilatura,
)


HTML_NEWS_BASIC = """
<!DOCTYPE html>
<html lang="tr">
<head>
  <title>Test Haber Başlığı</title>
  <meta property="og:title" content="OG: Test Haber Başlığı"/>
  <meta property="og:description" content="OG açıklama metni — özet."/>
  <meta property="og:image" content="https://example.com/image.jpg"/>
  <meta property="article:published_time" content="2025-09-01T12:00:00Z"/>
  <meta name="author" content="Ali Veli"/>
</head>
<body>
  <article>
    <h1>Test Haber Başlığı</h1>
    <p class="subtitle">Alt başlık burada</p>
    <p>Birinci paragraf — yeterince uzun olmalı ki extractor bunu içerikten saysın. Bu sebeple metnin uzunluğunu da arttırıyoruz.</p>
    <p>İkinci paragraf da yeterince uzun. Türkçe karakterler: ş, ç, ö, ü, ğ, İ, ı sorunsuz işlenmeli ve clean_text'te kalmalı.</p>
    <p>Üçüncü paragraf yine yeterli uzunlukta. trafilatura bu üç paragrafı body olarak çıkarmalı. Eğer çıkarmazsa fallback devreye girer ve OG metadata ile birleşik bir extraction yapar.</p>
  </article>
</body>
</html>
"""


HTML_WITH_DANGEROUS = """
<html><body>
<article>
<h1>XSS Test</h1>
<script>alert('xss')</script>
<style>body{display:none}</style>
<p>Birinci paragraf yeterince uzun bir cümledir, böylelikle extraction'a dahil edilebilsin diye yazıldı.</p>
<p>İkinci paragraf da uzun. <a href="javascript:alert(1)">bad link</a> içeriyor.</p>
<iframe src="https://evil.com"></iframe>
<button onclick="hack()">click me</button>
<p>Üçüncü paragraf da uzun bir metindir, böylece tutarlı bir test gövdesi olur.</p>
</article>
</body></html>
"""


HTML_FALLBACK = """
<html>
<head>
  <meta property="og:title" content="Fallback Title"/>
  <meta property="og:description" content="Sadece meta var — body kısa."/>
  <meta property="og:image" content="/relative/img.jpg"/>
</head>
<body>
<main>
<p>Tek bir paragraf var ama kısa.</p>
</main>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# _parse_iso_date
# ---------------------------------------------------------------------------


def test_parse_iso_date_z_format():
    dt = _parse_iso_date("2025-09-01T12:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.year == 2025 and dt.month == 9 and dt.day == 1
    assert dt.hour == 12


def test_parse_iso_date_with_offset():
    dt = _parse_iso_date("2025-09-01T15:00:00+03:00")
    assert dt is not None
    assert dt.hour == 12  # UTC'ye dönüşmüş


def test_parse_iso_date_date_only():
    dt = _parse_iso_date("2025-09-01")
    assert dt is not None
    assert dt.year == 2025


def test_parse_iso_date_invalid_returns_none():
    assert _parse_iso_date("not a date") is None
    assert _parse_iso_date("") is None


# ---------------------------------------------------------------------------
# _resolve_image_url
# ---------------------------------------------------------------------------


def test_resolve_absolute_https_unchanged():
    assert _resolve_image_url("https://x.com/a.jpg", "https://y.com") == "https://x.com/a.jpg"


def test_resolve_protocol_relative():
    assert _resolve_image_url("//cdn.example.com/img.jpg", "https://x.com/page") == (
        "https://cdn.example.com/img.jpg"
    )


def test_resolve_relative_path():
    assert _resolve_image_url("/img/a.jpg", "https://x.com/articles/123") == (
        "https://x.com/img/a.jpg"
    )


# ---------------------------------------------------------------------------
# _to_clean_text + sanitization
# ---------------------------------------------------------------------------


def test_clean_text_strips_dangerous_tags():
    text = _to_clean_text(HTML_WITH_DANGEROUS)
    assert "alert" not in text
    assert "javascript:" not in text.lower()
    assert "Birinci paragraf" in text


def test_clean_text_strips_short_paragraphs():
    """20 char altı text alınmaz."""
    html = "<html><body><p>Kısa</p><p>Bu paragraf yeterince uzun bir tanesidir, alınmalı.</p></body></html>"
    text = _to_clean_text(html)
    assert "Kısa" not in text
    assert "yeterince uzun" in text


# ---------------------------------------------------------------------------
# Strategy 1: extract_with_selectors
# ---------------------------------------------------------------------------


def test_selectors_full_match_high_confidence():
    selectors = {
        "title": "h1",
        "body": "article",
        "image": "meta[property='og:image']",
    }
    result = extract_with_selectors(
        HTML_NEWS_BASIC, url="https://example.com/test", selectors=selectors
    )
    assert result.strategy_used == "admin_selectors"
    assert "Test Haber Başlığı" in result.title
    assert len(result.clean_text) >= MIN_TEXT_LENGTH
    assert result.extraction_confidence >= 0.5


def test_selectors_no_match_zero_confidence():
    selectors = {"title": ".no-such-class", "body": ".no-such-class"}
    result = extract_with_selectors(
        HTML_NEWS_BASIC, url="https://example.com/test", selectors=selectors
    )
    assert result.extraction_confidence == 0.0
    assert result.error == "no selector matched"


def test_selectors_partial_match():
    selectors = {"title": "h1", "body": ".no-such-class"}
    result = extract_with_selectors(
        HTML_NEWS_BASIC, url="https://example.com/test", selectors=selectors
    )
    assert result.title  # title bulundu
    assert result.extraction_confidence > 0.0
    assert result.extraction_confidence < 0.5  # body yok → düşük conf


def test_selectors_image_relative_resolved():
    html = '<html><body><img class="hero" src="/img/hero.jpg"/></body></html>'
    selectors = {"image": ".hero"}
    result = extract_with_selectors(html, url="https://x.com/a/b", selectors=selectors)
    assert result.main_image_url == "https://x.com/img/hero.jpg"


# ---------------------------------------------------------------------------
# Strategy 2: trafilatura
# ---------------------------------------------------------------------------


def test_trafilatura_extracts_news():
    result = extract_with_trafilatura(HTML_NEWS_BASIC, url="https://example.com/news/1")
    assert result.strategy_used == "trafilatura"
    # trafilatura bazı içeriklerde title'ı tutmayabilir; başarılı extraction'da clean_text dolu olmalı
    assert len(result.clean_text) >= MIN_TEXT_LENGTH
    assert result.extraction_confidence >= 0.4


def test_trafilatura_fills_image_from_meta():
    """trafilatura kendi image vermez; soup ile og:image alınır."""
    result = extract_with_trafilatura(HTML_NEWS_BASIC, url="https://example.com/news/1")
    assert result.main_image_url == "https://example.com/image.jpg"


def test_trafilatura_fills_subtitle_from_og_description():
    result = extract_with_trafilatura(HTML_NEWS_BASIC, url="https://example.com/news/1")
    assert "OG açıklama" in (result.subtitle or "")


# ---------------------------------------------------------------------------
# Strategy 3: fallback
# ---------------------------------------------------------------------------


def test_fallback_uses_og_title():
    result = extract_fallback(HTML_FALLBACK, url="https://example.com/page")
    assert result.title == "Fallback Title"
    assert result.subtitle == "Sadece meta var — body kısa."


def test_fallback_resolves_relative_image():
    result = extract_fallback(HTML_FALLBACK, url="https://example.com/page")
    assert result.main_image_url == "https://example.com/relative/img.jpg"


def test_fallback_low_confidence_when_text_short():
    result = extract_fallback(HTML_FALLBACK, url="https://example.com/page")
    # Sadece meta var, body kısa → confidence düşük
    assert result.extraction_confidence < 0.5
    assert not result.successful


def test_fallback_h1_when_no_og_title():
    html = "<html><body><h1>H1 Başlık</h1><p>" + ("metin " * 100) + "</p></body></html>"
    result = extract_fallback(html, url="https://x.com")
    assert result.title == "H1 Başlık"


# ---------------------------------------------------------------------------
# Public API: extract_article — 3 kademeli
# ---------------------------------------------------------------------------


def test_extract_article_uses_selectors_first():
    selectors = {
        "title": "h1",
        "body": "article",
        "image": "meta[property='og:image']",
    }
    result = extract_article(
        HTML_NEWS_BASIC, url="https://example.com/test", selectors=selectors
    )
    assert result.strategy_used == "admin_selectors"
    assert result.successful


def test_extract_article_falls_through_to_trafilatura():
    """Selectors yoksa trafilatura."""
    result = extract_article(HTML_NEWS_BASIC, url="https://example.com/news/1")
    # trafilatura başarılı veya fallback — biri başarılı olmalı
    assert result.title or result.clean_text
    assert result.strategy_used in ("trafilatura", "fallback")


def test_extract_article_fallback_when_others_fail():
    """Sadece meta tag'li sayfa → fallback."""
    result = extract_article(HTML_FALLBACK, url="https://example.com")
    assert result.strategy_used in ("fallback", "trafilatura")
    # fallback bile en az title döner
    assert result.title


def test_extract_article_returns_extracted_dataclass():
    result = extract_article("<html></html>", url="https://x.com")
    assert isinstance(result, ExtractedArticle)
    assert result.url == "https://x.com"


def test_successful_property_requires_min_text_and_title():
    art = ExtractedArticle(url="x", title="T", clean_text="x" * (MIN_TEXT_LENGTH + 10))
    art.extraction_confidence = 0.5
    assert art.successful is True

    art2 = ExtractedArticle(url="x", title="T", clean_text="short")
    art2.extraction_confidence = 0.5
    assert art2.successful is False  # min text fail
