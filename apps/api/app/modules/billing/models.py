"""Billing ORM — UsageEvent (#27, #800 S1B post-cleanup).

T8-17 (2026-05-28): `app/models/generation.py`'den buraya taşındı (billing domain
sahiplenir; quota tracking + cost ledger). generations YAZAR ama billing OWNS
(master plan §2.4 + T8 mini-plan açık soru 5). T7-2 ile quota service zaten
billing/services'e taşınmıştı → model same-module gelince zincir billing'de TAM.
T8-16 (2026-05-28): Plan + Subscription + Invoice + AgencySeat + WebhookEvent
(Lemon Squeezy billing, Epic #448) `app/models/billing.py`'den buraya eklendi —
billing domain modelleri TAM bu dosyada.

NOT: Generation + SavedGeneration sınıfları #800 S1B'de KALDIRILDI
(research-only migration). Sadece UsageEvent kalır — quota tracking + cost
ledger için. `generation_id` kolonu DB'de nullable kalır (migration
20260514_1700) ama modelde tanımlı değil; tarihçe veri "anonim" referans.

docs/engineering/data-model.md §5.2 (UsageEvent)
PRD §3.7 (quota)
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
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UsageEvent(Base):
    """Quota tracking + cost ledger — sliding window query'ler için index'li."""

    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """'generation' | 'embedding' | 'login' | 'save' | 'export'"""

    provider: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(120))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))

    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_usage_events_user_created", "user_id", text("created_at DESC")),
        Index("idx_usage_events_type", "event_type", text("created_at DESC")),
        Index(
            "idx_usage_events_user_type_created",
            "user_id",
            "event_type",
            text("created_at DESC"),
        ),
    )


class Plan(Base):
    """Tier tanımı — USD primary, LS variant mapping.

    Seed: Migration 20260509_0400 ile 6 plan (free + starter + pro + agency_3/5/10)
    eklenir. ls_variant_id_* NULL placeholder; kullanıcı LS hesap açtığında doldurur.
    """

    __tablename__ = "plans"
    __table_args__ = (
        # Phase 8.2 PR-8.2-7: DB'de mevcut
        # Migration: 20260509_0400_lemon_squeezy_billing_schema.py
        # Aktif plan listesi — UI dropdown sıralı
        Index("idx_plans_active_order", "active", "display_order"),
    )

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
        # Partial UQ — bir aktif subscription per user (Pricing §2.4)
        # Migration: 20260509_0400_lemon_squeezy_billing_schema.py
        Index(
            "uniq_subscriptions_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('trialing', 'active', 'past_due')"),
        ),
        # Partial UQ — LS subscription_id idempotency (NULL bırakılabilir trial)
        Index(
            "idx_subscriptions_ls_subscription_id",
            "ls_subscription_id",
            unique=True,
            postgresql_where=text("ls_subscription_id IS NOT NULL"),
        ),
        # Phase 8.2 PR-8.2-13a (PR-8.2-7 follow-up): plain Index on (status, current_period_end).
        # Migration: 20260509_0400_lemon_squeezy_billing_schema.py L203-207
        # `op.create_index("idx_subscriptions_status_period", "subscriptions",
        # ["status", "current_period_end"])` — no partial, no unique.
        # PR-8.2-2 yalnız UQ-focused (2 partial unique); PR-8.2-7 farklı tabloları
        # kapsadı. Bu plain Index ikisinin de scope dışına düştü → alembic check
        # strict gate (PR-8.2-13) ilk run'da yakaladı (CI run #26364214021).
        Index(
            "idx_subscriptions_status_period",
            "status",
            "current_period_end",
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
    __table_args__ = (
        # Phase 8.2 PR-8.2-7: DB'de mevcut
        # Migration: 20260509_0400_lemon_squeezy_billing_schema.py
        # User invoice history sorgu
        Index("idx_invoices_user_created", "user_id", "created_at"),
    )

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
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'editor')", name="ck_agency_seats_role"),
        # Migration: 20260509_0400_lemon_squeezy_billing_schema.py
        # Bir invitation token / subscription başına 1 email
        UniqueConstraint(
            "subscription_id",
            "invited_email",
            name="uniq_agency_seats_email_per_subscription",
        ),
        # Phase 8.2 PR-8.2-7: subscription seat list sorgu
        Index("idx_agency_seats_subscription", "subscription_id"),
    )

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
    __table_args__ = (
        # Migration: 20260509_0400_lemon_squeezy_billing_schema.py
        # LS event idempotency key — aynı event 2× işlenmez
        UniqueConstraint(
            "provider",
            "ls_event_id",
            name="uniq_webhook_events_ls_event_id",
        ),
        # Phase 8.2 PR-8.2-7: Worker poll için pending event'ler
        Index(
            "idx_webhook_events_unprocessed",
            "created_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
    )

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
