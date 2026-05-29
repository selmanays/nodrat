"""User-facing billing endpoints (#53, #76, Epic #448).

docs/engineering/api-contracts.md §14 (User: Billing — Lemon Squeezy MoR)
docs/strategy/pricing-strategy.md §2 (tier matrix)
docs/legal/refund-policy.md (LS hosted refund)

Endpoints:
    GET    /app/billing/plans              — Public: tier listesi (USD primary)
    POST   /app/billing/checkout           — LS hosted checkout URL üret
    GET    /app/billing/subscription       — Mevcut abonelik durumu
    GET    /app/billing/portal-url         — LS Customer Portal redirect URL
    GET    /app/billing/invoices           — LS invoice referans listesi
    GET    /app/billing/seats              — Agency multi-seat liste
    POST   /app/billing/seats/invite       — Email davet (Agency)
    DELETE /app/billing/seats/{id}         — Seat çıkar

#470 KVKK m.9 server-side enforcement: checkout + portal-url endpoint'leri
require_foreign_transfer_consent dependency'i kullanır. Yurt dışı LS'ye PII
transfer öncesi açık rıza zorunlu.

LS hesap aktive olmamışsa (env vars boş) endpoint'ler 503 döner —
billing_not_configured (kullanıcıya "yakında" mesajı).
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db
from app.models.user import User
from app.modules.accounts.deps import get_current_user, require_foreign_transfer_consent
from app.modules.billing.models import (
    AgencySeat,
    Invoice,
    Plan,
    Subscription,
)
from app.providers import lemonsqueezy as ls

logger = logging.getLogger(__name__)
router = APIRouter()


def _billing_not_configured_503() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "BILLING_NOT_CONFIGURED",
            "message": (
                "Ücretli abonelik sistemi yakında aktif olacak. "
                "Lemon Squeezy hesap kurulumu tamamlandığında ödeme alabileceğiz."
            ),
        },
    )


# =============================================================================
# Response models
# =============================================================================


class PlanFeatures(BaseModel):
    allowed_models: list[str] = Field(default_factory=list)
    comparison_mode: bool = False
    style_profiles: bool = False
    style_profiles_slots: int | None = None
    visual_features: bool = False
    visual_premium_vlm: bool = False
    analysis_output: bool = False
    concurrent_gen: int = 1
    rate_per_hour: int = 5
    support_sla_hours: int = 0
    bulk_export: bool = False
    comparison_premium_model: bool = False


class PlanResponse(BaseModel):
    code: str
    name: str
    tier: str
    price_usd_monthly: float
    price_usd_yearly: float
    price_tl_display_monthly: float | None
    price_tl_display_yearly: float | None
    monthly_generation_limit: int
    seat_count: int
    features: dict[str, Any]
    available: bool = Field(description="LS variant_id atanmışsa True")


class PlansListResponse(BaseModel):
    plans: list[PlanResponse]
    currency_primary: str = "USD"
    billing_provider: str = "lemon_squeezy"
    refund_policy_url: str = "/legal/refund-policy"
    mesafeli_satis_url: str = "/legal/mesafeli-satis-sozlesmesi"


class CheckoutRequest(BaseModel):
    plan_code: str
    billing_cycle: str = Field(pattern="^(monthly|yearly)$")


class CheckoutResponse(BaseModel):
    checkout_url: str
    ls_variant_id: str
    expires_at: str | None = None


class SubscriptionResponse(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    billing_cycle: str
    trial_ends_at: datetime | None
    current_period_start: datetime
    current_period_end: datetime
    cancelled_at: datetime | None
    ends_at: datetime | None
    seat_count: int
    payment_provider: str
    ls_subscription_id: str | None
    next_invoice_amount_usd: float
    next_invoice_amount_tl_display_ref: float | None


class PortalUrlResponse(BaseModel):
    portal_url: str
    expires_at: str | None = None


class InvoiceItem(BaseModel):
    id: str
    ls_invoice_id: str
    ls_invoice_url: str | None
    issued_at: datetime
    amount_usd: float
    tax_amount_usd: float | None
    total_usd: float
    currency: str


class InvoicesListResponse(BaseModel):
    data: list[InvoiceItem]


class SeatItem(BaseModel):
    id: str
    user_id: str | None
    invited_email: str
    accepted_at: datetime | None
    role: str


class SeatsListResponse(BaseModel):
    subscription_id: str
    plan_code: str
    seat_count: int
    seats: list[SeatItem]


class SeatInviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="editor", pattern="^(admin|editor)$")


class SeatInviteResponse(BaseModel):
    seat_id: str
    invite_url: str
    invited_email: str


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/plans", response_model=PlansListResponse)
async def list_plans(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlansListResponse:
    """Public — tier listesi, USD primary."""
    result = await db.execute(
        select(Plan).where(Plan.active.is_(True)).order_by(Plan.display_order)
    )
    plans = result.scalars().all()

    items = []
    for p in plans:
        # LS variant_id atanmışsa "available" — yoksa "yakında"
        available = bool(p.ls_variant_id_monthly or p.ls_variant_id_yearly)
        items.append(
            PlanResponse(
                code=p.code,
                name=p.name,
                tier=p.tier,
                price_usd_monthly=float(p.price_usd_monthly),
                price_usd_yearly=float(p.price_usd_yearly),
                price_tl_display_monthly=(
                    float(p.price_tl_display_monthly) if p.price_tl_display_monthly else None
                ),
                price_tl_display_yearly=(
                    float(p.price_tl_display_yearly) if p.price_tl_display_yearly else None
                ),
                monthly_generation_limit=p.monthly_generation_limit,
                seat_count=p.seat_count,
                features=p.features,
                available=available,
            )
        )
    return PlansListResponse(plans=items)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutRequest,
    user: Annotated[User, Depends(require_foreign_transfer_consent)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckoutResponse:
    """LS hosted checkout URL üret — kullanıcı yeni tab'da açar.

    KVKK m.9 server-side gate: kullanıcı açık rızası yoksa 403 (#470).
    LS hesap konfigüre değilse 503.
    """
    if not ls.is_configured():
        raise _billing_not_configured_503()

    # Plan + variant_id resolve
    result = await db.execute(select(Plan).where(Plan.code == payload.plan_code))
    plan = result.scalar_one_or_none()
    if plan is None or not plan.active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PLAN_NOT_FOUND", "message": "Plan bulunamadı."},
        )

    variant_id = (
        plan.ls_variant_id_monthly
        if payload.billing_cycle == "monthly"
        else plan.ls_variant_id_yearly
    )
    if not variant_id:
        # Plan tanımlı ama LS variant atanmamış (kullanıcı LS'de variant
        # tanımlamamış henüz — env vars veya DB UPDATE ile gelir).
        raise _billing_not_configured_503()

    # Mevcut active subscription var mı? — race kontrolü
    existing = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["trialing", "active", "past_due"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SUBSCRIPTION_EXISTS",
                "message": (
                    "Aktif aboneliğiniz var. Plan değişimi için "
                    "/app/billing/portal-url üzerinden yönetebilirsiniz."
                ),
            },
        )

    # LS API call
    try:
        result = await ls.create_checkout(
            variant_id=variant_id,
            user_email=user.email,
            user_id=str(user.id),
            custom_data={"plan_code": plan.code, "billing_cycle": payload.billing_cycle},
        )
    except ls.LSAPIError as e:
        logger.error("ls.checkout_failed user_id=%s plan=%s err=%s", user.id, plan.code, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "LS_API_ERROR",
                "message": "Ödeme servisinde sorun oluştu, lütfen tekrar deneyin.",
            },
        ) from e

    logger.info(
        "ls.checkout_created user_id=%s plan=%s cycle=%s variant=%s",
        user.id,
        plan.code,
        payload.billing_cycle,
        variant_id,
    )
    return CheckoutResponse(
        checkout_url=result.checkout_url,
        ls_variant_id=result.ls_variant_id,
    )


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionResponse | None:
    """Mevcut subscription durumu — yoksa null."""
    result = await db.execute(
        select(Subscription, Plan)
        .join(Plan, Subscription.plan_id == Plan.id)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["trialing", "active", "past_due", "cancelled"]),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    sub, plan = row

    # Sıradaki fatura tutarı (cycle'a göre)
    if sub.billing_cycle == "monthly":
        next_amount_usd = float(plan.price_usd_monthly)
        next_amount_tl = (
            float(plan.price_tl_display_monthly) if plan.price_tl_display_monthly else None
        )
    else:
        next_amount_usd = float(plan.price_usd_yearly)
        next_amount_tl = (
            float(plan.price_tl_display_yearly) if plan.price_tl_display_yearly else None
        )

    return SubscriptionResponse(
        plan_code=plan.code,
        plan_name=plan.name,
        status=sub.status,
        billing_cycle=sub.billing_cycle,
        trial_ends_at=sub.trial_ends_at,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        cancelled_at=sub.cancelled_at,
        ends_at=sub.ends_at,
        seat_count=sub.seat_count,
        payment_provider=sub.payment_provider,
        ls_subscription_id=sub.ls_subscription_id,
        next_invoice_amount_usd=next_amount_usd,
        next_invoice_amount_tl_display_ref=next_amount_tl,
    )


@router.get("/portal-url", response_model=PortalUrlResponse)
async def get_portal_url(
    user: Annotated[User, Depends(require_foreign_transfer_consent)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PortalUrlResponse:
    """LS Customer Portal signed URL — cancel/update card/invoice listesi.

    KVKK m.9 server-side gate (#470).
    """
    if not ls.is_configured():
        raise _billing_not_configured_503()

    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["trialing", "active", "past_due", "cancelled"]),
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None or not sub.ls_customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_SUBSCRIPTION",
                "message": "Aktif aboneliğiniz yok. Önce bir plan seçin.",
            },
        )

    try:
        portal_url = await ls.get_customer_portal_url(sub.ls_customer_id)
    except ls.LSAPIError as e:
        logger.error("ls.portal_failed user_id=%s err=%s", user.id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "LS_API_ERROR", "message": "Ödeme servisi geçici hata."},
        ) from e

    return PortalUrlResponse(portal_url=portal_url)


@router.get("/invoices", response_model=InvoicesListResponse)
async def list_invoices(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvoicesListResponse:
    """LS invoice referans listesi — gerçek PDF LS hosted (signed URL TTL'li)."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.user_id == user.id)
        .order_by(Invoice.issued_at.desc())
        .limit(50)
    )
    invoices = result.scalars().all()
    return InvoicesListResponse(
        data=[
            InvoiceItem(
                id=str(inv.id),
                ls_invoice_id=inv.ls_invoice_id,
                ls_invoice_url=inv.ls_invoice_url,
                issued_at=inv.issued_at,
                amount_usd=float(inv.amount_usd),
                tax_amount_usd=float(inv.tax_amount_usd) if inv.tax_amount_usd else None,
                total_usd=float(inv.total_usd),
                currency=inv.currency,
            )
            for inv in invoices
        ]
    )


# ---- Multi-seat Agency endpoints (#451) ------------------------------------


@router.get("/seats", response_model=SeatsListResponse)
async def list_seats(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SeatsListResponse:
    """Agency tier kullanıcısı için seat listesi."""
    sub_result = await db.execute(
        select(Subscription, Plan)
        .join(Plan, Subscription.plan_id == Plan.id)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["trialing", "active"]),
            Plan.tier == "agency",
        )
    )
    row = sub_result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_AGENCY_SUBSCRIPTION", "message": "Agency aboneliği yok."},
        )
    sub, plan = row

    seats_result = await db.execute(select(AgencySeat).where(AgencySeat.subscription_id == sub.id))
    seats = seats_result.scalars().all()

    return SeatsListResponse(
        subscription_id=str(sub.id),
        plan_code=plan.code,
        seat_count=sub.seat_count,
        seats=[
            SeatItem(
                id=str(s.id),
                user_id=str(s.user_id) if s.user_id else None,
                invited_email=s.invited_email,
                accepted_at=s.accepted_at,
                role=s.role,
            )
            for s in seats
        ],
    )


@router.post("/seats/invite", response_model=SeatInviteResponse)
async def invite_seat(
    payload: SeatInviteRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SeatInviteResponse:
    """Agency tier'a seat email daveti gönder.

    Slot dolu ise 409. Davet kabul edilmemişse aynı email'e yeniden gönderilebilir
    (UNIQUE constraint subscription_id + invited_email — re-invite yok, mevcut
    kayıt güncellenmesi için ayrı endpoint).
    """
    sub_result = await db.execute(
        select(Subscription, Plan)
        .join(Plan, Subscription.plan_id == Plan.id)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["trialing", "active"]),
            Plan.tier == "agency",
        )
    )
    row = sub_result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_AGENCY_SUBSCRIPTION", "message": "Agency aboneliği yok."},
        )
    sub, _plan = row

    # Mevcut seat sayısı
    seats_result = await db.execute(select(AgencySeat).where(AgencySeat.subscription_id == sub.id))
    seats = list(seats_result.scalars().all())
    if len(seats) >= sub.seat_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SEAT_LIMIT_EXCEEDED",
                "message": (
                    f"Plan koltuk limiti dolu ({sub.seat_count}/{sub.seat_count}). "
                    f"Daha fazla koltuk için planı yükseltin."
                ),
            },
        )

    # Email zaten davetli mi
    for s in seats:
        if s.invited_email.lower() == payload.email.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "EMAIL_ALREADY_INVITED",
                    "message": "Bu e-posta zaten davet edilmiş.",
                },
            )

    invite_token = secrets.token_urlsafe(32)
    seat = AgencySeat(
        subscription_id=sub.id,
        invited_email=payload.email.lower(),
        invite_token=invite_token,
        role=payload.role,
    )
    db.add(seat)
    await db.commit()
    await db.refresh(seat)

    settings = get_settings()
    invite_url = f"{settings.next_public_app_url}/app/seats/accept?token={invite_token}"

    # TODO #451 — Resend email gönderim entegrasyonu sonradan
    logger.info(
        "agency_seat.invited subscription=%s email=%s role=%s",
        sub.id,
        payload.email,
        payload.role,
    )

    return SeatInviteResponse(
        seat_id=str(seat.id),
        invite_url=invite_url,
        invited_email=payload.email,
    )


@router.delete("/seats/{seat_id}")
async def remove_seat(
    seat_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Agency tier'dan seat çıkar — davet iptal veya kabul edilmiş seat silinir."""
    sub_result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["trialing", "active"]),
        )
    )
    sub = sub_result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_SUBSCRIPTION", "message": "Aktif abonelik yok."},
        )

    seat_result = await db.execute(
        select(AgencySeat).where(
            AgencySeat.id == seat_id,
            AgencySeat.subscription_id == sub.id,
        )
    )
    seat = seat_result.scalar_one_or_none()
    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SEAT_NOT_FOUND", "message": "Koltuk bulunamadı."},
        )

    await db.delete(seat)
    await db.commit()

    logger.info("agency_seat.removed seat_id=%s subscription=%s", seat_id, sub.id)
    return {"removed": True, "seat_id": str(seat_id)}
