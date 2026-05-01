"""Auth security helpers — Argon2id password hashing + JWT token management.

docs/engineering/threat-model.md §A02 (cryptographic), §A07 (auth)
docs/engineering/api-contracts.md §1.5 (auth flow)
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import get_settings


# Argon2id parameters (OWASP 2024 recommended)
# memory_cost: 19MiB, time_cost: 2 iterations, parallelism: 1
# Bu değerler hem güvenli hem yeterince hızlı (production p95 < 50ms)
_password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,  # 19 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


# =============================================================================
# Password hashing
# =============================================================================


def hash_password(plain: str) -> str:
    """Argon2id ile şifre hash'le.

    Çıktı self-contained — algoritma + params + salt + hash hepsi bir string'de.
    Verify edilirken hasher params değişebilir, eski hash'ler de doğrular.
    """
    return _password_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Şifreyi hash'e karşı doğrula.

    Returns True if match, False if mismatch (timing attack koruması).
    """
    try:
        _password_hasher.verify(hashed, plain)
        return True
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    """Hash params güncellenmeli mi? (Cost factor değiştiyse)."""
    return _password_hasher.check_needs_rehash(hashed)


# =============================================================================
# JWT tokens
# =============================================================================


def create_access_token(
    user_id: UUID,
    role: str,
    tier: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Short-lived access token (default 15 dk).

    Claims:
        sub: user_id (str)
        role: 'super_admin' | 'user'
        tier: 'free' | 'starter' | 'pro' | 'agency_seat'
        exp: expiration timestamp
        iat: issued at
        type: 'access'
    """
    settings = get_settings()
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_expire_minutes)

    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "tier": tier,
        "iat": now,
        "exp": now + expires_delta,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def create_refresh_token(user_id: UUID) -> tuple[str, str]:
    """Long-lived refresh token + DB hash.

    Returns:
        (raw_token, sha256_hash) — raw kullanıcıya, hash DB'ye.
    """
    settings = get_settings()

    # Cryptographically random refresh token (256 bit)
    raw = secrets.token_urlsafe(48)  # ~64 char

    # JWT-wrap the random token (so we can verify expiration server-side)
    payload: dict[str, Any] = {
        "jti": raw,
        "sub": str(user_id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(days=settings.jwt_refresh_expire_days),
        "type": "refresh",
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")

    # DB'ye hash'i kaydedeceğiz (raw saklamayız)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    return token, token_hash


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """JWT decode + validate.

    Raises:
        jwt.ExpiredSignatureError: token expired
        jwt.InvalidTokenError: invalid signature / malformed

    Returns:
        Decoded claims dict.
    """
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"Beklenen token type '{expected_type}', alınan '{payload.get('type')}'"
        )
    return payload


def hash_refresh_token(token: str) -> str:
    """Refresh token'ın SHA-256 hash'i — DB karşılaştırması için."""
    return hashlib.sha256(token.encode()).hexdigest()
