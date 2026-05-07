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
class BodyImage:
    """Article body içindeki <img> tag metadata (#300 MVP-1.4 PR-2).

    DOM'dan extract — RSS thumbnail VE og:image değil; haber gövdesindeki
    gerçek görsel(ler). Multi-image support. Bytes saklamayız (PR-3 NIM VLM
    process & discard).
    """

    url: str
    """Absolute URL (relative ise article URL'sine göre normalize edilir)."""
    alt: str = ""
    """<img alt="..."> attribute (ilk 500 char)."""
    caption: str = ""
    """En yakın <figure>/<figcaption> içeriği (ilk 500 char)."""
    position: int = 0
    """DOM order — 0-based body içindeki sıra."""


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
    """LEGACY (#300 PR-2): og:image / twitter:image meta. Kullanılmaz artık —
    body_images tercih edilir. Geriye uyumluluk için tutuldu, ileride drop."""
    body_images: list[BodyImage] = field(default_factory=list)
    """Article body <img> tag'lerinden extract edilen multi-image listesi (#300)."""
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


_NON_EDITORIAL_RE = re.compile(
    r"(?:^|[\s_/\-])"
    r"(?:"
    r"advertisement|advert|adsense|adsbygoogle|adunit|adslot|"
    r"sponsor(?:ed|ship)?|promo(?:ted|tion)?|"
    r"taboola|outbrain|criteo|adservice|googlesyndication|doubleclick|"
    r"reklam|reklamı|tanıtım|tanitim|"
    # logo / brand / dekoratif (TRT Haber logosu gibi kanal markaları)
    r"logo|brand|trademark|site[-_]?mark|"
    r"avatar|profile[-_]?pic(?:ture)?|gravatar|"
    r"share[-_]?(?:icon|btn|button|bar)|social[-_]?(?:icon|share|media)|"
    r"icon[-_]?small|emoji|favicon"
    r")"
    r"(?:[\s_/\-]|\d|$)",
    re.IGNORECASE,
)
_NON_EDITORIAL_SHORT_RE = re.compile(
    r"(?:^|[\s_/\-])(ads?|banner)(?:[\s_/\-]|\d|$)",
    re.IGNORECASE,
)
_NON_EDITORIAL_DOMAIN_RE = re.compile(
    r"(doubleclick\.net|googleadservices|googlesyndication|"
    r"amazon-adsystem|adsbygoogle|taboola\.com|outbrain\.com|"
    r"adservice\.google|criteo\.com|adnxs\.com|"
    r"gravatar\.com|gstatic\.com/youtube)",
    re.IGNORECASE,
)

# #304 fix — öneri/ilgili haber bölümleri (BBC "more stories" gibi)
# Class/id pattern'leri: related-stories, more-news, also-read, you-may-like,
# recommended, suggested, popular, trending, sidebar, carousel
# Türkçe pattern'ler: ilgili, öneri, benzer, popüler, sondakika, sizin-icin
# NOT: "widget" tek başına çok generic — Habertürk "widget-image" gibi asıl
#      içerik container'ları kullanıyor. Spesifik widget türleri (ad-widget,
#      social-widget, recommend-widget) zaten ayrı pattern'lerle yakalanıyor.
_RECOMMENDATION_RE = re.compile(
    r"(?:^|[\s_/\-])"
    r"(?:"
    r"recommend(?:ed|ation)?|related(?:[-_]?(?:stor|news|article|content|item|link))?|"
    r"suggest(?:ed|ion)?|more[-_]?(?:stor|news|article|read|item)|"
    r"also[-_]?(?:read|like|watch)|you[-_]?may[-_]?(?:like|enjoy|read|want)|"
    r"popular|trending|sidebar|carousel|"
    r"latest[-_]?(?:news|stor)|top[-_]?(?:stor|news|read)|"
    r"ilgili|öneri|önerilen|benzer|popüler|sondakika|sizin[-_]?için|sizin[-_]?icin|"
    r"diğer[-_]?haber|baska[-_]?haber|en[-_]?çok[-_]?okunan"
    r")"
    r"(?:[\s_/\-]|$)",
    re.IGNORECASE,
)


def _is_recommended_section(img: Tag) -> bool:
    """Img bir öneri/ilgili haber veya sidebar bölümünde mi? (#304 fix)

    Heuristic:
    - 10 ata level'a kadar tara
    - Semantic tag SKIP: <li> (öneri listesi), <aside>, <nav>, <header>, <footer>
    - Class/id regex (related|recommend|suggest|more-stor|sidebar|...)
    - Aria role: navigation, complementary, banner, contentinfo
    - <li> içindeyken kardeş <li> sayısı 1'den fazla (gerçek liste)
    """
    parent = img.parent
    depth = 0
    while parent is not None and depth < 10:
        if isinstance(parent, Tag):
            # Semantic skip — list item (öneri haberler), sidebar, nav, etc.
            # <li>: haber metninde madde işaretli liste genelde img içermez;
            # img içeren <li> öneri/ilgili haber listesidir.
            if parent.name in ("li", "aside", "nav", "header", "footer"):
                return True

            # Class / id pattern
            for attr_name in ("class", "id"):
                attr_val = parent.get(attr_name) or ""
                if isinstance(attr_val, list):
                    attr_val = " ".join(attr_val)
                if _RECOMMENDATION_RE.search(str(attr_val)):
                    return True

            # Aria role
            role = str(parent.get("role", "") or "").lower()
            if role in ("navigation", "complementary", "banner", "contentinfo"):
                return True

        parent = parent.parent if parent else None
        depth += 1

    return False


def _is_non_editorial_image(img: Tag, src: str) -> bool:
    """Reklam / logo / dekoratif öğe tespiti (#304 fix).

    Heuristic: img veya 5 ata level'a kadar herhangi bir element'in
    class/id/role/data-attribute'unda reklam veya logo işareti var mı?
    src URL'inde reklam ağı domaini veya path keyword'ü var mı?
    """
    # 1. URL domain / path
    if _NON_EDITORIAL_DOMAIN_RE.search(src):
        return True
    # path keyword (örn: /reklam/banner.jpg, /logo/site.png)
    if _NON_EDITORIAL_RE.search(src) or _NON_EDITORIAL_SHORT_RE.search(src):
        return True

    # 2. Image alt
    alt = str(img.get("alt", "") or "")
    if isinstance(alt, list):
        alt = " ".join(alt)
    if _NON_EDITORIAL_RE.search(alt):
        return True
    # "Reklam" tek başına Türkçe alt'larda yaygın
    if re.search(r"\breklam\b", alt, re.IGNORECASE):
        return True
    # "X logosu" / "X logo" Türkçe pattern
    if re.search(r"\b\w+\s+logo(?:su)?\b", alt, re.IGNORECASE):
        return True

    # 3. Image attributes (class/id/role)
    for attr_name in ("class", "id", "role"):
        attr_val = img.get(attr_name) or ""
        if isinstance(attr_val, list):
            attr_val = " ".join(attr_val)
        attr_str = str(attr_val)
        if _NON_EDITORIAL_RE.search(attr_str) or _NON_EDITORIAL_SHORT_RE.search(
            attr_str
        ):
            return True

    # 4. data-ad-* / data-google-query-id
    for attr in img.attrs.keys():
        a = str(attr).lower()
        if a.startswith("data-ad") or a == "data-google-query-id":
            return True

    # 5. Ata elementler (5 level'a kadar)
    parent = img.parent
    depth = 0
    while parent is not None and depth < 5:
        if isinstance(parent, Tag):
            for attr_name in ("class", "id"):
                attr_val = parent.get(attr_name) or ""
                if isinstance(attr_val, list):
                    attr_val = " ".join(attr_val)
                attr_str = str(attr_val)
                if _NON_EDITORIAL_RE.search(
                    attr_str
                ) or _NON_EDITORIAL_SHORT_RE.search(attr_str):
                    return True

            p_role = str(parent.get("role", "") or "").lower()
            if p_role in ("advertisement", "ad", "banner"):
                return True

            for attr in parent.attrs.keys():
                a = str(attr).lower()
                if a.startswith("data-ad") or a == "data-google-query-id":
                    return True

        parent = parent.parent if parent else None
        depth += 1

    return False


def extract_body_images(
    soup: BeautifulSoup, article_url: str
) -> list["BodyImage"]:
    """Article body içindeki <img> tag'lerini parse eder.

    Site profile sistemi (#304 fix):
      1. URL hostname'e göre `find_profile()` ile site profile bul
      2. Profile varsa:
         - `container_selector` ile body container override
         - `exclude_selectors` ile DOM'dan ilgili element'leri decompose
         - `main_image_selectors` whitelist ile sadece bu img'leri al
      3. Profile yoksa generic fallback chain (article/main/role=main/...)

    Tüm img'lere generic filter uygulanır:
      - Lazyload placeholder → data-src fallback
      - Reklam / logo / dekoratif filter (`_is_non_editorial_image`)
      - Öneri/ilgili haber section filter (`_is_recommended_section`)
      - Min size 100x100 hint
      - URL dedup
    """
    from app.core.site_profiles import find_profile

    profile = find_profile(article_url)

    # Container selection
    body_container: Tag | None = None
    if profile and profile.container_selector:
        body_container = soup.select_one(profile.container_selector)

    if body_container is None:
        candidate = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.find(
                class_=re.compile(r"(content|article|post|entry|story)", re.I)
            )
            or soup.body
            or soup
        )
        if isinstance(candidate, Tag):
            body_container = candidate

    if not isinstance(body_container, Tag):
        return []

    # Profile exclude_selectors → decompose
    # Sayfa modifiye edilir; aynı soup tekrar kullanılırsa not oluşur — ama
    # extractor'lar (selectors/trafilatura/fallback) farklı soup'lar kullanıyor
    # veya aynı soup'u sırayla tüketiyor. Tekrar çağrılırsa idempotent
    # (decompose edilmiş element zaten yok).
    if profile and profile.exclude_selectors:
        for sel in profile.exclude_selectors:
            try:
                for elem in body_container.select(sel):
                    elem.decompose()
            except Exception:  # pragma: no cover — geçersiz selector güvenliği
                continue

    # Whitelist mode (main_image_selectors) vs all
    if profile and profile.main_image_selectors:
        candidate_imgs: list[Tag] = []
        seen_ids: set[int] = set()
        for sel in profile.main_image_selectors:
            try:
                for img_tag in body_container.select(sel):
                    if isinstance(img_tag, Tag) and id(img_tag) not in seen_ids:
                        seen_ids.add(id(img_tag))
                        candidate_imgs.append(img_tag)
            except Exception:  # pragma: no cover
                continue
        img_iter = candidate_imgs
    else:
        img_iter = body_container.find_all("img")

    images: list[BodyImage] = []
    seen_urls: set[str] = set()
    position = 0

    # #304 fix — lazyload placeholder pattern (TRT Haber, vb. siteler kullanıyor)
    placeholder_re = re.compile(
        r"(lazyload-placeholder|lazy-load-placeholder|"
        r"placeholder\.(?:png|jpg|jpeg|gif|webp|svg)|"
        r"spacer\.(?:gif|png)|blank\.(?:gif|png)|loading\.(?:gif|png)|"
        r"transparent\.gif|1x1\.(?:gif|png))",
        re.IGNORECASE,
    )

    def _pick_src(img_tag: Tag) -> str:
        """src placeholder ise data-src'a fallback yap."""
        # Önce normal src'i dene
        primary = img_tag.get("src") or ""
        if isinstance(primary, list):
            primary = primary[0] if primary else ""
        primary = str(primary).strip()

        # Placeholder ise lazy-load attribute'lara düş
        if not primary or primary.startswith("data:") or placeholder_re.search(
            primary
        ):
            for lazy_attr in (
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-srcset",
            ):
                lazy = img_tag.get(lazy_attr) or ""
                if isinstance(lazy, list):
                    lazy = lazy[0] if lazy else ""
                lazy = str(lazy).strip()
                if "data-srcset" == lazy_attr and lazy:
                    # srcset format: "url1 1x, url2 2x" — ilk URL'i al
                    lazy = lazy.split(",")[0].split()[0].strip()
                if (
                    lazy
                    and not lazy.startswith("data:")
                    and not placeholder_re.search(lazy)
                ):
                    return lazy
            # Hiçbiri uygun değilse boş döndür (skip edilecek)
            return ""

        return primary

    for img in img_iter:
        if not isinstance(img, Tag):
            continue

        src = _pick_src(img)

        if not src or src.startswith("data:") or placeholder_re.search(src):
            continue

        absolute_url = _resolve_image_url(src, article_url)
        if not absolute_url.startswith(("http://", "https://")):
            continue

        # Dedup
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)

        # Küçük icon/logo skip — width veya height < 100
        try:
            w = int(str(img.get("width", "0")).strip("px") or 0)
            h = int(str(img.get("height", "0")).strip("px") or 0)
            if (w > 0 and w < 100) or (h > 0 and h < 100):
                continue
        except (ValueError, TypeError):
            pass

        # #304 fix — reklam / logo / dekoratif öğe filter
        if _is_non_editorial_image(img, absolute_url):
            continue

        # #304 fix — öneri/ilgili haber / sidebar bölümleri filter
        # (BBC "more stories" listesi <li>, related-articles widget vb.)
        if _is_recommended_section(img):
            continue

        alt_attr = img.get("alt") or ""
        if isinstance(alt_attr, list):
            alt_attr = " ".join(alt_attr)
        alt = str(alt_attr).strip()[:500]

        # Figure caption — generic extraction (#304 fix)
        # Önce <figcaption> ara (semantic, en güvenilir)
        # Yoksa figure içindeki img dışı tüm text (Evrensel <span class="small-title">,
        # diğer siteler <div class="caption">, <p>, vb.)
        # img tag'i text node yaratmıyor → figure.get_text() img alt'ını içermez,
        # sadece <figcaption> / <span> / <p> / vb. kardeş elementlerin text'ini alır.
        caption = ""
        figure = img.find_parent("figure")
        if figure and isinstance(figure, Tag):
            figcap = figure.find("figcaption")
            if figcap and isinstance(figcap, Tag):
                caption = figcap.get_text(" ", strip=True)[:500]
            else:
                # Fallback: figure içindeki tüm sibling text'i topla
                # (img'i geçici kaldır → text al → restore — ya da basitçe
                # tüm figure text'ini al; img zaten text node yaratmaz)
                full_text = figure.get_text(" ", strip=True)
                # img'in alt'ı eğer bir <span class="alt-text"> gibi
                # render edilmediyse text'e dahil olmaz. Yine de alt ile
                # tam çakışma varsa drop edip caption'ı boş bırak (bilgi yok).
                img_alt_text = str(img.get("alt", "") or "").strip()
                if isinstance(img.get("alt"), list):
                    img_alt_text = " ".join(img.get("alt") or []).strip()
                if full_text and full_text != img_alt_text:
                    # Alt'ı caption'dan çıkar (eğer caption alt ile başlıyor/sonlanıyorsa)
                    cleaned = full_text
                    if img_alt_text and cleaned.startswith(img_alt_text):
                        cleaned = cleaned[len(img_alt_text):].strip(" -—|:")
                    if img_alt_text and cleaned.endswith(img_alt_text):
                        cleaned = cleaned[: -len(img_alt_text)].strip(" -—|:")
                    if cleaned and cleaned != img_alt_text:
                        caption = cleaned[:500]

        images.append(
            BodyImage(
                url=absolute_url,
                alt=alt,
                caption=caption,
                position=position,
            )
        )
        position += 1

    return images


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

    # #300 PR-2 — body içindeki tüm img tag'leri (multi-image)
    result.body_images = extract_body_images(soup, url)

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

    # #300 PR-2 — body içindeki tüm img tag'leri (multi-image)
    result.body_images = extract_body_images(soup, url)

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

    # #300 PR-2 — body içindeki tüm img tag'leri (multi-image)
    result.body_images = extract_body_images(soup, url)

    return result


# ============================================================================
# Public API — 3 stratejiyi kademeli uygular
# ============================================================================


# ============================================================================
# Listing extractor — admin selector test (#70)
# ============================================================================


@dataclass
class ListingCard:
    """Listing/category sayfasındaki tek card preview'i (admin selector test)."""

    title: str | None = None
    link: str | None = None
    image_url: str | None = None
    date: str | None = None


def extract_listing_cards(
    html: str,
    *,
    url: str,
    selectors: dict[str, str],
    max_cards: int = 50,
) -> tuple[list[ListingCard], list[str]]:
    """Listing/category sayfasından card listesi çıkar.

    Admin selector test için — listing sayfasında card container, title,
    link, image, date selector'larını gerçek HTML'e karşı denenir.

    Args:
        html: page HTML
        url: page URL (relative link/image resolve için)
        selectors: dict — keys: card (zorunlu), title, link, image, date
        max_cards: maksimum dönülecek card sayısı (default 50)

    Returns:
        (cards, warnings) tuple. warnings field eksikliği için.
    """
    warnings: list[str] = []

    card_sel = selectors.get("card")
    if not card_sel:
        warnings.append("'card' selector zorunlu")
        return [], warnings

    soup = _make_soup(html)
    soup = _strip_dangerous(soup)

    matched_cards = soup.select(card_sel)
    if not matched_cards:
        warnings.append(f"'{card_sel}' hiçbir card bulunamadı")
        return [], warnings

    cards: list[ListingCard] = []
    missing_title = 0
    missing_link = 0
    missing_image = 0
    missing_date = 0

    for card in matched_cards[:max_cards]:
        if not isinstance(card, Tag):
            continue
        item = ListingCard()

        if title_sel := selectors.get("title"):
            node = card.select_one(title_sel)
            if isinstance(node, Tag):
                text = node.get_text(" ", strip=True)
                item.title = text or None
            if not item.title:
                missing_title += 1

        if link_sel := selectors.get("link"):
            node = card.select_one(link_sel)
            if isinstance(node, Tag):
                href = node.get("href")
                if isinstance(href, str) and href.strip():
                    item.link = urljoin(url, href.strip())
            if not item.link:
                missing_link += 1

        if image_sel := selectors.get("image"):
            node = card.select_one(image_sel)
            if isinstance(node, Tag):
                src = node.get("src") or node.get("data-src") or node.get("data-original")
                if isinstance(src, str) and src.strip():
                    item.image_url = _resolve_image_url(src.strip(), url)
            if not item.image_url:
                missing_image += 1

        if date_sel := selectors.get("date"):
            node = card.select_one(date_sel)
            if isinstance(node, Tag):
                value = node.get("datetime") or node.get_text(" ", strip=True)
                if isinstance(value, str) and value.strip():
                    item.date = value.strip()
            if not item.date:
                missing_date += 1

        cards.append(item)

    total = len(cards)
    if missing_title:
        warnings.append(f"{missing_title}/{total} card başlık eksik")
    if missing_link:
        warnings.append(f"{missing_link}/{total} card link eksik")
    if missing_image:
        warnings.append(f"{missing_image}/{total} card görsel eksik")
    if missing_date:
        warnings.append(f"{missing_date}/{total} card tarih eksik")

    return cards, warnings


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
