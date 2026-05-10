"""Admin /system endpoints — sistem durumu (observability) #358 MVP-1.6 B1.

Endpoint:
    GET /admin/system/health   — VPS + Postgres + MinIO + Contabo OS + containers + backups

Auth: require_admin
Cache: 60s in-memory (boto3 list_objects_v2 binlerce object pahalı)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Annotated, Any

import psutil
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.config import get_settings
from app.core.db import get_db
from app.core.storage import get_cold_storage_client, get_s3_client
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/system", tags=["admin-system"])


_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_TTL_SECONDS = 60.0


# ============================================================================
# Pydantic models
# ============================================================================


class CpuInfo(BaseModel):
    cores: int
    load_1m: float
    load_5m: float
    load_15m: float
    usage_pct: float


class RamInfo(BaseModel):
    total_mb: int
    used_mb: int
    free_mb: int
    used_pct: float


class DiskInfo(BaseModel):
    total_gb: float
    used_gb: float
    free_gb: float
    used_pct: float


class VpsInfo(BaseModel):
    hostname: str
    cpu: CpuInfo
    ram: RamInfo
    disk: DiskInfo


class TableSize(BaseModel):
    name: str
    size_mb: float
    row_count: int
    index_size_mb: float


class PostgresInfo(BaseModel):
    db_size_gb: float
    tables: list[TableSize]


class BucketInfo(BaseModel):
    name: str
    size_gb: float
    object_count: int


class MinioInfo(BaseModel):
    endpoint: str
    buckets: list[BucketInfo]


class ContaboInfo(BaseModel):
    endpoint: str
    bucket: str
    size_gb: float
    object_count: int
    by_prefix: dict[str, BucketInfo]


class BackupInfo(BaseModel):
    last_snapshot_at: str | None
    last_snapshot_age_h: float | None
    snapshot_count: int
    total_size_gb: float
    last_check_status: str


class SystemHealthResponse(BaseModel):
    vps: VpsInfo
    postgres: PostgresInfo
    minio: MinioInfo
    contabo_os: ContaboInfo
    backups: BackupInfo
    timestamp: str
    cache_age_seconds: int


# ============================================================================
# Collectors
# ============================================================================


def _collect_vps() -> VpsInfo:
    """VPS CPU/RAM/disk via psutil + /proc/loadavg."""
    cpu_percent = psutil.cpu_percent(interval=None)  # non-blocking
    cpu_count = psutil.cpu_count(logical=True) or 1
    load_1m, load_5m, load_15m = os.getloadavg()

    vm = psutil.virtual_memory()
    disk = shutil.disk_usage("/")

    # Container hostname yerine VPS_HOSTNAME env varsa onu kullan (compose'da set edilir)
    hostname = os.environ.get("VPS_HOSTNAME") or os.uname().nodename

    return VpsInfo(
        hostname=hostname,
        cpu=CpuInfo(
            cores=cpu_count,
            load_1m=round(load_1m, 2),
            load_5m=round(load_5m, 2),
            load_15m=round(load_15m, 2),
            usage_pct=round(cpu_percent, 1),
        ),
        ram=RamInfo(
            total_mb=int(vm.total / 1024 / 1024),
            used_mb=int(vm.used / 1024 / 1024),
            free_mb=int(vm.available / 1024 / 1024),
            used_pct=round(vm.percent, 1),
        ),
        disk=DiskInfo(
            total_gb=round(disk.total / 1024**3, 1),
            used_gb=round(disk.used / 1024**3, 1),
            free_gb=round(disk.free / 1024**3, 1),
            used_pct=round(disk.used / disk.total * 100, 1),
        ),
    )


async def _collect_postgres(db: AsyncSession) -> PostgresInfo:
    """Postgres DB size + table breakdown."""
    db_size = (
        await db.execute(
            sa_text("SELECT pg_database_size(current_database())::float")
        )
    ).scalar_one()
    db_size_gb = round(db_size / 1024**3, 2)

    table_rows = (
        await db.execute(
            sa_text(
                """
                SELECT
                    c.relname AS name,
                    pg_total_relation_size(c.oid) AS total_bytes,
                    pg_relation_size(c.oid) AS data_bytes,
                    COALESCE(s.n_live_tup, 0) AS row_count
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
                WHERE c.relkind = 'r' AND n.nspname = 'public'
                ORDER BY total_bytes DESC
                LIMIT 15
                """
            )
        )
    ).all()

    tables = [
        TableSize(
            name=row[0],
            size_mb=round(row[2] / 1024 / 1024, 1),
            row_count=int(row[3] or 0),
            index_size_mb=round((row[1] - row[2]) / 1024 / 1024, 1),
        )
        for row in table_rows
    ]

    return PostgresInfo(db_size_gb=db_size_gb, tables=tables)


def _collect_minio() -> MinioInfo:
    """MinIO bucket stats via boto3 (S3 API)."""
    try:
        client = get_s3_client()
        # MinIO listBuckets
        resp = client.list_buckets()
        buckets: list[BucketInfo] = []
        for b in resp.get("Buckets", []):
            name = b["Name"]
            try:
                # list_objects_v2 paginated, sayım için sum
                total_size = 0
                total_count = 0
                paginator = client.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=name, MaxKeys=1000):
                    for obj in page.get("Contents", []):
                        total_size += obj.get("Size", 0)
                        total_count += 1
                buckets.append(
                    BucketInfo(
                        name=name,
                        size_gb=round(total_size / 1024**3, 2),
                        object_count=total_count,
                    )
                )
            except (BotoCoreError, ClientError) as exc:
                logger.warning("minio bucket %s stats fail: %s", name, exc)
                buckets.append(
                    BucketInfo(name=name, size_gb=0.0, object_count=-1)
                )

        settings = get_settings()
        return MinioInfo(endpoint=settings.minio_endpoint, buckets=buckets)
    except Exception as exc:
        logger.exception("minio collect fail: %s", exc)
        return MinioInfo(endpoint="error", buckets=[])


def _collect_contabo_os() -> ContaboInfo:
    """Contabo Object Storage bucket stats with prefix grouping."""
    settings = get_settings()
    bucket_name = settings.s3_bucket
    endpoint = str(settings.s3_endpoint_url)

    try:
        client = get_cold_storage_client()
        total_size = 0
        total_count = 0
        by_prefix: dict[str, dict[str, int]] = {}
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name, MaxKeys=1000):
            for obj in page.get("Contents", []):
                size = obj.get("Size", 0)
                key = obj.get("Key", "")
                total_size += size
                total_count += 1

                # Top-level prefix grouping (cold/, restic/, ...)
                prefix = key.split("/", 1)[0] + "/" if "/" in key else "_root"
                if prefix not in by_prefix:
                    by_prefix[prefix] = {"size": 0, "count": 0}
                by_prefix[prefix]["size"] += size
                by_prefix[prefix]["count"] += 1

        return ContaboInfo(
            endpoint=endpoint,
            bucket=bucket_name,
            size_gb=round(total_size / 1024**3, 2),
            object_count=total_count,
            by_prefix={
                p: BucketInfo(
                    name=p, size_gb=round(d["size"] / 1024**3, 2), object_count=d["count"]
                )
                for p, d in by_prefix.items()
            },
        )
    except Exception as exc:
        logger.exception("contabo collect fail: %s", exc)
        return ContaboInfo(
            endpoint=endpoint,
            bucket=bucket_name,
            size_gb=0.0,
            object_count=0,
            by_prefix={},
        )


def _collect_backups() -> BackupInfo:
    """Restic snapshot health via subprocess + json parsing.

    NOT: API container'ında restic binary yoksa skip ile fallback döner.
    """
    try:
        # Restic env'i .env'den (RESTIC_REPOSITORY, RESTIC_PASSWORD, AWS keys)
        result = subprocess.run(
            ["restic", "snapshots", "--json"],
            capture_output=True,
            timeout=15,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return BackupInfo(
                last_snapshot_at=None,
                last_snapshot_age_h=None,
                snapshot_count=0,
                total_size_gb=0.0,
                last_check_status="restic_unavailable",
            )

        import json

        snapshots = json.loads(result.stdout)
        if not snapshots:
            return BackupInfo(
                last_snapshot_at=None,
                last_snapshot_age_h=None,
                snapshot_count=0,
                total_size_gb=0.0,
                last_check_status="no_snapshots",
            )

        latest = max(snapshots, key=lambda s: s.get("time", ""))
        latest_time = latest.get("time", "")
        snap_dt = datetime.fromisoformat(latest_time.replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - snap_dt).total_seconds() / 3600

        return BackupInfo(
            last_snapshot_at=latest_time,
            last_snapshot_age_h=round(age_h, 1),
            snapshot_count=len(snapshots),
            total_size_gb=0.0,  # restic stats ayrı çağrı pahalı, atla
            last_check_status="ok",
        )
    except FileNotFoundError:
        return BackupInfo(
            last_snapshot_at=None,
            last_snapshot_age_h=None,
            snapshot_count=0,
            total_size_gb=0.0,
            last_check_status="restic_not_installed",
        )
    except Exception as exc:
        logger.exception("backups collect fail: %s", exc)
        return BackupInfo(
            last_snapshot_at=None,
            last_snapshot_age_h=None,
            snapshot_count=0,
            total_size_gb=0.0,
            last_check_status=f"error: {str(exc)[:80]}",
        )


# ============================================================================
# Endpoint
# ============================================================================


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    summary="Sistem durum özeti — VPS + Postgres + MinIO + Contabo + backups",
)
async def system_health(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SystemHealthResponse:
    """Tüm sistem bileşenlerinin durumunu tek JSON'da döndürür.

    Cache: 60s in-memory (boto3 list_objects_v2 pahalı).
    """
    now = time.time()
    cached = _CACHE.get("data")
    cache_ts = _CACHE.get("ts", 0.0)
    if cached is not None and (now - cache_ts) < _CACHE_TTL_SECONDS:
        # Cache hit — sadece cache_age güncelle
        cached_resp = SystemHealthResponse(**cached)
        cached_resp.cache_age_seconds = int(now - cache_ts)
        return cached_resp

    # VPS + Postgres async/sync mix
    vps = _collect_vps()
    postgres = await _collect_postgres(db)

    # MinIO + Contabo OS — boto3 sync, asyncio.to_thread ile
    minio = await asyncio.to_thread(_collect_minio)
    contabo_os = await asyncio.to_thread(_collect_contabo_os)
    backups = await asyncio.to_thread(_collect_backups)

    response = SystemHealthResponse(
        vps=vps,
        postgres=postgres,
        minio=minio,
        contabo_os=contabo_os,
        backups=backups,
        timestamp=datetime.now(timezone.utc).isoformat(),
        cache_age_seconds=0,
    )

    _CACHE["data"] = response.model_dump()
    _CACHE["ts"] = now
    return response


# ============================================================================
# Disk panel (#570) — host disk + docker breakdown + safe build cache cleanup
# ============================================================================


class DiskCategory(BaseModel):
    """Disk kullanım kategorisi (UI piechart segmenti)."""

    key: str
    """images | containers | volumes | build_cache | logs | other"""

    label: str
    """Türkçe görünür ad."""

    bytes: int
    """Bayt cinsinden boyut."""

    reclaimable_bytes: int = 0
    """Anında geri kazanılabilir bayt (build_cache için anlamlı)."""


class DiskBreakdown(BaseModel):
    """GET /admin/system/disk response."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    categories: list[DiskCategory]
    docker_total_bytes: int
    """Docker'ın kapladığı toplam (categories breakdown'unun docker kısmı)."""

    reclaimable_bytes: int
    """Tüm kategorilerin reclaimable toplamı — cleanup endpoint'inin geri
    kazandıracağı tahmini boyut."""

    timestamp: str


class DiskCleanupResult(BaseModel):
    """POST /admin/system/disk/cleanup response."""

    reclaimed_bytes: int
    """Gerçekten geri kazanılan bayt."""

    items_deleted: int
    """Silinen build cache item sayısı."""

    duration_seconds: float
    timestamp: str


def _get_docker_client():
    """Docker SDK client; mount yoksa hata verir.

    docker-compose.yml api service'e /var/run/docker.sock mount edilmiş
    olmalı (#570). Read-only mount yeterli olmaz; cleanup write erişimi
    gerektirir.
    """
    import docker  # local import — ortamda yoksa endpoint hata yansıtır

    return docker.from_env()


def _collect_docker_breakdown() -> tuple[list[DiskCategory], int, int]:
    """Docker daemon API üzerinden breakdown.

    Returns: (categories, docker_total_bytes, reclaimable_total_bytes).
    """
    client = _get_docker_client()
    info = client.df()  # GET /system/df

    images_size = sum(int(i.get("Size") or 0) for i in (info.get("Images") or []))
    containers_size = sum(
        int(c.get("SizeRw") or 0) + int(c.get("SizeRootFs") or 0)
        for c in (info.get("Containers") or [])
    )
    volumes_size = sum(
        int(v.get("UsageData", {}).get("Size") or 0)
        for v in (info.get("Volumes") or [])
    )
    build_cache_entries = info.get("BuildCache") or []
    build_cache_total = sum(int(e.get("Size") or 0) for e in build_cache_entries)
    build_cache_reclaimable = sum(
        int(e.get("Size") or 0)
        for e in build_cache_entries
        if not e.get("InUse", False)
    )
    # Docker'ın kendi reclaimable mantığı: dangling images + unused volumes +
    # build cache. Image dangling = unreferenced. Volume reclaimable
    # UsageData.RefCount==0 ise.
    images_reclaimable = sum(
        int(i.get("Size") or 0)
        for i in (info.get("Images") or [])
        if (i.get("Containers") or 0) == 0
    )
    volumes_reclaimable = sum(
        int(v.get("UsageData", {}).get("Size") or 0)
        for v in (info.get("Volumes") or [])
        if (v.get("UsageData", {}).get("RefCount") or 0) == 0
    )

    categories = [
        DiskCategory(
            key="images",
            label="Docker Image'leri",
            bytes=images_size,
            reclaimable_bytes=images_reclaimable,
        ),
        DiskCategory(
            key="containers",
            label="Container'lar",
            bytes=containers_size,
        ),
        DiskCategory(
            key="volumes",
            label="Volume'lar (DB + MinIO)",
            bytes=volumes_size,
            reclaimable_bytes=volumes_reclaimable,
        ),
        DiskCategory(
            key="build_cache",
            label="Build Cache",
            bytes=build_cache_total,
            reclaimable_bytes=build_cache_reclaimable,
        ),
    ]
    docker_total = images_size + containers_size + volumes_size + build_cache_total
    reclaimable = (
        images_reclaimable + volumes_reclaimable + build_cache_reclaimable
    )
    return categories, docker_total, reclaimable


@router.get(
    "/disk",
    response_model=DiskBreakdown,
    summary="VPS disk kullanımı + Docker breakdown (#570)",
)
async def get_disk_breakdown(
    user: Annotated[User, Depends(require_admin)],
) -> DiskBreakdown:
    """Host disk usage (psutil) + Docker breakdown.

    UI'da piechart için kategoriler. Reclaimable toplamı 'Yer aç' butonunun
    geri kazandıracağı tahmini.
    """
    usage = shutil.disk_usage("/")

    docker_categories: list[DiskCategory] = []
    docker_total = 0
    docker_reclaimable = 0
    try:
        docker_categories, docker_total, docker_reclaimable = (
            _collect_docker_breakdown()
        )
    except Exception as exc:  # pragma: no cover — docker socket eksik fallback
        logger.warning("docker df failed: %s", exc)

    other_bytes = max(0, usage.used - docker_total)
    if other_bytes > 0:
        docker_categories.append(
            DiskCategory(
                key="other",
                label="Diğer (logs, system, /opt, ...)",
                bytes=other_bytes,
            )
        )

    return DiskBreakdown(
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        used_percent=round(usage.used / usage.total * 100, 1),
        categories=docker_categories,
        docker_total_bytes=docker_total,
        reclaimable_bytes=docker_reclaimable,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.post(
    "/disk/cleanup",
    response_model=DiskCleanupResult,
    summary="Build cache temizle — güvenli (#570)",
)
async def disk_cleanup(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DiskCleanupResult:
    """Yalnızca build cache'i temizler. Image/container/volume zarar görmez.

    Eşdeğer komut: `docker builder prune -af`.
    Audit log: admin_audit_log tablosuna kayıt.
    """
    from app.models.job import AdminAuditLog

    start = time.perf_counter()
    reclaimed = 0
    items = 0
    error: str | None = None
    try:
        client = _get_docker_client()
        # ApiClient ile prune (Build cache prune)
        res = client.api.prune_builds(all=True)
        reclaimed = int(res.get("SpaceReclaimed") or 0)
        deleted = res.get("CachesDeleted") or []
        items = len(deleted) if isinstance(deleted, list) else 0
    except Exception as exc:
        error = str(exc)[:300]
        logger.exception("disk cleanup failed: %s", exc)

    duration = round(time.perf_counter() - start, 2)

    # Audit log
    try:
        audit = AdminAuditLog(
            actor_id=user.id,
            action="disk_cleanup",
            target_type="system",
            event_metadata={
                "reclaimed_bytes": reclaimed,
                "items_deleted": items,
                "duration_seconds": duration,
                "error": error,
            },
        )
        db.add(audit)
        await db.commit()
    except Exception as audit_exc:  # pragma: no cover
        logger.warning("audit log write failed: %s", audit_exc)
        await db.rollback()

    if error:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail={"code": "DOCKER_ERROR", "reason": error})

    return DiskCleanupResult(
        reclaimed_bytes=reclaimed,
        items_deleted=items,
        duration_seconds=duration,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
