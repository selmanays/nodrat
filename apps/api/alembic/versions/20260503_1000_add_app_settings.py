"""Add app_settings table for runtime config (#263 — MVP-1.2 admin panel)

docs/engineering/data-model.md (admin settings)

Revision ID: 20260503_1000
Revises: 20260502_1900
Create Date: 2026-05-03 10:00:00 UTC
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260503_1000"
down_revision: str | None = "20260502_1900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "type",
            sa.String(16),
            nullable=False,
        ),
        sa.Column("group_name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("min_value", sa.Numeric(), nullable=True),
        sa.Column("max_value", sa.Numeric(), nullable=True),
        sa.Column("allowed_values", postgresql.JSONB(), nullable=True),
        sa.Column(
            "requires_restart",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_check_constraint(
        "app_settings_type_check",
        "app_settings",
        "type IN ('float','int','bool','string','json')",
    )
    op.create_index(
        "idx_app_settings_group",
        "app_settings",
        ["group_name"],
    )


def downgrade() -> None:
    op.drop_index("idx_app_settings_group", table_name="app_settings")
    op.drop_table("app_settings")
