"""#904 — articles.status taksonomi: archived → quarantine + discarded.

`archived` status DEĞERİ kaldırılır (#483 overload çözüldü). Mevcut ~1182
archived satır failed_jobs.job_type'a göre göç eder:
  - thin_content        → quarantine (extraction-miss, GÖRÜNÜR + retryable)
  - soft_404/duplicate/  → discarded  (gerçek kalıcı, terminal)
    invalid_url
  - kalan (bilinmeyen)   → quarantine (güvenli; recover_quarantined dener)

NOT: cold-tier `archived_at`/`cold_storage_key` AYRI alanlar; status='cleaned'
kalır, BU MIGRATION onlara DOKUNMAZ.

Idempotent: tüm UPDATE'ler `WHERE status='archived'`; rerun no-op.

Revision: 20260516_0100
Revises: 20260514_1900
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260516_0100"
down_revision: str | None = "20260514_1900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Eski CHECK'i kaldır (yeni değerlere izin vermek için).
    op.drop_constraint("ck_articles_status", "articles", type_="check")

    # 2) Veri göçü — sıra ÖNEMLİ (first-match-wins; thin_content öncelikli =
    #    en güvenli, retryable). Her UPDATE WHERE status='archived' (idempotent).
    op.execute(
        """
        UPDATE articles SET status='quarantine', updated_at=now()
        WHERE status='archived' AND id IN (
            SELECT a.id FROM articles a
            JOIN failed_jobs f ON f.article_url = a.source_url
            WHERE f.job_type = 'article.thin_content'
        )
        """
    )
    op.execute(
        """
        UPDATE articles SET status='discarded', updated_at=now()
        WHERE status='archived' AND id IN (
            SELECT a.id FROM articles a
            JOIN failed_jobs f ON f.article_url = a.source_url
            WHERE f.job_type IN (
                'article.soft_404',
                'article.duplicate_content',
                'article.invalid_url'
            )
        )
        """
    )
    # Eşleşen DLQ'su olmayan kalan archived (örn. eski #478 backfill) →
    # quarantine (güvenli; yeni cascade ile yeniden denenebilir).
    op.execute(
        "UPDATE articles SET status='quarantine', updated_at=now() "
        "WHERE status='archived'"
    )

    # 3) Yeni 6-değer CHECK.
    op.create_check_constraint(
        "ck_articles_status",
        "articles",
        "status IN ('discovered', 'fetched', 'cleaned', 'failed', "
        "'quarantine', 'discarded')",
    )


def downgrade() -> None:
    # quarantine + discarded → archived (lossy ama eski şemaya reversible).
    op.drop_constraint("ck_articles_status", "articles", type_="check")
    op.execute(
        "UPDATE articles SET status='archived' "
        "WHERE status IN ('quarantine', 'discarded')"
    )
    op.create_check_constraint(
        "ck_articles_status",
        "articles",
        "status IN ('discovered', 'fetched', 'cleaned', 'failed', 'archived')",
    )
