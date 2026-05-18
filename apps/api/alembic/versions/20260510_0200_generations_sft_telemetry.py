"""generations SFT telemetry kolonları (#563)

User-action telemetry + sft_eligible flag — Trendyol-LLM-7B-chat-v4.1.0
üzerine domain-spesifik fine-tune için altın etiketleme altyapısı.

7 yeni kolon (tümü nullable veya default değerli, backward compat):
  - user_action          → 'copied' | 'posted' | 'edited' | 'regenerated' | 'kept' | 'deleted'
  - action_at            → ilk user action zamanı
  - time_to_action_sec   → completed_at → action_at süresi
  - edited_text          → kullanıcının nihai düzenlenmiş metni (DPO için)
  - edit_distance        → Levenshtein normalize 0-1 (NUMERIC(4,3))
  - sft_eligible         → ETL filter flag (default false)
  - sft_excluded_reason  → eligible değilse audit nedeni

2 yeni CHECK constraint:
  - ck_generations_user_action     → enum guard
  - ck_generations_edit_distance   → 0-1 range guard

1 yeni partial index:
  - idx_generations_sft_eligible (sft_eligible, created_at DESC) WHERE sft_eligible = true
    → ETL nightly worker fast scan (sadece eligible satırlar).

Mevcut satırlar etkilenmez (lazy populate — endpoint'ler dolduracak).

Refs: #563
"""

import sqlalchemy as sa
from alembic import op

revision = "20260510_0200"
down_revision = "20260510_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column("user_action", sa.String(20), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("action_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("time_to_action_sec", sa.Integer(), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("edited_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("edit_distance", sa.Numeric(4, 3), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column(
            "sft_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "generations",
        sa.Column("sft_excluded_reason", sa.String(64), nullable=True),
    )

    op.create_check_constraint(
        "ck_generations_user_action",
        "generations",
        "user_action IS NULL OR user_action IN "
        "('copied', 'posted', 'edited', 'regenerated', 'kept', 'deleted')",
    )
    op.create_check_constraint(
        "ck_generations_edit_distance",
        "generations",
        "edit_distance IS NULL OR (edit_distance >= 0 AND edit_distance <= 1)",
    )

    op.create_index(
        "idx_generations_sft_eligible",
        "generations",
        ["sft_eligible", sa.text("created_at DESC")],
        postgresql_where=sa.text("sft_eligible = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_generations_sft_eligible", table_name="generations")
    op.drop_constraint("ck_generations_edit_distance", "generations", type_="check")
    op.drop_constraint("ck_generations_user_action", "generations", type_="check")
    op.drop_column("generations", "sft_excluded_reason")
    op.drop_column("generations", "sft_eligible")
    op.drop_column("generations", "edit_distance")
    op.drop_column("generations", "edited_text")
    op.drop_column("generations", "time_to_action_sec")
    op.drop_column("generations", "action_at")
    op.drop_column("generations", "user_action")
