"""Unit — sitemap parser + sitemap-ingestion discovery (#1527)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.modules.sources.tasks import sources as src_tasks
from app.shared.crawl.sitemap import parse_sitemap

URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://x.com/haber/a-1</loc><lastmod>2026-06-15T10:00:00Z</lastmod></url>
  <url><loc>https://x.com/haber/b-2</loc><lastmod>2026-06-10</lastmod></url>
  <url><loc>https://x.com/yazarlar/c</loc></url>
</urlset>"""

INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://x.com/sitemap-20260615.xml</loc></sitemap>
  <sitemap><loc>https://x.com/sitemap-20260601.xml</loc></sitemap>
  <sitemap><loc>https://x.com/authors.xml</loc></sitemap>
</sitemapindex>"""


# ---------------------------------------------------------------- parse_sitemap


def test_parse_urlset() -> None:
    entries, is_index = parse_sitemap(URLSET)
    assert is_index is False
    assert [e.loc for e in entries] == [
        "https://x.com/haber/a-1",
        "https://x.com/haber/b-2",
        "https://x.com/yazarlar/c",
    ]
    assert entries[0].lastmod == datetime(2026, 6, 15, 10, 0, 0, tzinfo=UTC)
    assert entries[1].lastmod == datetime(2026, 6, 10, 0, 0, 0, tzinfo=UTC)  # date-only
    assert entries[2].lastmod is None


def test_parse_index() -> None:
    entries, is_index = parse_sitemap(INDEX)
    assert is_index is True
    assert len(entries) == 3
    assert entries[0].loc.endswith("sitemap-20260615.xml")


def test_parse_malformed_returns_empty() -> None:
    assert parse_sitemap("<urlset><url><loc>kirik") == ([], False)


def test_parse_empty_returns_empty() -> None:
    assert parse_sitemap("") == ([], False)
    assert parse_sitemap("   ") == ([], False)


def test_parse_rejects_doctype_entity() -> None:
    """XXE / billion-laughs savunması — DOCTYPE/ENTITY içeren XML reddedilir."""
    xxe = (
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x "y">]>'
        "<urlset><url><loc>https://x/a</loc></url></urlset>"
    )
    assert parse_sitemap(xxe) == ([], False)


# ---------------------------------------------------- _provisional_title_from_url


def test_provisional_title() -> None:
    # #1640 — sondaki 8-hex makale-id'si (ANKA) başlığa girmemeli.
    assert (
        src_tasks._provisional_title_from_url("https://x.com/haber/ogretmenler-kadikoy-48ca9531")
        == "ogretmenler kadikoy"
    )
    assert (
        src_tasks._provisional_title_from_url(
            "https://www.ankahaber.net/haber/baskani-unluce-den-eskisehirspor-a-ziyaret-d7e7279d"
        )
        == "baskani unluce den eskisehirspor a ziyaret"
    )
    assert (
        src_tasks._provisional_title_from_url("https://t24.com.tr/haber/iyi-yasa,132") == "iyi yasa"
    )
    # Gerçek son-kelime (8-hex değil) kırpılmaz.
    assert (
        src_tasks._provisional_title_from_url("https://x.com/haber/babalar-gunu-etkinligi")
        == "babalar gunu etkinligi"
    )
    assert src_tasks._provisional_title_from_url("https://x.com/") == ""


# ---------------------------------------------------- _discover_from_sitemap


class _FakeDB:
    async def commit(self) -> None:
        return None


class _FakeSrc:
    id = "11111111-1111-1111-1111-111111111111"
    slug = "x"


def _capture_send_task(monkeypatch):
    sent: list = []
    monkeypatch.setattr(
        src_tasks.celery_app,
        "send_task",
        lambda name, args=None, **kw: sent.append((name, args)),
    )
    return sent


@pytest.mark.asyncio
async def test_discover_urlset_filters_and_sorts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_fetch(url, timeout=20.0):
        return 200, URLSET, None

    monkeypatch.setattr(src_tasks, "fetch_text", fake_fetch)
    sent = _capture_send_task(monkeypatch)

    cfg = {"sitemap_url": "https://x.com/sitemap.xml", "url_include": "/haber/", "max_items": 50}
    res = await src_tasks._discover_from_sitemap(_FakeDB(), _FakeSrc(), cfg)

    assert res["mode"] == "sitemap"
    assert res["dispatched"] == 2  # /yazarlar/ filtrelendi
    assert all(name == "tasks.articles.discover" for name, _ in sent)
    links = [args[1]["link"] for _, args in sent]
    assert all("/haber/" in link for link in links)
    assert links[0].endswith("a-1")  # lastmod desc: 06-15 önce
    # her payload non-empty title + link taşır (discover zorunluluğu)
    assert all(args[1]["title"] and args[1]["link"] for _, args in sent)


@pytest.mark.asyncio
async def test_discover_index_picks_latest_dated_subsitemap(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_fetch(url, timeout=20.0):
        if url.endswith("/sitemap.xml"):
            return 200, INDEX, None
        if "20260615" in url:
            return 200, URLSET, None
        return 200, "<urlset></urlset>", None  # eski sub (boş)

    monkeypatch.setattr(src_tasks, "fetch_text", fake_fetch)
    _capture_send_task(monkeypatch)

    cfg = {
        "sitemap_url": "https://x.com/sitemap.xml",
        "subsitemap_pattern": r"sitemap-\d{8}",
        "subsitemap_latest": 1,
        "url_include": "/haber/",
        "max_items": 50,
    }
    res = await src_tasks._discover_from_sitemap(_FakeDB(), _FakeSrc(), cfg)
    assert res["dispatched"] == 2  # en yeni dated sub (20260615) → 2 /haber/


@pytest.mark.asyncio
async def test_discover_max_items_cap(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_fetch(url, timeout=20.0):
        return 200, URLSET, None

    monkeypatch.setattr(src_tasks, "fetch_text", fake_fetch)
    sent = _capture_send_task(monkeypatch)

    cfg = {"sitemap_url": "https://x/s.xml", "url_include": "/haber/", "max_items": 1}
    res = await src_tasks._discover_from_sitemap(_FakeDB(), _FakeSrc(), cfg)
    assert res["dispatched"] == 1
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_discover_sitemap_fetch_fail(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_fetch(url, timeout=20.0):
        return 0, "", None

    monkeypatch.setattr(src_tasks, "fetch_text", fake_fetch)
    _capture_send_task(monkeypatch)

    cfg = {"sitemap_url": "https://x/s.xml"}
    res = await src_tasks._discover_from_sitemap(_FakeDB(), _FakeSrc(), cfg)
    assert res["skipped"] is True
    assert res["reason"].startswith("sitemap_fetch_failed")
