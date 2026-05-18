"""Add provider_call_logs (#23)

docs/engineering/data-model.md §4.5
docs/strategy/unit-economics.md §6

Tek tablo + 3 index. Forward-compatible — sadece CREATE.

Revision ID: 20260501_2200
Revises: 20260501_2100
Create Date: 2026-05-01 22:00:00 UTC
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260501_2200"
down_revision: str | None = "20260501_2100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_call_logs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120)),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("latency_ms", sa.Integer),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("generation_id", UUID(as_uuid=True)),
        sa.Column("article_id", UUID(as_uuid=True)),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("error_message", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "idx_provider_call_logs_created",
        "provider_call_logs",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_provider_call_logs_user_created",
        "provider_call_logs",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "idx_provider_call_logs_provider_created",
        "provider_call_logs",
        ["provider", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("provider_call_logs")
