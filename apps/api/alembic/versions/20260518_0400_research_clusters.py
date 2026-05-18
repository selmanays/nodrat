"""#1015 (Pivot Faz 3) — research_clusters + message_clusters (GLOBAL kümeleme)

Additive, izole. Mevcut tablolara DOKUNMAZ → backward-compatible,
zero-downtime. GLOBAL kanonik küme (no user_id) + user-scoped üyelik.

MERGE SIRASI (önemli): down_revision = 20260518_0300 (#1024 / Faz 2a).
Sıralı roadmap F2a→F3 gereği #1024 ÖNCE merge edilmeli; aksi halde
`alembic upgrade head` 0300'ü bulamaz. Sıra dışı merge olursa #1024
merge edilince bu zaten zincire oturur (linear).

Revision ID: 20260518_0400
Revises: 20260518_0300
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260518_0400"
down_revision: str | None = "20260518_0300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_clusters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("cluster_key", sa.String(length=320), nullable=False),
        sa.Column("cluster_type", sa.String(length=20), nullable=False),
        sa.Column("canonical_name", sa.String(length=200), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=True),
        sa.Column(
            "parent_cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_clusters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("centroid_embedding", sa.LargeBinary(), nullable=True),
        sa.Column(
            "is_public_figure",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("sensitivity_flag", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_research_clusters_key_active",
        "research_clusters",
        ["cluster_key"],
        unique=True,
        postgresql_where=sa.text("deprecated_at IS NULL"),
    )
    op.create_index(
        "idx_research_clusters_type_updated",
        "research_clusters",
        ["cluster_type", sa.text("updated_at DESC")],
    )

    op.create_table(
        "message_clusters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_clusters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mention_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("assigned_via", sa.String(length=20), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("message_id", "cluster_id", name="uq_message_cluster"),
    )
    op.create_index("idx_message_clusters_message", "message_clusters", ["message_id"])
    op.create_index(
        "idx_message_clusters_user_created",
        "message_clusters",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_message_clusters_cluster_user",
        "message_clusters",
        ["cluster_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_message_clusters_cluster_user", table_name="message_clusters")
    op.drop_index("idx_message_clusters_user_created", table_name="message_clusters")
    op.drop_index("idx_message_clusters_message", table_name="message_clusters")
    op.drop_table("message_clusters")
    op.drop_index("idx_research_clusters_type_updated", table_name="research_clusters")
    op.drop_index("uq_research_clusters_key_active", table_name="research_clusters")
    op.drop_table("research_clusters")
