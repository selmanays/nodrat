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


# =============================================================================
# 2FA — TOTP + Backup Codes (#56)
# =============================================================================
# pyotp implementation — RFC 6238 TOTP (30s window, 6 digits)
# Backup codes: 10 random "XXXX-XXXX" format, SHA-256 hash'li DB'de.

import pyotp  # noqa: E402

TOTP_ISSUER = "Nodrat"
TOTP_DIGITS = 6
TOTP_INTERVAL = 30  # saniye
TOTP_WINDOW = 1  # ±1 step (30s) clock skew toleransı
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8  # 'XXXXXXXX' — 4-4 separator ile gösterilir


def generate_totp_secret() -> str:
    """Yeni Base32-encoded TOTP secret üret (160 bit)."""
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, account_email: str) -> str:
    """otpauth:// URI üret. Frontend bunu QR koda çevirir.

    Format:
        otpauth://totp/Nodrat:user@example.com?secret=BASE32SECRET&issuer=Nodrat
    """
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
    return totp.provisioning_uri(name=account_email, issuer_name=TOTP_ISSUER)


def verify_totp_code(secret: str, code: str) -> bool:
    """Kullanıcı tarafından girilen 6 haneli TOTP kodunu doğrula.

    ±1 window (30s) toleransı clock skew için. Her kod sadece bir kez
    geçerli (replay koruması için DB-side timestamp tracking opsiyonel).
    """
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "").replace("-", "")
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
    return totp.verify(code, valid_window=TOTP_WINDOW)


def generate_backup_codes() -> list[str]:
    """10 adet random 8-karakterli alphanumeric backup kod üret.

    Returns plaintext list — SADECE setup'ta gösterilir, sonra hash'lenip
    DB'ye yazılır.
    """
    # Kolay typing için 0/O, 1/I/L gibi karakterleri hariç tut
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    codes = []
    for _ in range(BACKUP_CODE_COUNT):
        raw = "".join(secrets.choice(alphabet) for _ in range(BACKUP_CODE_LENGTH))
        # 'ABCD-EFGH' format (kullanıcıya gösterimde kolaylık)
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_backup_code(code: str) -> str:
    """Backup kodu hash'le. SHA-256 yeterli (kod high-entropy random,
    bcrypt/argon2 overkill)."""
    normalized = code.strip().replace("-", "").upper()
    return hashlib.sha256(normalized.encode()).hexdigest()


def verify_backup_code(provided: str, stored_hashes: list[str]) -> str | None:
    """Provided plaintext kodu hashed list ile karşılaştır.

    Returns:
        Match olan stored hash (DB'den çıkarılması için). Yoksa None.
    """
    if not provided:
        return None
    candidate = hash_backup_code(provided)
    return candidate if candidate in stored_hashes else None


def create_totp_challenge_token(user_id: UUID) -> str:
    """Login ve şifre doğrulandı, TOTP challenge bekleniyor — kısa ömürlü
    (5 dk) JWT. Verify-challenge endpoint'i bu token + TOTP code alıp gerçek
    access/refresh token'a dönüştürür.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "type": "totp_challenge",
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
