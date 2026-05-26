"""4 takedown endpoint + admin moderation (#35).

docs/legal/opinion-integration.md §3.4
docs/legal/incident-response.md §3 (24h SLA)

Public POST endpoints (auth gerektirmez — abuse reporting kolay erişilebilir):
    POST /legal/abuse              — Genel kötüye kullanım
    POST /legal/takedown           — 5651 içerik kaldırma
    POST /legal/copyright          — FSEK telif hakkı ihlali
    POST /legal/privacy-request    — KVKK md.11 (unutulma + erişim)

Admin endpoints (require_admin):
    GET    /admin/legal/requests
    GET    /admin/legal/requests/{ticket_id}
    PATCH  /admin/legal/requests/{ticket_id} (status/notes/action)

Anti-spam: IP-based rate limit (Redis token bucket — Faz 4 sıkılaştırma).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.models.job import AdminAuditLog
from app.models.user import User
from app.modules.legal.models import TakedownRequest

logger = logging.getLogger(__name__)
router = APIRouter()
admin_router = APIRouter()


# ============================================================================
# Pydantic schemas
# ============================================================================


class TakedownSubmission(BaseModel):
    """Public takedown form payload — 4 endpoint için ortak şema."""

    requester_email: EmailStr
    requester_name: str | None = Field(default=None, max_length=180)
    requester_phone: str | None = Field(default=None, max_length=40)
    requester_organization: str | None = Field(default=None, max_length=180)
    authority_claim: str | None = Field(
        default=None,
        max_length=500,
        description="Hangi sıfatla başvuruyor: telif sahibi / KVKK ilgili kişi / 5651 mağdur, vb.",
    )
    subject_url: str | None = Field(
        default=None,
        max_length=2000,
        description="Şikayet edilen URL (Nodrat üzerinde veya kaynak haber)",
    )
    description: str = Field(
        min_length=20,
        max_length=5000,
        description="Detaylı açıklama (zorunlu)",
    )
    evidence_urls: list[str] = Field(default_factory=list, max_length=10)


class TakedownPublicResponse(BaseModel):
    ticket_id: str
    request_type: str
    status: str
    sla_due_at: datetime
    message: str


class TakedownAdminPublic(BaseModel):
    id: UUID
    ticket_id: str
    request_type: str
    requester_name: str | None
    requester_email: str
    requester_phone: str | None
    requester_organization: str | None
    authority_claim: str | None
    subject_url: str | None
    description: str
    evidence_urls: list[str]
    status: str
    priority: str
    submitted_at: datetime
    triaged_at: datetime | None
    investigating_at: datetime | None
    resolved_at: datetime | None
    sla_due_at: datetime
    action_taken: str | None
    rejection_reason: str | None
    assigned_to: UUID | None
    internal_notes: str | None
    overdue: bool


class TakedownListResponse(BaseModel):
    data: list[TakedownAdminPublic]
    total: int
    overdue_count: int


class TakedownUpdateRequest(BaseModel):
    status: str | None = Field(default=None)
    priority: str | None = Field(default=None)
    action_taken: str | None = Field(default=None, max_length=2000)
    rejection_reason: str | None = Field(default=None, max_length=2000)
    internal_notes: str | None = Field(default=None, max_length=5000)
    assign_to_self: bool = False


# ============================================================================
# Helpers
# ============================================================================


URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _validate_evidence_urls(urls: list[str]) -> list[str]:
    """Sadece http/https URL'leri kabul et."""
    return [u for u in urls if isinstance(u, str) and URL_RE.match(u)][:10]


def _request_type_message(request_type: str) -> str:
    """Public response'da gösterilen güvence mesajı."""
    return {
        "abuse": "Şikayetiniz alındı. 24 saat içinde triaj ekibimiz inceler.",
        "takedown": (
            "5651 sayılı Kanun kapsamındaki kaldırma talebiniz alındı. "
            "24 saat içinde değerlendireceğiz. SLA 24 saat triaj + 7 gün karar."
        ),
        "copyright": (
            "FSEK kapsamındaki telif talebiniz alındı. Telif sahipliği "
            "doğrulandıktan sonra 7-30 gün içinde sonuçlandırılır."
        ),
        "privacy_request": (
            "KVKK md.11 kapsamındaki talebiniz alındı. KVKK'ya göre 30 gün "
            "içinde yanıtlanır; çoğu talep 7-14 gün içinde sonuçlanır."
        ),
    }.get(request_type, "Talebiniz alındı.")


async def _create_takedown(
    db: AsyncSession,
    *,
    request_type: str,
    payload: TakedownSubmission,
    request: Request,
    sla_hours: int = 24,
) -> TakedownRequest:
    """Yeni takedown_requests satırı + audit log."""
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent")

    sla_due = datetime.now(UTC) + timedelta(hours=sla_hours)

    record = TakedownRequest(
        request_type=request_type,
        requester_name=payload.requester_name,
        requester_email=payload.requester_email,
        requester_phone=payload.requester_phone,
        requester_organization=payload.requester_organization,
        authority_claim=payload.authority_claim,
        subject_url=payload.subject_url,
        description=payload.description,
        evidence_urls=_validate_evidence_urls(payload.evidence_urls),
        status="submitted",
        priority="critical" if request_type == "privacy_request" else "normal",
        sla_due_at=sla_due,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(record)
    await db.flush()
    await db.commit()
    await db.refresh(record)
    return record


def _is_overdue(req: TakedownRequest, now: datetime | None = None) -> bool:
    if req.status in ("action_taken", "rejected", "closed"):
        return False
    now = now or datetime.now(UTC)
    return req.sla_due_at < now


def _to_admin_public(req: TakedownRequest) -> TakedownAdminPublic:
    return TakedownAdminPublic(
        id=req.id,
        ticket_id=req.ticket_id,
        request_type=req.request_type,
        requester_name=req.requester_name,
        requester_email=req.requester_email,
        requester_phone=req.requester_phone,
        requester_organization=req.requester_organization,
        authority_claim=req.authority_claim,
        subject_url=req.subject_url,
        description=req.description,
        evidence_urls=req.evidence_urls or [],
        status=req.status,
        priority=req.priority,
        submitted_at=req.submitted_at,
        triaged_at=req.triaged_at,
        investigating_at=req.investigating_at,
        resolved_at=req.resolved_at,
        sla_due_at=req.sla_due_at,
        action_taken=req.action_taken,
        rejection_reason=req.rejection_reason,
        assigned_to=req.assigned_to,
        internal_notes=req.internal_notes,
        overdue=_is_overdue(req),
    )


# ============================================================================
# Public endpoints (auth gerektirmez)
# ============================================================================


@router.post(
    "/abuse",
    response_model=TakedownPublicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Genel kötüye kullanım bildirimi",
)
async def submit_abuse(
    payload: TakedownSubmission,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TakedownPublicResponse:
    """Spam, hakaret, taciz, kötüye kullanım bildirimleri."""
    record = await _create_takedown(db, request_type="abuse", payload=payload, request=request)
    return TakedownPublicResponse(
        ticket_id=record.ticket_id,
        request_type=record.request_type,
        status=record.status,
        sla_due_at=record.sla_due_at,
        message=_request_type_message("abuse"),
    )


@router.post(
    "/takedown",
    response_model=TakedownPublicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="5651 sayılı Kanun kaldırma talebi",
)
async def submit_takedown(
    payload: TakedownSubmission,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TakedownPublicResponse:
    """5651 sayılı Kanun kapsamındaki içerik kaldırma talepleri."""
    record = await _create_takedown(db, request_type="takedown", payload=payload, request=request)
    return TakedownPublicResponse(
        ticket_id=record.ticket_id,
        request_type=record.request_type,
        status=record.status,
        sla_due_at=record.sla_due_at,
        message=_request_type_message("takedown"),
    )


@router.post(
    "/copyright",
    response_model=TakedownPublicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="FSEK telif hakkı ihlali bildirimi",
)
async def submit_copyright(
    payload: TakedownSubmission,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TakedownPublicResponse:
    """5846 sayılı FSEK telif hakkı ihlali bildirimleri."""
    record = await _create_takedown(db, request_type="copyright", payload=payload, request=request)
    return TakedownPublicResponse(
        ticket_id=record.ticket_id,
        request_type=record.request_type,
        status=record.status,
        sla_due_at=record.sla_due_at,
        message=_request_type_message("copyright"),
    )


@router.post(
    "/privacy-request",
    response_model=TakedownPublicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="KVKK md.11 ilgili kişi başvurusu",
)
async def submit_privacy_request(
    payload: TakedownSubmission,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TakedownPublicResponse:
    """KVKK md.11: erişim, düzeltme, silme, unutulma, taşınabilirlik talepleri."""
    record = await _create_takedown(
        db,
        request_type="privacy_request",
        payload=payload,
        request=request,
        sla_hours=24,  # Triaj 24h, KVKK final yanıt 30 gün
    )
    return TakedownPublicResponse(
        ticket_id=record.ticket_id,
        request_type=record.request_type,
        status=record.status,
        sla_due_at=record.sla_due_at,
        message=_request_type_message("privacy_request"),
    )


# ============================================================================
# Admin endpoints (require_admin)
# ============================================================================


@admin_router.get(
    "",
    response_model=TakedownListResponse,
    summary="Takedown istekleri listesi",
)
async def list_requests(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request_type: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    only_overdue: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TakedownListResponse:
    stmt = select(TakedownRequest).order_by(TakedownRequest.submitted_at.desc())
    if request_type:
        stmt = stmt.where(TakedownRequest.request_type == request_type)
    if status_filter:
        stmt = stmt.where(TakedownRequest.status == status_filter)
    if only_overdue:
        now = datetime.now(UTC)
        stmt = stmt.where(TakedownRequest.sla_due_at < now).where(
            TakedownRequest.status.in_(["submitted", "triaging", "investigating"])
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    paged = stmt.limit(limit).offset(offset)
    rows = list((await db.execute(paged)).scalars().all())

    # Overdue count (separate query — independent of filter)
    now = datetime.now(UTC)
    overdue_count = (
        await db.execute(
            select(func.count(TakedownRequest.id))
            .where(TakedownRequest.sla_due_at < now)
            .where(TakedownRequest.status.in_(["submitted", "triaging", "investigating"]))
        )
    ).scalar() or 0

    return TakedownListResponse(
        data=[_to_admin_public(r) for r in rows],
        total=total,
        overdue_count=overdue_count,
    )


@admin_router.get(
    "/{ticket_id}",
    response_model=TakedownAdminPublic,
    summary="Takedown isteği detay (ticket_id)",
)
async def get_request(
    ticket_id: Annotated[str, Path()],
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TakedownAdminPublic:
    result = await db.execute(select(TakedownRequest).where(TakedownRequest.ticket_id == ticket_id))
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "TICKET_NOT_FOUND"})
    return _to_admin_public(record)


@admin_router.patch(
    "/{ticket_id}",
    response_model=TakedownAdminPublic,
    summary="Takedown isteği güncelle (status/priority/action/notes)",
)
async def update_request(
    ticket_id: Annotated[str, Path()],
    payload: TakedownUpdateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TakedownAdminPublic:
    result = await db.execute(select(TakedownRequest).where(TakedownRequest.ticket_id == ticket_id))
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "TICKET_NOT_FOUND"})

    now = datetime.now(UTC)
    changes: dict = {}

    if payload.status is not None:
        valid = {
            "submitted",
            "triaging",
            "investigating",
            "action_taken",
            "rejected",
            "closed",
        }
        if payload.status not in valid:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_STATUS", "valid": list(valid)},
            )
        # Otomatik timestamp updates
        if payload.status == "triaging" and record.triaged_at is None:
            record.triaged_at = now
        if payload.status == "investigating" and record.investigating_at is None:
            record.investigating_at = now
        if payload.status in ("action_taken", "rejected", "closed") and record.resolved_at is None:
            record.resolved_at = now
        changes["status"] = {"from": record.status, "to": payload.status}
        record.status = payload.status

    if payload.priority is not None:
        if payload.priority not in {"low", "normal", "high", "critical"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_PRIORITY"})
        changes["priority"] = {"from": record.priority, "to": payload.priority}
        record.priority = payload.priority

    if payload.action_taken is not None:
        record.action_taken = payload.action_taken.strip() or None
    if payload.rejection_reason is not None:
        record.rejection_reason = payload.rejection_reason.strip() or None
    if payload.internal_notes is not None:
        record.internal_notes = payload.internal_notes.strip() or None
    if payload.assign_to_self:
        record.assigned_to = admin.id
        changes["assigned_to"] = str(admin.id)

    # Audit log
    audit = AdminAuditLog(
        actor_id=admin.id,
        action="takedown.update",
        target_type="takedown_request",
        target_id=record.id,
        event_metadata={"ticket_id": record.ticket_id, "changes": changes},
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit)

    await db.commit()
    await db.refresh(record)
    return _to_admin_public(record)
