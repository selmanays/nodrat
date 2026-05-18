"""Billing models — Lemon Squeezy MoR (Epic #448, #53).

docs/engineering/data-model.md §6, §8 (Faz 6 billing schema)
docs/strategy/pricing-strategy.md §2 (tier matrix, USD primary)

Models:
    Plan              — Tier tanımları (USD primary, ls_variant_id mapping)
    Subscription      — Aktif abonelikler (LS-aware: ls_subscription_id, ls_customer_id, seat_count)
    Invoice           — LS invoice referans cache (PDF link, KDV LS keser)
    AgencySeat        — Multi-seat invitation/accept (#451)
    WebhookEvent      — LS webhook idempotency log (#450)

LS field naming: `ls_*` prefix, payment_provider VARCHAR(32) DEFAULT 'lemon_squeezy'.
Pivot path: PaymentProvider abstraction (architecture.md §A3) — Paddle scaffold #471
ile aynı schema kullanır (ls_* alanları paddle_* ile şarjö değişimi yapılmaz, sadece
ek payment_provider değer kabul eder; sub-issue #471 implementation kararı verir).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Plan(Base):
    """Tier tanımı — USD primary, LS variant mapping.

    Seed: Migration 20260509_0400 ile 6 plan (free + starter + pro + agency_3/5/10)
    eklenir. ls_variant_id_* NULL placeholder; kullanıcı LS hesap açtığında doldurur.
    """

    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    """'free', 'starter', 'pro', 'agency_3', 'agency_5', 'agency_10'"""

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    """'Pro', 'Agency (3 koltuk)' — kullanıcıya gösterilen ad"""

    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    """'starter', 'pro', 'agency' — User.tier ile eşleştirme"""

    # Pricing (USD primary; TL display referans)
    price_usd_monthly: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    price_usd_yearly: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    price_tl_display_monthly: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_tl_display_yearly: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    # LS variant ID mapping (kullanıcı manuel)
    ls_variant_id_monthly: Mapped[str | None] = mapped_column(String(180))
    ls_variant_id_yearly: Mapped[str | None] = mapped_column(String(180))

    # Limits
    monthly_generation_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    seat_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    max_context_cards: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("10")
    )

    # Feature flags (allowed_models, comparison_mode, style_profiles, ...)
    features: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Subscription(Base):
    """Aktif abonelik — LS-aware schema."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'cancelled', 'expired')",
            name="ck_subscriptions_status",
        ),
        CheckConstraint(
            "billing_cycle IN ('monthly', 'yearly')",
            name="ck_subscriptions_billing_cycle",
        ),
        CheckConstraint(
            "seat_count >= 1 AND seat_count <= 50",
            name="ck_subscriptions_seat_count",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'trialing'")
    )
    billing_cycle: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'monthly'")
    )

    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Lemon Squeezy referansları
    payment_provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'lemon_squeezy'"),
    )
    ls_subscription_id: Mapped[str | None] = mapped_column(String(180))
    ls_customer_id: Mapped[str | None] = mapped_column(String(180))
    ls_variant_id: Mapped[str | None] = mapped_column(String(180))
    ls_order_id: Mapped[str | None] = mapped_column(String(180))

    seat_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    extra_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata",  # DB column name
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Invoice(Base):
    """LS invoice referans cache — PDF LS hosted, Nodrat fatura kesmez."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    # LS referans
    ls_invoice_id: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    ls_invoice_url: Mapped[str | None] = mapped_column(Text)
    ls_order_id: Mapped[str | None] = mapped_column(String(180))

    # Tutar
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tax_amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    total_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'USD'"))
    fx_rate_tl: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    extra_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgencySeat(Base):
    """Multi-seat Agency invitation/accept (#451)."""

    __tablename__ = "agency_seats"
    __table_args__ = (CheckConstraint("role IN ('admin', 'editor')", name="ck_agency_seats_role"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    """nullable: davet kabul edilmemiş seat (kullanıcı henüz hesap oluşturmamış)"""

    invited_email: Mapped[str] = mapped_column(String(180), nullable=False)
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'editor'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WebhookEvent(Base):
    """LS webhook idempotency log (#450)."""

    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'lemon_squeezy'"),
    )
    ls_event_id: Mapped[str] = mapped_column(String(180), nullable=False)
    """LS event UUID — (provider, ls_event_id) UNIQUE = idempotency key"""

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
