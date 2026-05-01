"""Detail page extractor — 3 kademeli strateji (PRD §1.5).

Strateji:
  1. Kaynağa özel admin selectors (source_configs.config_json)
  2. trafilatura general-purpose extraction
  3. Fallback: meta tags (og:*, twitter:*) + paragraph extraction

Output: ExtractedArticle (title, subtitle, author, published_at, body_html,
clean_text, main_image_url, language, extraction_confidence)

Doküman: docs/engineering/data-model.md §3.4 (articles)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import trafilatura
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


# Minimum kabul edilebilir clean_text uzunluğu — bu altındaki extraction "failed" sayılır
MIN_TEXT_LENGTH = 200

# Sanitize'de tutmayacağımız tag'ler (XSS guard)
DANGEROUS_TAGS = {
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "form",
    "input",
    "button",
    "noscript",
}

# Çıkarılacak attribute'lar (event handlers + javascript:)
DANGEROUS_ATTRS = {"onclick", "onerror", "onload", "onmouseover", "onfocus", "onblur"}


@dataclass
class ExtractedArticle:
    """Detail extractor sonucu — articles tablosu için ham veri."""

    url: str
    title: str = ""
    subtitle: str = ""
    author: str | None = None
    published_at: datetime | None = None
    body_html: str = ""
    clean_text: str = ""
    main_image_url: str | None = None
    language: str = "tr"

    extraction_confidence: float = 0.0
    """0.0..1.0 — min text + selectors hit + meta hit bonusu."""

    strategy_used: str = "none"
    """'admin_selectors' | 'trafilatura' | 'fallback' | 'none'"""

    error: str | None = None

    @property
    def successful(self) -> bool:
        return (
            bool(self.title.strip())
            and len(self.clean_text) >= MIN_TEXT_LENGTH
            and self.extraction_confidence >= 0.3
        )


# ============================================================================
# HTML utilities
# ============================================================================


def _make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _strip_dangerous(soup: BeautifulSoup) -> BeautifulSoup:
    """XSS-prone tag/attribute'ları çıkar.

    bleach yerine bs4 ile manuel — ek dep gerekmez.
    """
    for tag_name in DANGEROUS_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        for attr in list(tag.attrs.keys()):
            if attr in DANGEROUS_ATTRS:
                del tag[attr]
            # javascript: URL guard
            elif attr in ("href", "src", "action") and isinstance(tag.attrs[attr], str):
                if tag.attrs[attr].lower().lstrip().startswith("javascript:"):
                    del tag[attr]
    return soup


def _to_clean_text(html_or_soup: str | BeautifulSoup) -> str:
    """HTML'den clean_text çıkar — paragraf temelli, fazlalık whitespace silinir."""
    soup = _make_soup(html_or_soup) if isinstance(html_or_soup, str) else html_or_soup
    soup = _strip_dangerous(soup)
    text_parts: list[str] = []
    for elem in soup.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
        if not isinstance(elem, Tag):
            continue
        t = elem.get_text(" ", strip=True)
        if t and len(t) >= 20:
            text_parts.append(t)
    text = "\n\n".join(text_parts)
    # Fazlalık boşluk
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _resolve_image_url(image_url: str, base_url: str) -> str:
    """Relative image URL'sini base'e göre absolute yap."""
    if not image_url:
        return image_url
    if image_url.startswith(("http://", "https://", "//")):
        if image_url.startswith("//"):
            scheme = urlparse(base_url).scheme or "https"
            return f"{scheme}:{image_url}"
        return image_url
    return urljoin(base_url, image_url)


def _parse_iso_date(value: str) -> datetime | None:
    """ISO 8601 date parse — Türkçe haber sitelerinin yaygın formatları."""
    if not value:
        return None
    value = value.strip()
    # Ortak ISO formatlar
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    # Fallback: Python 3.11+ fromisoformat
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _extract_meta(soup: BeautifulSoup, names: list[str]) -> str | None:
    """meta name/property attribute'ından değer döner (ilk eşleşen)."""
    for name in names:
        # property= (OG / Twitter)
        tag = soup.find("meta", attrs={"property": name})
        if isinstance(tag, Tag) and tag.get("content"):
            return str(tag.get("content")).strip()
        # name=
        tag = soup.find("meta", attrs={"name": name})
        if isinstance(tag, Tag) and tag.get("content"):
            return str(tag.get("content")).strip()
    return None


# ============================================================================
# Strategy 1 — Admin selectors (source_configs.config_json)
# ============================================================================


def extract_with_selectors(
    html: str,
    *,
    url: str,
    selectors: dict[str, str],
    language: str = "tr",
) -> ExtractedArticle:
    """Source-specific CSS selectors ile extract.

    Args:
        html: page HTML
        url: source URL (image resolve için)
        selectors: dict — keys: title, body, author, published, image, subtitle
        language: language code (default tr)

    Returns:
        ExtractedArticle, strategy_used='admin_selectors'
    """
    result = ExtractedArticle(url=url, language=language, strategy_used="admin_selectors")
    soup = _make_soup(html)
    soup = _strip_dangerous(soup)

    matched = 0
    expected = 0

    if title_sel := selectors.get("title"):
        expected += 1
        node = soup.select_one(title_sel)
        if isinstance(node, Tag):
            result.title = node.get_text(" ", strip=True)
            matched += 1

    if subtitle_sel := selectors.get("subtitle"):
        expected += 1
        node = soup.select_one(subtitle_sel)
        if isinstance(node, Tag):
            result.subtitle = node.get_text(" ", strip=True)
            matched += 1

    if author_sel := selectors.get("author"):
        expected += 1
        node = soup.select_one(author_sel)
        if isinstance(node, Tag):
            result.author = node.get_text(" ", strip=True) or None
            matched += 1

    if published_sel := selectors.get("published"):
        expected += 1
        node = soup.select_one(published_sel)
        if isinstance(node, Tag):
            value = node.get("datetime") or node.get_text(" ", strip=True)
            if isinstance(value, str):
                result.published_at = _parse_iso_date(value)
                if result.published_at is not None:
                    matched += 1

    if image_sel := selectors.get("image"):
        expected += 1
        node = soup.select_one(image_sel)
        if isinstance(node, Tag):
            src = node.get("src") or node.get("data-src") or node.get("content")
            if isinstance(src, str):
                result.main_image_url = _resolve_image_url(src, url)
                matched += 1

    if body_sel := selectors.get("body"):
        expected += 1
        node = soup.select_one(body_sel)
        if isinstance(node, Tag):
            result.body_html = str(node)
            result.clean_text = _to_clean_text(node)
            matched += 1

    if expected > 0 and matched > 0:
        # Selectors hit oranı (matched/expected) + min text length kontrolü
        coverage = matched / expected
        text_ok = len(result.clean_text) >= MIN_TEXT_LENGTH
        # Adminin kurallarını yazdığı için yüksek confidence ver
        result.extraction_confidence = (
            min(0.95, 0.5 + coverage * 0.5) if text_ok else min(0.4, coverage * 0.4)
        )
    else:
        result.extraction_confidence = 0.0
        result.error = "no selector matched"

    return result


# ============================================================================
# Strategy 2 — trafilatura
# ============================================================================


def extract_with_trafilatura(html: str, *, url: str, language: str = "tr") -> ExtractedArticle:
    """Genel amaçlı extractor. Türkçe içerikle iyi çalışır.

    trafilatura JSON output'undan title, author, date, content alınır.
    main_image_url ve subtitle ayrıca soup ile meta tag'lerden eklenir.
    """
    result = ExtractedArticle(url=url, language=language, strategy_used="trafilatura")
    try:
        # output_format='json' → metadata + content tek seferde
        output = trafilatura.extract(
            html,
            url=url,
            output_format="json",
            include_comments=False,
            include_images=False,
            include_tables=False,
            with_metadata=True,
            favor_precision=True,
        )
    except Exception as exc:  # pragma: no cover - external lib
        logger.warning("trafilatura raised exception url=%s err=%s", url, exc)
        result.error = f"trafilatura error: {exc}"
        return result

    if not output:
        result.error = "trafilatura returned empty"
        return result

    import json as _json

    try:
        data: dict[str, Any] = _json.loads(output)
    except (ValueError, TypeError):
        result.error = "trafilatura output not JSON"
        return result

    result.title = (data.get("title") or "").strip()
    result.author = (data.get("author") or "").strip() or None
    if date_str := data.get("date"):
        result.published_at = _parse_iso_date(date_str)
    result.clean_text = (data.get("text") or "").strip()
    if lang := data.get("language"):
        result.language = lang

    # subtitle + image meta tag'lerden tamamla
    soup = _make_soup(html)
    if og_desc := _extract_meta(soup, ["og:description", "twitter:description", "description"]):
        result.subtitle = og_desc
    if og_img := _extract_meta(soup, ["og:image", "twitter:image", "twitter:image:src"]):
        result.main_image_url = _resolve_image_url(og_img, url)

    # body_html: trafilatura HTML formatından da alalım
    try:
        body_html = trafilatura.extract(
            html,
            url=url,
            output_format="html",
            include_comments=False,
            include_images=False,
            include_tables=False,
            with_metadata=False,
        )
        if body_html:
            result.body_html = str(body_html)
    except Exception:
        pass

    # Confidence: title var + min text + tarih var + image var
    score = 0.0
    if result.title:
        score += 0.3
    if len(result.clean_text) >= MIN_TEXT_LENGTH:
        score += 0.4
    if result.published_at:
        score += 0.15
    if result.main_image_url:
        score += 0.05
    if result.author:
        score += 0.1
    result.extraction_confidence = round(min(score, 0.9), 2)

    return result


# ============================================================================
# Strategy 3 — Fallback (meta + paragraph)
# ============================================================================


def extract_fallback(html: str, *, url: str, language: str = "tr") -> ExtractedArticle:
    """Son çare extractor — sadece meta tag + p element'ler."""
    result = ExtractedArticle(url=url, language=language, strategy_used="fallback")
    soup = _make_soup(html)
    soup = _strip_dangerous(soup)

    # Title
    if title := _extract_meta(soup, ["og:title", "twitter:title"]):
        result.title = title
    else:
        h1 = soup.find("h1")
        if isinstance(h1, Tag):
            result.title = h1.get_text(" ", strip=True)
        elif isinstance(soup.title, Tag):
            result.title = soup.title.get_text(" ", strip=True)

    # Subtitle / description
    if desc := _extract_meta(soup, ["og:description", "twitter:description", "description"]):
        result.subtitle = desc

    # Author
    if author := _extract_meta(soup, ["author", "article:author"]):
        result.author = author

    # Published
    if published := _extract_meta(
        soup, ["article:published_time", "datePublished", "og:article:published_time"]
    ):
        result.published_at = _parse_iso_date(published)

    # Image
    if og_img := _extract_meta(soup, ["og:image", "twitter:image"]):
        result.main_image_url = _resolve_image_url(og_img, url)

    # Body — article veya main tag varsa onun içinden, yoksa tüm soup
    article_tag = soup.find("article") or soup.find("main")
    target = article_tag if isinstance(article_tag, Tag) else soup
    result.clean_text = _to_clean_text(target)

    # Confidence — fallback olduğu için düşük tavanlı
    score = 0.0
    if result.title:
        score += 0.25
    if len(result.clean_text) >= MIN_TEXT_LENGTH:
        score += 0.30
    if result.published_at:
        score += 0.10
    if result.main_image_url:
        score += 0.05
    result.extraction_confidence = round(min(score, 0.7), 2)
    return result


# ============================================================================
# Public API — 3 stratejiyi kademeli uygular
# ============================================================================


def extract_article(
    html: str,
    *,
    url: str,
    selectors: dict[str, str] | None = None,
    language: str = "tr",
) -> ExtractedArticle:
    """3 kademeli extraction (PRD §1.5).

    1. selectors verildiyse extract_with_selectors → confidence>=0.5 ise dön
    2. trafilatura → confidence>=0.5 ise dön
    3. fallback meta-extraction

    Output her zaman ExtractedArticle — caller .successful kontrolü yapmalı.
    """
    # 1) Selectors
    if selectors:
        attempt = extract_with_selectors(html, url=url, selectors=selectors, language=language)
        if attempt.extraction_confidence >= 0.5 and attempt.successful:
            return attempt

    # 2) trafilatura
    traf = extract_with_trafilatura(html, url=url, language=language)
    if traf.extraction_confidence >= 0.5 and traf.successful:
        return traf

    # 3) fallback
    fallback = extract_fallback(html, url=url, language=language)
    # Hangisi daha iyi başarılıysa onu döndür (selector denendi ama düşük olabilir)
    candidates = [c for c in [fallback, traf] if c.title or c.clean_text]
    if not candidates:
        return fallback
    return max(candidates, key=lambda c: c.extraction_confidence)
