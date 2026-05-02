"""Add article_chunks.chunk_text gin_trgm index for hybrid search (#171 PR-E)

docs/product/prd.md §2.7 (hybrid retrieval — sparse layer)

Revision ID: 20260502_1500
Revises: 20260502_1100
Create Date: 2026-05-02 15:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260502_1500"
down_revision: Union[str, None] = "20260502_1100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Hybrid search sparse layer — pg_trgm similarity (extension migration
    # 20260501_1900'de yüklü). dense (cosine) + sparse (trigram) RRF birleşir.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_article_chunks_text_trgm "
        "ON article_chunks USING gin (chunk_text gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agenda_cards_title_trgm "
        "ON agenda_cards USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agenda_cards_summary_trgm "
        "ON agenda_cards USING gin (summary gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_article_chunks_text_trgm")
    op.execute("DROP INDEX IF EXISTS idx_agenda_cards_title_trgm")
    op.execute("DROP INDEX IF EXISTS idx_agenda_cards_summary_trgm")
