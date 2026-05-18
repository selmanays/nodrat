"""article_chunks binary quantization scaffold (#221 MVP-1.5 PR-6).

Storage: vector(1024) float32 = 4 KB/chunk
         bit(1024)            = 128 B/chunk → 32x küçülme
NDCG@10 ≤ %3 düşer (pgvector docs).

Bu migration sadece SCAFFOLD — search akışı hâlâ float32 kullanır.
Binary kolon backfill task ile doldurulur, settings flag
(vector_quantization.enabled) opt-in. Eval gate sonrası primary
yapılması ayrı PR.

HNSW Hamming index pgvector 0.7+ ile gelir; mevcut sürüm 0.8.2 ✓.

Revision ID: 20260506_1830
Revises: 20260506_1500
Create Date: 2026-05-06 18:30:00
"""

from __future__ import annotations

from alembic import op

revision = "20260506_1830"
down_revision = "20260506_1500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Binary kolon
    op.execute(
        "ALTER TABLE article_chunks "
        "ADD COLUMN IF NOT EXISTS embedding_binary bit(1024)"
    )

    # 2. HNSW Hamming index — query'de bit_count(b1 # b2) için
    # CONCURRENTLY: write trafiği bloklamaz; CREATE INDEX'in tek başına
    # çalışması gerek (transaction outside).
    op.execute("COMMIT")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "idx_article_chunks_embedding_binary "
        "ON article_chunks USING hnsw (embedding_binary bit_hamming_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS idx_article_chunks_embedding_binary"
    )
    op.execute("COMMIT")
    op.execute(
        "ALTER TABLE article_chunks DROP COLUMN IF EXISTS embedding_binary"
    )
