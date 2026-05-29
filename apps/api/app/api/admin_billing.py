"""Admin billing endpoints — plan + LS variant_id yönetimi (#77).

docs/engineering/api-contracts.md §15 (Admin: Billing — plan management)
docs/strategy/pricing-strategy.md §2 (tier matrix, USD primary)

Endpoints:
    GET   /admin/plans                 — Tüm plan'lar (private fields dahil)
    PATCH /admin/plans/{plan_code}     — variant_id_* + active toggle update

Kullanım:
    LS hesap kurulduktan sonra her variant ID'si dashboard'dan kopyalanıp bu
    endpoint üzerinden ilgili plan'a atanır. ls_variant_id_* nullable kalır
    (free için), atandıktan sonra `/app/billing/plans` endpoint'inde
    `available: true` görülür.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.user import User
from app.modules.accounts.deps import require_admin
from app.modules.billing.models import Plan

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Models
# =============================================================================


class AdminPlanItem(BaseModel):
    """Admin görünümü — private alanları (ls_variant_id_*) içerir."""

    code: str
    name: str
    tier: str
    price_usd_monthly: float
    price_usd_yearly: float
    price_tl_display_monthly: float | None
    price_tl_display_yearly: float | None
    monthly_generation_limit: int
    seat_count: int
    max_context_cards: int
    features: dict[str, Any]
    ls_variant_id_monthly: str | None
    ls_variant_id_yearly: str | None
    active: bool
    display_order: int
    available: bool = Field(description="LS variant_id atanmışsa True (kullanıcıya görünür)")
    created_at: datetime
    updated_at: datetime


class AdminPlansListResponse(BaseModel):
    plans: list[AdminPlanItem]


class PlanUpdateRequest(BaseModel):
    """Admin update — sadece variant_id'ler ve active toggle değişir.

    Pricing/features/limits değişimleri DB migration ile yapılır (audit trail).
    """

    ls_variant_id_monthly: str | None = Field(default=None, max_length=180)
    ls_variant_id_yearly: str | None = Field(default=None, max_length=180)
    active: bool | None = None


# =============================================================================
# Helpers
# =============================================================================


def _to_admin_item(plan: Plan) -> AdminPlanItem:
    available = bool(plan.ls_variant_id_monthly or plan.ls_variant_id_yearly)
    return AdminPlanItem(
        code=plan.code,
        name=plan.name,
        tier=plan.tier,
        price_usd_monthly=float(plan.price_usd_monthly),
        price_usd_yearly=float(plan.price_usd_yearly),
        price_tl_display_monthly=(
            float(plan.price_tl_display_monthly)
            if plan.price_tl_display_monthly is not None
            else None
        ),
        price_tl_display_yearly=(
            float(plan.price_tl_display_yearly)
            if plan.price_tl_display_yearly is not None
            else None
        ),
        monthly_generation_limit=plan.monthly_generation_limit,
        seat_count=plan.seat_count,
        max_context_cards=plan.max_context_cards,
        features=plan.features,
        ls_variant_id_monthly=plan.ls_variant_id_monthly,
        ls_variant_id_yearly=plan.ls_variant_id_yearly,
        active=plan.active,
        display_order=plan.display_order,
        available=available,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=AdminPlansListResponse)
async def list_plans(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminPlansListResponse:
    """Tüm plan'ları listele — private fields dahil.

    Inactive olanlar da dahil; admin tüm tabloyu görür.
    """
    result = await db.execute(select(Plan).order_by(Plan.display_order))
    plans = result.scalars().all()
    return AdminPlansListResponse(plans=[_to_admin_item(p) for p in plans])


@router.patch("/{plan_code}", response_model=AdminPlanItem)
async def update_plan(
    payload: PlanUpdateRequest,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    plan_code: Annotated[str, Path(min_length=1, max_length=32)],
) -> AdminPlanItem:
    """Plan güncelle — variant_id_* ve active toggle.

    Boş string → NULL'a çevrilir (variant_id'yi temizleme).
    """
    result = await db.execute(select(Plan).where(Plan.code == plan_code))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PLAN_NOT_FOUND", "message": f"Plan '{plan_code}' bulunamadı."},
        )

    changed: list[str] = []

    if payload.ls_variant_id_monthly is not None:
        new_val = payload.ls_variant_id_monthly.strip() or None
        if new_val != plan.ls_variant_id_monthly:
            plan.ls_variant_id_monthly = new_val
            changed.append("ls_variant_id_monthly")

    if payload.ls_variant_id_yearly is not None:
        new_val = payload.ls_variant_id_yearly.strip() or None
        if new_val != plan.ls_variant_id_yearly:
            plan.ls_variant_id_yearly = new_val
            changed.append("ls_variant_id_yearly")

    if payload.active is not None and payload.active != plan.active:
        plan.active = payload.active
        changed.append("active")

    if changed:
        plan.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(plan)
        logger.info(
            "admin_plan_update plan=%s changed=%s admin=%s",
            plan.code,
            ",".join(changed),
            _admin.id,
        )

    return _to_admin_item(plan)
