"""Email service layer — token üretimi + send + email_log audit (#68).

Token security model:
    - Raw token = secrets.token_urlsafe(32) → kullanıcıya email ile gönderilir
    - DB'de SADECE SHA-256 hash saklanır (token_hash)
    - Doğrulama: input token'ı hash'le, DB'de eşleştir
    - Compromised DB → token'lar leak olmaz (sadece hash görünür)
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.email.templates import build_email_verify, build_password_reset
from app.models.email import EmailLog, EmailVerificationToken, PasswordResetToken
from app.modules.accounts.models import User
from app.providers.email import get_email_provider

logger = logging.getLogger(__name__)


# =============================================================================
# Token helpers
# =============================================================================


def _generate_token() -> tuple[str, str]:
    """Yeni token üret. Returns: (raw_token, sha256_hash)."""
    raw = secrets.token_urlsafe(32)
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, h


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# =============================================================================
# Email verification flow
# =============================================================================


async def create_email_verify_token(
    db: AsyncSession,
    user: User,
    ttl_hours: int | None = None,
) -> str:
    """Yeni email verify token oluştur ve DB'ye yaz. Raw token return eder.

    Aynı user için açık (used_at IS NULL) token'lar invalidate edilmez —
    multiple tokens valid olabilir. Sadece son üretilen kullanılır pratikte.
    """
    settings = get_settings()
    ttl = ttl_hours or settings.email_verify_token_ttl_hours
    raw, hashed = _generate_token()

    token = EmailVerificationToken(
        user_id=user.id,
        token_hash=hashed,
        email=user.email,
        expires_at=datetime.now(UTC) + timedelta(hours=ttl),
    )
    db.add(token)
    await db.flush()
    return raw


async def consume_email_verify_token(db: AsyncSession, raw_token: str) -> User | None:
    """Token'ı doğrula + tek kullanım (used_at set). Returns user or None."""
    hashed = _hash_token(raw_token)
    now = datetime.now(UTC)

    stmt = (
        select(EmailVerificationToken, User)
        .join(User, User.id == EmailVerificationToken.user_id)
        .where(
            EmailVerificationToken.token_hash == hashed,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > now,
            User.deleted_at.is_(None),
        )
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None

    token, user = row
    token.used_at = now
    user.email_verified = True
    await db.flush()
    return user


# =============================================================================
# Password reset flow
# =============================================================================


async def create_password_reset_token(
    db: AsyncSession,
    user: User,
    request_ip: str | None = None,
    ttl_hours: int | None = None,
) -> str:
    """Yeni password reset token oluştur."""
    settings = get_settings()
    ttl = ttl_hours or settings.password_reset_token_ttl_hours
    raw, hashed = _generate_token()

    token = PasswordResetToken(
        user_id=user.id,
        token_hash=hashed,
        request_ip=request_ip,
        expires_at=datetime.now(UTC) + timedelta(hours=ttl),
    )
    db.add(token)
    await db.flush()
    return raw


async def consume_password_reset_token(db: AsyncSession, raw_token: str) -> User | None:
    """Token'ı doğrula + tek kullanım. Returns user or None."""
    hashed = _hash_token(raw_token)
    now = datetime.now(UTC)

    stmt = (
        select(PasswordResetToken, User)
        .join(User, User.id == PasswordResetToken.user_id)
        .where(
            PasswordResetToken.token_hash == hashed,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
            User.deleted_at.is_(None),
        )
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None

    token, user = row
    token.used_at = now
    await db.flush()
    return user


# =============================================================================
# Send + log helpers
# =============================================================================


async def _log_and_send(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    recipient: str,
    sender: str,
    template: str,
    subject: str,
    html: str,
    text: str,
    reply_to: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> EmailLog:
    """email_log entry oluştur + provider çağır + status güncelle.

    Caller commit eder (commit yapılmaz burada — atomicity için).
    """
    log_entry = EmailLog(
        user_id=user_id,
        recipient=recipient,
        sender=sender,
        template=template,
        subject=subject,
        status="queued",
        metadata_json=metadata or {},
    )
    db.add(log_entry)
    await db.flush()  # log_entry.id'yi al

    provider = get_email_provider()
    log_entry.provider = provider.name

    try:
        result = await provider.send(
            to=recipient,
            sender=sender,
            subject=subject,
            html=html,
            text=text,
            reply_to=reply_to,
        )

        if result.success:
            log_entry.status = "sent"
            log_entry.provider_message_id = result.message_id
            log_entry.sent_at = datetime.now(UTC)
        else:
            log_entry.status = "failed"
            log_entry.error = result.error or "unknown error"
            logger.warning(
                "email.send.failed",
                extra={
                    "template": template,
                    "to": recipient[:50] + "...",
                    "error": (result.error or "")[:200],
                },
            )
    except Exception as exc:
        log_entry.status = "failed"
        log_entry.error = str(exc)[:500]
        logger.exception(
            "email.send.exception", extra={"template": template, "to_len": len(recipient)}
        )

    await db.flush()
    return log_entry


async def send_email_verify(
    db: AsyncSession,
    user: User,
    verify_url: str,
) -> EmailLog:
    """Email doğrulama maili gönder + email_log."""
    settings = get_settings()
    content = build_email_verify(
        verify_url=verify_url,
        ttl_hours=settings.email_verify_token_ttl_hours,
    )
    return await _log_and_send(
        db,
        user_id=user.id,
        recipient=user.email,
        sender=settings.resend_from_transactional,
        template="verify",
        subject=content.subject,
        html=content.html,
        text=content.text,
        reply_to=settings.resend_reply_to,
    )


async def send_password_reset(
    db: AsyncSession,
    user: User,
    reset_url: str,
    request_ip: str | None = None,
) -> EmailLog:
    """Şifre sıfırlama maili gönder + email_log."""
    settings = get_settings()
    content = build_password_reset(
        reset_url=reset_url,
        ttl_hours=settings.password_reset_token_ttl_hours,
        request_ip=request_ip,
    )
    return await _log_and_send(
        db,
        user_id=user.id,
        recipient=user.email,
        sender=settings.resend_from_transactional,
        template="password_reset",
        subject=content.subject,
        html=content.html,
        text=content.text,
        reply_to=settings.resend_reply_to,
        metadata={"request_ip": request_ip} if request_ip else {},
    )
