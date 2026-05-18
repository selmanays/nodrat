"""users.model_improvement_consent_* — KVKK 5. checkbox (#564)

KVKK md.5 "açık ve özgül amaç" prensibi gereği mevcut data_processing
ve foreign_transfer onaylarından AYRI bir 5. consent: kullanıcı verisinin
Nodrat'ın kendi yapay zeka modelinin (Trendyol-LLM-7B-chat-v4.1.0
üzerine domain-spesifik fine-tune) eğitiminde kullanımı için.

Mevcut foreign_transfer_consent_* patterni birebir takip edilir:
  - model_improvement_consent_at          → onay zamanı
  - model_improvement_consent_version     → aydınlatma metin sürümü ('v0.3')
  - model_improvement_consent_ip          → açık rıza IP'si (KVKK audit)
  - model_improvement_consent_text_hash   → SHA-256 (immutable kanıt)
  - model_improvement_consent_revoked_at  → KVKK m.11 geri çekme

Mevcut user'lar için opt-in: tüm kolonlar nullable, default null.
Eksik consent → sft_eligible=false (#563 _recompute_sft_eligibility).

Avukat ön-görüşü: 2026-05-10 (issue #564 yorumu) — onay verildi.

Refs: #564
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET

revision = "20260510_0300"
down_revision = "20260510_0200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "model_improvement_consent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "model_improvement_consent_version",
            sa.String(16),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "model_improvement_consent_ip",
            INET,
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "model_improvement_consent_text_hash",
            sa.String(64),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "model_improvement_consent_revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "model_improvement_consent_revoked_at")
    op.drop_column("users", "model_improvement_consent_text_hash")
    op.drop_column("users", "model_improvement_consent_ip")
    op.drop_column("users", "model_improvement_consent_version")
    op.drop_column("users", "model_improvement_consent_at")
