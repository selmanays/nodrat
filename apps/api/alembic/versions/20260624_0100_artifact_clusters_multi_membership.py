"""Faz 2 — Çoklu-küme üyeliği: artifact_clusters junction (additive, no-op)

Küme-merkezli abonelik vizyonu Faz 2: bir artefakt (cevap) tek küme yerine
BİRDEN ÇOK kümeye ait olabilir — birincil (cevabın baskın öznesi) + ikincil
(cevapta adı geçen diğer entity'ler). Örn. "DEM Parti neden gündemde" cevabı
DEM Parti (birincil) + Tülay Hatimoğulları / asgari ücret (ikincil) kümelerinde
görünür → "Asgari Ücret"e abone kullanıcı bu cevabı da görür.

SADECE yeni junction tablosu döşenir — `artifacts.cluster_id` (birincil pointer)
DOKUNULMAZ, davranış flag'le (`artifacts.multi_cluster.enabled` default OFF) gelir.
Additive, izole → backward-compatible, zero-downtime. Mevcut tablolara DOKUNMAZ.

FK ON DELETE (message_clusters deseniyle hizalı):
- artifact_clusters.artifact_id → CASCADE  (artefakt silinince üyelik düşer)
- artifact_clusters.cluster_id  → RESTRICT (global küme düğümü korunur)

UNIQUE(artifact_id, cluster_id) → bir artefakt bir kümeye en fazla TEK kez bağlı
(merge dedup + tekrar-attach idempotent). role: 'primary' | 'secondary'.

Revision ID: 20260624_0100
Revises: 20260621_0100
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0100"
down_revision: str | None = "20260621_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifact_clusters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_clusters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # 'primary' = cevabın baskın öznesi (artifacts.cluster_id ile aynı küme);
        # 'secondary' = cevapta adı geçen diğer entity kümesi.
        sa.Column(
            "role", sa.String(length=16), nullable=False, server_default=sa.text("'secondary'")
        ),
        # df (cevap-içi kanıt yoğunluğu) — feed/chip sıralaması için.
        sa.Column("relevance", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("artifact_id", "cluster_id", name="uq_artifact_cluster"),
    )
    # Feed okuma yolu: bir kümeye bağlı (birincil+ikincil) artefaktlar.
    op.create_index(
        "idx_artifact_clusters_cluster",
        "artifact_clusters",
        ["cluster_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_artifact_clusters_artifact",
        "artifact_clusters",
        ["artifact_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_artifact_clusters_artifact", table_name="artifact_clusters")
    op.drop_index("idx_artifact_clusters_cluster", table_name="artifact_clusters")
    op.drop_table("artifact_clusters")
