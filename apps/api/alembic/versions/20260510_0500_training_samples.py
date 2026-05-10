"""training_samples tablosu + 4 admin setting seed (#567)

ETL worker (apps/api/app/workers/tasks/sft_curator.py) ham generations
log'undan altın etiketlenmiş (sft_eligible=true) satırları curated
training dataset'ine dönüştürür. Trendyol-LLM-7B-chat-v4.1.0 üzerine
domain-spesifik fine-tune için.

Tablo:
  - generation_id (FK CASCADE) + user_id (FK CASCADE — KVKK md.11
    revoke + soft delete propagation)
  - task_type ∈ {content_generator, query_planner, style_analyzer}
  - prompt_version (audit)
  - input_payload + output_payload (JSONB ChatML)
  - edited_output (DPO için kullanıcı nihai metni)
  - quality_signals (citation ratio, edit_distance, schema_valid,
    char_count, source_count, time_to_action_sec)
  - sft_split ∈ {train, val, test}, deterministic hash(generation_id) % 100
  - curated_at + exported_at (HF dataset push tracking)

Idempotency: UNIQUE(generation_id, task_type) — worker 2 kez çalışsa
duplicate eklemez.

4 yeni admin setting (app_settings seed):
  - sft.curator.review_buffer_days     (INT, default 7)
  - sft.curator.daily_max_samples      (INT, default 1000)
  - sft.curator.min_quality_score      (FLOAT, default 0.7)
  - sft.curator.enabled                (BOOL, default false — kill switch)

Refs: #567
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "20260510_0500"
down_revision = "20260510_0400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_samples",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "generation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("input_payload", JSONB, nullable=False),
        sa.Column("output_payload", JSONB, nullable=False),
        sa.Column("edited_output", sa.Text(), nullable=True),
        sa.Column(
            "quality_signals",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("sft_split", sa.String(8), nullable=False),
        sa.Column(
            "curated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "task_type IN ('content_generator', 'query_planner', 'style_analyzer')",
            name="ck_training_samples_task_type",
        ),
        sa.CheckConstraint(
            "sft_split IN ('train', 'val', 'test')",
            name="ck_training_samples_sft_split",
        ),
    )

    op.create_index(
        "idx_training_samples_task",
        "training_samples",
        ["task_type", "sft_split"],
    )
    op.create_index(
        "idx_training_samples_user",
        "training_samples",
        ["user_id"],
    )
    op.create_index(
        "idx_training_samples_curated",
        "training_samples",
        [sa.text("curated_at DESC")],
    )
    op.create_index(
        "idx_training_samples_gen_task",
        "training_samples",
        ["generation_id", "task_type"],
        unique=True,
    )

    # 4 admin setting seed (settings_store ile runtime tunable)
    op.execute(
        """
        INSERT INTO app_settings (key, value, type, group_name, description)
        VALUES
            ('sft.curator.enabled', 'false'::jsonb, 'bool', 'sft',
             'SFT curator nightly worker on/off (kill switch).'),
            ('sft.curator.review_buffer_days', '7'::jsonb, 'int', 'sft',
             'Generation oluştuktan kaç gün sonra ETL''e dahil.'),
            ('sft.curator.daily_max_samples', '1000'::jsonb, 'int', 'sft',
             'Bir koşumda max sample sayısı (overflow protection).'),
            ('sft.curator.min_quality_score', '0.7'::jsonb, 'float', 'sft',
             'Quality signals composite threshold (0-1 arası).')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM app_settings WHERE key IN (
            'sft.curator.enabled',
            'sft.curator.review_buffer_days',
            'sft.curator.daily_max_samples',
            'sft.curator.min_quality_score'
        )
        """
    )

    op.drop_index("idx_training_samples_gen_task", table_name="training_samples")
    op.drop_index("idx_training_samples_curated", table_name="training_samples")
    op.drop_index("idx_training_samples_user", table_name="training_samples")
    op.drop_index("idx_training_samples_task", table_name="training_samples")
    op.drop_table("training_samples")
