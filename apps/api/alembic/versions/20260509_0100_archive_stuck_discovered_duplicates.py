"""14 stuck discovered article'ı archive et — duplicate_content loop temizliği (#488)

Production tanı (2026-05-09 00:30 UTC):
  articles.status='discovered' = 14
  Hepsinin updated_at = 2.8h önce (aynı dakikada).
  Worker log: hepsi fetch_detail succeeded {status: duplicate_content}.
  DLQ son 1 saat: 180 yeni article.duplicate_content permanent_info kaydı.

Sorun: _record_failure helper severity='permanent_info' iken article.status'u
değiştirmiyordu. Article discovered'da kalıyor → backfill_discovered task her
5 dk yeniden dispatch → fetch_detail tekrar duplicate_content → sonsuz loop.

Fix (kod tarafı PR ile birlikte):
  - state machine: DISCOVERED → ARCHIVED kabul edildi
  - _record_failure: article_status_override parametresi eklendi
  - duplicate_content path: STATUS_ARCHIVED (terminal, retry yok)

Bu migration mevcut 14 stuck article'ı kasıtlı archive eder. DLQ'da match
eden duplicate_content kayıtları zaten resolved (severity='permanent_info'
auto-resolve), tekrar yazılmıyor.

Match yöntemi: article.status='discovered' AND article.source_url IN (DLQ
permanent_info duplicate_content kayıtlarındaki source_url'ler, son 24h).

Beklenen etki: discovered 14 → 0 (loop kırıldı, DLQ permanent_info üretimi
saatte 180 → ~0).

Revision ID: 20260509_0100
Revises: 20260509_0000
Create Date: 2026-05-09 01:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260509_0100"
down_revision = "20260509_0000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET status = 'archived',
                updated_at = NOW()
            WHERE status = 'discovered'
              AND source_url IN (
                  SELECT DISTINCT (payload_json->>'source_url')
                  FROM failed_jobs
                  WHERE job_type = 'article.duplicate_content'
                    AND severity = 'permanent_info'
                    AND created_at >= NOW() - INTERVAL '24 hours'
              )
            """
        )
    )


def downgrade() -> None:
    # Geri alma sadece bu migration'ın etkilediği aralıkta:
    # son 1 saat içinde archive edilen + raw_html boş + cold_storage_key
    # boş olanlar bu migration'ın yaptığı işaretler (cold tier farklı).
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET status = 'discovered'
            WHERE status = 'archived'
              AND archived_at IS NULL
              AND cold_storage_key IS NULL
              AND updated_at >= NOW() - INTERVAL '1 hour'
            """
        )
    )
