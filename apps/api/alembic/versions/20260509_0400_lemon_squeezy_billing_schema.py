"""Lemon Squeezy MoR billing schema (#53, #450, #451, Epic #448)

Faz 6 ödeme altyapısı için 5 tablo:
  plans            — Tier tanımları (USD primary, ls_variant_id mapping)
  subscriptions    — Aktif abonelikler (ls_subscription_id, ls_customer_id, seat_count)
  invoices         — LS invoice referans cache (LS hosted PDF, KDV LS keser)
  agency_seats     — Multi-seat Agency invitation/accept (#451)
  webhook_events   — LS webhook idempotency log (#450)

Mevcut user'lar (Pro tier) için backward-compat:
  - plans seed migration sonrası UPDATE script'i ile doldurulur
  - Mevcut Pro user'lara subscription kaydı gerekirse manuel
  - Bu migration tablo oluşturma + seed plans (5 tier × 2 cycle = 10 row)

Tüm fiyatlar USD primary; tl_display_ref sadece referans (anlık FX).
LS variant_id'leri kullanıcı LS hesabını açtığında doldurulur — mevcut seed
NULL placeholder ile gelir, /admin/plans UI'dan veya direkt DB'den UPDATE ile
girilir.

Revision ID: 20260509_0400
Revises: 20260509_0300
Create Date: 2026-05-09 04:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260509_0400"
down_revision = "20260509_0300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =====================================================================
    # plans — tier tanımları (USD primary)
    # =====================================================================
    op.create_table(
        "plans",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        # 'starter', 'pro', 'agency_3', 'agency_5', 'agency_10'
        sa.Column("name", sa.String(80), nullable=False),
        # 'Starter', 'Pro', 'Agency (3 koltuk)', ...
        sa.Column("tier", sa.String(32), nullable=False),
        # 'starter', 'pro', 'agency' (kullanıcı tier'ı eşleştirme)
        # Pricing
        sa.Column("price_usd_monthly", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_usd_yearly", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_tl_display_monthly", sa.Numeric(10, 2)),
        sa.Column("price_tl_display_yearly", sa.Numeric(10, 2)),
        # LS variant ID mapping (kullanıcı LS hesabı açtığında doldurulur)
        sa.Column("ls_variant_id_monthly", sa.String(180)),
        sa.Column("ls_variant_id_yearly", sa.String(180)),
        # Limitler
        sa.Column("monthly_generation_limit", sa.Integer, nullable=False),
        sa.Column("seat_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("max_context_cards", sa.Integer, nullable=False, server_default="10"),
        # Feature flags (JSONB esnek)
        sa.Column(
            "features",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # 'allowed_models': ['deepseek_v4_flash'],
        # 'comparison_mode': false,
        # 'style_profiles': false,
        # 'visual_features': false,
        # 'analysis_output': false,
        # 'concurrent_gen': 1,
        # 'rate_per_hour': 5,
        # 'support_sla_hours': 48,
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_plans_active_order", "plans", ["active", "display_order"])

    # =====================================================================
    # subscriptions — aktif abonelikler (LS-aware)
    # =====================================================================
    op.create_table(
        "subscriptions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("plans.id"),
            nullable=False,
        ),
        # Status state machine: 'trialing' | 'active' | 'past_due' | 'cancelled' | 'expired'
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'trialing'"),
        ),
        # Billing cycle
        sa.Column(
            "billing_cycle",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'monthly'"),
        ),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True)),
        sa.Column(
            "current_period_start",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "current_period_end",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        # Iptal sonrası erişim sonu (current_period_end ile aynı genelde)
        sa.Column("last_paid_at", sa.DateTime(timezone=True)),
        # Lemon Squeezy referansları (Epic #448)
        sa.Column("payment_provider", sa.String(32), nullable=False, server_default=sa.text("'lemon_squeezy'")),
        sa.Column("ls_subscription_id", sa.String(180)),
        sa.Column("ls_customer_id", sa.String(180)),
        sa.Column("ls_variant_id", sa.String(180)),
        sa.Column("ls_order_id", sa.String(180)),
        # Multi-seat (#451)
        sa.Column("seat_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "metadata",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'cancelled', 'expired')",
            name="ck_subscriptions_status",
        ),
        sa.CheckConstraint(
            "billing_cycle IN ('monthly', 'yearly')",
            name="ck_subscriptions_billing_cycle",
        ),
        sa.CheckConstraint(
            "seat_count >= 1 AND seat_count <= 50",
            name="ck_subscriptions_seat_count",
        ),
    )
    # Sadece bir aktif subscription per user (Pricing §2.4)
    op.create_index(
        "uniq_subscriptions_active_per_user",
        "subscriptions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
    )
    op.create_index(
        "idx_subscriptions_status_period",
        "subscriptions",
        ["status", "current_period_end"],
    )
    op.create_index(
        "idx_subscriptions_ls_subscription_id",
        "subscriptions",
        ["ls_subscription_id"],
        unique=True,
        postgresql_where=sa.text("ls_subscription_id IS NOT NULL"),
    )

    # =====================================================================
    # invoices — LS invoice referans cache
    # =====================================================================
    # Nodrat fatura kesmez (LS MoR keser). Bu tablo LS invoice metadata'sını
    # cache'ler — kullanıcıya gösterilen "fatura listesi" buradan render edilir
    # (LS hosted PDF link).
    op.create_table(
        "invoices",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "subscription_id",
            UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        # LS referans (LS invoice resmi sahibi)
        sa.Column("ls_invoice_id", sa.String(180), nullable=False, unique=True),
        sa.Column("ls_invoice_url", sa.Text),
        # LS hosted PDF URL (signed, expires after TTL)
        sa.Column("ls_order_id", sa.String(180)),
        # Tutar (USD primary; TL display ref opsiyonel)
        sa.Column("amount_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("tax_amount_usd", sa.Numeric(10, 2)),
        sa.Column("total_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("fx_rate_tl", sa.Numeric(10, 4)),
        # LS lifecycle
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column(
            "metadata",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_invoices_user_created", "invoices", ["user_id", "created_at"])

    # =====================================================================
    # agency_seats — multi-seat Agency invitation/accept (#451)
    # =====================================================================
    op.create_table(
        "agency_seats",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "subscription_id",
            UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        # nullable: davet kabul edilmemiş seat
        sa.Column("invited_email", sa.String(180), nullable=False),
        sa.Column("invite_token", sa.String(64)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "role",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'editor'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'editor')",
            name="ck_agency_seats_role",
        ),
    )
    op.create_unique_constraint(
        "uniq_agency_seats_invite_token",
        "agency_seats",
        ["invite_token"],
    )
    op.create_unique_constraint(
        "uniq_agency_seats_email_per_subscription",
        "agency_seats",
        ["subscription_id", "invited_email"],
    )
    op.create_index(
        "idx_agency_seats_subscription",
        "agency_seats",
        ["subscription_id"],
    )

    # =====================================================================
    # webhook_events — LS webhook idempotency log (#450)
    # =====================================================================
    op.create_table(
        "webhook_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "provider",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'lemon_squeezy'"),
        ),
        sa.Column("ls_event_id", sa.String(180), nullable=False),
        # LS event UUID — idempotency key
        sa.Column("event_type", sa.String(64), nullable=False),
        # 'subscription_created', 'subscription_updated', etc.
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("signature_valid", sa.Boolean, nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uniq_webhook_events_ls_event_id",
        "webhook_events",
        ["provider", "ls_event_id"],
    )
    op.create_index(
        "idx_webhook_events_unprocessed",
        "webhook_events",
        ["created_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )

    # =====================================================================
    # Seed plans — 5 tier × 2 cycle (USD primary)
    # ls_variant_id NULL — kullanıcı LS hesap açtığında /admin/plans UI'dan
    # veya doğrudan DB UPDATE ile doldurulur.
    # =====================================================================
    op.execute(
        sa.text(
            """
            INSERT INTO plans (
                code, name, tier,
                price_usd_monthly, price_usd_yearly,
                price_tl_display_monthly, price_tl_display_yearly,
                monthly_generation_limit, seat_count, max_context_cards,
                features, active, display_order
            ) VALUES
            (
                'free', 'Free', 'free',
                0, 0,
                0, 0,
                10, 1, 5,
                '{"allowed_models": ["deepseek_v4_flash"], "comparison_mode": false, "style_profiles": false, "visual_features": false, "analysis_output": false, "concurrent_gen": 1, "rate_per_hour": 5, "support_sla_hours": 0}'::jsonb,
                true, 0
            ),
            (
                'starter', 'Starter', 'starter',
                8, 80,
                249, 2490,
                100, 1, 10,
                '{"allowed_models": ["deepseek_v4_flash"], "comparison_mode": false, "style_profiles": false, "visual_features": false, "analysis_output": false, "concurrent_gen": 2, "rate_per_hour": 20, "support_sla_hours": 48}'::jsonb,
                true, 1
            ),
            (
                'pro', 'Pro', 'pro',
                24, 240,
                749, 7490,
                500, 1, 20,
                '{"allowed_models": ["deepseek_v4_flash", "claude_haiku_4_5"], "comparison_mode": true, "style_profiles": true, "style_profiles_slots": 3, "visual_features": true, "analysis_output": true, "concurrent_gen": 3, "rate_per_hour": 60, "support_sla_hours": 24}'::jsonb,
                true, 2
            ),
            (
                'agency_3', 'Agency (3 koltuk)', 'agency',
                79, 790,
                2499, 24990,
                2500, 3, 50,
                '{"allowed_models": ["deepseek_v4_flash", "claude_haiku_4_5", "claude_sonnet_4_6"], "comparison_mode": true, "comparison_premium_model": true, "style_profiles": true, "style_profiles_slots": 10, "visual_features": true, "visual_premium_vlm": true, "analysis_output": true, "concurrent_gen": 5, "rate_per_hour": 120, "support_sla_hours": 12, "bulk_export": true}'::jsonb,
                true, 3
            ),
            (
                'agency_5', 'Agency (5 koltuk)', 'agency',
                129, 1290,
                4090, 40900,
                2500, 5, 50,
                '{"allowed_models": ["deepseek_v4_flash", "claude_haiku_4_5", "claude_sonnet_4_6"], "comparison_mode": true, "comparison_premium_model": true, "style_profiles": true, "style_profiles_slots": 10, "visual_features": true, "visual_premium_vlm": true, "analysis_output": true, "concurrent_gen": 5, "rate_per_hour": 120, "support_sla_hours": 12, "bulk_export": true}'::jsonb,
                true, 4
            ),
            (
                'agency_10', 'Agency (10 koltuk)', 'agency',
                249, 2490,
                7890, 78900,
                2500, 10, 50,
                '{"allowed_models": ["deepseek_v4_flash", "claude_haiku_4_5", "claude_sonnet_4_6"], "comparison_mode": true, "comparison_premium_model": true, "style_profiles": true, "style_profiles_slots": 10, "visual_features": true, "visual_premium_vlm": true, "analysis_output": true, "concurrent_gen": 5, "rate_per_hour": 120, "support_sla_hours": 12, "bulk_export": true}'::jsonb,
                true, 5
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("agency_seats")
    op.drop_table("invoices")
    op.drop_table("subscriptions")
    op.drop_table("plans")
