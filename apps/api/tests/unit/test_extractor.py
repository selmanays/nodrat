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


# ============================================================================
# Reklam / logo / dekoratif filter (#304 fix)
# ============================================================================


def _make_img(html_snippet: str):
    """Helper: HTML snippet'inden tek bir <img> tag'i çıkar."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_snippet, "html.parser")
    img = soup.find("img")
    return img


def test_non_editorial_filters_doubleclick_url():
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="https://example.com/photo.jpg">')
    assert _is_non_editorial_image(
        img, "https://googleads.g.doubleclick.net/banner.jpg"
    )


def test_non_editorial_filters_taboola():
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="https://taboola.com/x.jpg">')
    assert _is_non_editorial_image(img, "https://cdn.taboola.com/x.jpg")


def test_non_editorial_filters_alt_reklam():
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="https://example.com/x.jpg" alt="Reklam görseli">')
    assert _is_non_editorial_image(img, "https://example.com/x.jpg")


def test_non_editorial_filters_alt_logo_pattern():
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="https://example.com/x.jpg" alt="TRT Haber logosu">')
    assert _is_non_editorial_image(img, "https://example.com/x.jpg")


def test_non_editorial_filters_class_advertisement():
    from app.core.extractor import _is_non_editorial_image

    img = _make_img(
        '<img src="https://example.com/x.jpg" class="advertisement banner-img">'
    )
    assert _is_non_editorial_image(img, "https://example.com/x.jpg")


def test_non_editorial_filters_parent_class():
    from bs4 import BeautifulSoup
    from app.core.extractor import _is_non_editorial_image

    soup = BeautifulSoup(
        '<div class="ad-slot"><img src="https://example.com/banner.png"></div>',
        "html.parser",
    )
    img = soup.find("img")
    assert _is_non_editorial_image(img, "https://example.com/banner.png")


def test_non_editorial_filters_data_ad_attribute():
    from app.core.extractor import _is_non_editorial_image

    img = _make_img(
        '<img src="https://example.com/x.jpg" data-ad-unit="header">'
    )
    assert _is_non_editorial_image(img, "https://example.com/x.jpg")


def test_non_editorial_url_path_logo():
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="/img/logo.png">')
    assert _is_non_editorial_image(img, "https://site.com/assets/logo/site.png")


def test_non_editorial_keeps_normal_news_image():
    from app.core.extractor import _is_non_editorial_image

    img = _make_img(
        '<img src="https://example.com/news/2026/protest.jpg" '
        'alt="Sokakta toplanan kalabalık" class="article-image">'
    )
    assert not _is_non_editorial_image(
        img, "https://example.com/news/2026/protest.jpg"
    )


def test_non_editorial_keeps_image_inside_figure():
    from bs4 import BeautifulSoup
    from app.core.extractor import _is_non_editorial_image

    soup = BeautifulSoup(
        '<figure class="media"><img src="https://example.com/news.jpg" '
        'alt="Erdoğan açıklama yapıyor"><figcaption>Açıklama</figcaption></figure>',
        "html.parser",
    )
    img = soup.find("img")
    assert not _is_non_editorial_image(img, "https://example.com/news.jpg")


def test_extract_body_images_filters_ads_and_logos():
    """End-to-end: bir article HTML'inde reklam ve logo SKIP edilir, asıl
    haber görseli korunur."""
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <article>
      <header><img src="https://site.com/logo.png" alt="TRT Haber logosu"></header>
      <figure>
        <img src="https://site.com/news/protest.jpg" alt="Protesto eylemi"
             width="800" height="600">
        <figcaption>Protesto Ankara'da</figcaption>
      </figure>
      <div class="ad-slot">
        <img src="https://googlesyndication.com/banner.gif" alt="Reklam">
      </div>
      <p>Haber metni</p>
      <img src="https://taboola.com/sponsored.jpg" alt="İlginizi çekebilir">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/haber/x")
    urls = [i.url for i in images]

    # Sadece asıl haber görseli kalmalı
    assert "https://site.com/news/protest.jpg" in urls
    assert "https://site.com/logo.png" not in urls
    assert "https://googlesyndication.com/banner.gif" not in urls
    assert "https://taboola.com/sponsored.jpg" not in urls
    assert len(images) == 1


# ============================================================================
# Lazyload placeholder fallback (#304 fix)
# ============================================================================


def test_extract_body_images_skips_lazyload_placeholder():
    """src lazyload-placeholder ise data-src'e fallback yapılır."""
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <article>
      <figure>
        <img src="/static/images/lazyload-placeholder-1280x720.png"
             data-src="https://cdn.site.com/news/real-image.jpg"
             alt="Bakan Şimşek açıklaması"
             width="1280" height="720">
      </figure>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/haber/x")
    assert len(images) == 1
    # Placeholder değil, gerçek görsel alınmalı
    assert images[0].url == "https://cdn.site.com/news/real-image.jpg"


def test_extract_body_images_skips_when_only_placeholder():
    """src + tüm lazy attr'lar placeholder ise SKIP."""
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <article>
      <img src="/img/placeholder.png"
           data-src="/img/spacer.gif"
           alt="x" width="200" height="200">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/haber/x")
    assert len(images) == 0


def test_extract_body_images_handles_data_srcset():
    """data-srcset format: 'url1 1x, url2 2x' — ilk URL alınır."""
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <article>
      <img src="/img/placeholder.png"
           data-srcset="https://cdn.site.com/img/news.jpg 1x, https://cdn.site.com/img/news@2x.jpg 2x"
           alt="Haber" width="800" height="600">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/haber/x")
    assert len(images) == 1
    assert images[0].url == "https://cdn.site.com/img/news.jpg"


def test_extract_body_images_normal_src_not_placeholder():
    """src normal ise data-src kontrolüne gerek yok, normal src kullanılır."""
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <article>
      <img src="https://cdn.site.com/news/real.jpg"
           data-src="https://cdn.site.com/news/different.jpg"
           alt="x" width="800" height="600">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/haber/x")
    assert len(images) == 1
    assert images[0].url == "https://cdn.site.com/news/real.jpg"


# ============================================================================
# Recommended-section filter (#304 fix — BBC "more stories" gibi)
# ============================================================================


def test_recommended_filters_li_in_more_stories():
    """BBC pattern: <main> içindeki <li> içindeki img öneri haberdir, SKIP."""
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <main>
      <figure>
        <img src="https://cdn.bbc.com/news/main-photo.jpg"
             alt="Main news photo"
             width="800" height="600">
        <figcaption>Ana haber fotoğrafı</figcaption>
      </figure>
      <p>Haber metni paragrafları...</p>
      <div class="more-stories">
        <ul>
          <li><img src="https://cdn.bbc.com/news/related1.jpg"
                   alt="Bahçeli ve Özel" width="660" height="400"></li>
          <li><img src="https://cdn.bbc.com/news/related2.jpg"
                   alt="Eric Aniva" width="660" height="400"></li>
          <li><img src="https://cdn.bbc.com/news/related3.jpg"
                   alt="Abdullah Güler" width="660" height="400"></li>
        </ul>
      </div>
    </main>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://www.bbc.com/article")
    urls = [i.url for i in images]

    # Sadece ana haber görseli kalmalı
    assert "https://cdn.bbc.com/news/main-photo.jpg" in urls
    assert "https://cdn.bbc.com/news/related1.jpg" not in urls
    assert "https://cdn.bbc.com/news/related2.jpg" not in urls
    assert "https://cdn.bbc.com/news/related3.jpg" not in urls
    assert len(images) == 1


def test_recommended_filters_aside_sidebar():
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <article>
      <figure><img src="https://site.com/main.jpg" alt="Ana" width="800" height="600"></figure>
      <aside>
        <img src="https://site.com/sidebar-ad.jpg" alt="Yan" width="300" height="250">
      </aside>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/x")
    urls = [i.url for i in images]
    assert "https://site.com/main.jpg" in urls
    assert "https://site.com/sidebar-ad.jpg" not in urls


def test_recommended_filters_class_related_stories():
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <article>
      <img src="https://site.com/main.jpg" alt="Ana" width="800" height="600">
      <div class="related-stories">
        <img src="https://site.com/rel.jpg" alt="İlgili" width="400" height="300">
      </div>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/x")
    urls = [i.url for i in images]
    assert "https://site.com/main.jpg" in urls
    assert "https://site.com/rel.jpg" not in urls


def test_recommended_filters_turkish_ilgili():
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <article>
      <img src="https://site.com/main.jpg" alt="Ana" width="800" height="600">
      <div class="ilgili-haberler">
        <img src="https://site.com/ilgili.jpg" alt="İlgili" width="400" height="300">
      </div>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/x")
    urls = [i.url for i in images]
    assert "https://site.com/main.jpg" in urls
    assert "https://site.com/ilgili.jpg" not in urls


def test_recommended_keeps_figure_inside_main():
    """<main> içindeki <figure> normal — SKIP edilmemeli."""
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <main>
      <h1>Haber başlığı</h1>
      <figure>
        <img src="https://site.com/photo.jpg" alt="Haber fotoğrafı"
             width="800" height="600">
      </figure>
      <p>Haber metni</p>
    </main>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/x")
    assert len(images) == 1
    assert images[0].url == "https://site.com/photo.jpg"


def test_recommended_filters_aria_role_complementary():
    from bs4 import BeautifulSoup
    from app.core.extractor import extract_body_images

    html = """
    <main>
      <figure><img src="https://site.com/main.jpg" alt="Ana" width="800" height="600"></figure>
      <div role="complementary">
        <img src="https://site.com/comp.jpg" alt="Yan" width="400" height="300">
      </div>
    </main>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/x")
    urls = [i.url for i in images]
    assert "https://site.com/main.jpg" in urls
    assert "https://site.com/comp.jpg" not in urls
