"""Healthcheck endpoints — Kubernetes/Docker probes ve external monitoring için.

docs/engineering/api-contracts.md §2.1, §2.2 ile uyumlu.
"""

from typing import Any

from fastapi import APIRouter, Response, status

from app import __version__

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, Any]:
    """Lightweight liveness check — uygulama ayakta mı?

    Bu endpoint hızlı olmalı ve harici bağımlılıklara dokunmamalı.
    Detaylı dependency check için /readiness kullan.
    """
    return {
        "status": "ok",
        "version": __version__,
        "service": "nodrat-api",
    }


@router.get("/readiness", summary="Readiness probe")
async def readiness(response: Response) -> dict[str, Any]:
    """Bağımlılıkların hazır olduğunu kontrol et — migration done, providers reachable.

    DB, Redis, MinIO, provider'lar reachable mı?

    NOT: Faz 0+ kapsamında full implementation gelecek. Şu an placeholder.
    """
    checks: dict[str, str] = {
        "database": "pending",  # Faz 0 — DB connection check eklenecek
        "redis": "pending",  # Faz 0 — Redis ping eklenecek
        "minio": "pending",  # Faz 0 — MinIO bucket check eklenecek
        "providers": "pending",  # Faz 0 — provider healthcheck eklenecek
    }

    all_ready = all(v in {"ok", "pending"} for v in checks.values())
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "ready": all_ready,
        "version": __version__,
        "checks": checks,
    }
