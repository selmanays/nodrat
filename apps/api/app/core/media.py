"""Media (image) downloader.

PRD §1.8 + data-model.md §3.5 + threat-model.md §A06

Akış (download_image_url):
    1. URL canonicalize (cleaning.canonicalize_url ile aynı kurallar)
    2. HEAD check → Content-Length + Content-Type whitelist
    3. GET ile bytes indir (max MAX_IMAGE_BYTES)
    4. SHA-256 hash hesapla
    5. Result döner (caller MinIO upload + DB persist yapar)

Limitler (config'den de override edilebilir):
    MAX_IMAGE_BYTES = 10 MB
    MAX_REDIRECTS  = 5
    TIMEOUT        = 15s

Anti-pattern guard:
    - HEAD alamazsak GET → Content-Length değeri ile yine kontrol
    - data: URI / file:// REDDET (sadece http/https)
    - Content-Type whitelist dışında → reject (image/jpeg, png, webp, avif, gif)
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.core.http_client import get_nodrat_headers
from app.core.storage import ALLOWED_IMAGE_MIME, extension_for_mime

logger = logging.getLogger(__name__)


# Sınırlar
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_REDIRECTS = 5
DOWNLOAD_TIMEOUT = 15.0  # seconds


class ImageDownloadError(Exception):
    """Media download başarısızlığı — caller status='failed' set eder."""


class ImageRejected(Exception):
    """Görsel kabul kriterlerini karşılamıyor (MIME, size, scheme)."""


@dataclass
class DownloadedImage:
    """Inline indirilmiş görsel — caller MinIO put_object yapar."""

    url: str
    """Resolved (redirect sonrası) final URL"""

    data: bytes
    mime_type: str
    extension: str
    size_bytes: int
    sha256_hash: str

    @property
    def is_acceptable(self) -> bool:
        return (
            self.size_bytes > 0
            and self.size_bytes <= MAX_IMAGE_BYTES
            and self.mime_type.lower() in ALLOWED_IMAGE_MIME
        )


def _ensure_safe_scheme(url: str) -> None:
    """Sadece http/https kabul. file:/, data:, ftp:, gopher: → reject."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ImageRejected(f"unsafe scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ImageRejected("invalid url (no host)")


async def head_check(url: str, *, client: httpx.AsyncClient) -> tuple[str | None, int | None]:
    """HEAD ile content-type ve length öğren.

    Returns:
        (mime, size) — biri None olabilir (server header dönmediyse).
    """
    try:
        resp = await client.head(url)
    except httpx.RequestError:
        return None, None

    if resp.status_code >= 400:
        return None, None

    mime_raw = resp.headers.get("content-type") or ""
    size_raw = resp.headers.get("content-length")
    mime = mime_raw.split(";", 1)[0].strip().lower() if mime_raw else None
    try:
        size = int(size_raw) if size_raw else None
    except ValueError:
        size = None
    return mime, size


async def download_image_url(
    url: str,
    *,
    max_bytes: int = MAX_IMAGE_BYTES,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadedImage:
    """Görseli indir, validate et.

    Raises:
        ImageRejected: scheme/MIME/size whitelist ihlali
        ImageDownloadError: network/server hatası
    """
    _ensure_safe_scheme(url)

    headers = get_nodrat_headers()
    headers["Accept"] = (
        "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.5"
    )

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
    ) as client:
        # 1) HEAD pre-check
        head_mime, head_size = await head_check(url, client=client)
        if head_size is not None and head_size > max_bytes:
            raise ImageRejected(f"size pre-check: {head_size} > {max_bytes}")
        if head_mime is not None and extension_for_mime(head_mime) is None:
            raise ImageRejected(f"mime pre-check: {head_mime}")

        # 2) GET (stream — ilk MAX_BYTES'tan fazla okumayız)
        try:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise ImageDownloadError(
                        f"HTTP {resp.status_code} for {url}"
                    )

                # Server'ın gönderdiği son MIME (HEAD'den farklı olabilir)
                final_mime_raw = resp.headers.get("content-type", "") or ""
                final_mime = final_mime_raw.split(";", 1)[0].strip().lower()
                ext = extension_for_mime(final_mime)
                if ext is None:
                    raise ImageRejected(f"mime not allowed: {final_mime}")

                # Final size header
                final_size_header = resp.headers.get("content-length")
                if final_size_header:
                    try:
                        if int(final_size_header) > max_bytes:
                            raise ImageRejected(
                                f"size header: {final_size_header} > {max_bytes}"
                            )
                    except ValueError:
                        pass

                # Stream chunks — limit'i aşarsa kes
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ImageRejected(f"size streaming: > {max_bytes}")
                    chunks.append(chunk)

                final_url = str(resp.url)
        except httpx.RequestError as exc:
            raise ImageDownloadError(f"network error: {exc}") from exc

    data = b"".join(chunks)
    if not data:
        raise ImageDownloadError("empty body")

    sha256 = hashlib.sha256(data).hexdigest()

    return DownloadedImage(
        url=final_url,
        data=data,
        mime_type=final_mime,
        extension=ext,
        size_bytes=len(data),
        sha256_hash=sha256,
    )
