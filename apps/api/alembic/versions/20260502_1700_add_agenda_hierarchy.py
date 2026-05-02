"""Add agenda_cards.parent_card_id + level for RAPTOR-Lite hierarchy (#182)

docs/engineering/data-model.md §4 (agenda_cards extension)
docs/engineering/architecture.md §3.3 (clustering)

Revision ID: 20260502_1700
Revises: 20260502_1600
Create Date: 2026-05-02 17:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260502_1700"
down_revision: Union[str, None] = "20260502_1600"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Hierarchical clustering: daily → weekly → monthly
    op.add_column(
        "agenda_cards",
        sa.Column(
            "level",
            sa.String(16),
            nullable=False,
            server_default="daily",
        ),
    )
    op.add_column(
        "agenda_cards",
        sa.Column(
            "parent_card_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "agenda_cards_level_check",
        "agenda_cards",
        "level IN ('daily', 'weekly', 'monthly')",
    )

    op.create_foreign_key(
        "agenda_cards_parent_fkey",
        "agenda_cards",
        "agenda_cards",
        ["parent_card_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "idx_agenda_cards_level",
        "agenda_cards",
        ["level", "updated_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "idx_agenda_cards_parent",
        "agenda_cards",
        ["parent_card_id"],
        postgresql_where=sa.text("parent_card_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_agenda_cards_parent", table_name="agenda_cards")
    op.drop_index("idx_agenda_cards_level", table_name="agenda_cards")
    op.drop_constraint(
        "agenda_cards_parent_fkey", "agenda_cards", type_="foreignkey"
    )
    op.drop_constraint(
        "agenda_cards_level_check", "agenda_cards", type_="check"
    )
    op.drop_column("agenda_cards", "parent_card_id")
    op.drop_column("agenda_cards", "level")
