"""Media downloader unit tests.

Test stratejisi:
  - download_image_url httpx.MockTransport ile mocklanır
  - HEAD pre-check, MIME whitelist, size limit, scheme guard
  - storage helpers (extension_for_mime, build_image_key)
"""

from __future__ import annotations

import hashlib

import httpx
import pytest
from app.core.media import (
    MAX_IMAGE_BYTES,
    DownloadedImage,
    ImageDownloadError,
    ImageRejected,
    _sniff_image_mime,
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
    transport = _mock_transport_for(head_mime="text/html", head_size=200, get_mime="text/html")
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

        # Streaming yanıt: Content-Length YOK → header pre-check atlanır,
        # oversize ancak streaming sırasında yakalanır (#1033 — testin amacı).
        def _stream():
            yield body

        return httpx.Response(200, content=_stream(), headers={"content-type": "image/png"})

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


# ---------------------------------------------------------------------------
# _sniff_image_mime — magic bytes fallback (#427)
# ---------------------------------------------------------------------------


def test_sniff_jpeg():
    assert _sniff_image_mime(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image/jpeg"


def test_sniff_png():
    assert _sniff_image_mime(b"\x89PNG\r\n\x1a\nIHDR") == "image/png"


def test_sniff_gif87a():
    assert _sniff_image_mime(b"GIF87a\x00\x00\x00\x00") == "image/gif"


def test_sniff_gif89a():
    assert _sniff_image_mime(b"GIF89a\x00\x00\x00\x00") == "image/gif"


def test_sniff_webp():
    assert _sniff_image_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"


def test_sniff_avif():
    assert _sniff_image_mime(b"\x00\x00\x00 ftypavif\x00\x00\x00") == "image/avif"


def test_sniff_avis():
    """AV1 image sequence (animated AVIF) brand."""
    assert _sniff_image_mime(b"\x00\x00\x00 ftypavis\x00\x00\x00") == "image/avif"


def test_sniff_too_short():
    assert _sniff_image_mime(b"") is None
    assert _sniff_image_mime(b"abc") is None


def test_sniff_unknown_format():
    """SVG, BMP, PDF, HTML — None döner."""
    assert _sniff_image_mime(b"<svg xmlns") is None
    assert _sniff_image_mime(b"BM\x00\x00\x00\x00") is None
    assert _sniff_image_mime(b"%PDF-1.4") is None
    assert _sniff_image_mime(b"<!DOCTYPE html>") is None


def test_sniff_riff_but_not_webp():
    """RIFF AVI/WAV bezerine match yapma — sadece WEBP brand."""
    assert _sniff_image_mime(b"RIFF\x00\x00\x00\x00AVI LIST") is None
    assert _sniff_image_mime(b"RIFF\x00\x00\x00\x00WAVEfmt ") is None


# ---------------------------------------------------------------------------
# download_image_url — empty Content-Type → magic bytes fallback (#427)
# ---------------------------------------------------------------------------


def _png_bytes() -> bytes:
    """Minimal valid-ish PNG header for sniff success."""
    return b"\x89PNG\r\n\x1a\nIHDR" + b"\x00" * 1016


def _jpeg_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 1014


@pytest.mark.asyncio
async def test_download_empty_content_type_sniffs_jpeg(monkeypatch):
    """WhatsApp/Manifold senaryosu: 200 OK ama Content-Type yok. Bytes JPEG."""
    body = _jpeg_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            # Content-Type olmadan döndür
            return httpx.Response(200, headers={"content-length": str(len(body))})
        return httpx.Response(200, content=body, headers={"content-length": str(len(body))})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )

    result = await download_image_url("https://mmg.example.net/blob")
    assert result.mime_type == "image/jpeg"
    assert result.extension == "jpg"
    assert result.size_bytes == len(body)


@pytest.mark.asyncio
async def test_download_empty_content_type_sniffs_png(monkeypatch):
    body = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": str(len(body))})
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )

    result = await download_image_url("https://cdn.example.com/blob")
    assert result.mime_type == "image/png"
    assert result.extension == "png"


@pytest.mark.asyncio
async def test_download_empty_content_type_unknown_bytes_rejects(monkeypatch):
    """Content-Type yok + bytes herhangi bir whitelist'e match etmiyor → reject."""
    body = b"<!DOCTYPE html><html>not an image</html>" + b" " * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": str(len(body))})
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )

    with pytest.raises(ImageRejected, match="sniff failed"):
        await download_image_url("https://cdn.example.com/blob")


# ---------------------------------------------------------------------------
# download_image_url — 404/410 permanent classification (#427)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_404_at_head_raises_rejected(monkeypatch):
    """HEAD 404 → ImageRejected (permanent). Önceden head_check (None,None)
    döndürüyordu ve GET aşamasında ImageDownloadError oluyordu (transient).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(404)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )

    with pytest.raises(ImageRejected, match="404"):
        await download_image_url("https://example.com/gone.jpg")


@pytest.mark.asyncio
async def test_download_410_at_get_raises_rejected(monkeypatch):
    """HEAD bilinmiyor + GET 410 (Gone) → ImageRejected."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            # HEAD desteklenmiyor (bazı sunucular). 405 → head_check (None,None).
            return httpx.Response(405)
        return httpx.Response(410)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )

    with pytest.raises(ImageRejected, match="410"):
        await download_image_url("https://example.com/gone.jpg")


@pytest.mark.asyncio
async def test_download_503_still_transient(monkeypatch):
    """5xx ImageDownloadError olarak kalmalı (transient, retry edilir)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(503)
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": transport}),
    )

    with pytest.raises(ImageDownloadError, match="HTTP 503"):
        await download_image_url("https://example.com/temp-fail.jpg")
