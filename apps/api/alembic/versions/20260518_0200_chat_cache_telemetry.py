"""#981 — chat_cache_telemetry (generate-hattı prompt-cache segment ledger)

Additive, izole tablo. Mevcut tablolara DOKUNMAZ → backward-compatible,
zero-downtime. Yalnız token SAYISI + id'ler (KVKK: içerik yok). Writer
best-effort + runtime flag (observability.chat_cache_enabled) ile gated.

Revision ID: 20260518_0200
Revises: 20260518_0100
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260518_0200"
down_revision: str | None = "20260518_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_cache_telemetry",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("call_type", sa.String(length=32), nullable=False),
        sa.Column("call_seq", sa.SmallInteger(), nullable=True),
        sa.Column("tools_present", sa.Boolean(), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("seg_system", sa.Integer(), nullable=True),
        sa.Column("seg_tools_schema", sa.Integer(), nullable=True),
        sa.Column("seg_msg1_static", sa.Integer(), nullable=True),
        sa.Column("seg_msg1_history", sa.Integer(), nullable=True),
        sa.Column("seg_msg1_question", sa.Integer(), nullable=True),
        sa.Column("seg_rag_tool", sa.Integer(), nullable=True),
        sa.Column("seg_assistant_intermediate", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
    )
    op.create_index("idx_cct_created", "chat_cache_telemetry", [sa.text("created_at DESC")])
    op.create_index(
        "idx_cct_user_created",
        "chat_cache_telemetry",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index("idx_cct_conversation", "chat_cache_telemetry", ["conversation_id"])
    op.create_index(
        "idx_cct_calltype_created",
        "chat_cache_telemetry",
        ["call_type", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_cct_calltype_created", table_name="chat_cache_telemetry")
    op.drop_index("idx_cct_conversation", table_name="chat_cache_telemetry")
    op.drop_index("idx_cct_user_created", table_name="chat_cache_telemetry")
    op.drop_index("idx_cct_created", table_name="chat_cache_telemetry")
    op.drop_table("chat_cache_telemetry")
