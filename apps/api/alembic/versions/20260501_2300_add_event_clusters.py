"""Add event_clusters + event_articles (#20)

docs/engineering/data-model.md §4.2, §4.3

Revision ID: 20260501_2300
Revises: 20260501_2200
Create Date: 2026-05-01 23:00:00 UTC
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260501_2300"
down_revision: str | None = "20260501_2200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ============================================================
    # event_clusters
    # ============================================================
    op.execute(
        """
        CREATE TABLE event_clusters (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            canonical_title VARCHAR(500) NOT NULL,
            current_summary TEXT,
            embedding       vector(1024),

            first_seen_at   TIMESTAMPTZ NOT NULL,
            last_seen_at    TIMESTAMPTZ NOT NULL,
            last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            status          VARCHAR(16) NOT NULL DEFAULT 'developing',

            importance_score NUMERIC(3,2),
            freshness_score  NUMERIC(3,2),
            source_count     INTEGER NOT NULL DEFAULT 0,
            article_count    INTEGER NOT NULL DEFAULT 0,

            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CHECK (status IN ('developing', 'active', 'cooling', 'stale', 'archived'))
        );
        """
    )
    op.create_index(
        "idx_event_clusters_status_updated",
        "event_clusters",
        ["status", sa.text("last_updated_at DESC")],
    )
    op.execute(
        "CREATE INDEX idx_event_clusters_embedding "
        "ON event_clusters USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);"
    )
    op.create_index(
        "idx_event_clusters_last_seen",
        "event_clusters",
        [sa.text("last_seen_at DESC")],
    )

    op.execute(
        "CREATE TRIGGER trg_event_clusters_updated_at BEFORE UPDATE ON event_clusters "
        "FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();"
    )

    # ============================================================
    # event_articles
    # ============================================================
    op.create_table(
        "event_articles",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            sa.ForeignKey("event_clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "article_id",
            UUID(as_uuid=True),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("relationship_score", sa.Numeric(3, 2)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("event_id", "article_id", name="uq_event_articles_event_article"),
    )

    op.create_index("idx_event_articles_event", "event_articles", ["event_id"])
    op.create_index("idx_event_articles_article", "event_articles", ["article_id"])


def downgrade() -> None:
    op.drop_table("event_articles")
    op.execute("DROP TRIGGER IF EXISTS trg_event_clusters_updated_at ON event_clusters")
    op.execute("DROP INDEX IF EXISTS idx_event_clusters_embedding")
    op.execute("DROP INDEX IF EXISTS idx_event_clusters_last_seen")
    op.drop_index("idx_event_clusters_status_updated", table_name="event_clusters")
    op.execute("DROP TABLE event_clusters")
