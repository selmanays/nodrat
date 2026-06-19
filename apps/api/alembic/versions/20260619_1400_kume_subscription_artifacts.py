"""Faz 0 — Küme abonelik + artefakt iskeleti (additive, no-op)

Küme-merkezli abonelik vizyonu Faz 0: AÇIK kullanıcı↔küme aboneliği +
küme-bağlı paylaşılabilir artefakt (X gönderisi/thread/canvas) + revizyon
zinciri. SADECE veri kapları döşenir — davranış DEĞİŞMEZ (Faz 2-3).

Additive, izole → backward-compatible, zero-downtime. Mevcut tablolara
DOKUNMAZ; tek istisna research_clusters'a nullable `canonical_entity_id`
(anchor) eklenir (ADD COLUMN, ALTER değil mevcut kolon).

Karar (founder, 2026-06-19):
- Abonelik birimi = ResearchCluster (#1015); canonical_entity_id anchor (soft ref).
- Artefakt = ayrı artifacts + artifact_revisions tabloları (sürüm/DPO için).
- Sahiplik = generations modülü (ResearchCluster orada).

Soft-ref deseni (hard FK YOK, history-safety — trend subject_id deseni):
- artifacts.head_revision_id   → en güncel revizyon işaretçisi (app-maintained, no FK)
- research_clusters.canonical_entity_id → canonical_entities raw-SQL-only tablo (no FK)

FK ON DELETE:
- user_cluster_subscriptions.user_id    → CASCADE  (KVKK)
- user_cluster_subscriptions.cluster_id → RESTRICT (global düğüm korunur)
- artifacts.user_id     → CASCADE  (KVKK)
- artifacts.cluster_id  → RESTRICT (global düğüm korunur)
- artifacts.origin_message_id → SET NULL (legacy mesaj köprüsü; mesaj silinse de artefakt kalır)
- artifact_revisions.artifact_id        → CASCADE
- artifact_revisions.parent_revision_id → SET NULL (DAG)

Revision ID: 20260619_1400
Revises: 20260619_1300
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260619_1400"
down_revision: str | None = "20260619_1300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) research_clusters — anchor kolonu (soft ref, no FK)
    op.add_column(
        "research_clusters",
        sa.Column("canonical_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "idx_research_clusters_canonical_entity",
        "research_clusters",
        ["canonical_entity_id"],
        postgresql_where=sa.text("canonical_entity_id IS NOT NULL"),
    )

    # 2) user_cluster_subscriptions — açık, çıkılabilir abonelik
    op.create_table(
        "user_cluster_subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_clusters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("preferences", postgresql.JSONB(), nullable=True),
        sa.Column(
            "subscribed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    # Bir kullanıcı bir küme için en fazla TEK canlı abonelik (unsubscribe → slot boşalır)
    op.create_index(
        "uq_user_cluster_sub_live",
        "user_cluster_subscriptions",
        ["user_id", "cluster_id"],
        unique=True,
        postgresql_where=sa.text("unsubscribed_at IS NULL"),
    )
    op.create_index(
        "idx_user_cluster_sub_user_live",
        "user_cluster_subscriptions",
        ["user_id"],
        postgresql_where=sa.text("unsubscribed_at IS NULL"),
    )
    op.create_index(
        "idx_user_cluster_sub_cluster",
        "user_cluster_subscriptions",
        ["cluster_id"],
    )

    # 3) artifacts — küme-bağlı paylaşılabilir artefakt
    op.create_table(
        "artifacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
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
        sa.Column("artifact_type", sa.String(length=16), nullable=False),
        # Soft işaretçi (en güncel revizyon) — app-maintained, circular-FK YOK
        sa.Column("head_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "origin_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
    )
    op.create_index(
        "idx_artifacts_cluster_created",
        "artifacts",
        ["cluster_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_artifacts_user_created",
        "artifacts",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_artifacts_origin_message",
        "artifacts",
        ["origin_message_id"],
        postgresql_where=sa.text("origin_message_id IS NOT NULL"),
    )

    # 4) artifact_revisions — sürüm/revizyon zinciri (DAG)
    op.create_table(
        "artifact_revisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_seq", sa.Integer(), nullable=False),
        sa.Column(
            "parent_revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifact_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("revision_intent", sa.String(length=24), nullable=False),
        sa.Column("sources_used", postgresql.JSONB(), nullable=True),
        sa.Column("effective_query", sa.Text(), nullable=True),
        # Embedding KOPYALANIR, asla yeniden hesaplanmaz (HARD-STOP) — Faz 3 doldurur
        sa.Column("query_embedding", sa.LargeBinary(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("artifact_id", "revision_seq", name="uq_artifact_revision_seq"),
    )
    op.create_index(
        "idx_artifact_revisions_artifact",
        "artifact_revisions",
        ["artifact_id", "revision_seq"],
    )


def downgrade() -> None:
    op.drop_index("idx_artifact_revisions_artifact", table_name="artifact_revisions")
    op.drop_table("artifact_revisions")

    op.drop_index("idx_artifacts_origin_message", table_name="artifacts")
    op.drop_index("idx_artifacts_user_created", table_name="artifacts")
    op.drop_index("idx_artifacts_cluster_created", table_name="artifacts")
    op.drop_table("artifacts")

    op.drop_index("idx_user_cluster_sub_cluster", table_name="user_cluster_subscriptions")
    op.drop_index("idx_user_cluster_sub_user_live", table_name="user_cluster_subscriptions")
    op.drop_index("uq_user_cluster_sub_live", table_name="user_cluster_subscriptions")
    op.drop_table("user_cluster_subscriptions")

    op.drop_index("idx_research_clusters_canonical_entity", table_name="research_clusters")
    op.drop_column("research_clusters", "canonical_entity_id")
