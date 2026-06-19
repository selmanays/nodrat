"""Faz 1a — training_samples küme/artefakt şekli (additive, no-op)

SFT veri şeklini küme-merkezli vizyona hazırlar: training_samples'a artefakt +
küme bağlamı eklenir ki Faz 3'te generation→artefakt davranışı bağlandığı AN'dan
itibaren eğitim verisi DOĞRU granülde (küme/artefakt-bağlı) biriksin. Yanlış
granülde biriken veri geri kazanılamaz — bu yüzden şekil davranıştan ÖNCE döşenir.

Additive, izole → backward-compatible, zero-downtime. Mevcut kolonlar/satırlar
DEĞİŞMEZ; historical satırlarda yeni kolonlar NULL kalır. message_id yolu (mevcut
curator) AYNEN korunur. Curator artefakt-yolu Faz 3'te (gerçek veri + kesinleşmiş
revizyon-uygunluk semantiği) yazılacak.

Eklenenler:
- artifact_id (FK artifacts.id ON DELETE SET NULL) — training snapshot artefakt
  silinse de korunur (içerik redacted-immutable); KVKK cascade user_id'den gelir.
- artifact_revision_seq — hangi revizyondan curate edildi.
- cluster_id — hangi küme (soft ref, hard FK YOK; sample-creation anında IMMUTABLE,
  küme reassign'da retroaktif güncelleme yok — history-safety, trend subject_id deseni).
- uq_training_samples_artifact (partial unique) — artefakt-yolu idempotency.
- idx_training_samples_cluster (partial) — küme başına sample analitiği.

Embedding HARD-STOP: bu migration embedding/chunk verisine DOKUNMAZ.

Revision ID: 20260619_1500
Revises: 20260619_1400
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260619_1500"
down_revision: str | None = "20260619_1400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_samples",
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "training_samples",
        sa.Column("artifact_revision_seq", sa.Integer(), nullable=True),
    )
    op.add_column(
        "training_samples",
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Artefakt-yolu idempotency: bir (artefakt, revizyon, task, sample) için tek satır.
    op.create_index(
        "uq_training_samples_artifact",
        "training_samples",
        ["artifact_id", "artifact_revision_seq", "task_type", "sample_type"],
        unique=True,
        postgresql_where=sa.text("artifact_id IS NOT NULL"),
    )
    op.create_index(
        "idx_training_samples_cluster",
        "training_samples",
        ["cluster_id"],
        postgresql_where=sa.text("cluster_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_training_samples_cluster", table_name="training_samples")
    op.drop_index("uq_training_samples_artifact", table_name="training_samples")
    op.drop_column("training_samples", "cluster_id")
    op.drop_column("training_samples", "artifact_revision_seq")
    op.drop_column("training_samples", "artifact_id")
