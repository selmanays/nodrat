"""Robots.txt parser unit tests — zero-tolerance compliance.

Testler:
  - Disallow / → REDDET
  - Disallow /private → /private REDDET, / izinli
  - User-agent: NodratBot disallow > User-agent: *
  - Crawl-delay parse
  - Sitemap parse
  - 404 → allow all
  - 5xx / network error → fail-closed (deny)
  - Admin override yok (RobotsDisallowed kategorik)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.core.robots import (
    DEFAULT_CRAWL_DELAY_SEC,
    NODRAT_BOT_UA_TOKEN,
    RobotsDisallowed,
    _parse_text,
    can_fetch,
    enforce_or_raise,
    fetch_robots,
)

# ---------------------------------------------------------------------------
# _parse_text — pure parser
# ---------------------------------------------------------------------------


def test_parse_disallow_root():
    """Disallow / → ne NodratBot ne de * fetch yapabilir."""
    text = "User-agent: *\nDisallow: /\n"
    parser, sitemaps, delay = _parse_text(text)
    assert sitemaps == []
    assert delay is None
    assert not parser.can_fetch("NodratBot", "https://x.com/")
    assert not parser.can_fetch("*", "https://x.com/")


def test_parse_disallow_private_only():
    """Disallow /private → /private kapalı, /public izinli."""
    text = "User-agent: *\nDisallow: /private\n"
    parser, _, _ = _parse_text(text)
    assert not parser.can_fetch("NodratBot", "https://x.com/private/foo")
    assert parser.can_fetch("NodratBot", "https://x.com/public")


def test_parse_nodrat_specific_disallow():
    """User-agent: NodratBot için özel kural — * kuralından öncelikli."""
    text = (
        "User-agent: *\nAllow: /\n\n"
        f"User-agent: {NODRAT_BOT_UA_TOKEN}\nDisallow: /\n"
    )
    parser, _, _ = _parse_text(text)
    assert not parser.can_fetch(NODRAT_BOT_UA_TOKEN, "https://x.com/")


def test_parse_crawl_delay_nodrat_priority():
    """NodratBot crawl-delay'i * kuralından önceliklidir."""
    text = (
        "User-agent: *\nCrawl-delay: 10\n\n"
        f"User-agent: {NODRAT_BOT_UA_TOKEN}\nCrawl-delay: 3\n"
    )
    _parser, _sitemaps, delay = _parse_text(text)
    assert delay == 3.0


def test_parse_crawl_delay_star_fallback():
    """NodratBot kuralı yoksa * kuralı uygulanır."""
    text = "User-agent: *\nCrawl-delay: 5\n"
    _parser, _sitemaps, delay = _parse_text(text)
    assert delay == 5.0


def test_parse_sitemap():
    """Sitemap satırları parse edilir."""
    text = (
        "Sitemap: https://x.com/sitemap.xml\n"
        "Sitemap: https://x.com/news-sitemap.xml\n"
        "User-agent: *\nAllow: /\n"
    )
    _parser, sitemaps, _delay = _parse_text(text)
    assert len(sitemaps) == 2
    assert "https://x.com/sitemap.xml" in sitemaps


def test_parse_comment_stripping():
    """# yorum satırları parse'i bozmaz."""
    text = (
        "# Welcome\nUser-agent: *  # all bots\n"
        "Disallow: /admin  # admin panel\n"
    )
    parser, _, _ = _parse_text(text)
    assert not parser.can_fetch("*", "https://x.com/admin/login")
    assert parser.can_fetch("*", "https://x.com/")


# ---------------------------------------------------------------------------
# fetch_robots — async network
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_robots_404_allows():
    """robots.txt 404 → allow all kabul edilir."""
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(404, "", {}))):
        report = await fetch_robots("https://x.com")
    assert report.fetched is True
    assert report.base_url_allowed is True
    assert report.status_code == 404


@pytest.mark.asyncio
async def test_fetch_robots_network_error_failsafe():
    """Network error → fetched=False (caller fail-closed davranmalı)."""
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(0, "", {}))):
        report = await fetch_robots("https://x.com")
    assert report.fetched is False
    assert "fetch failed" in (report.error or "")


@pytest.mark.asyncio
async def test_fetch_robots_5xx_failsafe():
    """5xx upstream → fail-closed (kaynak eklenemez)."""
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(503, "", {}))):
        report = await fetch_robots("https://x.com")
    assert report.fetched is False


@pytest.mark.asyncio
async def test_fetch_robots_403_failsafe():
    """403 → robots kasıtlı kapalı, fail-closed."""
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(403, "", {}))):
        report = await fetch_robots("https://x.com")
    assert report.fetched is False


@pytest.mark.asyncio
async def test_fetch_robots_disallow_root_blocks():
    """Disallow / → base_url_allowed=False."""
    body = "User-agent: *\nDisallow: /\n"
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(200, body, {}))):
        report = await fetch_robots("https://x.com")
    assert report.fetched is True
    assert report.base_url_allowed is False


@pytest.mark.asyncio
async def test_fetch_robots_default_crawl_delay():
    """robots.txt'te crawl-delay yoksa default uygulanır."""
    body = "User-agent: *\nAllow: /\n"
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(200, body, {}))):
        report = await fetch_robots("https://x.com")
    assert report.crawl_delay_sec == DEFAULT_CRAWL_DELAY_SEC


# ---------------------------------------------------------------------------
# enforce_or_raise — admin override YOK
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_disallow_raises():
    """Disallow path → RobotsDisallowed kategorik exception."""
    body = "User-agent: *\nDisallow: /\n"
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(200, body, {}))):
        with pytest.raises(RobotsDisallowed):
            await enforce_or_raise("https://x.com/foo")


@pytest.mark.asyncio
async def test_enforce_network_error_raises():
    """Network error → RobotsDisallowed (fail-closed)."""
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(0, "", {}))):
        with pytest.raises(RobotsDisallowed):
            await enforce_or_raise("https://x.com")


@pytest.mark.asyncio
async def test_enforce_404_allows_returns_report():
    """robots.txt yoksa allow + report döner."""
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(404, "", {}))):
        report = await enforce_or_raise("https://x.com")
    assert report.base_url_allowed is True


@pytest.mark.asyncio
async def test_enforce_specific_path_allowed():
    """Disallow /admin ama / için izin → /article/123 izinli."""
    body = "User-agent: *\nDisallow: /admin\n"
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(200, body, {}))):
        report = await enforce_or_raise("https://x.com/article/123")
    assert report.base_url_allowed is True


@pytest.mark.asyncio
async def test_can_fetch_admin_override_unavailable():
    """Disallow var olduğunda 'admin override' parametresi YOK — sadece (allowed,report) döner."""
    body = "User-agent: *\nDisallow: /\n"
    with patch("app.core.robots.fetch_text", new=AsyncMock(return_value=(200, body, {}))):
        allowed, report = await can_fetch("https://x.com/page")
    assert allowed is False
    assert report.fetched is True


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_robots_invalid_url():
    """Geçersiz URL → fetched=False + error mesajı."""
    report = await fetch_robots("not-a-url")
    assert report.fetched is False
    assert "Invalid URL" in (report.error or "")
