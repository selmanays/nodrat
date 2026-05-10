"""RSS parser unit tests.

Test stratejisi: parse_feed_text saf fonksiyon — fixture string'ler ile test.
fetch_feed network mock'lanır.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.rss import (
    FeedItem,
    fetch_feed,
    parse_feed_text,
)


RSS_BASIC = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <link>https://example.com</link>
  <description>Test description</description>
  <language>tr-TR</language>
  <item>
    <title>İlk haber başlığı</title>
    <link>https://example.com/article-1</link>
    <description>Kısa özet</description>
    <pubDate>Mon, 01 Sep 2025 12:00:00 +0300</pubDate>
    <author>editor@example.com (Editor)</author>
    <enclosure url="https://example.com/img1.jpg" type="image/jpeg" length="12345"/>
  </item>
  <item>
    <title>İkinci haber</title>
    <link>https://example.com/article-2</link>
    <description>Diğer özet</description>
    <pubDate>Mon, 01 Sep 2025 11:00:00 +0300</pubDate>
  </item>
</channel>
</rss>
"""


RSS_NO_AUTHOR = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>NoAuthor</title><link>https://x.com</link><description>D</description>
  <item><title>T1</title><link>https://x.com/1</link></item>
</channel></rss>
"""


RSS_INVALID_ENTRY = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Mixed</title><link>https://x.com</link><description>D</description>
  <item><title>Valid</title><link>https://x.com/1</link></item>
  <item><title>Missing link</title></item>
  <item><link>https://x.com/3</link></item>
</channel></rss>
"""


# ---------------------------------------------------------------------------
# parse_feed_text
# ---------------------------------------------------------------------------


def test_parse_basic_feed():
    report = parse_feed_text(RSS_BASIC, feed_url="https://example.com/feed")
    assert report.fetched is True
    assert report.feed_title == "Test Feed"
    assert report.feed_link == "https://example.com"
    assert report.feed_language == "tr-TR"
    assert report.item_count == 2


def test_parse_basic_first_item_fields():
    report = parse_feed_text(RSS_BASIC)
    item = report.items[0]
    assert item.title == "İlk haber başlığı"
    assert item.link == "https://example.com/article-1"
    assert item.summary.startswith("Kısa özet")
    assert item.author is not None and "editor@example.com" in item.author
    assert isinstance(item.published_at, datetime)
    assert item.published_at.tzinfo is timezone.utc
    # 2025-09-01 12:00 +0300 → 09:00 UTC
    assert item.published_at.hour == 9


def test_parse_enclosure_image_url():
    report = parse_feed_text(RSS_BASIC)
    assert report.items[0].image_url == "https://example.com/img1.jpg"


def test_parse_no_author_returns_none():
    report = parse_feed_text(RSS_NO_AUTHOR)
    assert report.items[0].author is None


def test_parse_skips_invalid_entries():
    """Title yok veya link yok → skip."""
    report = parse_feed_text(RSS_INVALID_ENTRY)
    assert report.item_count == 1
    assert report.items[0].title == "Valid"


def test_parse_summary_truncated():
    """Summary 1000 karakterden uzunsa kesilir."""
    long = "x" * 5000
    rss = f"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>L</title><link>https://x.com</link><description>D</description>
  <item><title>T</title><link>https://x.com/1</link><description>{long}</description></item>
</channel></rss>"""
    report = parse_feed_text(rss)
    assert len(report.items[0].summary) <= 1000


def test_parse_atom_feed():
    """Atom feed de feedparser ile parse edilebilmeli."""
    atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Test</title>
  <link href="https://x.com"/>
  <id>https://x.com</id>
  <updated>2025-09-01T12:00:00Z</updated>
  <entry>
    <title>Atom item</title>
    <link href="https://x.com/a1"/>
    <id>tag:x.com,2025:1</id>
    <updated>2025-09-01T12:00:00Z</updated>
    <summary>Short</summary>
  </entry>
</feed>
"""
    report = parse_feed_text(atom)
    assert report.feed_title == "Atom Test"
    assert report.item_count == 1
    assert report.items[0].title == "Atom item"


# ---------------------------------------------------------------------------
# fetch_feed (mocked HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_feed_success():
    with patch(
        "app.core.rss.fetch_text",
        new=AsyncMock(return_value=(200, RSS_BASIC, {})),
    ):
        report = await fetch_feed("https://example.com/feed")
    assert report.fetched is True
    assert report.status_code == 200
    assert report.item_count == 2


@pytest.mark.asyncio
async def test_fetch_feed_network_error():
    with patch(
        "app.core.rss.fetch_text",
        new=AsyncMock(return_value=(0, "", {})),
    ):
        report = await fetch_feed("https://example.com/feed")
    assert report.fetched is False
    assert report.error is not None
    assert "fetch failed" in report.error


@pytest.mark.asyncio
async def test_fetch_feed_4xx():
    with patch(
        "app.core.rss.fetch_text",
        new=AsyncMock(return_value=(404, "Not Found", {})),
    ):
        report = await fetch_feed("https://example.com/feed")
    assert report.fetched is False
    assert report.status_code == 404
    assert "HTTP 404" in (report.error or "")


@pytest.mark.asyncio
async def test_fetch_feed_empty_body():
    with patch(
        "app.core.rss.fetch_text",
        new=AsyncMock(return_value=(200, "", {})),
    ):
        report = await fetch_feed("https://example.com/feed")
    assert report.fetched is False
    assert "empty" in (report.error or "")


def test_feed_item_dataclass_defaults():
    """FeedItem default değerler."""
    item = FeedItem(title="T", link="https://x.com")
    assert item.summary == ""
    assert item.author is None
    assert item.published_at is None
    assert item.image_url is None


# ---------------------------------------------------------------------------
# Conditional GET (#565) — ETag / If-Modified-Since
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_feed_304_not_modified_early_return():
    """304 dönerse `not_modified=True`, items boş, body parse edilmez."""
    mock = AsyncMock(return_value=(304, "", {}))
    with patch("app.core.rss.fetch_text", new=mock):
        report = await fetch_feed(
            "https://example.com/feed",
            etag='W/"abc123"',
            last_modified="Mon, 01 Sep 2025 09:00:00 GMT",
        )
    assert report.fetched is True
    assert report.status_code == 304
    assert report.not_modified is True
    assert report.item_count == 0
    assert report.error is None


@pytest.mark.asyncio
async def test_fetch_feed_sends_conditional_get_headers():
    """etag / last_modified verilirse If-None-Match + If-Modified-Since gider."""
    mock = AsyncMock(return_value=(304, "", {}))
    with patch("app.core.rss.fetch_text", new=mock):
        await fetch_feed(
            "https://example.com/feed",
            etag='W/"abc123"',
            last_modified="Mon, 01 Sep 2025 09:00:00 GMT",
        )
    # mock'u inceleyerek extra_headers'ı doğrula
    call_kwargs = mock.call_args.kwargs
    extra_headers = call_kwargs.get("extra_headers")
    assert extra_headers is not None
    assert extra_headers["If-None-Match"] == 'W/"abc123"'
    assert extra_headers["If-Modified-Since"] == "Mon, 01 Sep 2025 09:00:00 GMT"


@pytest.mark.asyncio
async def test_fetch_feed_no_conditional_when_no_etag():
    """etag/last_modified yoksa extra_headers None gider (no overhead)."""
    mock = AsyncMock(return_value=(200, RSS_BASIC, {}))
    with patch("app.core.rss.fetch_text", new=mock):
        await fetch_feed("https://example.com/feed")
    call_kwargs = mock.call_args.kwargs
    assert call_kwargs.get("extra_headers") is None


@pytest.mark.asyncio
async def test_fetch_feed_200_captures_etag_and_last_modified():
    """200 OK + response header'ları → FeedReport.etag + last_modified dolu."""
    response_headers = {
        "etag": 'W/"new-etag-456"',
        "last-modified": "Tue, 02 Sep 2025 10:00:00 GMT",
        "content-type": "application/rss+xml",
    }
    with patch(
        "app.core.rss.fetch_text",
        new=AsyncMock(return_value=(200, RSS_BASIC, response_headers)),
    ):
        report = await fetch_feed("https://example.com/feed")
    assert report.fetched is True
    assert report.not_modified is False
    assert report.etag == 'W/"new-etag-456"'
    assert report.last_modified == "Tue, 02 Sep 2025 10:00:00 GMT"


@pytest.mark.asyncio
async def test_fetch_feed_200_capitalized_etag_header():
    """Response header case-sensitivity edge — bazı sunucular `ETag` döner."""
    response_headers = {
        "ETag": 'W/"capital-case"',
        "Last-Modified": "Tue, 02 Sep 2025 10:00:00 GMT",
    }
    with patch(
        "app.core.rss.fetch_text",
        new=AsyncMock(return_value=(200, RSS_BASIC, response_headers)),
    ):
        report = await fetch_feed("https://example.com/feed")
    assert report.etag == 'W/"capital-case"'
    assert report.last_modified == "Tue, 02 Sep 2025 10:00:00 GMT"


@pytest.mark.asyncio
async def test_fetch_feed_200_no_etag_headers():
    """Sunucu ETag/Last-Modified göndermezse FeedReport.etag = None (no error)."""
    with patch(
        "app.core.rss.fetch_text",
        new=AsyncMock(return_value=(200, RSS_BASIC, {"content-type": "x"})),
    ):
        report = await fetch_feed("https://example.com/feed")
    assert report.fetched is True
    assert report.etag is None
    assert report.last_modified is None
