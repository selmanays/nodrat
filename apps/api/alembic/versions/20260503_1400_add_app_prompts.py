"""Add app_prompts table for runtime LLM prompts (#270 PR-B, MVP-1.2)

docs/engineering/data-model.md (admin prompts panel)

Revision ID: 20260503_1400
Revises: 20260503_1000
Create Date: 2026-05-03 14:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260503_1400"
down_revision: Union[str, None] = "20260503_1000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- app_prompts (current active version) ------------------------
    op.create_table(
        "app_prompts",
        sa.Column("name", sa.String(80), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("model_hint", sa.String(120), nullable=True),
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

    # ---- app_prompt_history (version archive) ------------------------
    op.create_table(
        "app_prompt_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_app_prompt_history_name_version",
        "app_prompt_history",
        ["name", "version"],
        unique=True,
    )
    op.create_index(
        "idx_app_prompt_history_name_created",
        "app_prompt_history",
        ["name", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_app_prompt_history_name_created",
        table_name="app_prompt_history",
    )
    op.drop_index(
        "idx_app_prompt_history_name_version",
        table_name="app_prompt_history",
    )
    op.drop_table("app_prompt_history")
    op.drop_table("app_prompts")
