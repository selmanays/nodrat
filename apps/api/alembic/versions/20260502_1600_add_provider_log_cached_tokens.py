"""Add provider_call_logs.cached_tokens for DeepSeek cache hit tracking (#171 PR-E)

docs/strategy/unit-economics.md §4.2 (DeepSeek cache hit cost projection)

Revision ID: 20260502_1600
Revises: 20260502_1500
Create Date: 2026-05-02 16:00:00 UTC
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_1600"
down_revision: str | None = "20260502_1500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # DeepSeek prompt cache hit/miss tracking
    op.add_column(
        "provider_call_logs",
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_call_logs", "cached_tokens")
