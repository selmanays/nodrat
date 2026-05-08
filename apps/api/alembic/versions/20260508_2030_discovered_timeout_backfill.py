"""discovered_timeout legacy 88 satır auto-resolve backfill (#463, Epic #443 follow-up)

`failed_jobs` tablosunda 88 satır `article.discovered_timeout` kaydı var. Tek
anda (spread=0, age 2.3h) yazılmış, manuel admin cleanup script kalıntısı.
Kod tabanında yazıcısı yok ve discovered article orphan'ı zaten 0 (sistem
düzgün çalışıyor; backfill_discovered + retry_failed kombinasyonu yetiyor).

Bu kayıtlar info-level — gerçek hata değil. severity='permanent_info' +
auto-resolve ile alarm sayımından çıkarılır.

Beklenen etki:
  failed_jobs unresolved 305 -> ~217 (-88, %29)

Revision ID: 20260508_2030
Revises: 20260508_1900
Create Date: 2026-05-08 20:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260508_2030"
down_revision = "20260508_1900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE failed_jobs
            SET severity = 'permanent_info',
                resolved_at = NOW(),
                resolution_note = COALESCE(
                    resolution_note,
                    'auto-resolved discovered_timeout legacy (#463 backfill)'
                )
            WHERE job_type = 'article.discovered_timeout'
              AND resolved_at IS NULL
            """
        )
    )


def downgrade() -> None:
    # Backfill geri alma: severity'yi 'error' geri çek, resolved_at NULL'a çek.
    # resolution_note'u dokunmuyoruz (idempotent değil).
    op.execute(
        sa.text(
            """
            UPDATE failed_jobs
            SET severity = 'error',
                resolved_at = NULL
            WHERE job_type = 'article.discovered_timeout'
              AND severity = 'permanent_info'
              AND resolution_note LIKE 'auto-resolved discovered_timeout legacy%'
            """
        )
    )
