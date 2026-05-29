"""Admin audit log viewer (#132).

docs/legal/kvkk-aydinlatma.md §8.3 — admin işlem kaydı transparency
docs/engineering/data-model.md — admin_audit_log tablosu

Endpoints:
    GET    /admin/audit              — paginated list with filters

Filters:
    action          — action type (örn. source.create, user.role_change)
    actor_id        — actor user id (UUID)
    target_type     — source | article | user | provider | takedown_request
    target_id       — target entity id (UUID)
    date_from/to    — created_at range (ISO 8601 date)
    limit           — 1-200 (default 50)
    offset          — pagination

Compliance:
    - KVKK §8.3: admin işlem kaydı transparency
    - Audit log SADECE okunur (no UPDATE/DELETE) — append-only by design
    - Read endpoint require_admin auth-walled
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.job import AdminAuditLog
from app.models.user import User
from app.modules.accounts.deps import require_admin

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Pydantic schemas
# =============================================================================


class AuditLogEntry(BaseModel):
    """Audit log read response item."""

    id: UUID
    actor_id: UUID
    actor_email: str | None = None
    """JOIN with users.email — soft-deleted user için None."""
    action: str
    target_type: str | None = None
    target_id: UUID | None = None
    event_metadata: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    data: list[AuditLogEntry]
    total: int
    limit: int
    offset: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="Admin audit log list (KVKK §8.3 transparency)",
)
async def list_audit_log(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    action: Annotated[str | None, Query(max_length=80)] = None,
    actor_id: Annotated[UUID | None, Query()] = None,
    target_type: Annotated[str | None, Query(max_length=80)] = None,
    target_id: Annotated[UUID | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogListResponse:
    """Admin işlemleri audit log'unu listele.

    Note: index'ler (idx_admin_audit_log_actor_created, action_created, target)
    SELECT'i optimize eder. created_at DESC primary order.
    """

    base = select(AdminAuditLog, User.email).outerjoin(User, AdminAuditLog.actor_id == User.id)

    filters = []
    if action:
        filters.append(AdminAuditLog.action == action)
    if actor_id:
        filters.append(AdminAuditLog.actor_id == actor_id)
    if target_type:
        filters.append(AdminAuditLog.target_type == target_type)
    if target_id:
        filters.append(AdminAuditLog.target_id == target_id)
    if date_from:
        filters.append(
            AdminAuditLog.created_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
        )
    if date_to:
        filters.append(
            AdminAuditLog.created_at < datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)
        )

    if filters:
        base = base.where(*filters)

    # Total count (filters dahil)
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Paged data
    paged = base.order_by(AdminAuditLog.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(paged)).all()

    entries = [
        AuditLogEntry(
            id=log.id,
            actor_id=log.actor_id,
            actor_email=email,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            event_metadata=log.event_metadata or {},
            ip_address=str(log.ip_address) if log.ip_address else None,
            user_agent=log.user_agent,
            created_at=log.created_at,
        )
        for log, email in rows
    ]

    return AuditLogListResponse(data=entries, total=total, limit=limit, offset=offset)
