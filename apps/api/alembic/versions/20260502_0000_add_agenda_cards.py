"""Add agenda_cards (#21)

docs/engineering/data-model.md §4.4

Revision ID: 20260502_0000
Revises: 20260501_2300
Create Date: 2026-05-02 00:00:00 UTC
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_0000"
down_revision: str | None = "20260501_2300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agenda_cards (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id        UUID NOT NULL REFERENCES event_clusters(id) ON DELETE CASCADE,

            title           VARCHAR(500) NOT NULL,
            summary         TEXT NOT NULL,
            key_points      JSONB NOT NULL DEFAULT '[]'::jsonb,
            content_angles  JSONB NOT NULL DEFAULT '[]'::jsonb,
            timeline        JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_refs     JSONB NOT NULL DEFAULT '[]'::jsonb,

            status          VARCHAR(16) NOT NULL DEFAULT 'developing',
            freshness_score NUMERIC(3,2),
            importance_score NUMERIC(3,2),

            embedding       vector(1024),

            generated_by_model VARCHAR(80),
            generation_request_id UUID,

            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CHECK (status IN ('developing', 'active', 'cooling', 'stale', 'archived'))
        );
        """
    )
    op.create_index("idx_agenda_cards_event", "agenda_cards", ["event_id"])
    op.create_index(
        "idx_agenda_cards_status_updated",
        "agenda_cards",
        ["status", sa.text("updated_at DESC")],
    )
    op.execute(
        "CREATE INDEX idx_agenda_cards_embedding "
        "ON agenda_cards USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);"
    )
    op.execute(
        "CREATE TRIGGER trg_agenda_cards_updated_at BEFORE UPDATE ON agenda_cards "
        "FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_agenda_cards_updated_at ON agenda_cards")
    op.execute("DROP INDEX IF EXISTS idx_agenda_cards_embedding")
    op.drop_index("idx_agenda_cards_status_updated", table_name="agenda_cards")
    op.drop_index("idx_agenda_cards_event", table_name="agenda_cards")
    op.execute("DROP TABLE agenda_cards")
