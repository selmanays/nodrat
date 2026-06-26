"""Faz 5.0 — Otomasyon Stüdyosu şema iskelesi (saf additive, no-op)

Founder merdiveninin 3. basamağı (sor→abone→otomasyona ekle). 3 tablo döşenir;
hiçbir okuyucu/yazıcı kod yok, tüm flag'ler OFF → davranış DEĞİŞMEZ.
social_accounts paylaşım fazına (5.4) kadar BOŞ kalır.

Additive + izole → backward-compatible, zero-downtime. Mevcut tablolara DOKUNMAZ.
FK sırası: social_accounts → automation_rules (social_account_id) → automation_runs.

FK ON DELETE:
- *.user_id → CASCADE (KVKK: hesap silinince kural/run/hesap gider)
- automation_rules.cluster_id / automation_runs.cluster_id → RESTRICT (paylaşımlı global düğüm korunur)
- automation_rules.social_account_id → SET NULL (hesap silinince kural paylaşımsıza düşer)
- automation_runs.rule_id → CASCADE
- automation_runs.artifact_id → SET NULL (artefakt silinse de run izi kalır)

Revision ID: 20260626_0100
Revises: 20260624_0100
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260626_0100"
down_revision: str | None = "20260624_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) social_accounts (BOŞ — paylaşım fazına 5.4 kadar dolmaz; rules FK'i için önce)
    op.create_table(
        "social_accounts",
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
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("provider_user_id", sa.String(length=128), nullable=True),
        sa.Column("handle", sa.String(length=64), nullable=True),
        sa.Column("access_token", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token", sa.LargeBinary(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'connected'")
        ),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('x')", name="ck_social_accounts_provider"),
        sa.CheckConstraint(
            "status IN ('connected','revoked','error')", name="ck_social_accounts_status"
        ),
    )
    op.create_index(
        "uq_social_accounts_user_provider_live",
        "social_accounts",
        ["user_id", "provider"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    # 2) automation_rules
    op.create_table(
        "automation_rules",
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
        sa.Column("trigger_config", postgresql.JSONB(), nullable=False),
        sa.Column("action_config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "mode",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'approval_queue'"),
        ),
        sa.Column(
            "social_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("social_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('approval_queue','full_auto')", name="ck_automation_rules_mode"
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','disabled')", name="ck_automation_rules_status"
        ),
    )
    op.create_index(
        "uq_automation_rules_user_cluster_live",
        "automation_rules",
        ["user_id", "cluster_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_automation_rules_cluster", "automation_rules", ["cluster_id"])
    op.create_index(
        "idx_automation_rules_user_live",
        "automation_rules",
        ["user_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 3) automation_runs
    op.create_table(
        "automation_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automation_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_clusters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default=sa.text("'queued'")
        ),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "status IN ('queued','pending','skipped_no_sources','skipped_quota',"
            "'skipped_no_consent','posted','rejected','failed')",
            name="ck_automation_runs_status",
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_automation_runs_dedupe"),
    )
    op.create_index(
        "idx_automation_runs_rule_created",
        "automation_runs",
        ["rule_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_automation_runs_status", "automation_runs", ["status"])


def downgrade() -> None:
    op.drop_index("idx_automation_runs_status", table_name="automation_runs")
    op.drop_index("idx_automation_runs_rule_created", table_name="automation_runs")
    op.drop_table("automation_runs")

    op.drop_index("idx_automation_rules_user_live", table_name="automation_rules")
    op.drop_index("idx_automation_rules_cluster", table_name="automation_rules")
    op.drop_index("uq_automation_rules_user_cluster_live", table_name="automation_rules")
    op.drop_table("automation_rules")

    op.drop_index("uq_social_accounts_user_provider_live", table_name="social_accounts")
    op.drop_table("social_accounts")
