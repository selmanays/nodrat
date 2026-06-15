"""Add trend tables — topics, topic_clusters, trend_snapshots, trend_signals (#1505)

Trend Intelligence Faz 2 PR-2a: kalıcı persistence şeması. Additive / zero-downtime
(yalnız yeni tablo; mevcut tabloya dokunulmaz). Davranış yok — worker PR-2b'de,
flag default OFF.

ORM modelleri: app/modules/trends/models.py (alembic check 0-diff parity şart;
app/models/__init__.py'ye kayıtlı). event_clusters PR-8.2-11 ivfflat deseni.

Revision ID: 20260615_1200
Revises: 20260519_0100
Create Date: 2026-06-15 12:00:00 UTC
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260615_1200"
down_revision: str | None = "20260519_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ============================================================
    # topics — kalıcı trend konusu kimliği
    # ============================================================
    op.create_table(
        "topics",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("topic_kind", sa.String(16), nullable=False),
        sa.Column("anchor_entity_normalized", sa.String(200)),
        sa.Column("anchor_entity_type", sa.String(20)),
        sa.Column("centroid_embedding", Vector(1024)),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "merged_into_topic_id",
            UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("article_count_total", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("cluster_count_total", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("admin_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
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
        sa.UniqueConstraint("slug", name="uq_topics_slug"),
        sa.CheckConstraint(
            "topic_kind IN ('entity', 'event', 'keyword', 'manual')",
            name="ck_topics_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'dormant', 'merged', 'archived')",
            name="ck_topics_status",
        ),
    )
    op.create_index(
        "idx_topics_status_last_seen",
        "topics",
        ["status", sa.text("last_seen_at DESC")],
    )
    op.create_index(
        "idx_topics_anchor",
        "topics",
        ["anchor_entity_normalized", "anchor_entity_type"],
    )
    op.execute(
        "CREATE INDEX idx_topics_centroid ON topics "
        "USING ivfflat (centroid_embedding vector_cosine_ops) WITH (lists = 50);"
    )
    op.execute(
        "CREATE TRIGGER trg_topics_updated_at BEFORE UPDATE ON topics "
        "FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();"
    )

    # ============================================================
    # topic_clusters — kalıcı topic ↔ transient event_cluster bağı
    # (event_cluster_id hard FK YOK — history subject'i aşar)
    # ============================================================
    op.create_table(
        "topic_clusters",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "topic_id",
            UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_score", sa.Numeric(4, 3)),
        sa.Column("assigned_by", sa.String(16), nullable=False, server_default=sa.text("'auto'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("topic_id", "event_cluster_id", name="uq_topic_clusters_topic_event"),
        sa.CheckConstraint(
            "assigned_by IN ('auto', 'admin_merge', 'admin_split')",
            name="ck_topic_clusters_assigned_by",
        ),
    )
    op.create_index("idx_topic_clusters_event", "topic_clusters", ["event_cluster_id"])

    # ============================================================
    # trend_snapshots — zaman-serisi (idempotency key'li)
    # (subject_id hard FK YOK — history subject'i aşar)
    # ============================================================
    op.create_table(
        "trend_snapshots",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_seconds", sa.Integer, nullable=False),
        sa.Column("algo_version", sa.SmallInteger, nullable=False),
        sa.Column("article_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "cumulative_article_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("unique_source_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("source_diversity", sa.Numeric(4, 3)),
        sa.Column("velocity_1h", sa.Numeric(8, 3)),
        sa.Column("velocity_6h", sa.Numeric(8, 3)),
        sa.Column("velocity_24h", sa.Numeric(8, 3)),
        sa.Column("acceleration", sa.Numeric(8, 3)),
        sa.Column("burst_score", sa.Numeric(6, 3)),
        sa.Column("novelty_score", sa.Numeric(4, 3)),
        sa.Column("credibility_score", sa.Numeric(4, 3)),
        sa.Column("trend_state", sa.String(12)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "subject_type",
            "subject_id",
            "bucket_start",
            "algo_version",
            name="uq_trend_snapshots_subject_bucket_algo",
        ),
        sa.CheckConstraint(
            "subject_type IN ('topic', 'cluster', 'entity')",
            name="ck_trend_snapshots_subject_type",
        ),
        sa.CheckConstraint(
            "trend_state IS NULL OR trend_state IN ('breaking', 'developing', 'stable', 'fading')",
            name="ck_trend_snapshots_trend_state",
        ),
    )
    op.create_index(
        "idx_trend_snapshots_bucket_burst",
        "trend_snapshots",
        [sa.text("bucket_start DESC"), sa.text("burst_score DESC")],
    )
    op.create_index(
        "idx_trend_snapshots_subject_bucket",
        "trend_snapshots",
        ["subject_id", sa.text("bucket_start DESC")],
    )
    op.create_index("idx_trend_snapshots_bucket", "trend_snapshots", ["bucket_start"])

    # ============================================================
    # trend_signals — kesikli tespit (v1: burst)
    # ============================================================
    op.create_table(
        "trend_signals",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.String(24), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_seconds", sa.Integer, nullable=False),
        sa.Column("algo_version", sa.SmallInteger, nullable=False),
        sa.Column("magnitude", sa.Numeric(6, 3)),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'new'")),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "subject_type",
            "subject_id",
            "signal_type",
            "detected_at",
            "algo_version",
            name="uq_trend_signals_dedup",
        ),
        sa.CheckConstraint(
            "subject_type IN ('topic', 'cluster', 'entity')",
            name="ck_trend_signals_subject_type",
        ),
        sa.CheckConstraint(
            "signal_type IN ('burst', 'demand_spike', 'new_actor', 'source_spike', 'sustained')",
            name="ck_trend_signals_signal_type",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'approved', 'dismissed', 'merged', 'split')",
            name="ck_trend_signals_status",
        ),
    )
    op.create_index(
        "idx_trend_signals_recent",
        "trend_signals",
        [sa.text("detected_at DESC"), "signal_type"],
    )
    op.create_index(
        "idx_trend_signals_status",
        "trend_signals",
        ["status", sa.text("detected_at DESC")],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_topics_updated_at ON topics;")
    op.drop_table("trend_signals")
    op.drop_table("trend_snapshots")
    op.drop_table("topic_clusters")
    op.drop_table("topics")
