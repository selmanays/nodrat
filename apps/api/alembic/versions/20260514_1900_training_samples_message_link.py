"""training_samples'a message_id FK + sample_type (#800 S1B).

SFT curator artık messages tablosundan da besleniyor (S1E rewrite ile).
Yeni FK + sample_type column'ı eklenir; UNIQUE constraint message-bazlı
güncellenir.

Revision: 20260514_1900
Revises: 20260514_1800
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260514_1900"
down_revision: str | None = "20260514_1800"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # message_id FK — messages tablosuna bağlantı (chat-derived sample'lar)
    op.add_column(
        "training_samples",
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    # sample_type — SFT vs DPO
    op.add_column(
        "training_samples",
        sa.Column(
            "sample_type",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'sft'"),
        ),
    )
    op.execute(
        sa.text("""
        ALTER TABLE training_samples
        ADD CONSTRAINT training_samples_sample_type_check
        CHECK (sample_type IN ('sft', 'dpo_chosen', 'dpo_rejected'))
    """)
    )

    # UNIQUE — message_id + task_type + sample_type
    # (generation_id eski kayıtlar için nullable kaldı, UNIQUE constraint S1B'de
    # zaten drop edildi; yeni message-bazlı UNIQUE eklenir.)
    op.execute(
        sa.text("""
        CREATE UNIQUE INDEX uq_training_samples_message_task_sample
        ON training_samples(message_id, task_type, sample_type)
        WHERE message_id IS NOT NULL
    """)
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_training_samples_message_task_sample"))
    op.execute(
        sa.text(
            "ALTER TABLE training_samples DROP CONSTRAINT IF EXISTS training_samples_sample_type_check"
        )
    )
    op.drop_column("training_samples", "sample_type")
    op.drop_column("training_samples", "message_id")
