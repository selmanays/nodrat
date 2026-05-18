"""#1013 (Faz 2a) — messages.effective_query (condense sonrası standalone sorgu)

Additive, nullable. Mevcut tablolara/sütunlara DOKUNMAZ → backward-compatible,
zero-downtime. condense (#833) sonrası bağlamlı/standalone sorgu metni;
assistant mesajına yazılır. SFT INPUT bütünlüğü (L1 önkoşulu): ham follow-up
L1 görünmez bağlamla kopuk kalır, effective_query cevabı üreten self-contained
sorgudur. None → curator ham content'e düşer (davranış değişmez).

Revision ID: 20260518_0300
Revises: 20260518_0200
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260518_0300"
down_revision: str | None = "20260518_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("effective_query", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "effective_query")
