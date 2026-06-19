"""Drop raw_html/cold-tier columns — ham-sayfa saklama niyeti kaldırıldı (#1634)

Cold-tier raw_html retention HİÇ devreye girmedi: raw HTML'i MinIO'ya yazan upstream
adım hiç bağlanmamıştı → `raw_html_storage_path` 23915 makalenin HEPSİNDE NULL,
0 arşiv (`cold_storage_key`/`archived_at` de daima NULL). Cold-tier task'ları +
body_html_drop + flag/beat #1634 PR-1 kod sökümünde kaldırıldı; bu migration
artıkalan 3 kolonu + archive-candidate index'i drop eder.

**Veri kaybı YOK** — üç kolon da tüm satırlarda NULL (cold-tier hiç yazmadı).
Backward-incompatible (DROP COLUMN) ama PR-1 deploy'u (ORM mapping kaldırma) bu
migration'dan ÖNCE canlı olacağı için deployed kod kolonları zaten seçmiyor
(deploy.yml: up -d → alembic upgrade sırası → zero-downtime).

Revision ID: 20260619_1300
Revises: 20260618_0100
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260619_1300"
down_revision: str | None = "20260618_0100"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Index önce drop (WHERE archived_at IS NULL — kolona bağımlı)
    op.drop_index("idx_articles_archive_candidate", table_name="articles")
    op.drop_column("articles", "raw_html_storage_path")
    op.drop_column("articles", "cold_storage_key")
    op.drop_column("articles", "archived_at")


def downgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("cold_storage_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("raw_html_storage_path", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_articles_archive_candidate",
        "articles",
        ["created_at"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )
