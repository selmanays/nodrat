"""Content Quality Gate — discovery + fetch aşamasında evergreen validation (#524).

Üç kategoride content failure'ı tek noktada yakalar:

1. **Invalid URL** (discovery): hostname/scheme eksik, fetch'e ulaşamayacak URL'ler
   reddedilir. Habertürk feed'inden gelen relative URL'ler (`/video/...`) örnek.

2. **Soft 404** (fetch sonrası): yayıncı silinen içerik için HTTP 200 + 404
   landing page döner. Title `<title>404 - Sayfa Bulunamadı</title>` veya
   body 404 mesajları. Evrensel'de yaygın kalıp.

3. **Thin content** (fetch sonrası): SPA hidrate (AA), live-blog sürekli
   güncellenen container, video player sayfaları. Body skeleton/empty,
   gerçek text yok.

Quality gate fail eden article'lar **terminal `status='archived'`**'a taşınır
(severity='permanent_info', retry yok). Aynı pattern duplicate_content (#488)
ve discovery URL filter (#504) ile uyumlu.

Generic — Türk haber siteleri + İngilizce + diğer dilleri kapsayacak şekilde
pattern listesi. Yeni source eklenirken pattern eklenebilir, ancak çoğu
kalıp ortak.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


# ============================================================================
# URL validation
# ============================================================================


def validate_url(url: str) -> tuple[bool, str | None]:
    """Discovery aşamasında URL validation.

    Returns:
        (valid, reason). valid=True → reason=None.
        valid=False → reason: 'empty' | 'no_scheme' | 'no_hostname' | 'invalid'

    Hostname + scheme zorunlu. Relative URL'ler (`/path`) veya scheme'siz
    (`example.com/foo`) reddedilir; fetch sırasında kesin fail olurlar.
    """
    if not url or not url.strip():
        return False, "empty"

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False, "invalid"

    if parsed.scheme not in ("http", "https"):
        return False, "no_scheme"

    if not parsed.netloc or "." not in parsed.netloc:
        return False, "no_hostname"

    return True, None


# ============================================================================
# Soft 404 detection
# ============================================================================


# Title pattern'leri — site genelinde ortak (Türkçe + İngilizce + bazı varyantlar)
_SOFT_404_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b404\b", re.IGNORECASE),
    re.compile(r"sayfa\s*bulunamad[ıi]", re.IGNORECASE),
    re.compile(r"page\s*not\s*found", re.IGNORECASE),
    re.compile(r"\bnot\s*found\b", re.IGNORECASE),
    re.compile(r"hata\s*404", re.IGNORECASE),
    re.compile(r"içerik\s*bulunamad[ıi]", re.IGNORECASE),
    re.compile(r"haber\s*bulunamad[ıi]", re.IGNORECASE),
)


# Body içinde 404 sinyalleri — title yetersiz olduğunda fallback
_SOFT_404_BODY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"aradığınız\s*sayfa.*bulunam", re.IGNORECASE | re.DOTALL),
    re.compile(r"this\s*page\s*does\s*not\s*exist", re.IGNORECASE),
    re.compile(r"sorry.*we\s*can[’']t\s*find", re.IGNORECASE),
)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _extract_title(html: str) -> str:
    """HTML'den <title> içeriğini çek (ilk eşleşme)."""
    if not html:
        return ""
    m = _TITLE_RE.search(html)
    if not m:
        return ""
    return m.group(1).strip()


def _is_soft_404(title: str, body_head: str) -> bool:
    """Title veya body başlangıcında 404 pattern'i."""
    if title:
        for pat in _SOFT_404_TITLE_PATTERNS:
            if pat.search(title):
                return True
    if body_head:
        for pat in _SOFT_404_BODY_PATTERNS:
            if pat.search(body_head):
                return True
    return False


# ============================================================================
# Thin content detection
# ============================================================================


_P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _extract_paragraph_text(html: str) -> str:
    """HTML'deki tüm <p> içeriğini birleştirilmiş plain text olarak döndür."""
    if not html:
        return ""
    parts: list[str] = []
    for m in _P_RE.finditer(html):
        text = _TAG_STRIP_RE.sub("", m.group(1)).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


# Thin content threshold'ları — yayıncılar arasında dengeli:
#   - 200 char altı: kesinlikle thin (header/footer + cookie banner mertebesi)
#   - 5+ paragraf: gerçek haber genelde olur
#   - text/html ratio < 1% kelime/byte: skeleton/placeholder
_MIN_TEXT_LENGTH = 200
_MIN_PARAGRAPH_COUNT = 2


def _is_thin_content(html: str) -> tuple[bool, str | None]:
    """Body'nin gerçek text içeriği yetersiz mi?

    Returns: (thin, reason). thin=False → reason=None.
    reason: 'no_paragraphs' | 'short_text' | 'low_density'
    """
    if not html:
        return True, "empty_body"

    paragraph_text = _extract_paragraph_text(html)
    if not paragraph_text:
        return True, "no_paragraphs"

    if len(paragraph_text) < _MIN_TEXT_LENGTH:
        return True, "short_text"

    # Density check — body uzun ama p text'i çok düşük oran (skeleton/SPA)
    body_len = len(html)
    if body_len > 5000 and len(paragraph_text) / body_len < 0.005:
        return True, "low_density"

    # Paragraph count — gerçek haber genelde 2+ p taşır
    p_count = len(_P_RE.findall(html))
    if p_count < _MIN_PARAGRAPH_COUNT:
        return True, "no_paragraphs"

    return False, None


# ============================================================================
# Content Quality check (orchestration)
# ============================================================================


@dataclass
class ContentQualityCheck:
    """Quality gate sonucu.

    passed=True → article extract pipeline'a devam edebilir.
    passed=False → record_failure + article_status_override=STATUS_ARCHIVED
    (terminal, retry yok — içerik yok demek).
    """

    passed: bool
    failure_reason: str | None  # 'soft_404' | 'thin_content' | None
    detail: str | None  # log için kategori subdetay


def check_response_quality(body: str, url: str) -> ContentQualityCheck:
    """HTTP fetch sonrası body için Content Quality Gate.

    İki katman (sırasıyla):
    1. Soft 404 — title/body 404 pattern'leri (Evrensel kalıbı)
    2. Thin content — paragraf yok, text < 200 char, veya skeleton density

    Body genelde tüm HTML; title extraction + ilk 2000 char body head pattern
    için yeterli (404 mesajları sayfa başında gelir).
    """
    if not body:
        return ContentQualityCheck(
            passed=False,
            failure_reason="thin_content",
            detail="empty_body",
        )

    # Layer 1: Soft 404
    title = _extract_title(body)
    body_head = body[:2000]
    if _is_soft_404(title, body_head):
        return ContentQualityCheck(
            passed=False,
            failure_reason="soft_404",
            detail=f"title='{title[:80]}'",
        )

    # Layer 2: Thin content
    thin, thin_reason = _is_thin_content(body)
    if thin:
        return ContentQualityCheck(
            passed=False,
            failure_reason="thin_content",
            detail=thin_reason,
        )

    return ContentQualityCheck(passed=True, failure_reason=None, detail=None)
