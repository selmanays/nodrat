"""external_article_id backfill — TRT .html pattern (#504)

#496 migration'ı TRT URL'lerinde \\.html extension'ı yakalamıyordu:
  /haber/.../944072.html → ext_id=NULL bırakıyordu

#504 ile pattern güncellendi: /haber/(\\d+)\\.html?(?:/|\\?|$). Bu migration
mevcut NULL kayıtlar için backfill yapar (yeni pattern). Canlı blog/video/
veri sayfaları (live-blog, canli-altin, /video/) zaten ID-tabanlı değil →
NULL kalır (bu doğru, onlar discovery'de skip edilecek).

Beklenen etki: 11 NULL → ~5 NULL (TRT haber + AA/Habertürk numeric ID
URL'leri yakalanır; live-blog ve veri sayfaları NULL kalır — onlar zaten
gelecekte discovery'de skip edilecek).

Revision ID: 20260509_0600
Revises: 20260509_0500
Create Date: 2026-05-09 06:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0600"
down_revision = "20260509_0500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 3 ayrı pattern ile COALESCE (asyncpg-uyumlu, \y yok):
    #   /haber/{id}[.html] → Evrensel + bazı TRT
    #   /{id}[.html]       → AA + path-prefix numeric suffix
    #   -{id}[.html]       → TRT slug-suffix (`-944072.html`)
    #
    # Güvenli backfill (UNIQUE ihlali önle):
    #   - CTE ile candidate'ları hesapla
    #   - ROW_NUMBER ile aynı (source_id, ext_id) için sadece en eski'i seç
    #   - NOT EXISTS ile başka bir article'ın bu ext_id'yi zaten almadığını
    #     doğrula (uq_articles_source_external_id partial index'i)
    op.execute(
        sa.text(
            r"""
            WITH candidate AS (
                SELECT id, source_id, created_at,
                       COALESCE(
                           substring(canonical_url FROM '/haber/([0-9]+)(?:\.html?)?(?:/|\?|$)'),
                           substring(canonical_url FROM '/([0-9]{6,})(?:\.html?)?(?:/|\?|$)'),
                           substring(canonical_url FROM '-([0-9]{6,})(?:\.html?)?(?:/|\?|$)')
                       ) AS computed_ext_id
                FROM articles
                WHERE external_article_id IS NULL
            ),
            ranked AS (
                SELECT id, source_id, computed_ext_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY source_id, computed_ext_id
                           ORDER BY created_at ASC
                       ) AS rn
                FROM candidate
                WHERE computed_ext_id IS NOT NULL
            )
            UPDATE articles a
            SET external_article_id = r.computed_ext_id
            FROM ranked r
            WHERE a.id = r.id
              AND r.rn = 1
              AND NOT EXISTS (
                  SELECT 1 FROM articles a3
                  WHERE a3.source_id = r.source_id
                    AND a3.external_article_id = r.computed_ext_id
              )
            """
        )
    )


def downgrade() -> None:
    # Geri alma yok — sadece backfill, kolon mevcut. Pattern değişiminin
    # geri alınması gerekirse cleaning.py değiştirilir.
    pass
