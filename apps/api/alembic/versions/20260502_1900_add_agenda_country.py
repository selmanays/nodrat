"""Add agenda_cards.country (ISO2) for geographic filter (#210)

docs/engineering/data-model.md (geographic_focus retrieval)

Revision ID: 20260502_1900
Revises: 20260502_1800
Create Date: 2026-05-02 19:00:00 UTC
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_1900"
down_revision: str | None = "20260502_1800"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agenda_cards",
        sa.Column("country", sa.String(2), nullable=True),
    )
    op.create_check_constraint(
        "agenda_cards_country_check",
        "agenda_cards",
        "country IS NULL OR length(country) = 2",
    )
    op.create_index(
        "idx_agenda_cards_country",
        "agenda_cards",
        ["country"],
        postgresql_where=sa.text("country IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_agenda_cards_country", table_name="agenda_cards")
    op.drop_constraint("agenda_cards_country_check", "agenda_cards", type_="check")
    op.drop_column("agenda_cards", "country")
