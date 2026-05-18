"""TOTP backup codes column (#56, R-SEC-01 mitigation)

Admin 2FA için backup recovery kodları. 10 adet random "XXXX-XXXX" format
kod, SHA-256 hash'li olarak users.totp_backup_codes JSON dizisinde saklanır.
Plaintext kodlar SADECE setup anında bir kez kullanıcıya gösterilir.

Kullanım: TOTP cihazı kaybolursa, kullanıcı backup kodlarından birini
girer, bu kod array'den çıkarılır (one-time use).

Mevcut: users.totp_secret (Text), users.totp_enabled (Boolean)
Yeni:    users.totp_backup_codes (JSONB, default '[]')

Revision ID: 20260509_0300
Revises: 20260509_0200
Create Date: 2026-05-09 03:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260509_0300"
down_revision = "20260509_0200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "totp_backup_codes",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "totp_backup_codes")
