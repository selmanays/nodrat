"""schema.org JSON-LD structured-data extractor — #904 Tier-0.

Generic — per-site selector YOK. Türk haber siteleri (AA, Habertürk, Fotomaç,
Hürriyet, Sabah, TRT...) `<script type="application/ld+json">` içinde
schema.org `NewsArticle.articleBody` yayar. Site HTML class'ları/DOM yapısı
değişse de bu sözleşme stabil kalır → `content_quality` `<p>`-sayım
gate'inin false-positive ettiği `<div>`-CMS / SSR siteleri burada generic
kurtarılır (canlı probe: Habertürk 1300+, Fotomaç 827 char articleBody).

Bu modül `extractor.py` tarafından import edilir; circular import'tan
kaçınmak için tarih parse'ı caller'a bırakılır (`published_raw` ham string;
`extractor._parse_iso_date` ile çözülür).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


# schema.org haber/makale tipleri (lowercase karşılaştırma).
_ARTICLE_TYPES: frozenset[str] = frozenset(
    {
        "newsarticle",
        "article",
        "reportagenewsarticle",
        "backgroundnewsarticle",
        "opinionnewsarticle",
        "analysisnewsarticle",
        "reviewnewsarticle",
        "blogposting",
        "liveblogposting",
    }
)

# Bazı siteler schema.org URL'iyle yazar: "http://schema.org/NewsArticle".
_TYPE_TAIL_RE = re.compile(r"[#/]")

# JSON öncesi/sonrası CDATA / HTML comment sarmalayıcıları (bazı CMS'ler ekler).
_CDATA_RE = re.compile(r"^\s*(?://\s*)?<!\[CDATA\[(.*?)\]\]>\s*$", re.DOTALL)


@dataclass
class StructuredArticle:
    """JSON-LD'den çıkarılan ham makale alanları (#904 Tier-0)."""

    found: bool = False
    title: str = ""
    clean_text: str = ""
    author: str | None = None
    published_raw: str | None = None
    """Ham tarih string'i — caller `_parse_iso_date` ile datetime'a çevirir."""
    image_url: str | None = None
    schema_type: str = ""
    """Eşleşen schema.org tipi (telemetri/debug için)."""


def _coerce_types(value: Any) -> list[str]:
    """`@type` str | list | None → lowercase tail listesi.

    "NewsArticle" → ["newsarticle"]; "http://schema.org/Article" → ["article"];
    ["NewsArticle","Article"] → ["newsarticle","article"].
    """
    out: list[str] = []
    items = value if isinstance(value, list) else [value]
    for item in items:
        if not isinstance(item, str):
            continue
        tail = _TYPE_TAIL_RE.split(item.strip())[-1]
        if tail:
            out.append(tail.lower())
    return out


def _node_text(value: Any) -> str:
    """str | {"@value": "..."} | list[...] → düz metin (ilk anlamlı)."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        inner = value.get("@value") or value.get("text") or value.get("name")
        return _node_text(inner) if inner is not None else ""
    if isinstance(value, list):
        for item in value:
            t = _node_text(item)
            if t:
                return t
    return ""


def _author_name(value: Any) -> str | None:
    """author: str | {name} | {@value} | [..] | Organization → isim."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        name = value.get("name") or value.get("@value")
        return _node_text(name) or None
    if isinstance(value, list):
        names = [n for n in (_author_name(a) for a in value) if n]
        return ", ".join(names) if names else None
    return None


def _image_url(value: Any) -> str | None:
    """image: str | {url|contentUrl} | [..] | ImageObject → ilk URL."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        url = value.get("url") or value.get("contentUrl") or value.get("@id")
        return _node_text(url) or None
    if isinstance(value, list):
        for item in value:
            u = _image_url(item)
            if u:
                return u
    return None


def _iter_nodes(data: Any) -> Iterator[dict]:
    """JSON-LD payload'unu derinlemesine yürü — dict / list / @graph.

    Tek script birden çok node taşıyabilir (list veya @graph). İç içe
    geçmiş node'lar (örn. isPartOf, mainEntity) da taranır; herhangi bir
    derinlikteki article node yakalanır.
    """
    if isinstance(data, list):
        for item in data:
            yield from _iter_nodes(item)
        return
    if not isinstance(data, dict):
        return
    yield data
    graph = data.get("@graph")
    if isinstance(graph, (list, dict)):
        yield from _iter_nodes(graph)


def _loads_lenient(blob: str) -> Any | None:
    """json.loads + hafif kurtarma (CDATA sarmal, kontrol karakteri).

    Agresif onarım YAPILMAZ (yanlış parse riski); yalnız yaygın CMS
    kirliliği temizlenir. Başarısızsa None (caller diğer script'e geçer).
    """
    if not blob or not blob.strip():
        return None
    text = blob.strip()
    m = _CDATA_RE.match(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    # Yalnız kontrol karakterlerini temizleyip tekrar dene (sık görülen tek hata).
    cleaned = "".join(ch for ch in text if ch >= " " or ch in "\t\n\r")
    try:
        return json.loads(cleaned)
    except (ValueError, TypeError):
        return None


def parse_jsonld(html: str, *, min_body_len: int = 200) -> StructuredArticle:
    """HTML'deki tüm JSON-LD script'lerini parse → en uzun articleBody'li
    haber/makale node'unu döndür.

    En uzun `articleBody` seçilir çünkü bazı sayfalar hem özet (kısa)
    hem tam gövde içeren birden çok node yayar (örn. WebPage + NewsArticle,
    veya AA gibi sadece kısa özet). `min_body_len` altındakiler `found`
    sayılmaz → caller (extractor) bir sonraki kademeye düşer.
    """
    result = StructuredArticle()
    if not html:
        return result

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover — defensive
        return result

    best_body_len = -1
    for script in soup.find_all("script"):
        if not isinstance(script, Tag):
            continue
        stype = str(script.get("type", "") or "").lower()
        if "ld+json" not in stype:
            continue
        raw = script.string
        if raw is None:
            raw = script.get_text()
        data = _loads_lenient(raw or "")
        if data is None:
            continue

        for node in _iter_nodes(data):
            types = _coerce_types(node.get("@type"))
            if not any(t in _ARTICLE_TYPES for t in types):
                continue
            body = _node_text(node.get("articleBody"))
            if not body:
                continue
            if len(body) <= best_body_len:
                continue

            best_body_len = len(body)
            title = _node_text(node.get("headline")) or _node_text(
                node.get("name")
            )
            result.found = True
            result.title = title
            result.clean_text = body
            result.author = _author_name(node.get("author"))
            result.published_raw = (
                _node_text(node.get("datePublished"))
                or _node_text(node.get("dateCreated"))
                or _node_text(node.get("dateModified"))
                or None
            )
            result.image_url = _image_url(node.get("image"))
            result.schema_type = next(
                (t for t in types if t in _ARTICLE_TYPES), types[0]
            )

    # min_body_len altıysa "bulunamadı" say (AA 76-159 char özet vakası →
    # caller trafilatura density kademesine düşer).
    if result.found and len(result.clean_text) < min_body_len:
        logger.debug(
            "jsonld articleBody too short (%d < %d) — defer to next tier",
            len(result.clean_text),
            min_body_len,
        )
        return StructuredArticle()

    return result
