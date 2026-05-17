"""#961 — messages.followup_suggestions (cevap-sonrası 5 dinamik takip sorusu)

Additive, nullable JSONB. Geriye-uyumlu: mevcut satırlar NULL kalır
(eski mesajlarda takip sorusu yok — sorun değil). Selamlama/kimlik/
meta veya degrade durumunda da NULL.

Revision ID: 20260518_0100
Revises: 20260516_0400
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260518_0100"
down_revision: str | None = "20260516_0400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "followup_suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("messages", "followup_suggestions")
