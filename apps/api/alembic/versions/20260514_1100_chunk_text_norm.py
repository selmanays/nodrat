"""article_chunks chunk_text_norm + functional GIN trigram (#781 hız).

Profil bulgusu: sparse BM25 query 14 saniye sürüyor çünkü `LOWER(quote_strip(c.chunk_text))`
inline ifadesi `idx_article_chunks_text_trgm` GIN index'ini bypass ediyor.

Çözüm: Nullable column `chunk_text_norm` + batched UPDATE + GIN trigram index.

NOT GENERATED STORED: postgres /dev/shm default 64MB çok küçük, ALTER ADD
GENERATED STORED tek seferde tüm tabloyu rewrite ediyor (DiskFullError).
Bunun yerine:
1. ADD COLUMN nullable (anında, ucuz)
2. Batched UPDATE 1000'erli (her batch bağımsız transaction)
3. CREATE INDEX

Trigger (INSERT/UPDATE chunk_text) BEFORE: chunk_text_norm hesapla.

Bekleyen kazanım: sparse 14s → ~200ms (index seek vs full scan).

Revision: 20260514_1100
Revises: 20260514_0100
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260514_1100"
down_revision: str | None = "20260514_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_QUOTE_CHARS = [
    "'",
    "‘",
    "’",
    "‚",
    "‛",
    "′",
    "ʼ",
    "ʹ",
    '"',
    "“",
    "”",
    "„",
    "‟",
    "″",
    "«",
    "»",
    "‹",
    "›",
    "`",
]


def _build_replace_chain(column: str) -> str:
    expr = column
    for q in _QUOTE_CHARS:
        sql_literal = "''''" if q == "'" else f"'{q}'"
        expr = f"REPLACE({expr}, {sql_literal}, '')"
    return expr


def upgrade() -> None:
    norm_expr = f"LOWER({_build_replace_chain('chunk_text')})"

    # 1) Nullable column — anlık, table rewrite yok
    op.execute(sa.text("ALTER TABLE article_chunks ADD COLUMN chunk_text_norm text"))

    # 2) Trigger BEFORE INSERT/UPDATE — yeni satırlarda otomatik populate
    trigger_norm = f"LOWER({_build_replace_chain('NEW.chunk_text')})"
    op.execute(
        sa.text(f"""
        CREATE OR REPLACE FUNCTION fn_chunk_text_norm()
        RETURNS trigger AS $$
        BEGIN
            NEW.chunk_text_norm := {trigger_norm};
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    )
    op.execute(
        sa.text("""
        CREATE TRIGGER trg_chunk_text_norm
        BEFORE INSERT OR UPDATE OF chunk_text
        ON article_chunks
        FOR EACH ROW
        EXECUTE FUNCTION fn_chunk_text_norm();
    """)
    )

    # 3) Backfill mevcut satırlar — tek transaction içinde (alembic auto-wraps).
    # NOT: COMMIT içeren PL/pgSQL DO bloğu alembic'te çalışmıyor
    # (InvalidTransactionTerminationError). 12K row × ~500 byte = ~6MB
    # tek UPDATE, memory sorun yok (GENERATED STORED'in shared_buffers
    # patlamasına neden olan table rewrite davranışı yoktur).
    op.execute(
        sa.text(f"""
        UPDATE article_chunks
        SET chunk_text_norm = {norm_expr}
        WHERE chunk_text_norm IS NULL
    """)  # noqa: S608
    )

    # 4) GIN trigram index
    op.execute(
        sa.text("""
        CREATE INDEX idx_article_chunks_text_norm_trgm
        ON article_chunks USING gin (chunk_text_norm gin_trgm_ops)
    """)
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_article_chunks_text_norm_trgm"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_chunk_text_norm ON article_chunks"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS fn_chunk_text_norm()"))
    op.execute(sa.text("ALTER TABLE article_chunks DROP COLUMN IF EXISTS chunk_text_norm"))
