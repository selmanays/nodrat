"""articles.cleaned_at — pipeline state-machine geçiş timestamp'i (#513)

Bug: admin Özet sayfası 'Temizlenen içerikler' chart'ı tek saatte (21:00 UTC)
2620 article gösteriyordu. Sebep: chart `articles.updated_at` üzerinden
gruplaniyor, ama updated_at çok-amaçlı (status değişimi, body_html drop, ext_id
backfill, dedup migration vb.). Migration toplu UPDATE'leri tüm cleaned
article'ların updated_at'ini eş zamanlı değiştirip chart'ı yığdı.

Çözüm: yeni `cleaned_at TIMESTAMPTZ NULL` kolonu — sadece pipeline status
'cleaned' geçişinde set edilir. Migration UPDATE'leri etkilemez. Aynı pattern
image_vlm processed_at'te zaten kullanılıyor (#479).

Backfill: mevcut cleaned article'lar için `cleaned_at = fetched_at` (gerçek
cleaning ~saniye/dakika içinde fetched_at'ten sonra olur, %1 doğruluk yeterli).

Index: chart query'si için partial index (cleaned_at) WHERE status='cleaned'.

Revision ID: 20260509_0800
Revises: 20260509_0700
Create Date: 2026-05-09 08:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0800"
down_revision = "20260509_0700"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Yeni kolon (nullable, default NULL — non-cleaned article'larda dolmaz)
    op.add_column(
        "articles",
        sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2) Backfill — mevcut cleaned article'lar için fetched_at (gerçek cleaning
    # zamanı tahmini). updated_at KULLANILMAZ — yığılma sebebi o.
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET cleaned_at = fetched_at
            WHERE status = 'cleaned'
              AND cleaned_at IS NULL
            """
        )
    )

    # 3) Partial index — chart query hot path
    op.create_index(
        "idx_articles_cleaned_at_status",
        "articles",
        ["cleaned_at"],
        postgresql_where=sa.text("status = 'cleaned' AND cleaned_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_articles_cleaned_at_status", table_name="articles")
    op.drop_column("articles", "cleaned_at")
