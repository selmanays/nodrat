"""Foreign transfer consent — TIA metadata sütunları (#470, KVKK m.9)

Avukat şartlı onayının (Epic #448 §3.9 N-09 RESOLVED) zorunlu kıldığı 5 maddelik
Transfer Impact Assessment kayıt sistemi için 4 yeni sütun ekler.

Mevcut: users.foreign_transfer_consent_at (DateTime, nullable)
Yeni:
  - foreign_transfer_consent_version VARCHAR(16) — aydınlatma metin sürümü ('v0.2')
  - foreign_transfer_consent_ip INET — açık rıza IP'si (TIA kayıt v)
  - foreign_transfer_consent_text_hash VARCHAR(64) — metin SHA-256 hash (immutable kanıt)
  - foreign_transfer_consent_revoked_at TIMESTAMPTZ — KVKK m.11 geri çekme

Mevcut user'lar bu yeni sütunlarda NULL kalır — gate sadece _at NOT NULL +
_revoked_at NULL koşulunu kontrol eder. Backfill akışı yok (mevcut consent'ler
v0.1 sayılır; yeni POST /app/consent/foreign-transfer çağrısı v0.2'ye yükseltir).

Revision ID: 20260509_0200
Revises: 20260509_0100
Create Date: 2026-05-09 02:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET


revision = "20260509_0200"
down_revision = "20260509_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("foreign_transfer_consent_version", sa.String(16), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("foreign_transfer_consent_ip", INET, nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("foreign_transfer_consent_text_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "foreign_transfer_consent_revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "foreign_transfer_consent_revoked_at")
    op.drop_column("users", "foreign_transfer_consent_text_hash")
    op.drop_column("users", "foreign_transfer_consent_ip")
    op.drop_column("users", "foreign_transfer_consent_version")
