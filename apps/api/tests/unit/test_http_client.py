"""HTTP client header tests — NodratBot kimliği zorunlu.

docs/legal/scraping-policy.md §2
"""

from __future__ import annotations

from app.core.http_client import (
    NODRAT_BOT_FROM,
    NODRAT_BOT_USER_AGENT,
    get_async_client,
    get_nodrat_headers,
)


def test_user_agent_includes_bot_landing_url():
    """UA string /bot landing URL'sini içermeli (transparency)."""
    assert "https://nodrat.com/bot" in NODRAT_BOT_USER_AGENT
    assert "NodratBot" in NODRAT_BOT_USER_AGENT


def test_user_agent_includes_contact_email():
    """UA contact e-posta legal@nodrat.com (yayıncı şikâyetleri için)."""
    assert "legal@nodrat.com" in NODRAT_BOT_USER_AGENT


def test_from_header_is_legal_inbox():
    """From header RFC 7231 — legal@nodrat.com."""
    assert NODRAT_BOT_FROM == "legal@nodrat.com"


def test_get_nodrat_headers_minimum_set():
    """User-Agent + From + Accept-Language ZORUNLU."""
    h = get_nodrat_headers()
    assert "User-Agent" in h
    assert h["User-Agent"] == NODRAT_BOT_USER_AGENT
    assert h["From"] == NODRAT_BOT_FROM
    assert h["Accept-Language"].startswith("tr-TR")


def test_get_nodrat_headers_extra_merge():
    """Caller ek header verirse merge edilir, default'lar override edilmez."""
    h = get_nodrat_headers()
    h_merged = {**h, "X-Custom": "1"}
    assert h_merged["User-Agent"] == NODRAT_BOT_USER_AGENT
    assert h_merged["X-Custom"] == "1"


def test_get_async_client_sets_default_timeout():
    """httpx client default timeout > 0 olmalı."""
    client = get_async_client()
    assert client.timeout.read is not None
    assert client.timeout.read > 0


def test_get_async_client_carries_nodrat_ua():
    """httpx client header'larında NodratBot UA gelmeli."""
    client = get_async_client()
    ua = client.headers.get("user-agent")
    assert ua == NODRAT_BOT_USER_AGENT
