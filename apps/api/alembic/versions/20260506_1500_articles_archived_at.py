"""Articles cold tier — archived_at + cold_storage_key (#219 MVP-1.5 PR-4)

Article cold tier retention task için DB schema:
    - articles.archived_at TIMESTAMPTZ NULL — soğuk depoya taşındı mı
    - articles.cold_storage_key TEXT NULL — Contabo OS bucket key
    - idx_articles_archive_candidate (created_at) WHERE archived_at IS NULL

Akış: 30+ gün eski raw_html → MinIO'dan oku → Contabo OS'a yaz (gz)
      → DB'de archived_at + cold_storage_key set → MinIO'dan sil.

Idempotent: archived_at NOT NULL olanlar zaten taşınmış, atlanır.

Revision ID: 20260506_1500
Revises: 20260505_1500
Create Date: 2026-05-06 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260506_1500"
down_revision = "20260505_1500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("cold_storage_key", sa.Text(), nullable=True),
    )
    # Cold tier candidate index: archived_at NULL + created_at sort
    op.create_index(
        "idx_articles_archive_candidate",
        "articles",
        ["created_at"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_articles_archive_candidate", table_name="articles"
    )
    op.drop_column("articles", "cold_storage_key")
    op.drop_column("articles", "archived_at")
