"""failed_jobs.severity + duplicate_content auto-resolve backfill (#445, Epic #443)

failed_jobs şu anda her şeyi tek torbada tutuyor — gerçek hata, RSS re-emit info,
warning hepsi aynı seviyede. Bu durum:
  - 74 article.duplicate_content kaydı alarm yorgunluğu yaratıyor (RSS re-emit)
  - Admin retry'inde permanent_info için retry mantıksız
  - Filter UI'sı için kategori yok

Bu migration:
  1. ALTER TABLE failed_jobs ADD COLUMN severity VARCHAR(20) NOT NULL DEFAULT 'error'
  2. CHECK constraint: severity IN ('error', 'warning', 'permanent_info')
  3. Index: idx_failed_jobs_severity_unresolved (severity, created_at DESC) WHERE resolved_at IS NULL
  4. Backfill: UPDATE article.duplicate_content satırlarını severity='permanent_info'
     ve resolved_at=now() (auto-resolve, alarm sayımından çıkarmak için)

Postgres 11+'de ADD COLUMN with DEFAULT instant — zero-downtime.
Backfill UPDATE chunks halinde (ihtiyatlı), tek transaction'da.

Revision ID: 20260508_1900
Revises: 20260507_1500
Create Date: 2026-05-08 19:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260508_1900"
down_revision = "20260507_1500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) severity kolonu — NOT NULL DEFAULT 'error' (Postgres 11+ instant)
    op.add_column(
        "failed_jobs",
        sa.Column(
            "severity",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'error'"),
        ),
    )

    # 2) Check constraint
    op.create_check_constraint(
        "ck_failed_jobs_severity",
        "failed_jobs",
        "severity IN ('error', 'warning', 'permanent_info')",
    )

    # 3) Index — admin sayfasının default sorgusu için
    op.create_index(
        "idx_failed_jobs_severity_unresolved",
        "failed_jobs",
        [sa.text("severity"), sa.text("created_at DESC")],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )

    # 4) Backfill — duplicate_content kayıtları RSS re-emit info, alarm değil.
    #    Auto-resolve + severity'yi permanent_info'ya çek.
    op.execute(
        sa.text(
            """
            UPDATE failed_jobs
            SET severity = 'permanent_info',
                resolved_at = NOW(),
                resolution_note = COALESCE(
                    resolution_note,
                    'auto-resolved RSS re-emit (#445 backfill)'
                )
            WHERE job_type = 'article.duplicate_content'
              AND resolved_at IS NULL
            """
        )
    )


def downgrade() -> None:
    # Backfill'i geri alma yok (idempotent değil, severity drop yeter)
    op.drop_index(
        "idx_failed_jobs_severity_unresolved", table_name="failed_jobs"
    )
    op.drop_constraint("ck_failed_jobs_severity", "failed_jobs", type_="check")
    op.drop_column("failed_jobs", "severity")
