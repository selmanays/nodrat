"""RSS feed parser — feedparser tabanlı, NodratBot UA ile fetch.

docs/engineering/api-contracts.md §4.1 (admin sources)
docs/engineering/architecture.md §3 (source pipeline)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import feedparser

from app.core.http_client import fetch_text

logger = logging.getLogger(__name__)


@dataclass
class FeedItem:
    """RSS feed entry — discover akışında article'lara dönüşür."""

    title: str
    link: str
    summary: str = ""
    author: str | None = None
    published_at: datetime | None = None
    image_url: str | None = None
    """Enclosure / media:content / og:image — RSS'te varsa."""

    raw_id: str | None = None


@dataclass
class FeedReport:
    """Feed parse sonucu — admin UI'da test ekranında gösterilir."""

    feed_url: str
    fetched: bool
    status_code: int = 0
    error: str | None = None

    feed_title: str = ""
    feed_description: str = ""
    feed_language: str | None = None
    feed_link: str | None = None

    items: list[FeedItem] = field(default_factory=list)

    bozo: bool = False
    """feedparser malformed feed bayrağı."""

    not_modified: bool = False
    """HTTP 304 Not Modified — Conditional GET hit. items boş gelir, çağıran
    discover dispatch yapmamalı (#565)."""

    etag: str | None = None
    """200 yanıtında sunucudan gelen ETag header — Source.etag'a persist edilir."""

    last_modified: str | None = None
    """200 yanıtında sunucudan gelen Last-Modified header — Source.last_modified'a
    persist edilir."""

    @property
    def item_count(self) -> int:
        return len(self.items)


def _to_datetime(time_struct: object) -> datetime | None:
    """feedparser'ın struct_time çıktısını UTC datetime'a dönüştür."""
    if not time_struct or not hasattr(time_struct, "tm_year"):
        return None
    try:
        return datetime(
            time_struct.tm_year,  # type: ignore[attr-defined]
            time_struct.tm_mon,  # type: ignore[attr-defined]
            time_struct.tm_mday,  # type: ignore[attr-defined]
            time_struct.tm_hour,  # type: ignore[attr-defined]
            time_struct.tm_min,  # type: ignore[attr-defined]
            time_struct.tm_sec,  # type: ignore[attr-defined]
            tzinfo=timezone.utc,
        )
    except (ValueError, AttributeError):
        return None


def _extract_image_url(entry: dict) -> str | None:
    """RSS entry'sinden ana görsel URL'sini bul (enclosure / media:content)."""
    # 1) media:content (Yahoo Media RSS)
    media_content = entry.get("media_content") or []
    for media in media_content:
        if isinstance(media, dict) and media.get("url"):
            return media["url"]

    # 2) media:thumbnail
    media_thumbs = entry.get("media_thumbnail") or []
    for thumb in media_thumbs:
        if isinstance(thumb, dict) and thumb.get("url"):
            return thumb["url"]

    # 3) enclosure (RSS 2.0)
    enclosures = entry.get("enclosures") or []
    for enc in enclosures:
        if isinstance(enc, dict):
            url = enc.get("href") or enc.get("url")
            mime = enc.get("type", "")
            if url and (not mime or mime.startswith("image/")):
                return url

    return None


def parse_feed_text(feed_text: str, *, feed_url: str = "") -> FeedReport:
    """Feed body text'ini parse eder. Network çağrısı yapmaz.

    Test edilebilir saf fonksiyon — fetch_feed onu wrap eder.
    """
    parsed = feedparser.parse(feed_text)
    report = FeedReport(
        feed_url=feed_url,
        fetched=True,
        status_code=200,
        bozo=bool(parsed.bozo),
    )

    feed = parsed.feed or {}
    report.feed_title = (feed.get("title") or "").strip()
    report.feed_description = (feed.get("description") or feed.get("subtitle") or "").strip()
    report.feed_language = feed.get("language")
    report.feed_link = feed.get("link")

    for entry in parsed.entries or []:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue

        published = _to_datetime(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )
        author = entry.get("author")
        if isinstance(author, str):
            author = author.strip() or None

        item = FeedItem(
            title=title,
            link=link,
            summary=(entry.get("summary") or "").strip()[:1000],  # truncate
            author=author,
            published_at=published,
            image_url=_extract_image_url(entry),
            raw_id=entry.get("id"),
        )
        report.items.append(item)

    return report


async def fetch_feed(
    feed_url: str,
    *,
    timeout: float = 15.0,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FeedReport:
    """Feed URL'sini NodratBot UA ile fetch + parse eder.

    Conditional GET (#565): etag veya last_modified verilirse If-None-Match /
    If-Modified-Since header'ları gönderilir; sunucu 304 dönerse
    `not_modified=True` ile early return. 200 dönerse response header'larından
    yeni ETag/Last-Modified yakalanır ve `FeedReport.etag` / `last_modified`
    alanlarına yazılır (çağıran Source row'una persist eder).

    Args:
        feed_url: RSS / Atom feed URL'si
        timeout: HTTP timeout
        etag: Önceki fetch'ten kaydedilen ETag (varsa) — If-None-Match için
        last_modified: Önceki fetch'ten kaydedilen Last-Modified (varsa) —
            If-Modified-Since için

    Returns:
        FeedReport — `not_modified=True` ise items boş, çağıran dispatch
        yapmamalı; `fetched=False` ise network/HTTP hatası.
    """
    extra_headers: dict[str, str] = {}
    if etag:
        extra_headers["If-None-Match"] = etag
    if last_modified:
        extra_headers["If-Modified-Since"] = last_modified

    status, body, headers = await fetch_text(
        feed_url,
        timeout=timeout,
        extra_headers=extra_headers or None,
    )

    if status == 0:
        return FeedReport(
            feed_url=feed_url,
            fetched=False,
            status_code=0,
            error="fetch failed (network/timeout)",
        )

    # 304 Not Modified — Conditional GET hit, body yok (#565)
    if status == 304:
        return FeedReport(
            feed_url=feed_url,
            fetched=True,
            status_code=304,
            not_modified=True,
        )

    if status >= 400:
        return FeedReport(
            feed_url=feed_url,
            fetched=False,
            status_code=status,
            error=f"HTTP {status}",
        )
    if not body or not body.strip():
        return FeedReport(
            feed_url=feed_url,
            fetched=False,
            status_code=status,
            error="empty body",
        )

    report = parse_feed_text(body, feed_url=feed_url)
    report.status_code = status

    # Sunucu yeni ETag/Last-Modified verdiyse yakala (Source row'una persist
    # edilecek). httpx.Response.headers case-insensitive ama dict() sonrası
    # key'ler lowercase olabiliyor; her iki durumu da ele al.
    if headers:
        report.etag = headers.get("etag") or headers.get("ETag")
        report.last_modified = headers.get("last-modified") or headers.get(
            "Last-Modified"
        )

    return report
