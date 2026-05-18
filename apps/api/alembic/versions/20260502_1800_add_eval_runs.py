"""Add eval_runs table for benchmark history persistence (#190)

docs/engineering/data-model.md (admin RAG observability)

Revision ID: 20260502_1800
Revises: 20260502_1700
Create Date: 2026-05-02 18:00:00 UTC
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260502_1800"
down_revision: str | None = "20260502_1700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("golden_set", sa.String(120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("n_queries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("top_k", sa.Integer, nullable=False, server_default="20"),
        sa.Column("ndcg_10", sa.Numeric(5, 4), nullable=True),
        sa.Column("map_5", sa.Numeric(5, 4), nullable=True),
        sa.Column("mrr_10", sa.Numeric(5, 4), nullable=True),
        sa.Column("recall_20", sa.Numeric(5, 4), nullable=True),
        sa.Column("p_5", sa.Numeric(5, 4), nullable=True),
        sa.Column("latency_ms_p50", sa.Numeric(8, 2), nullable=True),
        sa.Column("latency_ms_p95", sa.Numeric(8, 2), nullable=True),
        sa.Column("config_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("triggered_by", sa.String(80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_eval_runs_created", "eval_runs", [sa.text("created_at DESC")])
    op.create_index(
        "idx_eval_runs_golden_set", "eval_runs", ["golden_set", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_index("idx_eval_runs_golden_set", table_name="eval_runs")
    op.drop_index("idx_eval_runs_created", table_name="eval_runs")
    op.drop_table("eval_runs")
