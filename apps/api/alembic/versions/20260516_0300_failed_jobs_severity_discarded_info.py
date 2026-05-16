"""#904 — failed_jobs.severity +'discarded_info'.

#904 severity modeli:
  - error          : gerçek hata (alarm)
  - warning        : extraction-miss DAHİL — GÖRÜNÜR, auto-resolve YOK
  - permanent_info : legacy (geriye uyumluluk; yeni yazılmaz)
  - discarded_info : YENİ — yalnız gerçek kalıcı (true soft_404 /
    duplicate_content / invalid_url) → auto-resolve, default DLQ'da gizli

Backfill: mevcut permanent_info + gerçek-kalıcı job_type → discarded_info.
Eski permanent_info satırları geçerli kalır (reversible).

Revision: 20260516_0300
Revises: 20260516_0200
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260516_0300"
down_revision: str | None = "20260516_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CHECK'i genişlet (eski 20260508_1900: error/warning/permanent_info).
    op.drop_constraint("ck_failed_jobs_severity", "failed_jobs", type_="check")
    op.create_check_constraint(
        "ck_failed_jobs_severity",
        "failed_jobs",
        "severity IN ('error', 'warning', 'permanent_info', 'discarded_info')",
    )
    # Backfill: gerçek-kalıcı job_type'lı permanent_info → discarded_info.
    op.execute(
        """
        UPDATE failed_jobs SET severity='discarded_info'
        WHERE severity='permanent_info'
          AND job_type IN (
            'article.soft_404',
            'article.duplicate_content',
            'article.invalid_url'
          )
        """
    )


def downgrade() -> None:
    # discarded_info → permanent_info (eski 3-değer CHECK'e dön).
    op.execute(
        "UPDATE failed_jobs SET severity='permanent_info' "
        "WHERE severity='discarded_info'"
    )
    op.drop_constraint("ck_failed_jobs_severity", "failed_jobs", type_="check")
    op.create_check_constraint(
        "ck_failed_jobs_severity",
        "failed_jobs",
        "severity IN ('error', 'warning', 'permanent_info')",
    )
