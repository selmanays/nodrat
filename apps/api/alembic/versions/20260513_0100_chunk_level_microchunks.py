"""article_chunks chunk_level + parent_chunk_id columns (#767 Adım 1).

2-level chunking için schema:
  - chunk_level VARCHAR(8) DEFAULT 'macro' — 'macro' (256-400 token, LLM context)
    | 'micro' (128-200 token, search index)
  - parent_chunk_id UUID NULL FK→article_chunks.id — her micro hangi macro'dan

Backward-compat: mevcut 11K+ chunk default 'macro' olur, davranış değişmez.
Feature flag `chunker.micro_enabled` OFF iken hiç micro üretilmez.

Revision ID: 20260513_0100
Revises: 20260512_0300
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260513_0100"
down_revision: str | None = "20260512_0300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) chunk_level kolonu — mevcut tüm rows 'macro' (default backward-compat)
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

    # 2) parent_chunk_id — micro→macro link (nullable: macros NULL'a sahip)
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

    # 3) Index — micros retrieve ederken parent fetch için (level + parent partial)
    op.create_index(
        "idx_article_chunks_level_parent",
        "article_chunks",
        ["chunk_level", "parent_chunk_id"],
        postgresql_where=sa.text("chunk_level = 'micro'"),
    )

    # 4) Index — retrieval level filter (chunk_level='macro' aktif sorgular için)
    op.create_index(
        "idx_article_chunks_level_article",
        "article_chunks",
        ["chunk_level", "article_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_article_chunks_level_article", table_name="article_chunks")
    op.drop_index("idx_article_chunks_level_parent", table_name="article_chunks")
    op.drop_constraint(
        "fk_article_chunks_parent_chunk_id",
        "article_chunks",
        type_="foreignkey",
    )
    op.drop_column("article_chunks", "parent_chunk_id")
    op.drop_constraint(
        "ck_article_chunks_chunk_level",
        "article_chunks",
        type_="check",
    )
    op.drop_column("article_chunks", "chunk_level")
