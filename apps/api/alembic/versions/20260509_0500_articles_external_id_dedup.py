"""articles.external_article_id + dedup (97 slug-change duplicate consolidation) (#496)

Production tanı (2026-05-09 02:00 UTC):
  Aynı source + aynı haber ID + farklı slug → 2-4 ayrı article kaydı.
  Evrensel haberlerinin slug'ları yayım sonrası düzeltiliyor (örn. 'odtude' →
  'odtu-de'); RSS feed iki farklı URL veriyor, biz iki article INSERT ediyoruz.

  Audit: haber_id_dup_count = 97 set (en kötü 5982831 x4, 5982996 x4).
  Toplam ~240 wasted fetch_detail call'ı.

Bu migration:
  1. `articles.external_article_id TEXT NULL` kolonu ekler
  2. Index: `(source_id, external_article_id) WHERE NOT NULL` partial unique
     (race-safe; aynı source + aynı ext_id ikinci INSERT IntegrityError)
  3. Backfill: mevcut canonical_url'lerden ext_id extract (regex) →
     external_article_id'ya yazar
  4. Consolidation: aynı (source_id, external_article_id) set'inde EN ESKİ
     cleaned tut, kalan dup'ları status='archived' yap (cleaned'leri bozma —
     ayrı data quality issue)

Beklenen etki: 97 dup set → 0 (cleaned tek kalır, kalanlar archived).

Revision ID: 20260509_0500
Revises: 20260509_0400
Create Date: 2026-05-09 05:00:00

NOT: Paralel iş #498 (Lemon Squeezy billing schema) aynı revision ID
'20260509_0400'ü kullanmıştı (alembic multiple-head conflict). Bu migration
0500'a renumber edildi, down_revision LS migration'ına zincirlendi
(linear chain: 0300 → 0400 LS → 0500 ext_id dedup).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260509_0500"
down_revision = "20260509_0400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Yeni kolon
    op.add_column(
        "articles",
        sa.Column("external_article_id", sa.Text(), nullable=True),
    )

    # 2) Backfill — generic regex pattern. PostgreSQL substring with regex.
    # Patterns:
    #   /haber/(\d+)/  → Evrensel
    #   /(\d{6,})(?:/|\?|$) → AA / suffix numeric (6+ digit)
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET external_article_id = COALESCE(
                substring(canonical_url FROM '/haber/([0-9]+)(?:/|\\?|$)'),
                substring(canonical_url FROM '/([0-9]{6,})(?:/|\\?|$)')
            )
            WHERE external_article_id IS NULL
            """
        )
    )

    # 3) Partial unique index — aynı source + aynı ext_id tekil
    # NOT: dup'ları temizlemeden index UNIQUE yapamayız — önce consolidation,
    # sonra index. Sıra önemli.

    # 4) Consolidation: aynı (source_id, external_article_id) için en eski
    # cleaned'i tut (varsa), kalanları archived'a çek (ama cleaned olanları
    # değiştirme — eğer 2 cleaned varsa data quality issue, ayrı incelenir).
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY source_id, external_article_id
                        ORDER BY
                            -- Status öncelik: cleaned > archived > failed > diğer
                            CASE status
                                WHEN 'cleaned' THEN 0
                                WHEN 'archived' THEN 1
                                WHEN 'failed' THEN 2
                                ELSE 3
                            END,
                            created_at ASC
                    ) AS rn
                FROM articles
                WHERE external_article_id IS NOT NULL
            )
            UPDATE articles
            SET status = 'archived',
                updated_at = NOW()
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
              AND status NOT IN ('cleaned', 'archived')
            """
        )
    )

    # 5) Şimdi UNIQUE index (consolidation sonrası güvenli).
    # Cleaned x N veya Archived x N ihtimali kalmış olabilir (data quality);
    # bu durumda index oluşturmaya engel değil çünkü partial: önce mevcut
    # cleaned + archived karması varsa farklı status'lar tek tek tutuluyor.
    # Yine de güvenli olmak için ARCHIVED dup'ları bile tek bırakalım:
    op.execute(
        sa.text(
            """
            WITH ranked2 AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY source_id, external_article_id
                        ORDER BY
                            CASE status WHEN 'cleaned' THEN 0 ELSE 1 END,
                            created_at ASC
                    ) AS rn
                FROM articles
                WHERE external_article_id IS NOT NULL
            )
            DELETE FROM articles
            WHERE id IN (SELECT id FROM ranked2 WHERE rn > 1)
              AND status = 'archived'
            """
        )
    )

    # 6) Partial unique index
    op.create_index(
        "uq_articles_source_external_id",
        "articles",
        ["source_id", "external_article_id"],
        unique=True,
        postgresql_where=sa.text("external_article_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_articles_source_external_id", table_name="articles")
    op.drop_column("articles", "external_article_id")
