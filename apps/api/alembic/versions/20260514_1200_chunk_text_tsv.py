"""article_chunks chunk_text_tsv FTS column (#782 sparse query 5s → ~50ms).

Profil tespiti: trigram `c.chunk_text_norm % :q` uzun Türkçe query'lerde GIN
bitmap'in ~13K satır match etmesine sebep oluyor (common Turkish trigram'lar),
heap recheck 5+ saniye. Skip denendi → recall regresyonu.

Çözüm: tsvector full-text search column + GIN tsvector index. PostgreSQL
inverted index (RagFlow Elasticsearch BM25 eşdeğeri vibes). websearch_to_tsquery
ile natural language query parse.

Bekleyen kazanım: sparse 5s → ~50ms (inverted index seek).

Tasarım kararları:
- Config: 'simple' (Türkçe stemmer yok, tokenization yeterli — niş entity'ler
  zaten exact match gerekir; stemming "maçının" → "maç" potansiyel yanlış match)
- Trigger BEFORE UPDATE OF chunk_text_norm (chunk_text_norm zaten yeni — değişim
  tetiklenir, FTS otomatik güncellenir)
- Mevcut 13169 satır single UPDATE (chunk_text_norm zaten dolu, sadece tsv hesap)

Revision: 20260514_1200
Revises: 20260514_1100
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260514_1200"
down_revision: str | None = "20260514_1100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Nullable tsvector column
    op.execute(sa.text("ALTER TABLE article_chunks ADD COLUMN chunk_text_tsv tsvector"))

    # 2) Trigger BEFORE INSERT/UPDATE chunk_text_norm
    op.execute(
        sa.text("""
        CREATE OR REPLACE FUNCTION fn_chunk_text_tsv()
        RETURNS trigger AS $$
        BEGIN
            NEW.chunk_text_tsv := to_tsvector('simple', COALESCE(NEW.chunk_text_norm, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    )
    op.execute(
        sa.text("""
        CREATE TRIGGER trg_chunk_text_tsv
        BEFORE INSERT OR UPDATE OF chunk_text_norm
        ON article_chunks
        FOR EACH ROW
        EXECUTE FUNCTION fn_chunk_text_tsv();
    """)
    )

    # 3) Backfill mevcut satırlar
    op.execute(
        sa.text("""
        UPDATE article_chunks
        SET chunk_text_tsv = to_tsvector('simple', COALESCE(chunk_text_norm, ''))
        WHERE chunk_text_tsv IS NULL
    """)
    )

    # 4) GIN tsvector index
    op.execute(
        sa.text("""
        CREATE INDEX idx_article_chunks_text_tsv
        ON article_chunks USING gin (chunk_text_tsv)
    """)
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_article_chunks_text_tsv"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_chunk_text_tsv ON article_chunks"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS fn_chunk_text_tsv()"))
    op.execute(sa.text("ALTER TABLE article_chunks DROP COLUMN IF EXISTS chunk_text_tsv"))
