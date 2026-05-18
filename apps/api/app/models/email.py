"""Email-related ORM models (#68).

docs/legal/ropa.md §11 — transactional email envanteri
docs/legal/privacy-policy.md §10 — email retention 1 yıl
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EmailVerificationToken(Base):
    """Email doğrulama token'ı (24h TTL)."""

    __tablename__ = "email_verification_tokens"

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
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    """SHA-256 hash of the actual token (raw token sent only via email)."""

    email: Mapped[str] = mapped_column(Text, nullable=False)
    """Snapshot — kullanıcı doğrulama sırasında email değiştirebilir."""

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PasswordResetToken(Base):
    """Şifre sıfırlama token'ı (1h TTL)."""

    __tablename__ = "password_reset_tokens"

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
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    request_ip: Mapped[Any | None] = mapped_column(INET)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EmailLog(Base):
    """Transactional email gönderim kaydı (audit + retention 1 yıl).

    Status flow:
        queued → sent (success)
                → failed (provider hata)
                → bounced (webhook)
                → complained (webhook)
    """

    __tablename__ = "email_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    """Soft-delete user için NULL (audit trail kalır)."""

    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    """'verify' | 'password_reset' | 'welcome' | 'quota_warning' | ..."""

    subject: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'queued'"))
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'resend'")
    )
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    """Resend message ID — webhook tracking için."""

    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'bounced', 'complained')",
            name="ck_email_log_status",
        ),
        Index(
            "idx_email_log_user_created",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "idx_email_log_status_created",
            "status",
            text("created_at DESC"),
        ),
        Index(
            "idx_email_log_template_created",
            "template",
            text("created_at DESC"),
        ),
    )
