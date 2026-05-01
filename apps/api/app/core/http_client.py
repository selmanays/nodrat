"""NodratBot HTTP client — tüm crawler request'leri buradan geçer.

docs/legal/scraping-policy.md §2 (User-Agent + From + Accept-Language)
docs/legal/opinion-integration.md §3.3
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


# Standart NodratBot User-Agent — tüm scraping request'leri için ZORUNLU
NODRAT_BOT_USER_AGENT = (
    "NodratBot/1.0 (+https://nodrat.com/bot; contact: legal@nodrat.com)"
)

# RFC 7231 — From header (yayıncıya kim olduğumuzu söylüyor)
NODRAT_BOT_FROM = "legal@nodrat.com"

# Türkçe öncelikli içerik fetch edileceği için Accept-Language sabit
NODRAT_BOT_ACCEPT_LANGUAGE = "tr-TR,tr;q=0.9,en;q=0.5"


def get_nodrat_headers() -> dict[str, str]:
    """Tüm crawler HTTP istekleri için zorunlu header set'i.

    Bu fonksiyon TEK noktadan kontrol edilir — UA değişimi tek dosyadan yapılır.
    """
    return {
        "User-Agent": NODRAT_BOT_USER_AGENT,
        "From": NODRAT_BOT_FROM,
        "Accept-Language": NODRAT_BOT_ACCEPT_LANGUAGE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def get_async_client(
    *,
    timeout: float = 15.0,
    follow_redirects: bool = True,
    extra_headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """NodratBot kimliğiyle async httpx client döner.

    Default 15s timeout — RSS feed büyük olabiliyor.
    """
    headers = get_nodrat_headers()
    if extra_headers:
        headers.update(extra_headers)

    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=follow_redirects,
    )


async def fetch_text(
    url: str,
    *,
    timeout: float = 15.0,
    follow_redirects: bool = True,
) -> tuple[int, str, dict[str, Any]]:
    """Idempotent text fetch helper.

    Returns: (status_code, body_text, response_headers)
    """
    async with get_async_client(
        timeout=timeout,
        follow_redirects=follow_redirects,
    ) as client:
        try:
            response = await client.get(url)
            return response.status_code, response.text, dict(response.headers)
        except httpx.RequestError as exc:
            logger.warning("fetch_text failed url=%s err=%s", url, exc)
            return 0, "", {}
