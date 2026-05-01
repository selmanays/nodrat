"""Auth security helpers unit tests — Argon2id + JWT.

docs/engineering/threat-model.md §A02, §A07
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)


@pytest.mark.unit
class TestPasswordHashing:
    """Argon2id password hash test'leri."""

    def test_hash_creates_unique_value(self) -> None:
        """Aynı şifre 2 kez hash'lendiğinde farklı çıktı (random salt)."""
        h1 = hash_password("Test12345!password")
        h2 = hash_password("Test12345!password")
        assert h1 != h2

    def test_hash_starts_with_argon2id(self) -> None:
        """Argon2id algoritma kullanılıyor (bcrypt değil)."""
        h = hash_password("MyP@ssw0rd123!")
        assert h.startswith("$argon2id$")

    def test_verify_correct_password(self) -> None:
        plain = "C0rrect_P@ssw0rd!"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("C0rrect_P@ssw0rd!")
        assert verify_password("Wr0ng_P@ssword", hashed) is False

    def test_verify_empty_password(self) -> None:
        hashed = hash_password("Real_P@ssw0rd!")
        assert verify_password("", hashed) is False

    def test_needs_rehash_fresh_hash(self) -> None:
        """Yeni hash rehash gerektirmemeli."""
        h = hash_password("Test_P@ss123!")
        assert needs_rehash(h) is False


@pytest.mark.unit
class TestJWTAccessToken:
    """JWT access token testleri."""

    def test_create_and_decode_access_token(self) -> None:
        user_id = uuid4()
        token = create_access_token(user_id, role="user", tier="free")

        claims = decode_token(token, expected_type="access")
        assert claims["sub"] == str(user_id)
        assert claims["role"] == "user"
        assert claims["tier"] == "free"
        assert claims["type"] == "access"

    def test_access_token_with_super_admin(self) -> None:
        user_id = uuid4()
        token = create_access_token(user_id, role="super_admin", tier="agency_seat")
        claims = decode_token(token, expected_type="access")
        assert claims["role"] == "super_admin"
        assert claims["tier"] == "agency_seat"

    def test_decode_wrong_type_raises(self) -> None:
        """Refresh token, access olarak decode edilemez."""
        user_id = uuid4()
        access = create_access_token(user_id, "user", "free")
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(access, expected_type="refresh")

    def test_expired_token_raises(self) -> None:
        """Expired token decode'da hata."""
        user_id = uuid4()
        token = create_access_token(
            user_id,
            role="user",
            tier="free",
            expires_delta=timedelta(seconds=-1),  # geçmişte expired
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(token, expected_type="access")

    def test_tampered_token_raises(self) -> None:
        """Signature değiştirilmiş token reddedilir."""
        user_id = uuid4()
        token = create_access_token(user_id, "user", "free")
        # son karakteri değiştir (signature corrupt)
        tampered = token[:-1] + ("X" if token[-1] != "X" else "Y")
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(tampered, expected_type="access")


@pytest.mark.unit
class TestJWTRefreshToken:
    """Refresh token + hash testleri."""

    def test_create_refresh_returns_token_and_hash(self) -> None:
        user_id = uuid4()
        raw, h = create_refresh_token(user_id)
        assert raw != h
        assert len(h) == 64  # SHA-256 hex

    def test_refresh_hash_consistent(self) -> None:
        """Aynı raw için aynı hash."""
        user_id = uuid4()
        raw, h1 = create_refresh_token(user_id)
        h2 = hash_refresh_token(raw)
        assert h1 == h2

    def test_decode_refresh_token(self) -> None:
        user_id = uuid4()
        raw, _ = create_refresh_token(user_id)
        claims = decode_token(raw, expected_type="refresh")
        assert claims["sub"] == str(user_id)
        assert claims["type"] == "refresh"
        assert "jti" in claims  # random component
