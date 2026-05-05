"""Image pipeline VLM refactor (#300 MVP-1.4 PR-1)

article_images schema:
    - DROP: storage_url, mime_type, width, height, file_size, sha256_hash,
            perceptual_hash, uniq_article_images_hash index
    - ADD: vlm_caption, ocr_text, depicts (JSONB), processed_at, position
    - CHECK: status values güncel ('pending', 'processed', 'failed', 'skipped')

Bytes saklamıyoruz — process & discard pattern. Mevcut 'downloaded' row'lar
'pending' yapılır (PR-3 NIM VLM ile retroactive enrichment yapacak).

Revision ID: 20260505_1500
Revises: 20260503_1400
Create Date: 2026-05-05 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "20260505_1500"
down_revision = "20260503_1400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Eski check constraint'i drop (yeni status değerleri için yeniden oluşturulacak)
    op.drop_constraint("ck_article_images_status", "article_images", type_="check")

    # 2) Eski unique index'i drop (sha256_hash kolonuna bağımlı)
    op.drop_index("uniq_article_images_hash", table_name="article_images")

    # 3) Eski downloaded/duplicate row'larını 'pending' yap (VLM retroactive enrichment için)
    op.execute(
        "UPDATE article_images SET status = 'pending' "
        "WHERE status IN ('downloaded', 'duplicate')"
    )

    # 4) Storage-related kolonları drop
    op.drop_column("article_images", "storage_url")
    op.drop_column("article_images", "mime_type")
    op.drop_column("article_images", "width")
    op.drop_column("article_images", "height")
    op.drop_column("article_images", "file_size")
    op.drop_column("article_images", "sha256_hash")
    op.drop_column("article_images", "perceptual_hash")

    # 5) VLM pipeline kolonlarını ekle
    op.add_column(
        "article_images",
        sa.Column("vlm_caption", sa.Text(), nullable=True),
    )
    op.add_column(
        "article_images",
        sa.Column("ocr_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "article_images",
        sa.Column("depicts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "article_images",
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "article_images",
        sa.Column("position", sa.Integer(), nullable=True),
    )

    # 6) Yeni check constraint (güncel status değerleri)
    op.create_check_constraint(
        "ck_article_images_status",
        "article_images",
        "status IN ('pending', 'processed', 'failed', 'skipped')",
    )

    # 7) processed_at için index (admin/media filter ve queue ordering için)
    op.create_index(
        "idx_article_images_processed_at",
        "article_images",
        ["processed_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_article_images_processed_at", table_name="article_images")
    op.drop_constraint("ck_article_images_status", "article_images", type_="check")

    op.drop_column("article_images", "position")
    op.drop_column("article_images", "processed_at")
    op.drop_column("article_images", "depicts")
    op.drop_column("article_images", "ocr_text")
    op.drop_column("article_images", "vlm_caption")

    op.add_column(
        "article_images",
        sa.Column("perceptual_hash", sa.CHAR(64), nullable=True),
    )
    op.add_column(
        "article_images",
        sa.Column("sha256_hash", sa.CHAR(64), nullable=True),
    )
    op.add_column(
        "article_images",
        sa.Column("file_size", sa.Integer(), nullable=True),
    )
    op.add_column(
        "article_images",
        sa.Column("height", sa.Integer(), nullable=True),
    )
    op.add_column(
        "article_images",
        sa.Column("width", sa.Integer(), nullable=True),
    )
    op.add_column(
        "article_images",
        sa.Column("mime_type", sa.String(64), nullable=True),
    )
    op.add_column(
        "article_images",
        sa.Column("storage_url", sa.Text(), nullable=True),
    )

    op.create_index(
        "uniq_article_images_hash",
        "article_images",
        ["sha256_hash"],
        unique=True,
        postgresql_where=sa.text("sha256_hash IS NOT NULL AND status = 'downloaded'"),
    )

    op.create_check_constraint(
        "ck_article_images_status",
        "article_images",
        "status IN ('pending', 'downloaded', 'failed', 'duplicate')",
    )
