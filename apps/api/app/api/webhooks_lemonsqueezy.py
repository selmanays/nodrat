"""Lemon Squeezy webhook handler (#450, Epic #448).

docs/engineering/api-contracts.md §15 (Webhook spec)
docs/legal/payment-fallback-plan.md (R-FIN-04 fallback)

Endpoint:
    POST /api/webhooks/lemonsqueezy

Headers:
    X-Event-Name: subscription_created | subscription_updated | ...
    X-Signature:  HMAC SHA256 hex of body with LEMONSQUEEZY_SIGNING_SECRET

Idempotency: webhook_events tablosu (provider, ls_event_id) UNIQUE.
Aynı event 2x → 200 ack (no-op).

7 event tipi:
    subscription_created            → Subscription row insert (trialing veya active)
    subscription_updated            → variant değişimi (plan upgrade/downgrade)
    subscription_cancelled          → status='cancelled', ends_at set
    subscription_resumed            → status='active' (cancellation revoked)
    subscription_payment_success    → last_paid_at + Invoice insert
    subscription_payment_failed     → status='past_due'
    subscription_payment_recovered  → status='active'

Response:
    200 OK                  → event işlendi (veya idempotent skip)
    401 Unauthorized        → signature verify fail
    400 Bad Request         → unknown event_type / malformed payload
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.billing import Invoice, Plan, Subscription, WebhookEvent
from app.providers import lemonsqueezy as ls


logger = logging.getLogger(__name__)
router = APIRouter()


SUPPORTED_EVENTS = {
    "subscription_created",
    "subscription_updated",
    "subscription_cancelled",
    "subscription_resumed",
    "subscription_payment_success",
    "subscription_payment_failed",
    "subscription_payment_recovered",
}


def _parse_iso(s: str | None) -> datetime | None:
    """LS ISO 8601 → datetime (timezone-aware)."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _resolve_user_id(payload: dict[str, Any], db: AsyncSession) -> str | None:
    """LS payload'undan user_id çıkar — custom_data'da gelmiş olmalı."""
    meta = payload.get("meta", {})
    custom = meta.get("custom_data", {}) or {}
    user_id = custom.get("user_id")
    if user_id:
        return str(user_id)
    return None


async def _resolve_plan_by_variant(variant_id: str, db: AsyncSession) -> Plan | None:
    """LS variant_id → Plan row (monthly veya yearly variant ile match)."""
    result = await db.execute(
        select(Plan).where(
            (Plan.ls_variant_id_monthly == str(variant_id))
            | (Plan.ls_variant_id_yearly == str(variant_id))
        )
    )
    return result.scalar_one_or_none()


async def _handle_subscription_created(
    payload: dict[str, Any], db: AsyncSession
) -> str:
    """Yeni subscription row insert — trialing veya active."""
    data = payload["data"]
    attrs = data["attributes"]
    ls_subscription_id = str(data["id"])
    user_id_str = await _resolve_user_id(payload, db)
    if not user_id_str:
        return "user_id missing in custom_data"

    plan = await _resolve_plan_by_variant(str(attrs["variant_id"]), db)
    if plan is None:
        return f"plan not found for variant_id={attrs['variant_id']}"

    # Mevcut subscription var mı (idempotent guard — webhook 2x gelebilir)
    existing = await db.execute(
        select(Subscription).where(Subscription.ls_subscription_id == ls_subscription_id)
    )
    if existing.scalar_one_or_none():
        return "subscription already exists (idempotent skip)"

    # billing_cycle: variant monthly mi yearly mi
    billing_cycle = (
        "yearly" if str(attrs["variant_id"]) == plan.ls_variant_id_yearly else "monthly"
    )

    sub = Subscription(
        user_id=user_id_str,
        plan_id=plan.id,
        status=attrs["status"],
        billing_cycle=billing_cycle,
        trial_ends_at=_parse_iso(attrs.get("trial_ends_at")),
        current_period_start=_parse_iso(attrs.get("created_at")) or datetime.now(UTC),
        current_period_end=_parse_iso(attrs.get("renews_at")) or datetime.now(UTC),
        ls_subscription_id=ls_subscription_id,
        ls_customer_id=str(attrs["customer_id"]),
        ls_variant_id=str(attrs["variant_id"]),
        ls_order_id=str(attrs.get("order_id")) if attrs.get("order_id") else None,
        seat_count=plan.seat_count,
    )
    db.add(sub)

    return "subscription created"


async def _handle_subscription_updated(
    payload: dict[str, Any], db: AsyncSession
) -> str:
    """Variant değişimi (plan upgrade/downgrade) veya status update."""
    data = payload["data"]
    attrs = data["attributes"]
    ls_subscription_id = str(data["id"])

    result = await db.execute(
        select(Subscription).where(Subscription.ls_subscription_id == ls_subscription_id)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return f"subscription not found for ls_subscription_id={ls_subscription_id}"

    new_variant_id = str(attrs["variant_id"])
    if new_variant_id != sub.ls_variant_id:
        # Plan değişimi
        plan = await _resolve_plan_by_variant(new_variant_id, db)
        if plan is not None:
            sub.plan_id = plan.id
            sub.seat_count = plan.seat_count
            sub.ls_variant_id = new_variant_id
            sub.billing_cycle = (
                "yearly" if new_variant_id == plan.ls_variant_id_yearly else "monthly"
            )

    sub.status = attrs["status"]
    sub.current_period_end = _parse_iso(attrs.get("renews_at")) or sub.current_period_end
    sub.cancelled_at = _parse_iso(attrs.get("cancelled_at"))
    sub.ends_at = _parse_iso(attrs.get("ends_at"))
    sub.updated_at = datetime.now(UTC)

    return f"subscription updated: status={attrs['status']}"


async def _handle_subscription_cancelled(
    payload: dict[str, Any], db: AsyncSession
) -> str:
    data = payload["data"]
    attrs = data["attributes"]
    ls_subscription_id = str(data["id"])

    result = await db.execute(
        select(Subscription).where(Subscription.ls_subscription_id == ls_subscription_id)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return f"subscription not found"

    sub.status = "cancelled"
    sub.cancelled_at = _parse_iso(attrs.get("cancelled_at")) or datetime.now(UTC)
    sub.ends_at = _parse_iso(attrs.get("ends_at")) or sub.current_period_end
    sub.updated_at = datetime.now(UTC)
    return "subscription cancelled"


async def _handle_subscription_resumed(
    payload: dict[str, Any], db: AsyncSession
) -> str:
    data = payload["data"]
    ls_subscription_id = str(data["id"])

    result = await db.execute(
        select(Subscription).where(Subscription.ls_subscription_id == ls_subscription_id)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return "subscription not found"

    sub.status = "active"
    sub.cancelled_at = None
    sub.ends_at = None
    sub.updated_at = datetime.now(UTC)
    return "subscription resumed"


async def _handle_payment_success(
    payload: dict[str, Any], db: AsyncSession
) -> str:
    """Invoice row insert + last_paid_at update."""
    data = payload["data"]
    attrs = data["attributes"]

    ls_subscription_id = str(attrs.get("subscription_id"))
    result = await db.execute(
        select(Subscription).where(Subscription.ls_subscription_id == ls_subscription_id)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return f"subscription not found for ls_id={ls_subscription_id}"

    sub.last_paid_at = datetime.now(UTC)

    # Invoice cache
    ls_invoice_id = str(data["id"])
    existing = await db.execute(
        select(Invoice).where(Invoice.ls_invoice_id == ls_invoice_id)
    )
    if existing.scalar_one_or_none():
        return "invoice already cached (idempotent)"

    invoice = Invoice(
        subscription_id=sub.id,
        user_id=sub.user_id,
        ls_invoice_id=ls_invoice_id,
        ls_invoice_url=attrs.get("urls", {}).get("invoice_url")
        or attrs.get("invoice_url"),
        ls_order_id=str(attrs.get("order_id")) if attrs.get("order_id") else None,
        amount_usd=float(attrs.get("subtotal", 0)) / 100.0,
        # LS amounts in cents
        tax_amount_usd=float(attrs.get("tax", 0)) / 100.0 if attrs.get("tax") else None,
        total_usd=float(attrs.get("total", 0)) / 100.0,
        currency=attrs.get("currency", "USD"),
        issued_at=_parse_iso(attrs.get("created_at")) or datetime.now(UTC),
        paid_at=datetime.now(UTC),
    )
    db.add(invoice)
    return f"invoice created: ls_invoice_id={ls_invoice_id}"


async def _handle_payment_failed(payload: dict[str, Any], db: AsyncSession) -> str:
    data = payload["data"]
    attrs = data["attributes"]
    ls_subscription_id = str(attrs.get("subscription_id"))

    result = await db.execute(
        select(Subscription).where(Subscription.ls_subscription_id == ls_subscription_id)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return "subscription not found"
    sub.status = "past_due"
    sub.updated_at = datetime.now(UTC)
    return "subscription marked past_due"


async def _handle_payment_recovered(
    payload: dict[str, Any], db: AsyncSession
) -> str:
    data = payload["data"]
    attrs = data["attributes"]
    ls_subscription_id = str(attrs.get("subscription_id"))

    result = await db.execute(
        select(Subscription).where(Subscription.ls_subscription_id == ls_subscription_id)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return "subscription not found"
    sub.status = "active"
    sub.last_paid_at = datetime.now(UTC)
    sub.updated_at = datetime.now(UTC)
    return "subscription recovered to active"


EVENT_HANDLERS = {
    "subscription_created": _handle_subscription_created,
    "subscription_updated": _handle_subscription_updated,
    "subscription_cancelled": _handle_subscription_cancelled,
    "subscription_resumed": _handle_subscription_resumed,
    "subscription_payment_success": _handle_payment_success,
    "subscription_payment_failed": _handle_payment_failed,
    "subscription_payment_recovered": _handle_payment_recovered,
}


@router.post("/lemonsqueezy", status_code=status.HTTP_200_OK)
async def lemonsqueezy_webhook(
    request: Request,
    x_event_name: Annotated[str | None, Header()] = None,
    x_signature: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """LS webhook entry point — signature verify + idempotent dispatch."""
    body = await request.body()

    # 1. Signature verification
    if not x_signature or not ls.verify_webhook_signature(body, x_signature):
        logger.warning(
            "ls.webhook.signature_invalid event=%s body_len=%d",
            x_event_name,
            len(body),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_signature"},
        )

    # 2. Event type kontrol
    if not x_event_name or x_event_name not in SUPPORTED_EVENTS:
        # Unknown event → 200 ack (LS bilinmeyen event'leri yeniden denemesin)
        logger.info("ls.webhook.unknown_event event=%s (acked)", x_event_name)
        return {"status": "ignored", "reason": f"unknown_event_type: {x_event_name}"}

    # 3. Payload parse
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "malformed_json", "message": str(e)},
        ) from e

    # 4. Idempotency: ls_event_id (meta.event_id veya request body'de farklı yerde)
    meta = payload.get("meta", {}) or {}
    ls_event_id = str(
        meta.get("event_id")
        or meta.get("webhook_id")
        or payload.get("data", {}).get("id", f"unknown_{datetime.now(UTC).timestamp()}")
    )

    # webhook_events insert (UNIQUE constraint duplicate'i yakalar)
    event_row = WebhookEvent(
        provider="lemon_squeezy",
        ls_event_id=ls_event_id,
        event_type=x_event_name,
        payload=payload,
        signature_valid=True,
    )
    db.add(event_row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        # Aynı event 2x — idempotent skip
        logger.info(
            "ls.webhook.duplicate ls_event_id=%s event=%s (idempotent skip)",
            ls_event_id,
            x_event_name,
        )
        return {"status": "duplicate", "ls_event_id": ls_event_id}

    # 5. Dispatch
    handler = EVENT_HANDLERS[x_event_name]
    try:
        message = await handler(payload, db)
        event_row.processed_at = datetime.now(UTC)
        await db.commit()
        logger.info(
            "ls.webhook.processed event=%s ls_event_id=%s result=%s",
            x_event_name,
            ls_event_id,
            message,
        )
        return {"status": "processed", "message": message}
    except Exception as e:
        await db.rollback()
        # Re-fetch event_row (rollback yaptık) — error_message kaydı için
        # Ayrı transaction ile yaz
        async with db.bind.connect() as conn:  # type: ignore[attr-defined]
            from sqlalchemy import update as sa_update

            await conn.execute(
                sa_update(WebhookEvent.__table__)
                .where(WebhookEvent.__table__.c.ls_event_id == ls_event_id)
                .values(error_message=str(e)[:500])
            )
            await conn.commit()
        logger.error(
            "ls.webhook.handler_error event=%s ls_event_id=%s err=%s",
            x_event_name,
            ls_event_id,
            e,
        )
        # 500 dön → LS retry yapsın (recoverable error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "handler_error", "message": str(e)},
        ) from e
