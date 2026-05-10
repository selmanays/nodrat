"""articles.summary_embedding vector(1024) — article-level tema match (#661 Faz 5.2)

Mevcut chunk-level embedding niş bilgi için yeterli ama article ana teması için
ayrı bir vector lazım. Sorgu önce article-level match (ana tema), sonra
chunk-level (niş detay) → iki-aşamalı retrieval.

Embed input formula: `title + " " + (subtitle or "") + " " + first_paragraph[:200]`
Bu LangChain summary embedding pattern'i; haber ana teması yakalanır.

Index: HNSW bit_hamming (binary embedding gerekli değil — sadece pgvector
cosine_ops yeterli, IVFFlat 100 lists).

Backward-compat: NULL allowed. Eski article'lar summary_embedding NULL kalır.
Worker task ile background fill yapılır.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers
revision = "20260511_0100"
down_revision = "20260510_0500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Yeni column: 1024-dim (bge-m3 ile uyumlu)
    op.add_column(
        "articles",
        sa.Column("summary_embedding", Vector(1024), nullable=True),
    )
    # IVFFlat index — cosine_ops (semantic search için)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_articles_summary_emb "
        "ON articles USING ivfflat (summary_embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_articles_summary_emb")
    op.drop_column("articles", "summary_embedding")
