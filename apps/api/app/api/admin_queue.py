"""Admin queue / DLQ endpoints (#17, #444 broker overhaul).

docs/engineering/api-contracts.md §6.3, §6.4, §6.5
PRD §1.9 (retry policy)

Endpoints:
    GET    /admin/queue/overview              — Celery broker depth + DB sayaçları
    GET    /admin/queue/jobs/{type}           — crawler_jobs filtreli liste (legacy)
    GET    /admin/queue/failed                — failed_jobs (DLQ) listesi
    POST   /admin/queue/jobs/{id}/retry       — failed_jobs Celery dispatch + soft close
    DELETE /admin/queue/failed/{id}           — resolved_at set et (soft close)

Tüm endpoint'ler require_admin (super_admin).
Tüm değişiklikler admin_audit_log'a yazılır.

#444 değişikliği: overview endpoint'i `crawler_jobs` tablosundan değil, Celery
broker (Redis LLEN) + worker inspect API + ilgili tablo transitions'tan sayım
yapar. Retry endpoint Celery'ye gerçek `apply_async` ile dispatch eder.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_introspect import (
    get_active_counts_by_queue,
    get_queue_depths,
    get_worker_count,
    task_for_job_type,
)
from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.models.agenda import AgendaCard
from app.models.article import Article, ArticleImage
from app.models.job import AdminAuditLog, CrawlerJob, FailedJob
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Pydantic schemas
# ============================================================================


class QueueStat(BaseModel):
    name: str
    """Celery broker queue adı (crawl_queue, embedding_queue, ...)."""

    queued_count: int
    """Redis LLEN — broker'da pickup bekleyen task sayısı."""

    running_count: int
    """celery inspect().active() — şu an worker'da çalışan task sayısı."""

    succeeded_count_24h: int
    """Son 24h kuyruk-spesifik başarı yaklaşımı (tablo transitions)."""

    failed_count_24h: int
    """Son 24h failed_jobs kayıt sayısı (job_type prefix'e göre)."""


class QueueOverviewResponse(BaseModel):
    queues: list[QueueStat]
    failed_jobs_unresolved: int
    worker_count: int = 0
    """Aktif Celery worker sayısı — 0 ise broker'la haberleşemiyor demek."""


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
    severity: str = "error"
    """error | warning | permanent_info — #445."""
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
            severity=getattr(j, "severity", "error"),
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
    """Geriye dönük uyumluluk: Celery task_id UUID parse edilebilirse o,
    aksi halde original FailedJob.id."""

    scheduled_at: datetime
    celery_task_id: str = ""
    """Celery'ye `apply_async` ile gönderilen task ID — broker'da takip için."""


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


# Celery broker'a yansıyan kuyruklar — celery_app.py task_routes ile birebir.
# Sıralama UI'da kart sırasına yansır (Source → Embedding → Event → Image VLM).
_TRACKED_QUEUES: tuple[str, ...] = (
    "crawl_queue",
    "embedding_queue",
    "event_queue",
    "image_vlm_queue",
)

# Her kuyruk için 24h success'i hangi tablo transition'ından okuyacağımız.
# 24h fail her zaman failed_jobs (job_type prefix LIKE) — uniform.
_QUEUE_FAILED_PREFIXES: dict[str, tuple[str, ...]] = {
    "crawl_queue": ("article.", "source.", "media."),
    "embedding_queue": ("embedding.", "embed.", "chunk."),
    "event_queue": ("clustering.", "agenda.", "raptor.", "event."),
    "image_vlm_queue": ("image.", "image_vlm.", "media.image."),
}


async def _success_count_24h(
    db: AsyncSession, queue: str, since: datetime
) -> int:
    """Kuyruk-spesifik 24h başarı yaklaşımı.

    Tam metrik için worker_task_log tablosu gerekir (gelecekte). Şu an her
    kuyruk için ilgili tablo transition sayımı:
      - crawl       : articles.status='cleaned' AND updated_at >= since
      - embedding   : article_chunks update yerine — daha pahalı, şimdilik 0
      - event       : agenda_cards.created_at >= since
      - image_vlm   : article_images.status='processed' AND updated_at >= since
    """
    if queue == "crawl_queue":
        stmt = select(func.count(Article.id)).where(
            Article.status == "cleaned",
            Article.updated_at >= since,
        )
    elif queue == "event_queue":
        stmt = select(func.count(AgendaCard.id)).where(
            AgendaCard.created_at >= since
        )
    elif queue == "image_vlm_queue":
        stmt = select(func.count(ArticleImage.id)).where(
            ArticleImage.status == "processed",
            ArticleImage.processed_at >= since,
        )
    else:
        # embedding_queue: chunk tablosu üzerinden direkt sayım yapılabilir ama
        # büyük veri setinde yavaş. PR-2'de worker_task_log eklenince netleşir.
        return 0
    return int((await db.execute(stmt)).scalar() or 0)


async def _failed_count_24h(
    db: AsyncSession, prefixes: tuple[str, ...], since: datetime
) -> int:
    """Failed_jobs job_type prefix LIKE — 24h aralığı."""
    from sqlalchemy import or_

    stmt = select(func.count(FailedJob.id)).where(
        FailedJob.created_at >= since,
        or_(*[FailedJob.job_type.like(f"{p}%") for p in prefixes]),
    )
    return int((await db.execute(stmt)).scalar() or 0)


@router.get(
    "/overview",
    response_model=QueueOverviewResponse,
    summary="Kuyruk özeti — Celery broker depth + DB sayaçları",
)
async def queue_overview(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QueueOverviewResponse:
    """4 ana kuyruk için canlı durum.

    queued = Redis LLEN (broker pickup bekleyen)
    running = celery inspect().active() (worker'da çalışan)
    succeeded_24h = ilgili tablo transition (yaklaşık)
    failed_24h = failed_jobs son 24h, job_type prefix eşleştirme
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Broker tarafı paralel
    depths = await get_queue_depths(_TRACKED_QUEUES)
    actives = await get_active_counts_by_queue(_TRACKED_QUEUES)
    worker_count = await get_worker_count()

    queues: list[QueueStat] = []
    for qname in _TRACKED_QUEUES:
        succ = await _success_count_24h(db, qname, since)
        fail = await _failed_count_24h(
            db, _QUEUE_FAILED_PREFIXES.get(qname, ()), since
        )
        queues.append(
            QueueStat(
                name=qname,
                queued_count=depths.get(qname, 0),
                running_count=actives.get(qname, 0),
                succeeded_count_24h=succ,
                failed_count_24h=fail,
            )
        )

    failed_unresolved = (
        await db.execute(
            select(func.count(FailedJob.id)).where(FailedJob.resolved_at.is_(None))
        )
    ).scalar() or 0

    return QueueOverviewResponse(
        queues=queues,
        failed_jobs_unresolved=int(failed_unresolved),
        worker_count=worker_count,
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
    severity: Annotated[
        str | None,
        Query(
            description=(
                "Filter by severity. None=hepsi (default permanent_info hariç), "
                "'error'/'warning'/'permanent_info'/'all'"
            )
        ),
    ] = None,
    include_info: Annotated[
        bool,
        Query(description="permanent_info kayıtlarını dahil et (default False)"),
    ] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FailedJobListResponse:
    """Failed jobs listesi.

    Default davranış (#445): `permanent_info` severity kayıtları (RSS re-emit gibi
    info-level olaylar) listelemeden hariç tutulur — alarm yorgunluğunu azaltır.
    `include_info=true` veya `severity='permanent_info'` ile dahil edilebilir.
    """
    stmt = select(FailedJob).order_by(FailedJob.created_at.desc())
    if unresolved_only:
        stmt = stmt.where(FailedJob.resolved_at.is_(None))
    if job_type:
        stmt = stmt.where(FailedJob.job_type == job_type)
    if source_id:
        stmt = stmt.where(FailedJob.source_id == source_id)

    # Severity filter — #445
    if severity and severity != "all":
        stmt = stmt.where(FailedJob.severity == severity)
    elif not include_info:
        # Default: permanent_info'yu liste dışı tut
        stmt = stmt.where(FailedJob.severity != "permanent_info")

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    paged = stmt.limit(limit).offset(offset)
    rows = list((await db.execute(paged)).scalars().all())

    return FailedJobListResponse(
        data=[FailedJobPublic.from_orm(j) for j in rows],
        total=total,
    )


def _payload_arg_for_task(job_type: str, payload: dict[str, Any]) -> Any:
    """Celery task'ın args[0]'ı için payload'tan doğru tek argümanı çek.

    Article tarafı task'ları (`tasks.articles.fetch_detail` vs.) `article_id`
    bekler. Image task'ları `article_image_id` bekler.
    payload_json içinde `article_id` veya `image_id` olabilir; yoksa None döner.
    """
    if job_type.startswith("article."):
        return payload.get("article_id")
    if job_type.startswith(("image.", "image_vlm.", "media.image.")):
        return payload.get("article_image_id") or payload.get("image_id")
    if job_type.startswith("media."):
        return payload.get("article_image_id")
    return None


@router.post(
    "/jobs/{failed_id}/retry",
    response_model=RetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Failed job'u retry et — Celery'ye apply_async + DLQ resolved işaretle",
)
async def retry_failed_job(
    failed_id: Annotated[UUID, Path()],
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RetryResponse:
    """Failed job'u Celery'ye gerçek dispatch eder, DLQ'da resolved işaretler.

    #444 öncesi: sadece `crawler_jobs` INSERT, kimse pickup etmiyordu.
    #444 sonrası: `apply_async` ile broker'a giriyor, dönen task_id audit'e
    yazılıyor.
    """
    failed = await db.get(FailedJob, failed_id)
    if failed is None:
        raise HTTPException(status_code=404, detail={"code": "FAILED_JOB_NOT_FOUND"})
    if failed.resolved_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ALREADY_RESOLVED"},
        )

    task_name = task_for_job_type(failed.job_type)
    if task_name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "JOB_TYPE_NOT_DISPATCHABLE",
                "job_type": failed.job_type,
            },
        )

    payload = failed.payload_json or {}
    arg = _payload_arg_for_task(failed.job_type, payload)
    if arg is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PAYLOAD_MISSING_TARGET_ID",
                "job_type": failed.job_type,
                "expected_keys": ["article_id", "article_image_id"],
            },
        )

    # Celery dispatch — broker erişilemezse 503 dön, DLQ resolved işaretleme.
    try:
        async_result = celery_app.send_task(
            task_name,
            args=[str(arg)],
            queue=None,  # task_routes config'inden queue resolve eder
            priority=7,  # admin retry → biraz öncelikli (default 5/10)
        )
        celery_task_id = async_result.id
    except Exception as exc:
        logger.exception(
            "retry_dispatch_failed failed_id=%s task=%s err=%s",
            failed_id,
            task_name,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "BROKER_UNAVAILABLE"},
        )

    # DLQ row'u resolve olarak işaretle
    failed.resolved_at = datetime.now(timezone.utc)
    failed.resolved_by = admin.id
    failed.retry_count = (failed.retry_count or 0) + 1
    if not failed.resolution_note:
        failed.resolution_note = (
            f"admin retry by {admin.email} (celery_task_id={celery_task_id})"
        )

    await _audit(
        db,
        actor_id=admin.id,
        action="failed_job.retry",
        target_type="failed_job",
        target_id=failed.id,
        metadata={
            "job_type": failed.job_type,
            "task_name": task_name,
            "celery_task_id": celery_task_id,
            "source_id": str(failed.source_id) if failed.source_id else None,
            "target_arg": str(arg),
        },
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.commit()

    return RetryResponse(
        new_job_id=UUID(celery_task_id) if _is_uuid(celery_task_id) else failed.id,
        scheduled_at=datetime.now(timezone.utc),
        celery_task_id=celery_task_id,
    )


def _is_uuid(s: str) -> bool:
    try:
        UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


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
