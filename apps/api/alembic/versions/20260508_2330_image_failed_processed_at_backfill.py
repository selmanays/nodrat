"""article_images failed kayıtları için processed_at backfill (#479)

Production tanı (2026-05-08 23:30 UTC):
  article_images.status='failed' = 23
  └─ processed_at IS NULL: 23 (TÜMÜ)

Eski image_vlm task fail path'leri (ImageRejected/NIM_API_KEY/VLMError)
status='failed' set ediyor ama `processed_at` NULL bırakıyordu. Sonuç:
  - admin queue 24s başarısız sayacı zaman bazında ölçülemez
  - kullanıcı 19+ NIM 403 fail'i yaşadı, 'Görsel VLM 24s başarısız: 0' gördü

Bu migration mevcut NULL processed_at'leri NOW() ile doldurur (yaklaşık;
NIM 403 son saatlerde başladığı için gerçeğe yakın). Task tarafı PR'da
fail path'lerine `img.processed_at = NOW()` ekleniyor — gelecekte yeni
fail'ler doğrudan zamanlı işaretlenir.

Revision ID: 20260508_2330
Revises: 20260508_2300
Create Date: 2026-05-08 23:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260508_2330"
down_revision = "20260508_2300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill: failed images için processed_at NULL ise NOW() set et.
    # NIM 403 son saatte başladığı için NOW() gerçeğe yakın bir tahmin;
    # admin queue 24h sayacı bunlar son 24h içinde sayar.
    op.execute(
        sa.text(
            """
            UPDATE article_images
            SET processed_at = NOW()
            WHERE status = 'failed'
              AND processed_at IS NULL
            """
        )
    )


def downgrade() -> None:
    # Geri alma: processed_at'i NULL'a çek (sadece bu migration'ın
    # backfill'i; gerçek fail timestamp'i 1 saat içindeyse). Konservatif:
    # son 1 saatte set edilenler bu migration olmuş varsayılır.
    op.execute(
        sa.text(
            """
            UPDATE article_images
            SET processed_at = NULL
            WHERE status = 'failed'
              AND processed_at >= NOW() - INTERVAL '1 hour'
            """
        )
    )
