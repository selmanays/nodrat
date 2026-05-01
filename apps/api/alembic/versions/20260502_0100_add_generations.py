"""Add generations + usage_events + saved_generations (#27)

docs/engineering/data-model.md §5.1, §5.2, §5.3
PRD §3.6, §3.7

NOT: style_profiles tablosu Faz 5'te eklenecek; FK constraint şimdilik yok
(generations.style_profile_id sadece UUID kolon olarak duruyor).

Revision ID: 20260502_0100
Revises: 20260502_0000
Create Date: 2026-05-02 01:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID


revision: str = "20260502_0100"
down_revision: Union[str, None] = "20260502_0000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # generations (data-model.md §5.1)
    # ============================================================
    op.create_table(
        "generations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_text", sa.Text, nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("output_type", sa.String(32), nullable=False),
        sa.Column("tone", sa.String(32)),
        sa.Column("length", sa.String(16)),
        sa.Column(
            "show_sources",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("retrieval_plan_json", JSONB),
        sa.Column(
            "used_agenda_card_ids",
            ARRAY(UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "used_chunk_ids",
            ARRAY(UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("output_json", JSONB),
        sa.Column("warnings", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_provider", sa.String(80)),
        sa.Column("model_name", sa.String(120)),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost_estimate_usd", sa.Numeric(10, 6)),
        # style_profile_id: Faz 5 style_profiles tablosu eklenince FK eklenecek
        sa.Column("style_profile_id", UUID(as_uuid=True)),
        sa.Column("halu_flagged_at", sa.DateTime(timezone=True)),
        sa.Column(
            "halu_flagged_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("saved_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "mode IN ('current', 'weekly', 'archive', 'comparison')",
            name="ck_generations_mode",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'insufficient_data')",
            name="ck_generations_status",
        ),
    )

    op.create_index(
        "idx_generations_user_created",
        "generations",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_generations_status",
        "generations",
        ["status", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_generations_saved",
        "generations",
        ["user_id", sa.text("saved_at DESC")],
        postgresql_where=sa.text("saved_at IS NOT NULL"),
    )
    op.create_index(
        "idx_generations_mode",
        "generations",
        ["mode", sa.text("created_at DESC")],
    )
    # Output JSONB GIN index — sources/posts içinden arama (PRD §3.7)
    op.execute(
        "CREATE INDEX idx_generations_output_gin "
        "ON generations USING gin (output_json jsonb_path_ops)"
    )

    # ============================================================
    # usage_events (data-model.md §5.2)
    # ============================================================
    op.create_table(
        "usage_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(80)),
        sa.Column("model", sa.String(120)),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column(
            "metadata",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "idx_usage_events_user_created",
        "usage_events",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_usage_events_type",
        "usage_events",
        ["event_type", sa.text("created_at DESC")],
    )
    # Quota query optimization (kalan üretim hesabı, sliding window)
    op.create_index(
        "idx_usage_events_user_type_created",
        "usage_events",
        ["user_id", "event_type", sa.text("created_at DESC")],
    )

    # ============================================================
    # saved_generations (data-model.md §5.3)
    # ============================================================
    op.create_table(
        "saved_generations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "generation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("note", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "user_id", "generation_id", name="uq_saved_generations_user_gen"
        ),
    )

    op.create_index(
        "idx_saved_generations_user",
        "saved_generations",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_saved_generations_user", table_name="saved_generations")
    op.drop_table("saved_generations")
    op.drop_index("idx_usage_events_user_type_created", table_name="usage_events")
    op.drop_index("idx_usage_events_type", table_name="usage_events")
    op.drop_index("idx_usage_events_user_created", table_name="usage_events")
    op.drop_table("usage_events")
    op.execute("DROP INDEX IF EXISTS idx_generations_output_gin")
    op.drop_index("idx_generations_mode", table_name="generations")
    op.drop_index("idx_generations_saved", table_name="generations")
    op.drop_index("idx_generations_status", table_name="generations")
    op.drop_index("idx_generations_user_created", table_name="generations")
    op.drop_table("generations")
