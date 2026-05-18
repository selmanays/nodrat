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
    result = extract_article(HTML_NEWS_BASIC, url="https://example.com/test", selectors=selectors)
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
# #529 — SPA / Next.js short-article cascade
# ============================================================================


# AA Next.js benzeri yapı: <main> boş, içerik inner div'de + boilerplate <p>
# uzun (precision modu boilerplate'i seçip body'yi kaçırma riski).
HTML_SPA_EMPTY_MAIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
  <title>SPA Test Haber</title>
  <meta property="og:title" content="SPA Test Haber"/>
  <meta property="og:description" content="Açıklama"/>
  <meta property="og:image" content="https://x.com/img.jpg"/>
  <meta property="article:published_time" content="2026-05-08T10:00:00Z"/>
  <meta name="author" content="Test Yazar"/>
</head>
<body>
  <header><nav>Menü</nav></header>
  <main id="main-content" class="flex-grow"></main>
  <div class="layout-shell">
    <div dir="ltr" class="embed-responsive prose max-w-none lora space-y-4">
      <p>Birinci paragraf — yeterince uzun, gerçek haber metni burada
      başlıyor ve bilgi içeriyor.</p>
      <p>İkinci paragraf — devam eden haber metni, ayrıntı veriyor ve
      yine bilgilendirici niteliktedir.</p>
    </div>
  </div>
  <footer>
    <p class="caustenRegular text-sm leading-relaxed text-shareNewsTextColor">
    Anadolu Ajansı web sitesinde, AA Haber Akış Sistemi (HAS) üzerinden
    abonelere sunulan haberler, özetlenerek yayımlanmaktadır. Abonelik
    için lütfen iletişime geçiniz.
    </p>
  </footer>
</body>
</html>
"""


def test_extract_fallback_falls_through_when_main_is_empty():
    """#529: <main> boş → fallback whole-soup'a fall-through yapmalı.

    Bug öncesi: extract_fallback boş <main>'i target alıp 0 char dönüyordu;
    trafilatura'nın boilerplate (HAS disclaimer) çıktısı kazanıyordu.
    """
    result = extract_fallback(HTML_SPA_EMPTY_MAIN, url="https://x.com/news/1")
    # Fall-through aktif → en az MIN_TEXT_LENGTH kadar text bulunmalı
    assert len(result.clean_text) >= MIN_TEXT_LENGTH, (
        f"Empty <main> guard failed: clean_text len={len(result.clean_text)}"
    )
    # İçerik gerçek body olmalı (sadece boilerplate değil)
    assert "Birinci paragraf" in result.clean_text or "İkinci paragraf" in result.clean_text


def test_trafilatura_multimode_picks_longer_when_precision_thin():
    """#529: precision modu kısa makaleleri reddediyor — multi-mode cascade.

    SPA HTML'de precision modu boilerplate / dar bir parça döndürüyorsa
    default veya recall mode daha uzun (ve gerçek) metni getirmeli.
    """
    result = extract_with_trafilatura(HTML_SPA_EMPTY_MAIN, url="https://x.com/news/1")
    # Multi-mode cascade ile en az gerçek body extract edilmiş olmalı
    assert result.title  # meta'dan
    # Precision-only mode (eski davranış) bu HTML'de çok kısa veya hiç
    # text vermiyor; cascade en az 100 char getirmeli.
    assert len(result.clean_text) > 100, (
        f"Multi-mode cascade failed: clean_text len={len(result.clean_text)}"
    )


def test_extract_article_prefers_successful_over_higher_confidence():
    """#529: SPA boilerplate vakası — fallback `.successful=True` ama
    confidence düşük; trafilatura `.successful=False` ama confidence yüksek
    olabilir. Yeni kural: önce successful olanı seç.
    """
    result = extract_article(HTML_SPA_EMPTY_MAIN, url="https://x.com/news/1")
    # Hangi strateji kazanırsa kazansın, sonuç successful olmalı
    assert result.successful, (
        f"strategy={result.strategy_used} conf={result.extraction_confidence} "
        f"text_len={len(result.clean_text)}"
    )


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
    assert _is_non_editorial_image(img, "https://googleads.g.doubleclick.net/banner.jpg")


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

    img = _make_img('<img src="https://example.com/x.jpg" class="advertisement banner-img">')
    assert _is_non_editorial_image(img, "https://example.com/x.jpg")


def test_non_editorial_filters_parent_class():
    from app.core.extractor import _is_non_editorial_image
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(
        '<div class="ad-slot"><img src="https://example.com/banner.png"></div>',
        "html.parser",
    )
    img = soup.find("img")
    assert _is_non_editorial_image(img, "https://example.com/banner.png")


def test_non_editorial_filters_data_ad_attribute():
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="https://example.com/x.jpg" data-ad-unit="header">')
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
    assert not _is_non_editorial_image(img, "https://example.com/news/2026/protest.jpg")


def test_non_editorial_keeps_image_inside_figure():
    from app.core.extractor import _is_non_editorial_image
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(
        '<figure class="media"><img src="https://example.com/news.jpg" '
        'alt="Erdoğan açıklama yapıyor"><figcaption>Açıklama</figcaption></figure>',
        "html.parser",
    )
    img = soup.find("img")
    assert not _is_non_editorial_image(img, "https://example.com/news.jpg")


# ---------------------------------------------------------------------------
# #600 — bakinazik kaynaklarındaki yeni görsel noise pattern'leri
# ---------------------------------------------------------------------------


def test_non_editorial_filters_banner_with_extension():
    """SavunmaSanayiST: SAHA-2026 etkinlik banner — `_Banner.webp`.

    Eski regex `(?:^|[\\s_/-])(ads?|banner)(?:[\\s_/-]|\\d|$)` boundary
    olarak `.` karakterini almıyordu → `Banner.webp` match ETMİYORDU.
    Fix: boundary'ye `.` eklendi.
    """
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="https://x/Banner.webp" alt="savunmasanayist-banner">')
    assert _is_non_editorial_image(
        img,
        "https://www.savunmasanayist.com/wp-content/uploads/2026/04/"
        "Savunmasanayist.com_SAHA-2026-SYS-Grup_Banner.webp",
    )


def test_non_editorial_filters_icon_file_prefix():
    """Bianet: static icon CDN'i — `static.bianet.org/icons/icon-large-facebook.svg`.

    Hem path (`/icons/`) hem filename (`icon-large-`) prefix yakalar.
    """
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="https://static.bianet.org/icons/icon-large-facebook.svg">')
    assert _is_non_editorial_image(img, "https://static.bianet.org/icons/icon-large-facebook.svg")


def test_non_editorial_filters_static_path_logo_brand():
    """`/static/img/logo/...` veya `/static/icons/...` path patterns."""
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="https://x.com/static/img/logo/site.png">')
    assert _is_non_editorial_image(img, "https://x.com/static/img/logo/site.png")


def test_non_editorial_filters_ui_alt_gorseli_buyut():
    """Bianet lightbox button: alt='Görseli Büyüt'.

    UI element ikonları, gerçek body görseli değil — exclude.
    """
    from app.core.extractor import _is_non_editorial_image

    img = _make_img('<img src="https://x/zoom.svg" alt="Görseli Büyüt">')
    assert _is_non_editorial_image(img, "https://x/zoom.svg")


def test_non_editorial_filters_ui_alt_share_buttons():
    """UI 'Paylaş' / 'Read more' / 'Daha fazla' alt text'leri."""
    from app.core.extractor import _is_non_editorial_image

    for alt in ("Paylaş", "Daha Fazla", "Yorumlar", "Read more", "View all"):
        img = _make_img(f'<img src="https://x/btn.svg" alt="{alt}">')
        assert _is_non_editorial_image(img, "https://x/btn.svg"), f"UI alt '{alt}' yakalanmadı"


def test_non_editorial_keeps_normal_image_with_long_alt():
    """Regression: gerçek haber görselinin alt'ı UI text'lerini içerse bile
    (örn. 'Erdoğan ekonomi paylaşımı yaptı') match etmemeli — UI regex
    `^...$` anchored, başında/sonunda."""
    from app.core.extractor import _is_non_editorial_image

    img = _make_img(
        '<img src="https://example.com/protest.jpg" '
        'alt="Erdoğan ekonomi paylaşımı yaptı, sokakta protesto">'
    )
    assert not _is_non_editorial_image(img, "https://example.com/protest.jpg")


def test_extract_body_images_filters_ads_and_logos():
    """End-to-end: bir article HTML'inde reklam ve logo SKIP edilir, asıl
    haber görseli korunur."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

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


# ============================================================================
# Site profile sistemi (#304 fix)
# ============================================================================


def test_profile_match_bbc_com():
    from app.core.site_profiles import find_profile

    p = find_profile("https://www.bbc.com/turkce/articles/abc123")
    assert p is not None
    assert "bbc.com" in p.domains


def test_profile_match_bbc_co_uk():
    from app.core.site_profiles import find_profile

    p = find_profile("https://www.bbc.co.uk/news/article/x")
    assert p is not None
    assert "bbc.co.uk" in p.domains


def test_profile_match_evrensel():
    from app.core.site_profiles import find_profile

    p = find_profile("https://www.evrensel.net/haber/123/x")
    assert p is not None
    assert "evrensel.net" in p.domains


def test_profile_no_match_unknown_site():
    from app.core.site_profiles import find_profile

    p = find_profile("https://random-site.example/news/x")
    assert p is None


def test_profile_strips_www_prefix():
    from app.core.site_profiles import find_profile

    p1 = find_profile("https://www.bbc.com/x")
    p2 = find_profile("https://bbc.com/x")
    assert p1 is p2


# ----- bakinazik #585 yeni 5 profile -----------------------------------------


def test_profile_match_hurriyet():
    from app.core.site_profiles import find_profile

    p = find_profile("https://www.hurriyet.com.tr/dunya/article-123")
    assert p is not None
    assert "hurriyet.com.tr" in p.domains
    assert p.container_selector == "section.news-detail-content"


def test_profile_match_webtekno():
    from app.core.site_profiles import find_profile

    p = find_profile("https://www.webtekno.com/foo-h216663.html")
    assert p is not None
    assert "webtekno.com" in p.domains


def test_profile_match_beyazperde():
    from app.core.site_profiles import find_profile

    p = find_profile("https://www.beyazperde.com/haberler/filmler/x/")
    assert p is not None
    assert "beyazperde.com" in p.domains
    # tracking pixel data-uri figure'ları exclude edilmeli
    assert "figure.thumbnail" in p.exclude_selectors


def test_profile_match_bloomberght_subdomain():
    """tr.bloomberght.com gibi alt-domain de match etmeli."""
    from app.core.site_profiles import find_profile

    p = find_profile("https://tr.bloomberght.com/x-3777197")
    assert p is not None
    assert "bloomberght.com" in p.domains


def test_profile_match_elle():
    from app.core.site_profiles import find_profile

    p = find_profile("https://www.elle.com.tr/guzellik/saglik/x")
    assert p is not None
    assert "elle.com.tr" in p.domains
    assert "img.fr-dib" in p.main_image_selectors


def test_beyazperde_profile_excludes_tracking_pixel_figures():
    """Beyaz Perde: figure.article-main-figure → al; figure.thumbnail (data-uri
    tracking pixel) → exclude."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <html><body>
      <div class="article-content">
        <figure class="article-figure article-main-figure">
          <img src="https://tr.web.img4.acsta.net/r_654_368/img/hero.jpg" alt="hero">
        </figure>
        <p>İçerik metni burada.</p>
        <figure class="thumbnail">
          <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt="">
        </figure>
        <figure class="thumbnail">
          <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt="">
        </figure>
      </div>
      <aside class="gd-col-right">
        <img src="https://example.com/ad.jpg" alt="ad">
      </aside>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://www.beyazperde.com/haberler/filmler/x/")
    srcs = [i.url for i in images]
    # Hero JPG dahil, data-uri thumbnail ve aside ad dışında
    assert any("hero.jpg" in s for s in srcs)
    assert not any("data:image" in s for s in srcs)
    assert not any("ad.jpg" in s for s in srcs)


def test_hurriyet_profile_excludes_sidebar_widgets():
    """Hürriyet: section.news-detail-content içerik; sidebar widget'lar exclude."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <html><body>
      <section class="news-detail-content">
        <p>Haber giriş metni.</p>
        <img src="https://i.hurimg.com/i/hurriyet/main.jpg" alt="ana görsel">
        <p>Devam metni.</p>
        <div class="sidebar__content">
          <img src="https://static.hurriyet.com.tr/logo.svg" alt="logo">
        </div>
        <div class="news-tags">
          <a class="news-tags__link">tag</a>
        </div>
        <div class="weather-city-widget">
          <img src="https://example.com/weather.png">
        </div>
      </section>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://www.hurriyet.com.tr/dunya/x")
    srcs = [i.url for i in images]
    assert any("main.jpg" in s for s in srcs)
    assert not any("logo.svg" in s for s in srcs)
    assert not any("weather.png" in s for s in srcs)


def test_bbc_profile_extracts_only_main_figure():
    """BBC profili: main içindeki figure img'leri al, li içindekileri SKIP."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    # BBC pattern — gerçek production HTML'i mimik eder
    html = """
    <main class="css-men093">
      <div class="css-1cvxiy9">
        <div class="css-bg8vrv">
          <figure class="css-1qn0xuy">
            <img src="https://ichef.bbci.co.uk/main-news.jpg"
                 alt="Ana haber görseli" width="800" height="600">
          </figure>
        </div>
      </div>
      <p>Haber metni paragrafları</p>
      <div class="css-1cvxiy9">
        <div class="css-bg8vrv">
          <figure class="css-1qn0xuy">
            <img src="https://ichef.bbci.co.uk/main-news-2.jpg"
                 alt="Ana haber görseli (alternative)" width="640" height="480">
          </figure>
        </div>
      </div>
      <ul>
        <li><img src="https://ichef.bbci.co.uk/related-1.jpg"
                 alt="Bahçeli/Özel" width="660" height="400"></li>
        <li><img src="https://ichef.bbci.co.uk/related-2.jpg"
                 alt="Eric Aniva" width="660" height="400"></li>
        <li><img src="https://ichef.bbci.co.uk/related-3.jpg"
                 alt="Abdullah Güler" width="660" height="400"></li>
      </ul>
    </main>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://www.bbc.com/turkce/articles/test")
    urls = [i.url for i in images]

    # Sadece <figure> içindeki ana görseller alınmalı
    assert "https://ichef.bbci.co.uk/main-news.jpg" in urls
    assert "https://ichef.bbci.co.uk/main-news-2.jpg" in urls
    # <li> içindeki öneri haberler alınmamalı (BBC profile exclude eder)
    assert "https://ichef.bbci.co.uk/related-1.jpg" not in urls
    assert "https://ichef.bbci.co.uk/related-2.jpg" not in urls
    assert "https://ichef.bbci.co.uk/related-3.jpg" not in urls
    assert len(images) == 2


def test_unknown_site_uses_generic_fallback():
    """Profili olmayan site için generic chain — <article> tag'i bulur."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <img src="https://random.com/photo.jpg" alt="Photo"
           width="800" height="600">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://random-site.com/news/x")
    assert len(images) == 1
    assert images[0].url == "https://random.com/photo.jpg"


# ============================================================================
# Generic figure caption extraction (#304 fix)
# Evrensel <span class="small-title"> ve diğer non-<figcaption> patternler
# ============================================================================


def test_figure_caption_with_figcaption():
    """Standart <figcaption> — semantic, en güvenilir."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <figure>
        <img src="https://site.com/img.jpg" alt="Test" width="800" height="600">
        <figcaption>Test fotoğraf altı yazısı</figcaption>
      </figure>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/x")
    assert len(images) == 1
    assert images[0].caption == "Test fotoğraf altı yazısı"


def test_figure_caption_evrensel_pattern():
    """Evrensel: <figure> içinde <span class="small-title"><p>.

    Bu pattern <figcaption> kullanmaz. Generic fallback yakalamalı.
    """
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <figure class="manset-foto">
        <img src="https://www.evrensel.net/img/x.jpg"
             alt="Asansörde sıkışan iki yabancının hikâyesi: 'Bluescat' sahnede"
             width="1280" height="720">
        <span class="small-title"><p>Bluescat adlı oyundan bir sahne.</p></span>
      </figure>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://www.evrensel.net/haber/x")
    assert len(images) == 1
    assert images[0].caption == "Bluescat adlı oyundan bir sahne."


def test_figure_caption_strips_alt_overlap():
    """Eğer figure text alt ile başlıyorsa duplicate kalkar."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <figure>
        <img src="https://site.com/x.jpg" alt="Anahtar bilgi" width="800" height="600">
        <span>Anahtar bilgi — Ek context buradadır</span>
      </figure>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/x")
    assert len(images) == 1
    # "Anahtar bilgi" alt ile çakışıyor → strip
    assert "Ek context" in images[0].caption
    assert images[0].caption != "Anahtar bilgi"


def test_figure_caption_no_caption_when_only_alt():
    """Figure içinde sadece <img> var, caption boş kalmalı."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <figure>
        <img src="https://site.com/x.jpg" alt="Sadece bu" width="800" height="600">
      </figure>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/x")
    assert len(images) == 1
    assert images[0].caption == ""


def test_figure_caption_figcaption_priority():
    """Hem <figcaption> hem ek metin varsa <figcaption> öncelikli."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <figure>
        <img src="https://site.com/x.jpg" alt="x" width="800" height="600">
        <figcaption>Asıl figcaption</figcaption>
        <span>Ek text</span>
      </figure>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://site.com/x")
    # figcaption öncelikli
    assert "Asıl figcaption" in images[0].caption


# ---------------------------------------------------------------------------
# #603 — Yapısal görsel filter (kök çözüm: boilerplate decompose + size + aspect)
# ---------------------------------------------------------------------------


def test_structural_decomposes_aside_before_extraction():
    """Aside içindeki img'ler — site_profile yokken bile decompose edilmeli."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <html><body>
      <article>
        <figure>
          <img src="https://site.com/news.jpg" alt="Haber" width="800" height="600">
        </figure>
        <p>Haber metni burada.</p>
      </article>
      <aside class="gd-col-right">
        <img src="https://static.bianet.org/icons/icon-large-facebook.svg" alt="FB">
      </aside>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://example.com/article/x")
    urls = [i.url for i in images]
    assert any("news.jpg" in u for u in urls)
    assert not any("icon-large-facebook" in u for u in urls)


def test_structural_decomposes_nav_header_footer():
    """Nav/header/footer img'leri (logo, sosyal media) elenir."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <html><body>
      <header><img src="https://x/logo.png" alt="Logo" width="180" height="60"></header>
      <nav><img src="https://x/menu-icon.svg" alt="Menu"></nav>
      <article>
        <img src="https://x/news.jpg" alt="Haber" width="800" height="600">
        <p>İçerik</p>
      </article>
      <footer><img src="https://x/twitter-icon.png" alt="Twitter"></footer>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://example.com/x")
    urls = [i.url for i in images]
    assert any("news.jpg" in u for u in urls)
    assert not any("logo.png" in u for u in urls)
    assert not any("menu-icon" in u for u in urls)
    assert not any("twitter-icon" in u for u in urls)


def test_structural_decomposes_role_banner_complementary():
    """role=banner ve role=complementary elementleri (semantic landmark)."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <html><body>
      <div role="banner"><img src="https://x/site-banner.webp" alt="Banner" width="1280" height="120"></div>
      <article>
        <img src="https://x/news.jpg" alt="Haber" width="800" height="600">
        <p>İçerik</p>
      </article>
      <div role="complementary"><img src="https://x/promo.jpg" alt="Promo" width="300" height="250"></div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://example.com/x")
    urls = [i.url for i in images]
    assert any("news.jpg" in u for u in urls)
    assert not any("site-banner" in u for u in urls)
    assert not any("promo.jpg" in u for u in urls)


def test_structural_size_threshold_200():
    """width veya height < 200 → exclude (icon/logo)."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <img src="https://x/small-icon.png" width="48" height="48" alt="ikon">
      <img src="https://x/medium-decor.png" width="180" height="180" alt="dekor">
      <img src="https://x/news-photo.jpg" width="800" height="600" alt="Haber fotoğrafı">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://x.com/article/x")
    urls = [i.url for i in images]
    assert not any("small-icon" in u for u in urls)
    assert not any("medium-decor" in u for u in urls)
    assert any("news-photo" in u for u in urls)


def test_structural_aspect_ratio_excludes_banner():
    """Aspect ratio > 5 (banner) veya < 0.2 (vertical strip) → exclude."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <img src="https://x/event-banner.webp" width="1280" height="120" alt="SAHA 2026">
      <img src="https://x/vertical-ad.png" width="160" height="900" alt="Reklam">
      <img src="https://x/normal-photo.jpg" width="800" height="600" alt="Haber">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://x.com/article/x")
    urls = [i.url for i in images]
    assert not any("event-banner" in u for u in urls)
    assert not any("vertical-ad" in u for u in urls)
    assert any("normal-photo" in u for u in urls)


def test_structural_size_attr_missing_keeps_image():
    """HTML attr'da width/height yoksa defansif: img'i tut (filter pas geçer).

    Çünkü gerçek haber görselleri responsive CSS ile boyutlanır, HTML attr
    nadiren bulunur. Eksikse generic regex/section filter zinciri yakalar.
    """
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <img src="https://x/news.jpg" alt="Haber fotoğrafı">
      <p>Haber metni</p>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://x.com/article/x")
    urls = [i.url for i in images]
    assert any("news.jpg" in u for u in urls)


def test_structural_decomposes_social_share_widget():
    """Share/social bar widget'ları (`class*='social-share'`) elenir."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <p>Haber metni</p>
      <img src="https://x/news.jpg" alt="Haber" width="800" height="600">
      <div class="social-share-bar">
        <img src="https://x/fb.svg" alt="FB" width="40" height="40">
        <img src="https://x/twitter.svg" alt="TW" width="40" height="40">
      </div>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://x.com/article/x")
    urls = [i.url for i in images]
    assert any("news.jpg" in u for u in urls)
    assert not any("fb.svg" in u for u in urls)
    assert not any("twitter.svg" in u for u in urls)


# ---------------------------------------------------------------------------
# #604 — Lazy-load placeholder kök çözüm (JNews jeg-empty.png + data-src öncelik)
# ---------------------------------------------------------------------------


def test_lazy_load_data_src_priority_over_placeholder_src():
    """C4Defence WordPress JNews vakası: src='jeg-empty.png' placeholder,
    data-src='gerçek-haber.webp'. data-src her zaman tercih edilmeli."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <img src="https://www.c4defence.com/wp-content/themes/jnews/assets/img/jeg-empty.png"
           data-src="https://www.c4defence.com/wp-content/uploads/2026/05/northrop-grumman-f16-radar-sozlesmesi-scaled.webp"
           alt="F-16 radar" width="1200" height="675">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://www.c4defence.com/tr/f-16-x/")
    urls = [i.url for i in images]
    assert any("northrop-grumman-f16-radar" in u for u in urls)
    assert not any("jeg-empty" in u for u in urls)


def test_lazy_load_data_original_priority():
    """data-original (alternative lazy-load attr name) öncelikli."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <img src="https://x/loading.gif"
           data-original="https://x/news-photo.jpg"
           alt="Haber" width="800" height="600">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://x.com/article/x")
    urls = [i.url for i in images]
    assert any("news-photo.jpg" in u for u in urls)
    assert not any("loading.gif" in u for u in urls)


def test_jeg_empty_placeholder_excluded_when_only_src():
    """src='jeg-empty.png' var, data-src yok → image atlandı (placeholder)."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <img src="https://x/wp-content/themes/jnews/assets/img/jeg-empty.png" alt="Empty" width="800" height="600">
      <p>Article body</p>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://x.com/article/x")
    assert len(images) == 0


def test_theme_assets_path_treated_as_placeholder():
    """`/wp-content/themes/.../assets/img/X.png` → placeholder (theme dekoratif)."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <img src="https://x/wp-content/themes/twentytwentyfour/assets/img/decorator.png" alt="dec" width="800" height="600">
      <img src="https://x/wp-content/uploads/2026/05/news.webp" alt="Haber" width="800" height="600">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://x.com/article/x")
    urls = [i.url for i in images]
    assert any("uploads/2026" in u for u in urls)
    assert not any("themes/" in u for u in urls)


def test_noimage_keyword_treated_as_placeholder():
    """`noimage`, `no-image`, `default-image` keyword içeren src placeholder."""
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <article>
      <img src="https://x/static/noimage.png" alt="" width="800" height="600">
      <img src="https://x/no-image-default.jpg" alt="" width="800" height="600">
      <img src="https://x/cdn/default-image.webp" alt="" width="800" height="600">
      <img src="https://x/uploads/news.jpg" alt="Haber" width="800" height="600">
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://x.com/article/x")
    urls = [i.url for i in images]
    assert any("uploads/news.jpg" in u for u in urls)
    assert len([u for u in urls if "noimage" in u or "no-image" in u or "default-image" in u]) == 0


def test_bianet_profile_excludes_author_modal_most_read():
    """Bianet pattern (#629 follow-up): <main> içinde news-single + author chip +
    most-read widget + image enlargement modal aynı anda var. Profile container'ı
    section.news-single'a daraltır; ccard--author + modal + box--most-read +
    section--pushed exclude edilir. Sonuç: sadece hero + body figure'lar.
    """
    from app.core.extractor import extract_body_images
    from bs4 import BeautifulSoup

    html = """
    <main class="page-news-single">
      <section class="news-single content-part">
        <div class="top-part">
          <a class="ccard ccard--author ccard--author-chip" href="/yazar/x">
            <div class="img-wrapper">
              <img src="https://static.bianet.org/profile/2024/x/author.jpg"
                   class="card-img-left" alt="Yazar Adı" width="80" height="80">
            </div>
          </a>
          <div class="figure-wrapper">
            <figure>
              <img src="https://static.bianet.org/yazi/2026/04/hero.jpg"
                   alt="Hero başlık" width="1200" height="675">
            </figure>
          </div>
        </div>
        <div class="bottom-part">
          <div class="actions-wrapper sticky-0">
            <a class="btn-facebook"><img src="https://static.bianet.org/icons/icon-large-facebook.svg" alt=""></a>
          </div>
          <p>Haber metni paragrafları...</p>
          <figure class="image">
            <img src="https://static.bianet.org/2026/04/body-1.jpg" alt="" width="800" height="600">
          </figure>
          <figure class="image">
            <img src="https://static.bianet.org/2026/04/body-2.jpg" alt="" width="800" height="600">
          </figure>
        </div>
        <div class="modal fade fig-modal" id="figModal">
          <div class="modal-dialog"><div class="modal-content"><div class="modal-body">
            <img src="https://static.bianet.org/big-yazi/2026/04/hero.jpg" alt="Hero büyük">
          </div></div></div>
        </div>
      </section>
      <section class="section--pushed">
        <div class="section__content">
          <div class="box box--most-read">
            <div class="news-wrapper">
              <a class="ccard ccard--news ccard--news-small" href="/x1">
                <div class="img-wrapper">
                  <img src="https://static.bianet.org/list-haber/2026/05/rec1.jpg"
                       alt="Öneri 1" width="200" height="120">
                </div>
              </a>
              <a class="ccard ccard--news ccard--news-small" href="/x2">
                <div class="img-wrapper">
                  <img src="https://static.bianet.org/list-yazi/2026/05/rec2.jpg"
                       alt="Öneri 2" width="200" height="120">
                </div>
              </a>
            </div>
          </div>
        </div>
      </section>
    </main>
    """
    soup = BeautifulSoup(html, "html.parser")
    images = extract_body_images(soup, "https://bianet.org/yazi/test-azicik-radyasyon-318589")
    urls = [i.url for i in images]

    assert "https://static.bianet.org/yazi/2026/04/hero.jpg" in urls
    assert "https://static.bianet.org/2026/04/body-1.jpg" in urls
    assert "https://static.bianet.org/2026/04/body-2.jpg" in urls
    assert "https://static.bianet.org/profile/2024/x/author.jpg" not in urls
    assert "https://static.bianet.org/big-yazi/2026/04/hero.jpg" not in urls
    assert "https://static.bianet.org/list-haber/2026/05/rec1.jpg" not in urls
    assert "https://static.bianet.org/list-yazi/2026/05/rec2.jpg" not in urls
    assert len(images) == 3


def test_bianet_profile_registered():
    """Bianet site profile PROFILES tuple'ında mevcut ve domain match'i çalışıyor."""
    from app.core.site_profiles import find_profile

    p = find_profile("https://bianet.org/yazi/foo-123")
    assert p is not None
    assert "bianet.org" in p.domains
    assert p.container_selector == "section.news-single"
    assert ".ccard--author" in p.exclude_selectors
    assert ".box--most-read" in p.exclude_selectors
    assert ".modal" in p.exclude_selectors

    # alt-domain uyumu (örn. m.bianet.org)
    p2 = find_profile("https://m.bianet.org/yazi/foo")
    assert p2 is not None
    assert p2 is p
