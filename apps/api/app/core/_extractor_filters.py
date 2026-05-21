"""Internal extractor filter helpers — regex patterns + classifier functions.

PR-C internal split (T6 #1085 god-file refactor):
- Daha önce `app.core.extractor` (line 166-349) içinde inline'dı
- Bu modül **internal helper**; pure refactor — davranış değişikliği YOK
- Public consumer: `app.core.extractor` (top-level import; re-export)
- Modül-dışı **doğrudan import edilmez** — stable API DEĞİL

Refs:
- PR #1144 — extract_body_images characterization tests (regression safety-net)
- core/extractor.py — public surface bu helper'ları kullanır
"""

from __future__ import annotations

import re

from bs4 import Tag

# ============================================================================
# Regex patterns — non-editorial / recommendation classifier inputs
# ============================================================================

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
    r"(?:[\s_/\-.]|\d|$)",  # #600 — `.` boundary ekle (ext yakalama)
    re.IGNORECASE,
)
_NON_EDITORIAL_SHORT_RE = re.compile(
    # #600 — `.` boundary ekle: `Banner.webp` artık match eder
    r"(?:^|[\s_/\-])(ads?|banner)(?:[\s_/\-.]|\d|$)",
    re.IGNORECASE,
)
# #600 — Icon dosya adları + path patterns
# Generic icon (icon-large-X, icon_small_Y, /icons/X, /static/icons/Y)
_ICON_FILE_RE = re.compile(
    r"(?:^|/)icons?[/_-]"  # /icons/, /icon-, _icon_
    r"|(?:^|[/_-])icon[-_][a-z]"  # icon-name, _icon-name
    r"|/static/(?:img/)?(?:logo|icon|brand|social)",  # /static/icons/, /static/img/logo
    re.IGNORECASE,
)
# UI element alt texts (lightbox button, share, more, etc.)
_UI_ELEMENT_ALT_RE = re.compile(
    r"^(?:"
    r"görsel(?:i|leri)?\s*büyüt|büyütmek\s*için|"
    r"daha\s*fazla|devamını\s*oku|tümünü\s*gör|"
    r"yorum(?:lar)?\s*(?:gör|yap)?|paylaş|"
    r"open\s*(?:image|in)|enlarge|zoom|"
    r"read\s*more|view\s*all|see\s*more"
    r")\s*$",
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


# ============================================================================
# Filter functions
# ============================================================================


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
    # #600 — icon dosya adları (icon-large-facebook.svg, /static/icons/, vs.)
    if _ICON_FILE_RE.search(src):
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
    # #600 — UI element alt'ları (lightbox/zoom button, "Görseli Büyüt", vs.)
    if _UI_ELEMENT_ALT_RE.match(alt.strip()):
        return True

    # 3. Image attributes (class/id/role)
    for attr_name in ("class", "id", "role"):
        attr_val = img.get(attr_name) or ""
        if isinstance(attr_val, list):
            attr_val = " ".join(attr_val)
        attr_str = str(attr_val)
        if _NON_EDITORIAL_RE.search(attr_str) or _NON_EDITORIAL_SHORT_RE.search(attr_str):
            return True

    # 4. data-ad-* / data-google-query-id
    for attr in img.attrs:
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
                if _NON_EDITORIAL_RE.search(attr_str) or _NON_EDITORIAL_SHORT_RE.search(attr_str):
                    return True

            p_role = str(parent.get("role", "") or "").lower()
            if p_role in ("advertisement", "ad", "banner"):
                return True

            for attr in parent.attrs:
                a = str(attr).lower()
                if a.startswith("data-ad") or a == "data-google-query-id":
                    return True

        parent = parent.parent if parent else None
        depth += 1

    return False
