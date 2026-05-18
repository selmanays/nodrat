"""RSS realtime polling Faz 2 — sources tier shadow mode + telemetry (#578)

Forward-compatible: yeni 3 kolon nullable; 2 app_settings flag default'ları
shadow mode (hesap var, uygulama yok) → davranış değişmez.

Faz 0+1 (#565, migration 20260510_0100) zaten ekledi:
  - sources.polling_tier (default 'normal'), consecutive_unchanged, etag, ...

Bu Faz 2:
  - sources.would_be_tier      : shadow mode hesabının yazılacağı kolon
  - sources.tier_changed_at    : dwell-time guard (15dk minimum)
  - sources.tier_metadata      : telemetry JSONB (items_1h, items_6h, ...)
  - app_settings.rss.tier_shadow_mode (default true)
  - app_settings.rss.tier_apply_enabled (default false; Faz 3'te true)

Revision ID: 20260510_0400
Revises: 20260510_0300
Create Date: 2026-05-10 04:00:00 UTC

NOT: İlk PR'da revision='20260510_0200' yazıldı; PR #571 sonrası main'e gelen
PR #575 (generations SFT telemetry) ve PR #574 (users model_improvement_consent)
'20260510_0200' ve '20260510_0300' revision'larını aldı. Branched migration
çakışmasını önlemek için bu migration zincirin sonuna alındı (revision =
20260510_0400, down_revision = 20260510_0300). Şema tarafsız (#578 hotfix).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260510_0400"
down_revision = "20260510_0300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("would_be_tier", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column(
            "tier_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "tier_metadata",
            postgresql.JSONB(),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_sources_would_be_tier",
        "sources",
        "would_be_tier IS NULL OR would_be_tier IN ('hot', 'normal', 'cold', 'hibernate')",
    )

    op.execute(
        sa.text(
            """
            INSERT INTO app_settings
                (key, value, type, group_name, description, updated_at, created_at)
            VALUES
                (
                    'rss.tier_shadow_mode',
                    'true'::jsonb,
                    'bool',
                    'rss',
                    'Adaptive tier hesabı shadow modda çalışır (hesap var, uygulama yok). Faz 2 default true; 7 gün gözlem sonrası Faz 3''te false yapılıp tier_apply_enabled=true ile aktif edilir.',
                    NOW(),
                    NOW()
                ),
                (
                    'rss.tier_apply_enabled',
                    'false'::jsonb,
                    'bool',
                    'rss',
                    'Adaptive tier hesabını polling_tier''a UYGULA. shadow_mode=false + apply_enabled=true → polling_tier = would_be_tier transition. Faz 2''de false; Faz 3''te beat refactor ve worker concurrency artışıyla birlikte true yapılır.',
                    NOW(),
                    NOW()
                )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM app_settings "
            "WHERE key IN ('rss.tier_shadow_mode', 'rss.tier_apply_enabled')"
        )
    )
    op.drop_constraint("ck_sources_would_be_tier", "sources", type_="check")
    op.drop_column("sources", "tier_metadata")
    op.drop_column("sources", "tier_changed_at")
    op.drop_column("sources", "would_be_tier")
