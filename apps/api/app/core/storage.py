"""MinIO/S3 object storage helper.

docs/engineering/architecture.md §2 (storage)
docs/engineering/threat-model.md §A06 (file upload validation)

Konvansiyon (PRD §1.8 + data-model.md §3.5):
    bucket: settings.minio_bucket_images
    key:    images/{source_slug}/{yyyy}/{mm}/{dd}/{image_id}.{ext}

Bu modül senkron — Celery worker context'inde çağrılır. API tarafından
async context'te çağrılırsa run_in_executor ile sarın.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)


# MIME → extension mapping (whitelist)
ALLOWED_IMAGE_MIME = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/gif": "gif",
}

DEFAULT_REGION = "us-east-1"


@dataclass
class UploadResult:
    """MinIO put_object sonucu."""

    bucket: str
    key: str
    storage_url: str
    """s3://bucket/key — DB'de tutulur, presigned URL Faz 2'de generate edilir."""


def get_s3_client() -> boto3.client:
    """boto3 S3 client (MinIO endpoint).

    Path-style addressing (MinIO subdomain virtual-hosting'i desteklemez).
    """
    settings = get_settings()
    endpoint_scheme = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{endpoint_scheme}://{settings.minio_endpoint}"

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_root_user,
        aws_secret_access_key=settings.minio_root_password.get_secret_value(),
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
        region_name=DEFAULT_REGION,
    )


def get_cold_storage_client() -> boto3.client:
    """boto3 S3 client (Contabo Object Storage — cold tier, #219 MVP-1.5 PR-4).

    Konfig: S3_ENDPOINT_URL + S3_REGION + S3_ACCESS_KEY_ID + S3_SECRET_ACCESS_KEY
    Bucket: settings.s3_bucket (örn: nodrat-prod)

    Hot tier (MinIO) ↔ Cold tier (Contabo OS) farklı:
        - MinIO: lokal volume, hızlı, sınırlı disk (250 GB VPS NVMe)
        - Contabo OS: uzak, S3-compatible, geniş (250 GB OS), egress 32 TB dahil

    PR-4 cold tier task 30+ gün eski raw_html'leri MinIO'dan Contabo'ya taşır.
    """
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=str(settings.s3_endpoint_url),
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name=settings.s3_region,
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def ensure_bucket(bucket_name: str) -> bool:
    """Bucket yoksa oluştur. Idempotent.

    Returns True if created or already exists, False on error.
    """
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=bucket_name)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket", "NotFound"):
            try:
                client.create_bucket(Bucket=bucket_name)
                return True
            except (ClientError, BotoCoreError) as inner:
                logger.error("bucket create failed name=%s err=%s", bucket_name, inner)
                return False
        logger.warning("head_bucket failed name=%s code=%s", bucket_name, code)
        return False


def upload_bytes(
    *,
    bucket: str,
    key: str,
    data: bytes,
    content_type: str,
    metadata: dict[str, str] | None = None,
) -> UploadResult:
    """Bytes → MinIO put_object.

    Caller bucket'ı ensure_bucket ile garantilemiş olmalı (cold-start cost).
    """
    client = get_s3_client()
    extra: dict[str, object] = {"ContentType": content_type}
    if metadata:
        extra["Metadata"] = metadata

    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=io.BytesIO(data),
        **extra,
    )

    return UploadResult(
        bucket=bucket,
        key=key,
        storage_url=f"s3://{bucket}/{key}",
    )


def build_image_key(
    *, source_slug: str, image_id: str, extension: str, year: int, month: int, day: int
) -> str:
    """Standart image key path."""
    safe_slug = source_slug.lower().replace("/", "-")
    safe_ext = extension.lower().lstrip(".")
    return f"images/{safe_slug}/{year:04d}/{month:02d}/{day:02d}/{image_id}.{safe_ext}"


def extension_for_mime(mime: str) -> str | None:
    """Whitelist MIME → uzantı. None ise reject."""
    return ALLOWED_IMAGE_MIME.get(mime.lower().split(";", 1)[0].strip())
