"""Faz 5.2b — artifacts.origin kolonu (additive, zero-downtime)

#1785 Otomasyon Stüdyosu: artefaktın kaynağını ayırt et — 'interactive' (kullanıcı
sorgusu) vs 'automation' (oto-koşum). Feed/UI'da ayrım için. Mevcut tüm artefaktlar
server_default 'interactive' ile geriye-dönük backfill (NOT NULL güvenli).

Additive + default + CHECK → backward-compatible, zero-downtime.

Revision ID: 20260627_0100
Revises: 20260626_0100
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260627_0100"
down_revision: str | None = "20260626_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column(
            "origin",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'interactive'"),
        ),
    )
    # Zero-downtime CHECK: NOT VALID (yalnız catalog, tablo taraması/uzun ACCESS
    # EXCLUSIVE yok) + ayrı VALIDATE (SHARE UPDATE EXCLUSIVE — okuma/yazma serbest).
    # Tüm mevcut satırlar default 'interactive' → VALIDATE anında geçer.
    op.execute(
        "ALTER TABLE artifacts ADD CONSTRAINT ck_artifacts_origin "
        "CHECK (origin IN ('interactive','automation')) NOT VALID"
    )
    op.execute("ALTER TABLE artifacts VALIDATE CONSTRAINT ck_artifacts_origin")


def downgrade() -> None:
    op.drop_constraint("ck_artifacts_origin", "artifacts", type_="check")
    op.drop_column("artifacts", "origin")
