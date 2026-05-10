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


async def _curl_fallback(
    url: str, timeout: float
) -> tuple[int, str, dict[str, Any]]:
    """#237 — httpx h11 strict parser bazı sunucu config'lerini reddediyor
    (örn. Anadolu Ajansı 'multiple Transfer-Encoding headers'). Curl daha
    lenient — RemoteProtocolError için fallback.
    """
    import asyncio
    import subprocess

    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [
                "curl", "-sL",
                "--max-time", str(int(timeout)),
                "-H", f"User-Agent: {NODRAT_BOT_USER_AGENT}",
                "-H", f"From: {NODRAT_BOT_FROM}",
                "-H", f"Accept-Language: {NODRAT_BOT_ACCEPT_LANGUAGE}",
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "-w", "%{http_code}",
                "-o", "-",
                url,
            ],
            capture_output=True,
            text=False,
            check=False,
        )
    except Exception as exc:
        logger.warning("curl fallback subprocess failed url=%s err=%s", url, exc)
        return 0, "", {}

    if proc.returncode != 0:
        logger.warning(
            "curl fallback exit %d url=%s stderr=%s",
            proc.returncode, url, proc.stderr.decode(errors="replace")[:200],
        )
        return 0, "", {}

    raw = proc.stdout or b""
    # Last 3 chars are the http_code from -w
    if len(raw) < 3:
        return 0, "", {}
    try:
        status_code = int(raw[-3:].decode(errors="replace"))
    except ValueError:
        status_code = 0
    body_bytes = raw[:-3]
    try:
        body_text = body_bytes.decode("utf-8", errors="replace")
    except Exception:
        body_text = ""
    return status_code, body_text, {}


async def fetch_text(
    url: str,
    *,
    timeout: float = 15.0,
    follow_redirects: bool = True,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, str, dict[str, Any]]:
    """Idempotent text fetch helper.

    Args:
        extra_headers: NodratBot default header'larına eklenecek opsiyonel
            header'lar (Conditional GET için If-None-Match / If-Modified-Since
            gibi). Curl fallback path'inde DESTEKLENMEZ — h11 protocol err
            durumunda extra_headers düşer; çağıran 200 OK fallback'i kabul
            etmeli (304 vermeyebilir, full body döner).
    """
    async with get_async_client(
        timeout=timeout,
        follow_redirects=follow_redirects,
        extra_headers=extra_headers,
    ) as client:
        try:
            response = await client.get(url)
            return response.status_code, response.text, dict(response.headers)
        except httpx.RemoteProtocolError as exc:
            # #237 — sunucu strict h11 parsing fail (örn. AA çift TE header)
            logger.warning(
                "fetch_text httpx protocol err, retrying with curl url=%s err=%s",
                url, exc,
            )
            return await _curl_fallback(url, timeout)
        except httpx.RequestError as exc:
            logger.warning("fetch_text failed url=%s err=%s", url, exc)
            return 0, "", {}
