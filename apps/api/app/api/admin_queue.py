"""Admin queue / DLQ endpoints (#17).

docs/engineering/api-contracts.md §6.3, §6.4, §6.5
PRD §1.9 (retry policy)

Endpoints:
    GET    /admin/queue/overview              — kuyruk özeti (Celery + DB sayaçları)
    GET    /admin/queue/jobs/{type}           — crawler_jobs filtreli liste
    GET    /admin/queue/failed                — failed_jobs (DLQ) listesi
    POST   /admin/queue/jobs/{id}/retry       — failed_jobs içinden retry
    DELETE /admin/queue/failed/{id}           — resolved_at set et (soft close)

Tüm endpoint'ler require_admin (super_admin).
Tüm değişiklikler admin_audit_log'a yazılır.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.models.job import AdminAuditLog, CrawlerJob, FailedJob
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Pydantic schemas
# ============================================================================


class QueueStat(BaseModel):
    name: str
    queued_count: int
    running_count: int
    succeeded_count_24h: int
    failed_count_24h: int


class QueueOverviewResponse(BaseModel):
    queues: list[QueueStat]
    failed_jobs_unresolved: int


class CrawlerJobPublic(BaseModel):
    id: UUID
    job_type: str
    status: str
    priority: int
    attempt_count: int
    max_attempts: int
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    source_id: UUID | None
    article_id: UUID | None
    payload: dict[str, Any]

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, job: CrawlerJob) -> "CrawlerJobPublic":  # type: ignore[override]
        return cls(
            id=job.id,
            job_type=job.job_type,
            status=job.status,
            priority=job.priority,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            scheduled_at=job.scheduled_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error_message=job.error_message,
            source_id=job.source_id,
            article_id=job.article_id,
            payload=job.payload_json or {},
        )


class CrawlerJobListResponse(BaseModel):
    data: list[CrawlerJobPublic]
    total: int


class FailedJobPublic(BaseModel):
    id: UUID
    original_job_id: UUID | None
    job_type: str
    source_id: UUID | None
    article_url: str | None
    error_message: str
    stack_trace: str | None
    retry_count: int
    last_attempt_at: datetime
    resolved_at: datetime | None
    resolved_by: UUID | None
    resolution_note: str | None
    payload: dict[str, Any]

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, j: FailedJob) -> "FailedJobPublic":  # type: ignore[override]
        return cls(
            id=j.id,
            original_job_id=j.original_job_id,
            job_type=j.job_type,
            source_id=j.source_id,
            article_url=j.article_url,
            error_message=j.error_message,
            stack_trace=j.stack_trace,
            retry_count=j.retry_count,
            last_attempt_at=j.last_attempt_at,
            resolved_at=j.resolved_at,
            resolved_by=j.resolved_by,
            resolution_note=j.resolution_note,
            payload=j.payload_json or {},
        )


class FailedJobListResponse(BaseModel):
    data: list[FailedJobPublic]
    total: int


class RetryResponse(BaseModel):
    new_job_id: UUID
    scheduled_at: datetime


class ResolveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


# ============================================================================
# Helpers
# ============================================================================


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    action: str,
    target_type: str,
    target_id: UUID,
    metadata: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    audit = AdminAuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        event_metadata=metadata or {},
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(audit)


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/overview",
    response_model=QueueOverviewResponse,
    summary="Kuyruk özeti — DB sayaçları",
)
async def queue_overview(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QueueOverviewResponse:
    """Crawler_jobs üzerinden kuyruk başına özet sayaçlar.

    Note: Bu endpoint Celery inspect API'sine direkt erişmez (Celery ile sync
    çalışan worker process'lere broadcast pahalı). DB-tabanlı sayaçlar Faz 1
    için yeterli.
    """
    # job_type prefix'inden kuyruğa eşle (architecture.md §3.1)
    queue_map = {
        "crawl_queue": ["source.", "article.", "media."],
        "cleaning_queue": ["clean."],
        "embedding_queue": ["embed."],
        "event_queue": ["event."],
    }
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)

    queues: list[QueueStat] = []
    for qname, prefixes in queue_map.items():
        # like ANY (...) için OR çalışmasını ifade et
        from sqlalchemy import or_

        pattern_filters = or_(
            *[CrawlerJob.job_type.like(f"{p}%") for p in prefixes]
        )

        stats: dict[str, int] = {}
        for status_val in ("queued", "running", "succeeded", "failed"):
            stmt = select(func.count(CrawlerJob.id)).where(
                CrawlerJob.status == status_val,
                pattern_filters,
            )
            if status_val in ("succeeded", "failed"):
                stmt = stmt.where(
                    CrawlerJob.created_at >= twenty_four_hours_ago
                )
            row = (await db.execute(stmt)).scalar() or 0
            stats[status_val] = row

        queues.append(
            QueueStat(
                name=qname,
                queued_count=stats["queued"],
                running_count=stats["running"],
                succeeded_count_24h=stats["succeeded"],
                failed_count_24h=stats["failed"],
            )
        )

    failed_unresolved = (
        await db.execute(
            select(func.count(FailedJob.id)).where(FailedJob.resolved_at.is_(None))
        )
    ).scalar() or 0

    return QueueOverviewResponse(
        queues=queues,
        failed_jobs_unresolved=failed_unresolved,
    )


@router.get(
    "/jobs/{job_type}",
    response_model=CrawlerJobListResponse,
    summary="Crawler job listesi (job_type filtresi)",
)
async def list_jobs(
    job_type: Annotated[str, Path()],
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CrawlerJobListResponse:
    stmt = (
        select(CrawlerJob)
        .where(CrawlerJob.job_type == job_type)
        .order_by(CrawlerJob.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(CrawlerJob.status == status_filter)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    paged = stmt.limit(limit).offset(offset)
    rows = list((await db.execute(paged)).scalars().all())

    return CrawlerJobListResponse(
        data=[CrawlerJobPublic.from_orm(j) for j in rows],
        total=total,
    )


@router.get(
    "/failed",
    response_model=FailedJobListResponse,
    summary="Failed jobs (DLQ) listesi",
)
async def list_failed(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    job_type: Annotated[str | None, Query()] = None,
    unresolved_only: Annotated[bool, Query()] = True,
    source_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FailedJobListResponse:
    stmt = select(FailedJob).order_by(FailedJob.created_at.desc())
    if unresolved_only:
        stmt = stmt.where(FailedJob.resolved_at.is_(None))
    if job_type:
        stmt = stmt.where(FailedJob.job_type == job_type)
    if source_id:
        stmt = stmt.where(FailedJob.source_id == source_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    paged = stmt.limit(limit).offset(offset)
    rows = list((await db.execute(paged)).scalars().all())

    return FailedJobListResponse(
        data=[FailedJobPublic.from_orm(j) for j in rows],
        total=total,
    )


@router.post(
    "/jobs/{failed_id}/retry",
    response_model=RetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Failed job'u retry et (yeni crawler_jobs satırı + DLQ resolved işaretle)",
)
async def retry_failed_job(
    failed_id: Annotated[UUID, Path()],
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RetryResponse:
    """Failed job için yeni bir CrawlerJob satırı yaratıp DLQ'da resolved işaretler.

    NOT: Celery dispatch (apply_async) Faz 1 article worker pipeline'ı eklendiğinde
    burada job_type'a göre eklenir. Şimdilik DB-level retry ledger.
    """
    failed = await db.get(FailedJob, failed_id)
    if failed is None:
        raise HTTPException(status_code=404, detail={"code": "FAILED_JOB_NOT_FOUND"})
    if failed.resolved_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ALREADY_RESOLVED"},
        )

    new_job = CrawlerJob(
        job_type=failed.job_type,
        status="queued",
        priority=70,  # admin retry → biraz öncelikli
        payload_json=failed.payload_json,
        source_id=failed.source_id,
        scheduled_at=datetime.now(timezone.utc),
    )
    db.add(new_job)

    failed.resolved_at = datetime.now(timezone.utc)
    failed.resolved_by = admin.id
    failed.retry_count = (failed.retry_count or 0) + 1
    if not failed.resolution_note:
        failed.resolution_note = f"admin retry by {admin.email}"

    await _audit(
        db,
        actor_id=admin.id,
        action="failed_job.retry",
        target_type="failed_job",
        target_id=failed.id,
        metadata={
            "job_type": failed.job_type,
            "source_id": str(failed.source_id) if failed.source_id else None,
            "new_job_id": str(new_job.id) if new_job.id else None,
        },
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.commit()
    await db.refresh(new_job)

    return RetryResponse(
        new_job_id=new_job.id,
        scheduled_at=new_job.scheduled_at,
    )


@router.delete(
    "/failed/{failed_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Failed job'u resolve olarak işaretle (DLQ'dan kaldırma)",
)
async def resolve_failed_job(
    failed_id: Annotated[UUID, Path()],
    payload: ResolveRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    failed = await db.get(FailedJob, failed_id)
    if failed is None:
        raise HTTPException(status_code=404, detail={"code": "FAILED_JOB_NOT_FOUND"})
    if failed.resolved_at is not None:
        # Idempotent: zaten resolved → 204 (no-op)
        return

    failed.resolved_at = datetime.now(timezone.utc)
    failed.resolved_by = admin.id
    failed.resolution_note = (payload.note or "").strip()[:500] or "resolved by admin"

    await _audit(
        db,
        actor_id=admin.id,
        action="failed_job.resolve",
        target_type="failed_job",
        target_id=failed.id,
        metadata={"note": failed.resolution_note, "job_type": failed.job_type},
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.commit()
