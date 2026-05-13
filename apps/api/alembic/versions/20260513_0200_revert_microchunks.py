"""Revert microchunks (#767 deneme negatif → tam temizlik).

Adım 1 (microchunk reform) eval sonucu nötr çıktı (recall@5 değişmedi,
latency +%26). Kullanıcı kararı: dormant altyapı tutma, tam temizlik
(dosyalar kafa karıştırmasın, storage boşa kalmasın).

Bu migration #767 ile eklenen schema + data'yı geri alır:
  - 29,804 micro chunk rows DELETE
  - chunker.micro_* 4 admin setting rows DELETE
  - parent_chunk_id kolonu DROP (FK + index dahil)
  - chunk_level kolonu DROP (CHECK + 2 index dahil)

Schema rolls back to revision 20260512_0300 (rerank cleanup) state.

Wiki ve score_history JSON'ları korunur (skor referansı + öğrenme).

Revision ID: 20260513_0200
Revises: 20260513_0100
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "20260513_0200"
down_revision: str | None = "20260513_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Micro chunks DELETE (29,804 rows production'da)
    op.execute("DELETE FROM article_chunks WHERE chunk_level = 'micro'")

    # 2) Admin settings DELETE (4 chunker.micro_* keys)
    op.execute(
        "DELETE FROM app_settings WHERE key IN ("
        "'chunker.micro_enabled', "
        "'chunker.micro_target_tokens', "
        "'chunker.micro_max_tokens', "
        "'chunker.micro_min_tokens')"
    )

    # 3) Indexes drop
    op.drop_index("idx_article_chunks_level_article", table_name="article_chunks")
    op.drop_index("idx_article_chunks_level_parent", table_name="article_chunks")

    # 4) FK + parent_chunk_id column drop
    op.drop_constraint(
        "fk_article_chunks_parent_chunk_id",
        "article_chunks",
        type_="foreignkey",
    )
    op.drop_column("article_chunks", "parent_chunk_id")

    # 5) CHECK + chunk_level column drop
    op.drop_constraint(
        "ck_article_chunks_chunk_level",
        "article_chunks",
        type_="check",
    )
    op.drop_column("article_chunks", "chunk_level")


def downgrade() -> None:
    """Re-introduce columns (data DELETE'i geri getirmek imkansız —
    micros + setting rows kalıcı kaybolur). Sadece schema reset.
    """
    op.add_column(
        "article_chunks",
        sa.Column(
            "chunk_level",
            sa.String(length=8),
            nullable=False,
            server_default="macro",
        ),
    )
    op.create_check_constraint(
        "ck_article_chunks_chunk_level",
        "article_chunks",
        "chunk_level IN ('macro', 'micro')",
    )
    op.add_column(
        "article_chunks",
        sa.Column(
            "parent_chunk_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_article_chunks_parent_chunk_id",
        "article_chunks",
        "article_chunks",
        ["parent_chunk_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_article_chunks_level_parent",
        "article_chunks",
        ["chunk_level", "parent_chunk_id"],
        postgresql_where=sa.text("chunk_level = 'micro'"),
    )
    op.create_index(
        "idx_article_chunks_level_article",
        "article_chunks",
        ["chunk_level", "article_id"],
    )
