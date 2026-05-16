"""#904 — articles.extract_attempts (deneme-tabanlı retry sayacı).

retry_failed eski yaş-tabanlı (`created_at >= now()-72h`) pencere yerine
deneme-tabanlı: extract_attempts < max → retry; >= max & quarantine → discarded.

Revision: 20260516_0200
Revises: 20260516_0100
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260516_0200"
down_revision: str | None = "20260516_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL DEFAULT 0 — Postgres 11+ instant (rewrite yok).
    op.add_column(
        "articles",
        sa.Column(
            "extract_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("articles", "extract_attempts")
