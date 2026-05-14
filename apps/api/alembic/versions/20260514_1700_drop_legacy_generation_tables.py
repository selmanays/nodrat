"""Drop generations + saved_generations (#800 S1B — chat-only).

Chat-only migration: form modu kalktığı için generations + saved_generations
tabloları artık gereksiz. SFT tarihçesini korumak için training_samples ve
usage_events.generation_id FK kaldırılır + nullable kalır (anonim referans).

KRİTİK CASCADE etkileri:
- training_samples.generation_id FK CASCADE → FK drop, generation_id NULL
  bırakılır (tarihçe veri korunur, "anonim" referans)
- saved_generations TABLO DROP (kullanılmıyor)
- usage_events.generation_id FK CASCADE → FK drop, NULL kalır
- messages.generation_id FK SET NULL → kolon DROP (artık standalone)

generations TABLO DROP en son.

Revision: 20260514_1700
Revises: 20260514_1500
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260514_1700"
down_revision: str | None = "20260514_1500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) training_samples — generation_id FK kaldır, nullable kalır
    op.execute(sa.text(
        "ALTER TABLE training_samples "
        "DROP CONSTRAINT IF EXISTS training_samples_generation_id_fkey"
    ))
    op.execute(sa.text(
        "ALTER TABLE training_samples ALTER COLUMN generation_id DROP NOT NULL"
    ))
    # UNIQUE (generation_id, task_type) constraint kaldırılır — message_id (S1C)
    # ile yeni UNIQUE eklenir.
    op.execute(sa.text(
        "ALTER TABLE training_samples DROP CONSTRAINT IF EXISTS "
        "training_samples_generation_id_task_type_key"
    ))

    # 2) usage_events — generation_id FK kaldır + kolon nullable
    # NOT: Kolon var mı kontrolü yapılır (modelde generation_id zaten yok,
    # mevcut DB'de olabilir veya olmayabilir).
    op.execute(sa.text(
        "ALTER TABLE usage_events "
        "DROP CONSTRAINT IF EXISTS usage_events_generation_id_fkey"
    ))
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'usage_events' AND column_name = 'generation_id'
            ) THEN
                EXECUTE 'ALTER TABLE usage_events ALTER COLUMN generation_id DROP NOT NULL';
            END IF;
        END $$;
    """))

    # 3) messages — generation_id FK + kolon kaldır (standalone artık)
    op.execute(sa.text(
        "ALTER TABLE messages "
        "DROP CONSTRAINT IF EXISTS messages_generation_id_fkey"
    ))
    op.execute(sa.text(
        "DROP INDEX IF EXISTS idx_messages_generation"
    ))
    op.execute(sa.text(
        "ALTER TABLE messages DROP COLUMN IF EXISTS generation_id"
    ))

    # 4) saved_generations TABLO DROP (kullanım yok)
    op.execute(sa.text("DROP TABLE IF EXISTS saved_generations CASCADE"))

    # 5) generations TABLO DROP (en son)
    op.execute(sa.text("DROP TABLE IF EXISTS generations CASCADE"))


def downgrade() -> None:
    """Downgrade — tarihçe veri kaybı geri alınamaz.

    Bu migration destructive. Downgrade sadece schema'yı geri kurar; data
    geri gelmez. Production'da rollback yapılmamalı (staging-only).
    """
    # generations tablosu — minimal schema (data değil)
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS generations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            request_text TEXT NOT NULL,
            mode VARCHAR(16) NOT NULL,
            output_type VARCHAR(32) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS saved_generations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            generation_id UUID NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
            saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, generation_id)
        )
    """))
    op.execute(sa.text(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS generation_id UUID "
        "REFERENCES generations(id) ON DELETE SET NULL"
    ))
    op.execute(sa.text(
        "ALTER TABLE training_samples ADD CONSTRAINT training_samples_generation_id_fkey "
        "FOREIGN KEY (generation_id) REFERENCES generations(id) ON DELETE CASCADE"
    ))
