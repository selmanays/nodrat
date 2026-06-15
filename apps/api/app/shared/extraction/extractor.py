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
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import trafilatura
from bs4 import BeautifulSoup, Tag

from app.shared.extraction.structured_data import parse_jsonld

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
    """'structured_data' | 'admin_selectors' | 'trafilatura' | 'fallback' | 'none'"""

    error: str | None = None

    @property
    def successful(self) -> bool:
        return (
            bool(self.title.strip())
            and len(self.clean_text) >= MIN_TEXT_LENGTH
            and self.extraction_confidence >= 0.3
        )

    def apply_title_fallback(self, fallback: str) -> None:
        """Sayfa başlık vermediğinde keşif (RSS/sitemap/card) başlığını kullan (#1529).

        Yalnız `title` boşken devreye girer; dolu title'ı override ETMEZ. Generic
        (per-site değil) — title-eksik atipik sayfaları (gov/regülasyon, bazı SSR)
        gereksiz quarantine'den kurtarır. text/conf gate (>=MIN, >=0.3) korunur.
        """
        if not self.title.strip() and fallback and fallback.strip():
            self.title = fallback.strip()


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
            if attr in DANGEROUS_ATTRS or (
                attr in ("href", "src", "action")
                and isinstance(tag.attrs[attr], str)
                and tag.attrs[attr].lower().lstrip().startswith("javascript:")
            ):
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


# Internal filter helpers (PR-C internal split — T6 #1085).
# Regex patterns ve `_is_*` classifier'lar `_extractor_filters.py`'a taşındı
# (davranış değişmedi; pure refactor). Diğer modüller bu helper'ları DOĞRUDAN
# import etmez — yalnız `app.core.extractor` public surface'i kullanılır.
from app.shared.extraction._filters import (  # noqa: E402
    _is_non_editorial_image,
    _is_recommended_section,
)


def extract_body_images(soup: BeautifulSoup, article_url: str) -> list[BodyImage]:
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
    from app.shared.extraction.site_profiles import find_profile

    profile = find_profile(article_url)

    # #603 — Yapısal boilerplate temizliği (kök çözüm, regex-yamalama yerine):
    # Body container seçilmeden ÖNCE soup'tan sayfa şablonu element'lerini
    # decompose et. Aside/nav/header/footer + role=banner/complementary +
    # social-share / newsletter widget'ları her sayfada AYNI içeriği taşır
    # (logo, sosyal medya ikonları, etkinlik banner'ları, lightbox UI).
    # Bunlar haber gövdesinin parçası DEĞİL → kaynaktan kaldırılır.
    #
    # Decompose idempotent: tekrar çağrıda zaten yok. Profile sahibi siteler
    # de bundan fayda görür (whitelist'leri sıkılaştırmak gerekmez).
    _BOILERPLATE_SELECTORS = (
        "aside",
        "nav",
        "header",
        "footer",
        "[role=banner]",
        "[role=complementary]",
        "[role=navigation]",
        "[role=contentinfo]",
        # Social / share / newsletter sticker boilerplate
        "[class*='social-share']",
        "[class*='social-media']",
        "[class*='share-bar']",
        "[class*='share-button']",
        "[class*='newsletter']",
        "[class*='subscribe']",
        # Cookie banner / GDPR popup
        "[class*='cookie-banner']",
        "[class*='cookie-consent']",
        "[id*='cookie-banner']",
    )
    for sel in _BOILERPLATE_SELECTORS:
        try:
            for elem in soup.select(sel):
                elem.decompose()
        except Exception:  # pragma: no cover — geçersiz selector güvenliği  # noqa: S112
            continue

    # Container selection
    body_container: Tag | None = None
    if profile and profile.container_selector:
        body_container = soup.select_one(profile.container_selector)

    if body_container is None:
        candidate = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.find(class_=re.compile(r"(content|article|post|entry|story)", re.I))
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
            except Exception:  # pragma: no cover — geçersiz selector güvenliği  # noqa: S112
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
            except Exception:  # pragma: no cover  # noqa: S112
                continue
        img_iter = candidate_imgs
    else:
        img_iter = body_container.find_all("img")

    images: list[BodyImage] = []
    seen_urls: set[str] = set()
    position = 0

    # #304 / #604 — Lazyload placeholder pattern.
    # Genişletildi (#604):
    #   - `*-empty.*` (jeg-empty.png, page-empty.gif gibi theme placeholder'ları)
    #   - WordPress theme assets (`/wp-content/themes/.../assets/.../X.(png|jpg|...)`)
    #     genelde dekoratif placeholder; gerçek görsel `wp-content/uploads/`'ta
    #   - `noimage`, `default-image`, `dummy` keywords
    placeholder_re = re.compile(
        r"(lazyload-placeholder|lazy-load-placeholder|"
        r"placeholder\.(?:png|jpg|jpeg|gif|webp|svg)|"
        r"spacer\.(?:gif|png)|blank\.(?:gif|png)|loading\.(?:gif|png)|"
        r"transparent\.gif|1x1\.(?:gif|png)|"
        # #604 — JNews / generic empty placeholder
        r"[-_]empty\.(?:png|jpg|jpeg|gif|webp|svg)|"
        r"noimage|no[-_]image|default[-_]image|dummy[-_]?img|"
        # #604 — WordPress theme assets path (placeholder'lar burada)
        r"/wp-content/themes/[^/]+/assets/img/[^/]*\.(?:png|jpg|jpeg|gif|webp|svg))",
        re.IGNORECASE,
    )

    def _pick_src(img_tag: Tag) -> str:
        """src placeholder ise data-src'a fallback yap.

        Sıralama: src normalse src; src placeholder/empty/data-uri ise sırayla
        data-src → data-original → data-lazy-src → data-srcset (ilk URL).
        Hiçbiri uygun değilse boş string (skip).

        #604 — placeholder regex genişletildi (jeg-empty.png, theme/assets
        path, noimage keyword) → C4Defence WordPress JNews vakası burada
        yakalanır: src='jeg-empty.png' regex match → data-src'a düşer.
        """
        # Önce normal src'i dene
        primary = img_tag.get("src") or ""
        if isinstance(primary, list):
            primary = primary[0] if primary else ""
        primary = str(primary).strip()

        # Placeholder ise lazy-load attribute'lara düş
        if not primary or primary.startswith("data:") or placeholder_re.search(primary):
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
                if lazy_attr == "data-srcset" and lazy:
                    # srcset format: "url1 1x, url2 2x" — ilk URL'i al
                    lazy = lazy.split(",")[0].split()[0].strip()
                if lazy and not lazy.startswith("data:") and not placeholder_re.search(lazy):
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

        # #603 — Boyut & aspect ratio guard (kök çözüm).
        # Küçük: 200x200 altı genelde icon/logo (50px FB ikonu, 100px nav button).
        # Banner aspect: 5:1+ ratio = "banner" formatı (sayfa üstü/altı reklam,
        # etkinlik bannerı). 1:5- ratio = vertical strip (sidebar reklam).
        # Yalnızca HTML attr'da DEKLARE EDİLEN ölçüler kullanılır — eksikse
        # defansif (gerçek görselleri yanlışlıkla atmak istemiyoruz).
        try:
            w = int(str(img.get("width", "0")).strip("px") or 0)
            h = int(str(img.get("height", "0")).strip("px") or 0)
            # 1) Min boyut: width veya height < 200 → icon-büyüklüğü, exclude.
            if (w > 0 and w < 200) or (h > 0 and h < 200):
                continue
            # 2) Aspect ratio: ikisi de mevcutsa banner/strip detect.
            if w > 0 and h > 0:
                aspect = w / h if h else 999.0
                if aspect > 5.0 or aspect < 0.2:
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
                        cleaned = cleaned[len(img_alt_text) :].strip(" -—|:")
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
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            continue
    # Fallback: Python 3.11+ fromisoformat
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
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


def _trafilatura_json_extract(html: str, *, url: str, **flags: Any) -> dict[str, Any] | None:
    """Tek mod trafilatura JSON çağrısı — fail/empty/parse-error → None.

    #529 multi-mode cascade için yardımcı.
    """
    import json as _json

    try:
        output = trafilatura.extract(
            html,
            url=url,
            output_format="json",
            include_comments=False,
            include_images=False,
            include_tables=False,
            with_metadata=True,
            **flags,
        )
    except Exception as exc:  # pragma: no cover - external lib
        logger.warning("trafilatura raised exception url=%s mode=%s err=%s", url, flags, exc)
        return None

    if not output:
        return None

    try:
        return _json.loads(output)
    except (ValueError, TypeError):
        return None


# Trafilatura cascade: precision → default → recall.
# - precision: konservatif, uzun makalelerde gürültü siler.
#   AMA Next.js / SPA SSR'da kısa makaleler için içeriği reddedip yalnızca
#   boilerplate'i (örn. AA HAS abonelik disclaimer) döndürebilir (#529).
# - default: trafilatura'nın varsayılan dengeli mod.
# - recall: en agresif, son çare. Reklam/menü gürültüsü olabilir.
_TRAFILATURA_MODES: list[tuple[str, dict[str, Any]]] = [
    ("precision", {"favor_precision": True}),
    ("default", {}),
    ("recall", {"favor_recall": True}),
]


def extract_with_trafilatura(html: str, *, url: str, language: str = "tr") -> ExtractedArticle:
    """Genel amaçlı extractor. Türkçe içerikle iyi çalışır.

    Multi-mode cascade (#529): precision → default → recall. İlk
    `MIN_TEXT_LENGTH` üstüne ulaşan modu seç; hiçbiri ulaşmazsa en uzun çıktıyı
    döndür (caller .successful kontrolü yapar).

    main_image_url ve subtitle her zaman soup ile meta tag'lerden tamamlanır.
    """
    result = ExtractedArticle(url=url, language=language, strategy_used="trafilatura")

    chosen_data: dict[str, Any] | None = None
    chosen_flags: dict[str, Any] = {}
    longest_data: dict[str, Any] | None = None
    longest_flags: dict[str, Any] = {}
    longest_len = -1

    for _mode_name, flags in _TRAFILATURA_MODES:
        data = _trafilatura_json_extract(html, url=url, **flags)
        if data is None:
            continue
        text_len = len((data.get("text") or "").strip())
        if text_len > longest_len:
            longest_data, longest_flags, longest_len = data, flags, text_len
        if text_len >= MIN_TEXT_LENGTH:
            chosen_data, chosen_flags = data, flags
            break

    # Tüm modlar threshold altıysa en uzun çıktıyı al — caller fallback
    # stratejisi ile karşılaştırıp en iyisini seçer.
    if chosen_data is None:
        chosen_data, chosen_flags = longest_data, longest_flags

    if chosen_data is None:
        result.error = "trafilatura returned empty (all modes)"
        return result

    data = chosen_data
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

    # body_html: kazanan mod ile tek extract
    try:
        body_html = trafilatura.extract(
            html,
            url=url,
            output_format="html",
            include_comments=False,
            include_images=False,
            include_tables=False,
            with_metadata=False,
            **chosen_flags,
        )
        if body_html:
            result.body_html = str(body_html)
    except Exception:  # noqa: S110
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

    # Body — article veya main tag varsa onun içinden, yoksa tüm soup.
    # #529: Next.js / SPA SSR sayfalarında <main> var ama içi boş olabilir
    # (içerik client-side hydration ile gelir). Bu durumda whole-soup'a
    # fall-through yap — yoksa fallback 0 char döner ve trafilatura'nın
    # boilerplate (örn. AA HAS disclaimer) çıktısı "kazanır".
    article_tag = soup.find("article") or soup.find("main")
    if isinstance(article_tag, Tag):
        text = _to_clean_text(article_tag)
        if len(text) < MIN_TEXT_LENGTH:
            text = _to_clean_text(soup)
        result.clean_text = text
    else:
        result.clean_text = _to_clean_text(soup)

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


def extract_structured_tier(html: str, *, url: str, language: str = "tr") -> ExtractedArticle:
    """#904 Tier-0 — schema.org JSON-LD `articleBody` generic extractor.

    Per-site selector YOK. `articleBody` düz proza olduğu için `_to_clean_text`
    (`<div>` text + <20 char satır drop sorunu) BYPASS edilir — doğrudan
    clean_text'e atanır. subtitle/image meta'dan, body_images soup'tan
    tamamlanır (mevcut helper'lar reuse).
    """
    result = ExtractedArticle(url=url, language=language, strategy_used="structured_data")
    sd = parse_jsonld(html, min_body_len=MIN_TEXT_LENGTH)
    if not sd.found:
        result.error = "no schema.org article JSON-LD"
        return result

    result.title = sd.title
    # articleBody düz metin → whitespace normalize (HTML tag yok, _to_clean_text YOK).
    text = re.sub(r"\n{3,}", "\n\n", sd.clean_text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    result.clean_text = text
    result.author = sd.author or None
    if sd.published_raw:
        result.published_at = _parse_iso_date(sd.published_raw)

    soup = _make_soup(html)
    if og_desc := _extract_meta(soup, ["og:description", "twitter:description", "description"]):
        result.subtitle = og_desc
    if sd.image_url:
        result.main_image_url = _resolve_image_url(sd.image_url, url)
    elif og_img := _extract_meta(soup, ["og:image", "twitter:image"]):
        result.main_image_url = _resolve_image_url(og_img, url)

    # Confidence: JSON-LD yüksek-güven sinyali (admin yazmasa da kaynak yayınlar).
    score = 0.0
    if result.title:
        score += 0.35
    if len(result.clean_text) >= MIN_TEXT_LENGTH:
        score += 0.45
    if result.published_at:
        score += 0.10
    if result.author:
        score += 0.05
    if result.main_image_url:
        score += 0.05
    result.extraction_confidence = round(min(score, 0.95), 2)

    result.body_images = extract_body_images(soup, url)
    return result


def extract_article(
    html: str,
    *,
    url: str,
    selectors: dict[str, str] | None = None,
    language: str = "tr",
    render_client: Any | None = None,
) -> ExtractedArticle:
    """#904 generic kademeli extraction (per-site selector YOK).

    0. Tier-0 structured-data (schema.org JSON-LD) → conf>=0.6 & successful ise dön
    1. (legacy) selectors verildiyse extract_with_selectors → conf>=0.5 ise dön
    2. trafilatura multi-mode (#529 density backbone) → conf>=0.5 ise dön
    3. fallback meta-extraction
    → .successful tie-break (Tier-0 dahil): en uzun successful, yoksa conf.

    `render_client`: #904 deferred seam — gerçek client-side SPA için headless
    render tier. MVP cut-list #71; ŞU AN implement EDİLMEDİ (canlı veri mevcut
    kayıpta SPA olmadığını kanıtladı). İmza geleceğe hazır; None ⇒ no-op.

    Output her zaman ExtractedArticle — caller .successful kontrolü yapmalı.
    """
    # 0) Tier-0 structured-data (generic, en güvenilir; Habertürk/Fotomaç buradan)
    structured = extract_structured_tier(html, url=url, language=language)
    if structured.extraction_confidence >= 0.6 and structured.successful:
        return structured

    # 1) Selectors (legacy — prod'da selectors=None; #904 detay-selector ölü)
    if selectors:
        attempt = extract_with_selectors(html, url=url, selectors=selectors, language=language)
        if attempt.extraction_confidence >= 0.5 and attempt.successful:
            return attempt

    # 2) trafilatura (density backbone — AA SSR vakası buradan, #529)
    traf = extract_with_trafilatura(html, url=url, language=language)
    if traf.extraction_confidence >= 0.5 and traf.successful:
        return traf

    # 3) fallback
    fallback = extract_fallback(html, url=url, language=language)

    # #529 + #904: .successful=True olanların en uzun text'lisi; yoksa
    # confidence tie-break. Tier-0 (structured) da adaylara dahil — AA gibi
    # JSON-LD özeti kısa olup density daha uzunsa density kazansın; tersi
    # de geçerli.
    candidates = [c for c in [structured, fallback, traf] if c.title or c.clean_text]
    if not candidates:
        return fallback
    successful_only = [c for c in candidates if c.successful]
    if successful_only:
        return max(successful_only, key=lambda c: len(c.clean_text))
    return max(candidates, key=lambda c: c.extraction_confidence)
