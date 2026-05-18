"""Messages tablosuna feedback + DPO kolonları (#800 S1B).

Halu flag + user action + DPO rejection için gerekli alanlar. SFT
eligibility recompute logic'i bu alanları okur.

Revision: 20260514_1800
Revises: 20260514_1700
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260514_1800"
down_revision: str | None = "20260514_1700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Halu flag
    op.add_column(
        "messages", sa.Column("halu_flagged_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "messages",
        sa.Column(
            "halu_flagged_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("messages", sa.Column("halu_flagged_reason", sa.Text(), nullable=True))

    # User action (SFT signal)
    op.add_column("messages", sa.Column("user_action", sa.String(length=16), nullable=True))
    op.add_column(
        "messages", sa.Column("user_action_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("messages", sa.Column("edit_distance", sa.Numeric(3, 2), nullable=True))
    op.add_column("messages", sa.Column("edited_content", sa.Text(), nullable=True))

    # SFT eligibility
    op.add_column(
        "messages",
        sa.Column(
            "sft_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("messages", sa.Column("sft_excluded_reason", sa.String(length=64), nullable=True))
    op.add_column(
        "messages", sa.Column("sft_recomputed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # DPO (halu-rejected pair için)
    op.add_column(
        "messages",
        sa.Column(
            "dpo_rejected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("messages", sa.Column("dpo_chosen_content", sa.Text(), nullable=True))

    # Index — SFT curator query'leri için
    op.execute(
        sa.text("""
        CREATE INDEX idx_messages_sft_eligible ON messages(sft_eligible, role)
        WHERE sft_eligible = true AND role = 'assistant'
    """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX idx_messages_dpo_rejected ON messages(dpo_rejected, role)
        WHERE dpo_rejected = true AND role = 'assistant'
    """)
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_messages_dpo_rejected"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_messages_sft_eligible"))
    for col in (
        "dpo_chosen_content",
        "dpo_rejected",
        "sft_recomputed_at",
        "sft_excluded_reason",
        "sft_eligible",
        "edited_content",
        "edit_distance",
        "user_action_at",
        "user_action",
        "halu_flagged_reason",
        "halu_flagged_by",
        "halu_flagged_at",
    ):
        op.drop_column("messages", col)
