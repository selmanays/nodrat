"""Content Quality Gate testleri (#524).

Discovery URL validation + fetch sonrası body kalite kontrolü. Üç kategori:
1. Invalid URL (Habertürk relative)
2. Soft 404 (Evrensel silinen haber, HTTP 200 + 404 landing)
3. Thin content (AA SPA skeleton, AA live-blog, video player)

Production gerçek vakalarından sample'lar dahil.
"""

from __future__ import annotations

from app.core.content_quality import (
    ContentQualityCheck,
    check_response_quality,
    validate_url,
)

# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------


def test_validate_url_valid_https():
    valid, reason = validate_url("https://www.evrensel.net/haber/12345/test")
    assert valid is True
    assert reason is None


def test_validate_url_valid_http():
    valid, reason = validate_url("http://example.com/test")
    assert valid is True


def test_validate_url_relative_no_scheme():
    """Habertürk RSS bazen relative dönüyor — discovery'de skip."""
    valid, reason = validate_url("/video/haber/izle/test")
    assert valid is False
    assert reason == "no_scheme"


def test_validate_url_no_hostname():
    """https:// + path ama netloc boş."""
    valid, reason = validate_url("https:///path-only")
    assert valid is False
    assert reason == "no_hostname"


def test_validate_url_empty():
    valid, reason = validate_url("")
    assert valid is False
    assert reason == "empty"

    valid, reason = validate_url("   ")
    assert valid is False
    assert reason == "empty"


def test_validate_url_invalid_scheme():
    valid, reason = validate_url("ftp://example.com/file")
    assert valid is False
    assert reason == "no_scheme"

    valid, reason = validate_url("javascript:alert(1)")
    assert valid is False


def test_validate_url_no_dot_in_hostname():
    """localhost veya internal hostname — production'da geçersiz."""
    valid, reason = validate_url("https://localhost/test")
    assert valid is False
    assert reason == "no_hostname"


# ---------------------------------------------------------------------------
# check_response_quality — soft 404
# ---------------------------------------------------------------------------


def test_quality_soft_404_evrensel_real_sample():
    """Production gerçek vakası — Evrensel silinmiş haberin landing page'i."""
    body = """
    <html><head>
    <title>404 - Sayfa Bulunamadı - Evrensel</title>
    </head><body>
    <p>Sitemizde zorunlu ve isteğe bağlı çerezler kullanıyoruz...</p>
    <p>"Kabul Et" butonuna tıklayarak isteğe bağlı çerezleri kabul...</p>
    </body></html>
    """
    result = check_response_quality(body, "https://www.evrensel.net/haber/123/test")
    assert result.passed is False
    assert result.failure_reason == "soft_404"
    assert "404" in (result.detail or "")


def test_quality_soft_404_english():
    body = """<html><head><title>Page Not Found</title></head><body><p>...</p></body></html>"""
    result = check_response_quality(body, "https://example.com/x")
    assert result.passed is False
    assert result.failure_reason == "soft_404"


def test_quality_soft_404_haber_bulunamadi():
    """Türkçe varyant: 'haber bulunamadı'."""
    body = """<html><head><title>Haber Bulunamadı</title></head><body></body></html>"""
    result = check_response_quality(body, "https://example.com/x")
    assert result.passed is False
    assert result.failure_reason == "soft_404"


# ---------------------------------------------------------------------------
# check_response_quality — thin content
# ---------------------------------------------------------------------------


def test_quality_thin_empty_body():
    result = check_response_quality("", "https://example.com/x")
    assert result.passed is False
    assert result.failure_reason == "thin_content"
    assert result.detail == "empty_body"


def test_quality_thin_no_paragraphs():
    """Sadece header/footer var, p yok → thin."""
    body = "<html><head><title>Real Title</title></head><body><div>nav</div></body></html>"
    result = check_response_quality(body, "https://example.com/x")
    assert result.passed is False
    assert result.failure_reason == "thin_content"
    assert result.detail in ("no_paragraphs", "empty_body")


def test_quality_thin_short_text():
    """Title var, p var ama 200 char altı."""
    body = """<html><head><title>News</title></head><body>
    <p>Çok kısa haber.</p><p>Bir cümle daha.</p></body></html>"""
    result = check_response_quality(body, "https://example.com/x")
    assert result.passed is False
    assert result.failure_reason == "thin_content"
    assert result.detail == "short_text"


def test_quality_thin_low_density_spa_skeleton():
    """AA SPA — body uzun ama p text density düşük (skeleton)."""
    skeleton_body = (
        "<html><head><title>News</title></head><body>"
        + ('<div class="bg-skeletonColor animate-pulse"></div>' * 200)
        + "<p>az</p>"
        + "</body></html>"
    )
    result = check_response_quality(skeleton_body, "https://www.aa.com.tr/tr/test")
    assert result.passed is False
    assert result.failure_reason == "thin_content"
    # 'low_density' or 'short_text' depending on threshold path
    assert result.detail in ("low_density", "short_text")


# ---------------------------------------------------------------------------
# check_response_quality — passes (gerçek haber)
# ---------------------------------------------------------------------------


def test_quality_passes_real_article():
    """Gerçek haber sayfası — title + birkaç p + 200+ char text."""
    body = """<html><head><title>Türkiye'de yeni gelişme</title></head>
    <body>
    <h1>Başlık</h1>
    <p>İlk paragraf burada gerçek bir haber metni içeriyor. Bu cümle yeterince
    uzun olmalı, gerçek haberlerin ilk paragrafı genelde 100+ karakter olur.</p>
    <p>İkinci paragraf devam ediyor. Bu da ek detay sağlıyor ve haberin
    içeriğini destekliyor. Yeterli text var.</p>
    <p>Üçüncü paragraf ile birlikte toplam 200+ char text mevcut.</p>
    </body></html>"""
    result = check_response_quality(body, "https://example.com/news/test")
    assert result.passed is True
    assert result.failure_reason is None


def test_quality_passes_dataclass_shape():
    """ContentQualityCheck dataclass alanları doğru."""
    result = ContentQualityCheck(passed=True, failure_reason=None, detail=None)
    assert result.passed is True
    assert result.failure_reason is None

    fail = ContentQualityCheck(passed=False, failure_reason="soft_404", detail="title='404'")
    assert fail.passed is False
    assert fail.failure_reason == "soft_404"


# ---------------------------------------------------------------------------
# #598 — HTML5 implicit <p> close (bianet pattern)
# ---------------------------------------------------------------------------


def test_quality_passes_html5_implicit_p_close():
    """Bianet vakası: <p> açılır ama </p> kapanmaz (HTML5 valid).

    Eski regex `<p[^>]*>(.*?)</p>` re.DOTALL ile tek dev paragraf yakalardı
    (p_count=1 < MIN=2 → false positive thin_content). BS-based fix ile
    ayrı paragraflar doğru sayılır.
    """
    body = """<html><head><title>Bir terennümün serencamı</title></head>
    <body>
    <h1>Başlık</h1>
    <p>Tarih her zaman mürekkeple yazılmaz. Bazen bir nefesin ucunda titrer.
    <p>Rivayet edilir ki, uzak bir zamanın derinliklerinde, Sasani saraylarının
    gölgeli taş avlularında yankılanan ezgilerin ardında iki usta müzisyen vardı.
    <p>Terennüm. Belki de bu çağrının en güzel adıydı. Terennüm etmek, yalnızca
    bir sözü dile getirmek değildi. Yeterince uzun ek metin burada.
    <p>İşte tam da bu ilahi sesin ortasındayken bir isim ve o ismin ilahi gayreti
    düştü önümüze.
    </body></html>"""
    result = check_response_quality(body, "https://bianet.org/yazi/x")
    assert result.passed is True, f"Beklenen passed=True, alındı: {result.failure_reason}"
    assert result.failure_reason is None


def test_count_paragraphs_html5_implicit_close():
    """_count_paragraphs BS-based — </p> olmadan da doğru sayım."""
    from app.core.content_quality import _count_paragraphs

    html = "<div><p>Bir<p>İki<p>Üç metin paragrafı</div>"
    assert _count_paragraphs(html) == 3


def test_extract_paragraph_text_html5_implicit_close():
    """_extract_paragraph_text BS-based — </p> olmadan da doğru text."""
    from app.core.content_quality import _extract_paragraph_text

    html = "<div><p>Birinci<p>İkinci<p>Üçüncü</div>"
    text = _extract_paragraph_text(html)
    assert "Birinci" in text
    assert "İkinci" in text
    assert "Üçüncü" in text
