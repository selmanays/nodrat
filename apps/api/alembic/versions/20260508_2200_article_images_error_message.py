"""article_images.error_message kolonu — fail nedenini DB'de sakla (#477)

Eskiden process_article_image_vlm task'ı article_images.status='failed' set
ediyordu ama hata mesajını sadece task return value'sunda (Celery result
backend) tutuyordu. UI tarafından erişilemez.

Sonuç: Media sayfasında "Başarısız" badge yanında "VLM çıktısı yok" jenerik
mesaj — gerçek nedenin ne olduğu (NIM 403, image rejected, timeout) gizli.
2026-05-08 NIM API key 403 olayında bu durumun maliyeti netleşti.

Bu migration `error_message TEXT NULL` kolonu ekler. Task güncellemesi PR'da.

Revision ID: 20260508_2200
Revises: 20260508_2100
Create Date: 2026-05-08 22:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260508_2200"
down_revision = "20260508_2100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "article_images",
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("article_images", "error_message")
