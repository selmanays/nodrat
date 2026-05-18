"""Admin queue / DLQ endpoints (#17, #444 broker overhaul).

docs/engineering/api-contracts.md §6.3, §6.4, §6.5
PRD §1.9 (retry policy)

Endpoints:
    GET    /admin/queue/overview              — Celery broker depth + DB sayaçları
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

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_introspect import (
    get_broker_snapshot,
    task_for_job_type,
)
from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.core.maintenance_tracker import (
    TRACKED_TASKS,
    get_last_runs,
    is_tracked,
    task_human_label,
    task_pipeline,
)
from app.models.agenda import AgendaCard
from app.models.article import Article, ArticleImage
from app.models.job import AdminAuditLog, FailedJob
from app.models.user import User
from app.workers.celery_app import celery_app

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


# #904 — CrawlerJobPublic/CrawlerJobListResponse KALDIRILDI (crawler_jobs
# tablosu drop edildi; sıfır write — Redis broker introspection kullanılır).


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
    def from_orm(cls, j: FailedJob) -> FailedJobPublic:  # type: ignore[override]
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


# #462 — Bulk operations
class BulkRequest(BaseModel):
    ids: list[UUID] = Field(..., min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class BulkResultItem(BaseModel):
    id: UUID
    ok: bool
    code: str | None = None
    """Hata kodu (BROKER_UNAVAILABLE, JOB_TYPE_NOT_DISPATCHABLE, ...) veya None."""
    celery_task_id: str | None = None


class BulkResponse(BaseModel):
    succeeded: int
    failed: int
    results: list[BulkResultItem]


# #468 — Maintenance task introspection
class MaintenanceTaskInfo(BaseModel):
    task_name: str
    """Celery task name — admin manuel tetiklemede kullanılır."""

    label: str
    """İnsancıl ad (Türkçe)."""

    pipeline: str
    """Hangi boru hattı: Kazıyıcı / Vektörleştirici / Görsel VLM."""

    interval_human: str
    """Beat schedule insancıllaştırılmış (ör. 'Her 5 dakika', 'Saatte bir :25')."""

    queue: str
    """Routing queue (crawl_queue / image_vlm_queue / embedding_queue)."""

    last_run: dict[str, Any] | None
    """Son çalışma payload'u (started_at, finished_at, status, summary, ...)
    veya None — task hiç çalışmamış / TTL düşmüş."""


class MaintenanceListResponse(BaseModel):
    tasks: list[MaintenanceTaskInfo]


class MaintenanceRunNowResponse(BaseModel):
    task_name: str
    celery_task_id: str
    triggered_at: datetime


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


async def _image_vlm_failed_count_24h(
    db: AsyncSession, since: datetime
) -> int:
    """#479 — image_vlm fail'leri failed_jobs'a yazılmıyor (task tarafı sadece
    article_images.status='failed' set ediyor). Sayım `article_images` tablosu
    üzerinden, processed_at >= since (fail anı) kullanılır."""
    stmt = select(func.count(ArticleImage.id)).where(
        ArticleImage.status == "failed",
        ArticleImage.processed_at >= since,
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

    Performance (#475):
      Eski: 3 ayrı broker call + 9 sıralı DB sorgusu = ~4.3 saniye
      Yeni: tek `get_broker_snapshot` (5s cache) + `asyncio.gather` ile 9 DB
            sorgusu paralel = cache miss ~500ms, cache hit ~50ms
    """
    since = datetime.now(UTC) - timedelta(hours=24)

    # Broker snapshot async başlat (cache 5s) — DB sırasında paralel ilerler
    snapshot_task = asyncio.create_task(get_broker_snapshot(_TRACKED_QUEUES))

    # DB — AsyncSession concurrent operations desteklemiyor → sıralı çalıştır.
    # Toplam 9 sorgu ~120ms; broker snapshot zaten arka planda paralel.
    success_results: list[int] = []
    fail_results: list[int] = []
    for qname in _TRACKED_QUEUES:
        success_results.append(await _success_count_24h(db, qname, since))
    for qname in _TRACKED_QUEUES:
        # #479 — image_vlm fail'leri failed_jobs'a yazılmıyor (task tarafı
        # sadece article_images.status='failed' set ediyor). Image dalı
        # ayrı, article_images tablosundan sayar.
        if qname == "image_vlm_queue":
            fail_results.append(
                await _image_vlm_failed_count_24h(db, since)
            )
        else:
            fail_results.append(
                await _failed_count_24h(
                    db, _QUEUE_FAILED_PREFIXES.get(qname, ()), since
                )
            )

    failed_unresolved = (
        await db.execute(
            select(func.count(FailedJob.id)).where(FailedJob.resolved_at.is_(None))
        )
    ).scalar() or 0

    # Şimdi snapshot bitmiş olur
    snapshot = await snapshot_task
    depths = snapshot.get("queue_depths", {})
    actives = snapshot.get("active_counts", {})
    worker_count = snapshot.get("worker_count", 0)

    queues: list[QueueStat] = []
    for i, qname in enumerate(_TRACKED_QUEUES):
        queues.append(
            QueueStat(
                name=qname,
                queued_count=depths.get(qname, 0),
                running_count=actives.get(qname, 0),
                succeeded_count_24h=success_results[i],
                failed_count_24h=fail_results[i],
            )
        )

    return QueueOverviewResponse(
        queues=queues,
        failed_jobs_unresolved=int(failed_unresolved),
        worker_count=worker_count,
    )


# #904 — GET /admin/queue/jobs/{job_type} (legacy crawler_jobs listesi)
# KALDIRILDI. crawler_jobs tablosu drop edildi (sıfır write — Celery/Redis
# broker introspection /admin/queue/overview kullanılır). FailedJob retry
# (POST /jobs/{id}/retry) ayrı endpoint, korunur.


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
        # Default: auto-resolve/info severity'leri liste dışı tut.
        # #904 — discarded_info (gerçek kalıcı) de permanent_info gibi gizli;
        # 'warning' (extraction-miss dahil) GÖRÜNÜR kalır (görünürlük ilkesi).
        stmt = stmt.where(
            FailedJob.severity.notin_(("permanent_info", "discarded_info"))
        )

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
    failed.resolved_at = datetime.now(UTC)
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
        scheduled_at=datetime.now(UTC),
        celery_task_id=celery_task_id,
    )


def _is_uuid(s: str) -> bool:
    try:
        UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


async def _retry_one(
    db: AsyncSession,
    failed: FailedJob,
    actor_id: UUID,
    *,
    request: Request,
) -> tuple[bool, str | None, str | None]:
    """Tek bir FailedJob için retry helper. Bulk endpoint paylaşır.

    Returns: (ok, error_code, celery_task_id)
    """
    if failed.resolved_at is not None:
        return False, "ALREADY_RESOLVED", None

    task_name = task_for_job_type(failed.job_type)
    if task_name is None:
        return False, "JOB_TYPE_NOT_DISPATCHABLE", None

    arg = _payload_arg_for_task(failed.job_type, failed.payload_json or {})
    if arg is None:
        return False, "PAYLOAD_MISSING_TARGET_ID", None

    try:
        async_result = celery_app.send_task(
            task_name, args=[str(arg)], queue=None, priority=7
        )
        celery_task_id = async_result.id
    except Exception as exc:
        logger.exception(
            "bulk_retry_dispatch_failed id=%s task=%s err=%s",
            failed.id, task_name, exc,
        )
        return False, "BROKER_UNAVAILABLE", None

    failed.resolved_at = datetime.now(UTC)
    failed.resolved_by = actor_id
    failed.retry_count = (failed.retry_count or 0) + 1
    if not failed.resolution_note:
        failed.resolution_note = (
            f"bulk admin retry (celery_task_id={celery_task_id})"
        )

    await _audit(
        db,
        actor_id=actor_id,
        action="failed_job.bulk_retry",
        target_type="failed_job",
        target_id=failed.id,
        metadata={
            "job_type": failed.job_type,
            "task_name": task_name,
            "celery_task_id": celery_task_id,
        },
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return True, None, celery_task_id


@router.post(
    "/failed/bulk-retry",
    response_model=BulkResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Toplu retry — listeden her id için Celery dispatch + DLQ resolve",
)
async def bulk_retry(
    payload: BulkRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkResponse:
    """Çoklu failed_job için tek transaction altında retry. Atomik değil — her
    id için ayrı sonuç döner. Partial failure mümkün."""
    rows = list(
        (
            await db.execute(
                select(FailedJob).where(FailedJob.id.in_(payload.ids))
            )
        ).scalars().all()
    )
    rows_by_id = {r.id: r for r in rows}

    results: list[BulkResultItem] = []
    succ = 0
    failed_ct = 0
    for fid in payload.ids:
        failed = rows_by_id.get(fid)
        if failed is None:
            results.append(
                BulkResultItem(id=fid, ok=False, code="FAILED_JOB_NOT_FOUND")
            )
            failed_ct += 1
            continue
        ok, code, tid = await _retry_one(db, failed, admin.id, request=request)
        results.append(
            BulkResultItem(id=fid, ok=ok, code=code, celery_task_id=tid)
        )
        if ok:
            succ += 1
        else:
            failed_ct += 1

    await db.commit()
    return BulkResponse(succeeded=succ, failed=failed_ct, results=results)


@router.post(
    "/failed/bulk-resolve",
    response_model=BulkResponse,
    summary="Toplu resolve — listeden her id için resolved_at set",
)
async def bulk_resolve(
    payload: BulkRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkResponse:
    """Çoklu failed_job için resolve. Idempotent — zaten resolved olanlar OK."""
    rows = list(
        (
            await db.execute(
                select(FailedJob).where(FailedJob.id.in_(payload.ids))
            )
        ).scalars().all()
    )
    rows_by_id = {r.id: r for r in rows}

    note = (payload.note or "").strip()[:500] or "bulk resolved by admin"

    results: list[BulkResultItem] = []
    succ = 0
    failed_ct = 0
    now = datetime.now(UTC)

    for fid in payload.ids:
        failed = rows_by_id.get(fid)
        if failed is None:
            results.append(
                BulkResultItem(id=fid, ok=False, code="FAILED_JOB_NOT_FOUND")
            )
            failed_ct += 1
            continue
        if failed.resolved_at is not None:
            # Idempotent — already resolved sayılır success
            results.append(BulkResultItem(id=fid, ok=True, code="ALREADY_RESOLVED"))
            succ += 1
            continue

        failed.resolved_at = now
        failed.resolved_by = admin.id
        failed.resolution_note = note

        await _audit(
            db,
            actor_id=admin.id,
            action="failed_job.bulk_resolve",
            target_type="failed_job",
            target_id=failed.id,
            metadata={"note": note, "job_type": failed.job_type},
            ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        results.append(BulkResultItem(id=fid, ok=True))
        succ += 1

    await db.commit()
    return BulkResponse(succeeded=succ, failed=failed_ct, results=results)


# ============================================================================
# #468 — Maintenance task list + run-now
# ============================================================================


_MAINTENANCE_INTERVAL_HUMAN: dict[str, str] = {
    "tasks.articles.backfill_discovered": "Her 5 dk",
    "tasks.articles.retry_failed": "Saatte bir (:25)",
    "tasks.image_vlm.backfill_pending": "Her 5 dk",
    "tasks.image_vlm.retry_failed": "Saatte bir (:20)",
    "tasks.articles.backfill_missing_chunks": "2 saatte bir (:30)",
    # #904 — operatör-tetikli (beat YOK); quarantine toplu kurtarma.
    "tasks.articles.recover_quarantined": "Manuel (operatör)",
    "tasks.sources.recompute_extract_health": "6 saatte bir (:40)",
}


_MAINTENANCE_QUEUE: dict[str, str] = {
    "tasks.articles.backfill_discovered": "crawl_queue",
    "tasks.articles.retry_failed": "crawl_queue",
    "tasks.image_vlm.backfill_pending": "image_vlm_queue",
    "tasks.image_vlm.retry_failed": "image_vlm_queue",
    "tasks.articles.backfill_missing_chunks": "embedding_queue",
    "tasks.articles.recover_quarantined": "crawl_queue",
    "tasks.sources.recompute_extract_health": "crawl_queue",
}


@router.get(
    "/maintenance",
    response_model=MaintenanceListResponse,
    summary="Bakım görevleri (backfill/retry) listesi + son çalışma",
)
async def list_maintenance_tasks(
    admin: Annotated[User, Depends(require_admin)],
) -> MaintenanceListResponse:
    """5 backfill/retry maintenance task için ad + interval + son sonuç."""
    last = await get_last_runs(TRACKED_TASKS)
    items = [
        MaintenanceTaskInfo(
            task_name=t,
            label=task_human_label(t),
            pipeline=task_pipeline(t),
            interval_human=_MAINTENANCE_INTERVAL_HUMAN.get(t, "—"),
            queue=_MAINTENANCE_QUEUE.get(t, "—"),
            last_run=last.get(t),
        )
        for t in TRACKED_TASKS
    ]
    return MaintenanceListResponse(tasks=items)


@router.post(
    "/maintenance/{task_name}/run-now",
    response_model=MaintenanceRunNowResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bakım görevini admin tarafından şimdi çalıştır",
)
async def run_maintenance_now(
    task_name: Annotated[str, Path()],
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MaintenanceRunNowResponse:
    """Whitelist'teki bakım task'ını Celery'ye apply_async ile gönderir."""
    if not is_tracked(task_name):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MAINTENANCE_TASK_NOT_FOUND",
                "task_name": task_name,
            },
        )

    queue_name = _MAINTENANCE_QUEUE.get(task_name)

    try:
        async_result = celery_app.send_task(
            task_name,
            args=[],
            kwargs={},  # task default kwargs uygulanır (batch, max_age_hours)
            queue=queue_name,
            priority=8,  # admin manuel tetikleme yüksek öncelik
        )
        celery_task_id = async_result.id
    except Exception as exc:
        logger.exception(
            "maintenance_dispatch_failed task=%s err=%s", task_name, exc
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "BROKER_UNAVAILABLE"},
        )

    triggered_at = datetime.now(UTC)

    # target_id None — AdminAuditLog FK yok, Celery task UUID format farklı
    # olabilir; metadata.celery_task_id'de tam ID var
    audit = AdminAuditLog(
        actor_id=admin.id,
        action="maintenance.run_now",
        target_type="celery_task",
        target_id=None,
        event_metadata={
            "task_name": task_name,
            "celery_task_id": celery_task_id,
            "queue": queue_name,
        },
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit)
    await db.commit()

    return MaintenanceRunNowResponse(
        task_name=task_name,
        celery_task_id=celery_task_id,
        triggered_at=triggered_at,
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

    failed.resolved_at = datetime.now(UTC)
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
