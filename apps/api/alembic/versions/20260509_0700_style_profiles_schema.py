"""Style profiles schema (#52, Faz 5)

PRD §5.6 + data-model §7.1-7.2 ile uyumlu. Generation tablosunda mevcut
`style_profile_id` kolonu (PRD §5 hazırlık) artık FK olarak çalışır.

Tablolar:
  style_profiles  — kullanıcı stil profili (rules_json)
  style_samples   — stil profiline ait örnek metinler

Generation FK eklenmesi: SET NULL (profile silinince generation'lar nötr stil
ile yeniden render edilebilir).

Revision ID: 20260509_0700
Revises: 20260509_0600
Create Date: 2026-05-09 07:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260509_0700"
down_revision = "20260509_0600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "style_profiles",
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
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("style_summary", sa.Text(), nullable=True),
        sa.Column(
            "rules_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "sample_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'csv_import', 'public_account', 'x_personal')",
            name="ck_style_profiles_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'analyzing', 'ready', 'failed')",
            name="ck_style_profiles_status",
        ),
    )
    op.create_index(
        "idx_style_profiles_user",
        "style_profiles",
        ["user_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "style_samples",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "style_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("style_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "char_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_style_samples_profile",
        "style_samples",
        ["style_profile_id"],
    )

    # Generation.style_profile_id artık FK; mevcut nullable kolon zaten var.
    op.create_foreign_key(
        "fk_generations_style_profile",
        "generations",
        "style_profiles",
        ["style_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_generations_style_profile", "generations", type_="foreignkey"
    )
    op.drop_index("idx_style_samples_profile", table_name="style_samples")
    op.drop_table("style_samples")
    op.drop_index("idx_style_profiles_user", table_name="style_profiles")
    op.drop_table("style_profiles")
