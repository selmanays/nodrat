"""Faz 7 — chat→research fiziksel rename (tablo + app_settings + CHECK + constraint adları)

Pivot tamamlama (kullanıcı talebi: "chat ifadesi DB dahil hiçbir yerde kalmamalı"):
- chat_cache_telemetry → research_cache_telemetry (+ pkey/fkey constraint adları)
- app_settings: chat.* anahtarları → research.* (ORM/SETTING_REGISTRY ile hizalı;
  prod'da yalnız chat.l1_windowed_context_enabled satırı var)
- ck_training_samples_task_type: model ile hizala ('research_answer' dahil;
  training_samples BOŞ → satır UPDATE gerekmez; prod constraint zaten 'chat_answer'
  içermiyordu, salt model↔DB tutarlılığı)

B-grup DOKUNULMAZ: provider operation 'chat' (provider_log enum), LLM sağlayıcı
chat-completions primitifi, dış model adları (Trendyol-LLM-7B-chat, deepseek-chat).

Revision ID: 20260519_0100
Revises: 20260518_0400
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260519_0100"
down_revision: str | None = "20260518_0400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_constraint(table: str, old: str, new: str) -> None:
    """pg_constraint'te varsa güvenle yeniden adlandır (idempotent)."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{old}') THEN
                ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new};
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    # 1) Tablo + bağlı constraint/index adları (chat → research)
    op.execute("ALTER TABLE IF EXISTS chat_cache_telemetry RENAME TO research_cache_telemetry")
    _rename_constraint(
        "research_cache_telemetry",
        "chat_cache_telemetry_pkey",
        "research_cache_telemetry_pkey",
    )
    _rename_constraint(
        "research_cache_telemetry",
        "chat_cache_telemetry_user_id_fkey",
        "research_cache_telemetry_user_id_fkey",
    )
    op.execute(
        "ALTER INDEX IF EXISTS chat_cache_telemetry_pkey RENAME TO research_cache_telemetry_pkey"
    )

    # 2) app_settings anahtar rename: chat.X → research.X (çakışma guard)
    op.execute(
        "UPDATE app_settings SET key = 'research.' || substring(key from 6) "
        "WHERE key LIKE 'chat.%' "
        "AND NOT EXISTS (SELECT 1 FROM app_settings b "
        "WHERE b.key = 'research.' || substring(app_settings.key from 6))"
    )

    # 3) CHECK constraint'i ORM ile hizala (research_answer)
    op.execute(
        "ALTER TABLE training_samples DROP CONSTRAINT IF EXISTS ck_training_samples_task_type"
    )
    op.execute(
        "ALTER TABLE training_samples ADD CONSTRAINT "
        "ck_training_samples_task_type CHECK (task_type IN "
        "('content_generator','research_answer','query_planner','style_analyzer'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE training_samples DROP CONSTRAINT IF EXISTS ck_training_samples_task_type"
    )
    op.execute(
        "ALTER TABLE training_samples ADD CONSTRAINT "
        "ck_training_samples_task_type CHECK (task_type IN "
        "('content_generator','query_planner','style_analyzer'))"
    )
    # settings geri-al: dev best-effort, yalnız bilinen prod anahtarı
    op.execute(
        "UPDATE app_settings SET key = 'chat.' || substring(key from 10) "
        "WHERE key = 'research.l1_windowed_context_enabled'"
    )
    op.execute(
        "ALTER INDEX IF EXISTS research_cache_telemetry_pkey RENAME TO chat_cache_telemetry_pkey"
    )
    _rename_constraint(
        "research_cache_telemetry",
        "research_cache_telemetry_user_id_fkey",
        "chat_cache_telemetry_user_id_fkey",
    )
    _rename_constraint(
        "research_cache_telemetry",
        "research_cache_telemetry_pkey",
        "chat_cache_telemetry_pkey",
    )
    op.execute("ALTER TABLE IF EXISTS research_cache_telemetry RENAME TO chat_cache_telemetry")
