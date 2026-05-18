"""72h+ failed article'ları status='archived'a çek (#478)

Production tanı (2026-05-08 23:00 UTC):
  articles.status='failed' = 150
  └─ age 0-24h: 1
  └─ age 24-72h: 12
  └─ age >72h:  137  (kaynak haber muhtemelen artık erişilemez)

`retry_failed_articles` task'ı `max_age_hours=72` filter ile çalışır — 72h+ olanları
zaten yeniden denemiyor. Ama articles.status='failed' kalıyor; UI Haberler
sayfasında "Başarısız: 150" gösteriyor, alarm yorgunluğu yaratıyor.

Articles schema check constraint: status IN ('discovered', 'fetched', 'cleaned',
'failed', 'archived'). 'archived' zaten mevcut (cold tier için kullanılır), bu
migration eski failed kayıtları o statusa çeker — UI default sorgudan kaybolur,
admin gerekirse archived filter ile görür.

Beklenen etki: failed 150 -> ~13 (gerçek son 72h fail'leri).

Revision ID: 20260508_2300
Revises: 20260508_2200
Create Date: 2026-05-08 23:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260508_2300"
down_revision = "20260508_2200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET status = 'archived',
                updated_at = NOW()
            WHERE status = 'failed'
              AND created_at < NOW() - INTERVAL '72 hours'
            """
        )
    )


def downgrade() -> None:
    # Geri alma: bu migration'la archive edilenleri 'failed'e çek.
    # archived_at cold tier'a yazılmadığı için sadece 72h+ status='archived'
    # AND archived_at IS NULL → eski stale failed olanlardır.
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET status = 'failed'
            WHERE status = 'archived'
              AND archived_at IS NULL
              AND created_at < NOW() - INTERVAL '72 hours'
            """
        )
    )
