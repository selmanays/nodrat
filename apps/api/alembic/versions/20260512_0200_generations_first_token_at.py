"""Add generations.first_token_at column for TTFT observability (#739).

Stream endpoint SSE 'first_token' event'i geldiğinde gen_row.first_token_at
timestamp set olur. Dashboard'da p50/p95 TTFT (created_at → first_token_at)
ölçülebilir.

#684 EPIC AC5 follow-up: önceden TTFT için ölçüm yoktu, manuel gözlem
"16-22sn → 10-15sn" yansımıştı. Otomatik ölçüm bu PR ile gelir.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "20260512_0200"
down_revision = "20260512_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column(
            "first_token_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment=(
                "Stream'da ilk SSE 'first_token' event'i timestamp'i. "
                "TTFT = first_token_at - created_at. #739"
            ),
        ),
    )
    # Index için partial — sadece dolu olan rows (önceki rows NULL kalır)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_generations_first_token "
        "ON generations(first_token_at) "
        "WHERE first_token_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_generations_first_token")
    op.drop_column("generations", "first_token_at")
