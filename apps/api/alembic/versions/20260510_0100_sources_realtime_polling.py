"""RSS realtime polling Faz 0+1 — sources schema + Conditional GET fields (#565)

Forward-compatible: kolonlar nullable veya default eski davranışa eş.

5 yeni kolon eklenir:
  - etag, last_modified : Conditional GET (HTTP 304 destek için)
  - realtime_enabled    : per-source opt-in flag (default false)
  - polling_tier        : adaptive tier hesabı için (Faz 2'de doldurulur)
  - consecutive_unchanged: peş peşe 304 sayacı (Faz 2 tier kararında kullanılır)

1 app_settings seed:
  - rss.realtime_master_enabled (bool, default false) — global feature flag

Revision ID: 20260510_0100
Revises: 20260509_0900
Create Date: 2026-05-10 01:00:00 UTC
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260510_0100"
down_revision = "20260509_0900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("etag", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("last_modified", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column(
            "realtime_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "polling_tier",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'normal'"),
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "consecutive_unchanged",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_check_constraint(
        "ck_sources_polling_tier",
        "sources",
        "polling_tier IN ('hot', 'normal', 'cold', 'hibernate')",
    )

    op.execute(
        sa.text(
            """
            INSERT INTO app_settings
                (key, value, type, group_name, description, updated_at, created_at)
            VALUES
                (
                    'rss.realtime_master_enabled',
                    'false'::jsonb,
                    'bool',
                    'rss',
                    'Global kill-switch for adaptive RSS polling. False iken her kaynak crawl_interval_minutes ile sabit polling yapar (legacy). True olduğunda realtime_enabled=true olan kaynaklar adaptive tier kullanır (Faz 2+).',
                    NOW(),
                    NOW()
                )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM app_settings WHERE key = 'rss.realtime_master_enabled'"))
    op.drop_constraint("ck_sources_polling_tier", "sources", type_="check")
    op.drop_column("sources", "consecutive_unchanged")
    op.drop_column("sources", "polling_tier")
    op.drop_column("sources", "realtime_enabled")
    op.drop_column("sources", "last_modified")
    op.drop_column("sources", "etag")
