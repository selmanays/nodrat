"""Admin user yönetimi endpoint'leri (#69).

docs/engineering/api-contracts.md §9 (admin/users)
docs/engineering/data-model.md §2.1 (users tablosu)
docs/engineering/threat-model.md §2 (role enforcement)

Endpoints:
    GET    /admin/users              — Liste (filter: role, tier, is_active, deleted, q)
    GET    /admin/users/stats        — Tier dağılımı + aktif/pasif/silinmiş sayaçlar
    GET    /admin/users/{id}         — Detay
    PATCH  /admin/users/{id}         — role/tier/is_active değiştir
    POST   /admin/users/{id}/restore — Soft-delete'i geri al

require_admin tüm endpoint'lerde. Her değişiklik admin_audit_log'a yazılır.

Anti-patterns:
    - Email değiştirme YOK (auth flow'a tabi)
    - password_hash hiç dönmez
    - Admin kendi role'ünü 'user'a düşüremez (lockout koruması)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.models.job import AdminAuditLog
from app.models.user import Session, User


logger = logging.getLogger(__name__)
router = APIRouter()


# Locked vocab — Data Model §2.1
ALLOWED_ROLES: tuple[str, ...] = ("super_admin", "user")
ALLOWED_TIERS: tuple[str, ...] = ("free", "starter", "pro", "agency_seat")

RoleT = Literal["super_admin", "user"]
TierT = Literal["free", "starter", "pro", "agency_seat"]


# =============================================================================
# Pydantic schemas
# =============================================================================


class AdminUserSummary(BaseModel):
    """List endpoint kullanıcı satırı — password_hash YOK."""

    id: UUID
    email: str
    full_name: str | None
    role: str
    tier: str
    locale: str
    email_verified: bool
    is_active: bool
    totp_enabled: bool
    last_login_at: datetime | None
    created_at: datetime
    deleted_at: datetime | None


class AdminUserListResponse(BaseModel):
    data: list[AdminUserSummary]
    total: int
    limit: int
    offset: int


class AdminUserDetail(AdminUserSummary):
    """Detay payload — KVKK consent timestamp'leri dahil."""

    kvkk_acknowledgment_at: datetime | None
    data_processing_consent_at: datetime | None
    foreign_transfer_consent_at: datetime | None
    marketing_consent_at: datetime | None
    last_login_ip: str | None
    updated_at: datetime


class AdminUserPatchRequest(BaseModel):
    """PATCH /admin/users/{id} — sadece role/tier/is_active değiştirilir.

    Email/password/KVKK consent admin'den değiştirilmez (privacy + audit).
    """

    role: RoleT | None = None
    tier: TierT | None = None
    is_active: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class AdminUserRestoreRequest(BaseModel):
    """Soft-deleted hesabı geri yüklerken admin notu (audit için)."""

    note: str | None = Field(default=None, max_length=500)


class TierStat(BaseModel):
    tier: str
    count: int


class RoleStat(BaseModel):
    role: str
    count: int


class AdminUserStatsResponse(BaseModel):
    """Tier dağılımı + aktif/pasif/silinmiş sayaçlar."""

    total: int
    active: int
    inactive: int
    deleted: int
    email_verified: int
    by_tier: list[TierStat]
    by_role: list[RoleStat]


# =============================================================================
# Helpers
# =============================================================================


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    action: str,
    target_type: str,
    target_id: UUID,
    metadata: dict[str, Any] | None = None,
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


def _to_summary(user: User) -> AdminUserSummary:
    return AdminUserSummary(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tier=user.tier,
        locale=user.locale,
        email_verified=user.email_verified,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        deleted_at=user.deleted_at,
    )


def _to_detail(user: User) -> AdminUserDetail:
    return AdminUserDetail(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tier=user.tier,
        locale=user.locale,
        email_verified=user.email_verified,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        deleted_at=user.deleted_at,
        kvkk_acknowledgment_at=user.kvkk_acknowledgment_at,
        data_processing_consent_at=user.data_processing_consent_at,
        foreign_transfer_consent_at=user.foreign_transfer_consent_at,
        marketing_consent_at=user.marketing_consent_at,
        last_login_ip=str(user.last_login_ip) if user.last_login_ip is not None else None,
        updated_at=user.updated_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/stats",
    response_model=AdminUserStatsResponse,
    summary="Kullanıcı sayaçları (tier × role × silinme)",
)
async def user_stats(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserStatsResponse:
    """Tier dağılımı + aktif/pasif/silinmiş + email verified sayaçları."""
    # Total (deleted dahil)
    total = (await db.execute(select(func.count(User.id)))).scalar() or 0

    # Soft delete sayaçları
    deleted = (
        await db.execute(
            select(func.count(User.id)).where(User.deleted_at.is_not(None))
        )
    ).scalar() or 0

    active = (
        await db.execute(
            select(func.count(User.id)).where(
                User.deleted_at.is_(None), User.is_active.is_(True)
            )
        )
    ).scalar() or 0

    inactive = (
        await db.execute(
            select(func.count(User.id)).where(
                User.deleted_at.is_(None), User.is_active.is_(False)
            )
        )
    ).scalar() or 0

    email_verified = (
        await db.execute(
            select(func.count(User.id)).where(
                User.deleted_at.is_(None), User.email_verified.is_(True)
            )
        )
    ).scalar() or 0

    # Tier dağılımı (silinmemiş hesaplar)
    tier_rows = (
        await db.execute(
            select(User.tier, func.count(User.id))
            .where(User.deleted_at.is_(None))
            .group_by(User.tier)
            .order_by(func.count(User.id).desc())
        )
    ).all()
    by_tier = [TierStat(tier=row[0], count=row[1]) for row in tier_rows]

    role_rows = (
        await db.execute(
            select(User.role, func.count(User.id))
            .where(User.deleted_at.is_(None))
            .group_by(User.role)
            .order_by(func.count(User.id).desc())
        )
    ).all()
    by_role = [RoleStat(role=row[0], count=row[1]) for row in role_rows]

    return AdminUserStatsResponse(
        total=int(total),
        active=int(active),
        inactive=int(inactive),
        deleted=int(deleted),
        email_verified=int(email_verified),
        by_tier=by_tier,
        by_role=by_role,
    )


@router.get(
    "",
    response_model=AdminUserListResponse,
    summary="Kullanıcı listesi (admin)",
)
async def list_users(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    role: Annotated[str | None, Query(description="Filter by role")] = None,
    tier: Annotated[str | None, Query(description="Filter by tier")] = None,
    is_active: Annotated[bool | None, Query()] = None,
    deleted: Annotated[
        bool | None, Query(description="True=sadece silinmişler, False=silinmemişler")
    ] = False,
    q: Annotated[str | None, Query(description="Email içinde arama")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUserListResponse:
    """Filter + arama ile kullanıcı listesi.

    deleted parametresi:
        None  → tüm kayıtlar
        True  → sadece silinmiş
        False → sadece aktif (default — privacy)
    """
    base_stmt = select(User).order_by(User.created_at.desc())

    if role is not None:
        base_stmt = base_stmt.where(User.role == role)
    if tier is not None:
        base_stmt = base_stmt.where(User.tier == tier)
    if is_active is not None:
        base_stmt = base_stmt.where(User.is_active.is_(is_active))
    if deleted is True:
        base_stmt = base_stmt.where(User.deleted_at.is_not(None))
    elif deleted is False:
        base_stmt = base_stmt.where(User.deleted_at.is_(None))
    if q:
        base_stmt = base_stmt.where(User.email.ilike(f"%{q}%"))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    paged = base_stmt.limit(limit).offset(offset)
    rows = list((await db.execute(paged)).scalars().all())
    summaries = [_to_summary(u) for u in rows]

    return AdminUserListResponse(
        data=summaries, total=int(total), limit=limit, offset=offset
    )


@router.get(
    "/{user_id}",
    response_model=AdminUserDetail,
    summary="Kullanıcı detay",
)
async def get_user(
    user_id: Annotated[UUID, Path()],
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserDetail:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND"})
    return _to_detail(target)


@router.patch(
    "/{user_id}",
    response_model=AdminUserDetail,
    summary="role/tier/is_active güncelle",
)
async def patch_user(
    user_id: Annotated[UUID, Path()],
    payload: AdminUserPatchRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserDetail:
    """Admin kullanıcı role/tier/is_active değiştirebilir.

    Korumalar:
        - Admin kendi role'ünü 'user'a düşüremez (lockout)
        - Admin kendi is_active=False yapamaz
        - Locked vocab: role ∈ {super_admin, user}, tier ∈ {free, starter, pro, agency_seat}
        - Soft-deleted hesap PATCH edilemez (önce restore)
    """
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND"})

    if target.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "USER_DELETED",
                "title": "Silinmiş hesap güncellenemez. Önce restore.",
            },
        )

    changed: dict[str, Any] = {}

    if payload.role is not None and payload.role != target.role:
        if payload.role not in ALLOWED_ROLES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_ROLE", "allowed": list(ALLOWED_ROLES)},
            )
        # Self-demote koruması — admin kendi yetkisini düşüremez
        if target.id == admin.id and payload.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SELF_ROLE_DEMOTE_FORBIDDEN",
                    "title": "Kendi admin yetkisini düşüremezsin (lockout koruması).",
                },
            )
        changed["role"] = {"from": target.role, "to": payload.role}
        target.role = payload.role

    if payload.tier is not None and payload.tier != target.tier:
        if payload.tier not in ALLOWED_TIERS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_TIER", "allowed": list(ALLOWED_TIERS)},
            )
        changed["tier"] = {"from": target.tier, "to": payload.tier}
        target.tier = payload.tier

    if payload.is_active is not None and payload.is_active != target.is_active:
        # Self-disable koruması
        if target.id == admin.id and payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SELF_DEACTIVATE_FORBIDDEN",
                    "title": "Kendi hesabını pasif yapamazsın (lockout koruması).",
                },
            )
        changed["is_active"] = {
            "from": target.is_active,
            "to": payload.is_active,
        }
        target.is_active = payload.is_active

    if not changed:
        # Hiçbir alan değişmedi — 200 ile mevcut state'i dön (idempotent)
        return _to_detail(target)

    await _audit(
        db,
        actor_id=admin.id,
        action="user.role_change" if "role" in changed else "user.update",
        target_type="user",
        target_id=target.id,
        metadata={"changes": changed, "note": payload.note},
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.commit()
    await db.refresh(target)
    return _to_detail(target)


@router.post(
    "/{user_id}/restore",
    response_model=AdminUserDetail,
    summary="Soft-deleted hesabı geri yükle",
)
async def restore_user(
    user_id: Annotated[UUID, Path()],
    payload: AdminUserRestoreRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserDetail:
    """Soft-delete'i geri al: deleted_at=NULL + is_active=TRUE.

    Hard delete cron 30 gün içinde geçmediyse restore mümkün.
    Refresh token rotation: tüm eski sessionlar revoked kalır (security).
    """
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND"})

    if target.deleted_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "NOT_DELETED",
                "title": "Bu hesap zaten aktif (soft-delete edilmemiş).",
            },
        )

    deleted_snapshot = target.deleted_at
    target.deleted_at = None
    target.is_active = True

    # Eski oturumları güvenlik gereği revoke tut. Yeni login zorunlu.
    revoke_stmt = (
        update(Session)
        .where(Session.user_id == target.id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    await db.execute(revoke_stmt)

    await _audit(
        db,
        actor_id=admin.id,
        action="user.restore",
        target_type="user",
        target_id=target.id,
        metadata={
            "previous_deleted_at": deleted_snapshot.isoformat()
            if deleted_snapshot
            else None,
            "note": payload.note,
        },
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.commit()
    await db.refresh(target)
    return _to_detail(target)
