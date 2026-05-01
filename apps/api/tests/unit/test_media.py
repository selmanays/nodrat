"""Media downloader unit tests.

Test stratejisi:
  - download_image_url httpx.MockTransport ile mocklanır
  - HEAD pre-check, MIME whitelist, size limit, scheme guard
  - storage helpers (extension_for_mime, build_image_key)
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.media import (
    DOWNLOAD_TIMEOUT,
    MAX_IMAGE_BYTES,
    DownloadedImage,
    ImageDownloadError,
    ImageRejected,
    download_image_url,
)
from app.core.storage import (
    ALLOWED_IMAGE_MIME,
    build_image_key,
    extension_for_mime,
)


# ---------------------------------------------------------------------------
# storage helpers
# ---------------------------------------------------------------------------


def test_extension_for_mime_jpeg():
    assert extension_for_mime("image/jpeg") == "jpg"
    assert extension_for_mime("image/JPEG") == "jpg"
    assert extension_for_mime("image/jpeg; charset=utf-8") == "jpg"


def test_extension_for_mime_webp_avif():
    assert extension_for_mime("image/webp") == "webp"
    assert extension_for_mime("image/avif") == "avif"


def test_extension_for_mime_unknown_returns_none():
    assert extension_for_mime("image/svg+xml") is None
    assert extension_for_mime("image/bmp") is None
    assert extension_for_mime("application/pdf") is None
    assert extension_for_mime("text/html") is None


def test_extension_for_mime_empty():
    assert extension_for_mime("") is None


def test_build_image_key_format():
    key = build_image_key(
        source_slug="evrensel",
        image_id="abc123",
        extension="jpg",
        year=2026,
        month=5,
        day=1,
    )
    assert key == "images/evrensel/2026/05/01/abc123.jpg"


def test_build_image_key_normalizes():
    """Slug büyükharfse + ext'te leading dot varsa düzeltilir."""
    key = build_image_key(
        source_slug="My/Slug",
        image_id="x",
        extension=".PNG",
        year=2026,
        month=5,
        day=1,
    )
    assert key == "images/my-slug/2026/05/01/x.png"


def test_allowed_image_mime_set():
    """Whitelist beklediğimiz MIME'leri kapsamalı."""
    expected = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/avif",
        "image/gif",
    }
    assert set(ALLOWED_IMAGE_MIME.keys()) == expected


# ---------------------------------------------------------------------------
# download_image_url — scheme guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_rejects_data_uri():
    with pytest.raises(ImageRejected, match="unsafe scheme"):
        await download_image_url("data:image/png;base64,iVBORw0KGgo")


@pytest.mark.asyncio
async def test_download_rejects_file_uri():
    with pytest.raises(ImageRejected, match="unsafe scheme"):
        await download_image_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_download_rejects_ftp():
    with pytest.raises(ImageRejected, match="unsafe scheme"):
        await download_image_url("ftp://example.com/image.jpg")


@pytest.mark.asyncio
async def test_download_rejects_no_host():
    with pytest.raises(ImageRejected):
        await download_image_url("https:///image.jpg")


# ---------------------------------------------------------------------------
# download_image_url — full path with mocked HTTPX transport
# ---------------------------------------------------------------------------


def _make_image_bytes(size: int = 1024) -> bytes:
    """Dummy image bytes (PNG header + padding)."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * (size - 8)


def _mock_transport_for(
    *,
    head_status: int = 200,
    head_mime: str = "image/png",
    head_size: int | None = 1024,
    get_status: int = 200,
    get_mime: str = "image/png",
    body: bytes | None = None,
) -> httpx.MockTransport:
    """httpx MockTransport — HEAD + GET response'ları script'le."""
    body_bytes = body if body is not None else _make_image_bytes(1024)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            headers: dict[str, str] = {"content-type": head_mime}
            if head_size is not None:
                headers["content-length"] = str(head_size)
            return httpx.Response(head_status, headers=headers)
        # GET
        get_headers = {
            "content-type": get_mime,
            "content-length": str(len(body_bytes)),
        }
        return httpx.Response(get_status, content=body_bytes, headers=get_headers)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_download_success_png(monkeypatch):
    body = _make_image_bytes(2048)
    transport = _mock_transport_for(
        head_mime="image/png", head_size=len(body), get_mime="image/png", body=body
    )

    # download_image_url AsyncClient'ı yeniden inşa ediyor; MockTransport patch'leyelim.
    original_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    result = await download_image_url("https://example.com/img.png")
    assert isinstance(result, DownloadedImage)
    assert result.mime_type == "image/png"
    assert result.extension == "png"
    assert result.size_bytes == len(body)
    assert result.sha256_hash == hashlib.sha256(body).hexdigest()
    assert result.is_acceptable


@pytest.mark.asyncio
async def test_download_rejects_html_mime(monkeypatch):
    """Server yanlışlıkla HTML döndürürse reddet."""
    transport = _mock_transport_for(
        head_mime="text/html", head_size=200, get_mime="text/html"
    )
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )

    with pytest.raises(ImageRejected, match="mime"):
        await download_image_url("https://example.com/page.html")


@pytest.mark.asyncio
async def test_download_rejects_oversize_pre_check(monkeypatch):
    """HEAD'de Content-Length > 10MB → reject."""
    transport = _mock_transport_for(
        head_mime="image/png",
        head_size=MAX_IMAGE_BYTES + 1,
        get_mime="image/png",
        body=_make_image_bytes(1024),
    )
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )

    with pytest.raises(ImageRejected, match="size"):
        await download_image_url("https://example.com/big.png")


@pytest.mark.asyncio
async def test_download_503_raises_download_error(monkeypatch):
    transport = _mock_transport_for(
        head_status=503, head_mime="image/png", head_size=None, get_status=503
    )
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )
    with pytest.raises(ImageDownloadError, match="HTTP 503"):
        await download_image_url("https://example.com/img.png")


@pytest.mark.asyncio
async def test_download_streaming_oversize_caught(monkeypatch):
    """Server Content-Length yalanlasa bile streaming sırasında kesilir."""
    body = _make_image_bytes(MAX_IMAGE_BYTES + 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            # HEAD'de küçük göster, GET'te aşırı dön
            return httpx.Response(
                200, headers={"content-type": "image/png", "content-length": "1024"}
            )
        return httpx.Response(
            200, content=body, headers={"content-type": "image/png"}
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )
    with pytest.raises(ImageRejected, match="streaming"):
        await download_image_url("https://example.com/lying.png")


# ---------------------------------------------------------------------------
# DownloadedImage.is_acceptable
# ---------------------------------------------------------------------------


def test_downloaded_image_acceptable_jpeg():
    img = DownloadedImage(
        url="https://x.com/a.jpg",
        data=b"x",
        mime_type="image/jpeg",
        extension="jpg",
        size_bytes=1024,
        sha256_hash="abc",
    )
    assert img.is_acceptable


def test_downloaded_image_unacceptable_zero_size():
    img = DownloadedImage(
        url="https://x.com/a.jpg",
        data=b"",
        mime_type="image/jpeg",
        extension="jpg",
        size_bytes=0,
        sha256_hash="abc",
    )
    assert not img.is_acceptable


def test_downloaded_image_unacceptable_oversize():
    img = DownloadedImage(
        url="https://x.com/a.jpg",
        data=b"x",
        mime_type="image/jpeg",
        extension="jpg",
        size_bytes=MAX_IMAGE_BYTES + 1,
        sha256_hash="abc",
    )
    assert not img.is_acceptable
