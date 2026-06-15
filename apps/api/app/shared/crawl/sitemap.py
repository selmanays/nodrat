"""Sitemap (sitemapindex / urlset) parser — pure, I/O-free (#1527).

JS-render'lı / statik card-scrape edilemeyen siteler için sitemap tabanlı
makale keşfi. `parse_sitemap` network çağrısı YAPMAZ; fetch + dispatch task
katmanında (sources/tasks/sources.py `_discover_from_sitemap`).

Generic body extraction (#904 JSON-LD → density → fallback) keşfedilen URL'lerden
gövdeyi çeker; bu modül yalnız "hangi URL'ler" sorusunu yanıtlar.

docs/engineering/architecture.md (crawl)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime

# Defensive: aşırı büyük gövde + entity-expansion (billion laughs) / DOCTYPE reddi.
# Sitemap'ler güvenilir haber sitelerinden fetch edilir ama yine de fail-safe.
_MAX_SITEMAP_BYTES = 25 * 1024 * 1024  # 25 MB


@dataclass(slots=True)
class SitemapEntry:
    """Tek sitemap girdisi — bir makale URL'si (urlset) veya alt-sitemap (index)."""

    loc: str
    lastmod: datetime | None = None


def _localname(tag: str) -> str:
    """'{ns}urlset' → 'urlset' (namespace-agnostik, lowercase)."""
    return tag.rsplit("}", 1)[-1].lower()


def _parse_lastmod(text: str | None) -> datetime | None:
    """W3C Datetime / ISO8601 lastmod → tz-aware UTC datetime (parse edilemezse None)."""
    if not text or not text.strip():
        return None
    raw = text.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_sitemap(xml_text: str) -> tuple[list[SitemapEntry], bool]:
    """Sitemap XML parse → (entries, is_index).

    is_index=True → entries alt-sitemap'lerdir (<sitemap> child'ları);
    is_index=False → entries makale URL'leridir (<url> child'ları).

    Bozuk/boş/güvensiz XML → ([], False) (fail-safe, exception fırlatmaz).
    """
    if not xml_text or not xml_text.strip():
        return [], False
    if len(xml_text.encode("utf-8", errors="ignore")) > _MAX_SITEMAP_BYTES:
        return [], False
    # DOCTYPE/ENTITY içeren XML'i reddet (XXE / entity-expansion savunması).
    head = xml_text[:2048].lower()
    if "<!doctype" in head or "<!entity" in head:
        return [], False

    try:
        # Güvenlik: DOCTYPE/ENTITY reddi + size guard yukarıda XXE + billion-laughs
        # vektörlerini kapatır; stdlib ElementTree zaten dış-entity resolve etmez.
        root = ET.fromstring(xml_text)  # noqa: S314
    except ET.ParseError:
        return [], False

    is_index = _localname(root.tag) == "sitemapindex"
    child_name = "sitemap" if is_index else "url"

    entries: list[SitemapEntry] = []
    for child in root:
        if _localname(child.tag) != child_name:
            continue
        loc: str | None = None
        lastmod: datetime | None = None
        for el in child:
            ln = _localname(el.tag)
            if ln == "loc" and el.text and el.text.strip():
                loc = el.text.strip()
            elif ln == "lastmod":
                lastmod = _parse_lastmod(el.text)
        if loc:
            entries.append(SitemapEntry(loc=loc, lastmod=lastmod))
    return entries, is_index
