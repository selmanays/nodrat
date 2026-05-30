"""Robots.txt parser + zero-tolerance compliance enforcer.

docs/legal/scraping-policy.md §3.3
docs/legal/opinion-integration.md §6 (zero tolerance)
docs/legal/compliance-brief.md §4 (admin override yok)

Politika:
  - Disallow path → kaynak EKLENMEZ (RobotsDisallowed exception)
  - User-agent öncelik sırası: NodratBot > * > yok
  - Crawl-delay: NodratBot için varsa uygulanır (default: 1.0s)
  - Sitemap path'leri parse edilir
  - Re-check: her crawl öncesi (db'deki robots_txt_check_at güncel tutulur)

Anti-pattern (HARD STOP):
  - Admin override mekanizması YOK — disallow → kategorik red
  - "Test mode bypass" YOK
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from app.shared.http.client import (
    NODRAT_BOT_USER_AGENT,
    fetch_text,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# NodratBot UA token (UA string içinden parse'lar bu token'a bakacak)
NODRAT_BOT_UA_TOKEN = "NodratBot"  # noqa: S105

# Default crawl-delay (saniye) — robots.txt'te yoksa
DEFAULT_CRAWL_DELAY_SEC = 1.0


class RobotsDisallowed(Exception):
    """Disallow ihlali — kaynak ekleme/crawl kategorik olarak reddedilir."""

    def __init__(self, url: str, reason: str = "Disallow rule matched"):
        self.url = url
        self.reason = reason
        super().__init__(f"Robots.txt disallows {url}: {reason}")


class RobotsFetchError(Exception):
    """Robots.txt fetch edilemedi (network/timeout). Caller failsafe karar verir."""


@dataclass
class RobotsReport:
    """Robots.txt fetch + parse sonucu — DB'ye kaydedilir."""

    domain: str
    robots_url: str
    fetched: bool
    """robots.txt indirilebildi mi (404 olabilir, indirilebildi sayılır)"""

    status_code: int = 0
    raw_text: str = ""
    sitemaps: list[str] = field(default_factory=list)
    crawl_delay_sec: float = DEFAULT_CRAWL_DELAY_SEC

    base_url_allowed: bool = True
    """Site kökü (/) NodratBot için izinli mi?"""

    error: str | None = None


def _parse_text(robots_text: str) -> tuple[RobotFileParser, list[str], float | None]:
    """Robots.txt text'ini parse eder, sitemap + crawl-delay'i çıkarır.

    Standart kütüphane RobotFileParser kullanılır + manuel sitemap/crawl-delay extract.
    """
    parser = RobotFileParser()
    parser.parse(robots_text.splitlines())

    sitemaps: list[str] = []
    crawl_delay: float | None = None
    current_ua: str | None = None
    nodrat_ua_active = False
    star_ua_active = False
    nodrat_delay: float | None = None
    star_delay: float | None = None

    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_lower = key.strip().lower()
        value_str = value.strip()

        if key_lower == "user-agent":
            current_ua = value_str.lower()
            nodrat_ua_active = current_ua == NODRAT_BOT_UA_TOKEN.lower()
            star_ua_active = current_ua == "*"
        elif key_lower == "sitemap":
            if value_str:
                sitemaps.append(value_str)
        elif key_lower == "crawl-delay":
            try:
                delay = float(value_str)
            except ValueError:
                continue
            if nodrat_ua_active and nodrat_delay is None:
                nodrat_delay = delay
            elif star_ua_active and star_delay is None:
                star_delay = delay

    # NodratBot için crawl-delay > * > default
    if nodrat_delay is not None:
        crawl_delay = nodrat_delay
    elif star_delay is not None:
        crawl_delay = star_delay

    return parser, sitemaps, crawl_delay


def _domain_root(url: str) -> str:
    """https://x.com/foo → https://x.com"""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"


async def fetch_robots(domain_or_url: str) -> RobotsReport:
    """Domain için robots.txt fetch eder + parse eder.

    Args:
        domain_or_url: 'https://example.com' veya 'https://example.com/foo'

    Returns:
        RobotsReport — fetched=False ise network error (caller failsafe);
                       fetched=True + status 4xx → robots yok kabul edilir (allow all).

    Note:
        Network failure DURUMUNDA kaynak eklenmez (failsafe deny).
        Caller exception yakalamalı veya RobotsReport.fetched kontrolü yapmalı.
    """
    try:
        root = _domain_root(domain_or_url)
    except ValueError as e:
        return RobotsReport(
            domain=domain_or_url,
            robots_url="",
            fetched=False,
            error=str(e),
        )

    robots_url = urljoin(root, "/robots.txt")
    domain = urlparse(root).netloc

    status, body, _headers = await fetch_text(robots_url, timeout=10.0)

    report = RobotsReport(
        domain=domain,
        robots_url=robots_url,
        fetched=status > 0,
        status_code=status,
        raw_text=body,
    )

    if status == 0:
        report.error = "fetch failed (network/timeout)"
        return report

    # 404 / 410 → robots yok demektir, default allow
    if status in (404, 410):
        report.base_url_allowed = True
        return report

    if status >= 500:
        report.error = f"upstream error {status}"
        report.fetched = False  # fail-closed
        return report

    if status >= 400:
        # 401/403 etc: robots dosyası kasıtlı kapalı → fail-closed
        report.error = f"forbidden {status}"
        report.fetched = False
        return report

    parser, sitemaps, crawl_delay = _parse_text(body)
    report.sitemaps = sitemaps
    if crawl_delay is not None:
        report.crawl_delay_sec = max(crawl_delay, DEFAULT_CRAWL_DELAY_SEC)

    # Site kökü NodratBot için izinli mi?
    base_path = urljoin(root, "/")
    can_fetch_nodrat = parser.can_fetch(NODRAT_BOT_USER_AGENT, base_path)
    can_fetch_star = parser.can_fetch("*", base_path)
    # NodratBot UA token bulunmadıysa parser * kuralına düşer; ikisini de check.
    report.base_url_allowed = can_fetch_nodrat and can_fetch_star

    return report


async def can_fetch(url: str) -> tuple[bool, RobotsReport]:
    """URL fetch edilebilir mi? Disallow varsa False.

    Returns:
        (allowed, report) — allowed False ise caller RobotsDisallowed yükseltmeli.
    """
    report = await fetch_robots(url)
    if not report.fetched:
        # Failsafe: robots fetch edilemedi → fetch reddet
        return False, report

    # Robots dosyası 404 → allow
    if report.status_code in (404, 410) or not report.raw_text:
        return True, report

    parser, _sitemaps, _delay = _parse_text(report.raw_text)
    can_nodrat = parser.can_fetch(NODRAT_BOT_USER_AGENT, url)
    can_star = parser.can_fetch("*", url)
    allowed = can_nodrat and can_star
    return allowed, report


async def enforce_or_raise(url: str) -> RobotsReport:
    """URL fetch edilemezse RobotsDisallowed exception yükseltir.

    Source ekleme akışında bu fonksiyon çağrılır. Disallow → admin override YOK.
    """
    allowed, report = await can_fetch(url)
    if not allowed:
        if not report.fetched:
            raise RobotsDisallowed(
                url,
                reason=f"robots.txt fetch failed: {report.error or 'unknown'}",
            )
        raise RobotsDisallowed(url, reason="Disallow rule matched")
    return report
