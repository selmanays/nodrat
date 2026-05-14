"""article_chunks keywords + question_keywords kolonları (#778 Faz 3).

RagFlow adaptation: per-chunk LLM-extracted keywords + questions.
BM25 sparse retrieval'da yüksek ağırlık (RagFlow field weighting:
question_tks=6x, important_kwd=5x, title=2x, content=1x).

Bu chunk'a "çocuk" gibi discriminative kelime düşerse, "çocukların bahis..."
sorgusu doğru article'ı bulabilir — şu anki sistem bunu kaçırıyor (#778
açılış vakası).

Revision: 20260514_0100
Revises: 20260513_0200
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260514_0100"
down_revision: str | None = "20260513_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Keywords: LLM-extracted 3-5 anahtar kavram per chunk
    op.add_column(
        "article_chunks",
        sa.Column(
            "keywords",
            postgresql.ARRAY(sa.String(length=80)),
            nullable=True,
        ),
    )
    # 2) Question keywords: LLM-generated 3 olası soru per chunk (RagFlow pattern)
    op.add_column(
        "article_chunks",
        sa.Column(
            "question_keywords",
            postgresql.ARRAY(sa.String(length=200)),
            nullable=True,
        ),
    )
    # 3) Keywords last updated — backfill takibi için
    op.add_column(
        "article_chunks",
        sa.Column(
            "keywords_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # 4) GIN index — array overlap search hızlandırma
    op.create_index(
        "idx_article_chunks_keywords_gin",
        "article_chunks",
        ["keywords"],
        postgresql_using="gin",
        postgresql_where=sa.text("keywords IS NOT NULL"),
    )
    op.create_index(
        "idx_article_chunks_question_keywords_gin",
        "article_chunks",
        ["question_keywords"],
        postgresql_using="gin",
        postgresql_where=sa.text("question_keywords IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_article_chunks_question_keywords_gin", table_name="article_chunks"
    )
    op.drop_index("idx_article_chunks_keywords_gin", table_name="article_chunks")
    op.drop_column("article_chunks", "keywords_updated_at")
    op.drop_column("article_chunks", "question_keywords")
    op.drop_column("article_chunks", "keywords")
