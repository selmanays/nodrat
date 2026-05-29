"""User + Session SQLAlchemy modelleri.

docs/engineering/data-model.md §2.1, §2.2
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class User(Base):
    """Kullanıcı modeli — KVKK uyumlu (4 onay timestamp'i, soft delete).

    docs/engineering/data-model.md §2.1
    docs/legal/opinion-integration.md §3.5 (4 checkbox)
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120))

    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'user'"),
    )  # 'super_admin' | 'user'

    tier: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'free'"),
    )  # 'free' | 'starter' | 'pro' | 'agency_seat'

    locale: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'tr-TR'"),
    )

    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )

    # ---- KVKK consent timestamps (4 ayrı checkbox — Legal §3.5) ----
    kvkk_acknowledgment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """KVKK Aydınlatma Metni okundu onayı."""

    data_processing_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Kişisel veri işleme onayı."""

    foreign_transfer_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Yurt dışı LLM provider'a veri aktarımı onayı (KVKK md.9)."""

    foreign_transfer_consent_version: Mapped[str | None] = mapped_column(String(16))
    """Aydınlatma metin sürümü ('v0.2'). #470 — TIA kayıt."""

    foreign_transfer_consent_ip: Mapped[Any | None] = mapped_column(INET)
    """Açık rıza alındığı IP. #470 — TIA kayıt v (KVKK m.9 audit)."""

    foreign_transfer_consent_text_hash: Mapped[str | None] = mapped_column(String(64))
    """Aydınlatma metni SHA-256 hash (immutable kanıt). #470."""

    foreign_transfer_consent_revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    """KVKK m.11 — geri çekme tarihi. NOT NULL ise gate 403 döner. #470."""

    # ---- KVKK 5. checkbox: model improvement (Trendyol fine-tune) — #564 ----
    model_improvement_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Üretim verisinin model eğitiminde kullanımı için açık rıza zamanı.
    Eksik ise generations.sft_eligible=false (#563)."""

    model_improvement_consent_version: Mapped[str | None] = mapped_column(String(16))
    """Aydınlatma metin sürümü (örn. 'v0.3'). #564 — TIA kayıt."""

    model_improvement_consent_ip: Mapped[Any | None] = mapped_column(INET)
    """Açık rıza alındığı IP. #564 — KVKK audit."""

    model_improvement_consent_text_hash: Mapped[str | None] = mapped_column(String(64))
    """Aydınlatma metni SHA-256 hash (immutable kanıt). #564."""

    model_improvement_consent_revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    """KVKK m.11 — geri çekme tarihi. NOT NULL ise sft_eligible=false +
    training_samples cascade silme (#567 task). #564."""

    marketing_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Pazarlama iletisi onayı (opsiyonel)."""

    # ---- 2FA (Faz 6+) — #56 admin TOTP zorunlu ----
    totp_secret: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
    )
    totp_backup_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    # ---- Tracking ----
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[Any | None] = mapped_column(INET)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Soft delete — KVKK silme talebinde set edilir, 30 gün sonra hard delete."""

    # ---- Relationships ----
    sessions: Mapped[list[Session]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "idx_users_role",
            "role",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_users_tier",
            "tier",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_users_email_verified",
            "email_verified",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Session(Base):
    """Oturum kayıtları — refresh token rotation için.

    docs/engineering/data-model.md §2.2
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
    """Refresh token'ın SHA-256 hash'i (raw token saklamayız)."""

    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[Any | None] = mapped_column(INET)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="sessions")

    __table_args__ = (
        Index(
            "idx_sessions_user_id",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "idx_sessions_expires_at",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )
