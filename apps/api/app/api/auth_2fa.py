"""2FA endpoints — TOTP setup, verify, disable, login challenge (#56).

docs/engineering/threat-model.md §2.6 (R-SEC-01 mitigation)
docs/engineering/api-contracts.md §3.8

Endpoints:
    POST /auth/2fa/setup              — Yeni TOTP secret üret + otpauth URL döner
    POST /auth/2fa/verify-setup       — Setup'ı doğrula (ilk TOTP kod) + enable + backup codes
    POST /auth/2fa/verify-challenge   — Login sonrası TOTP challenge → tam token
    POST /auth/2fa/disable            — 2FA'yı kapat (password + TOTP gerek)
    POST /auth/2fa/regenerate-backup  — Yeni backup codes üret (mevcutları geçersiz kıl)
    GET  /auth/2fa/status             — Mevcut 2FA durumu

Avukat 7 ön-launch maddesinden #56 — paid launch öncesi admin 2FA zorunlu.

Login flow (modified):
    1. POST /auth/login (email + password)
    2. Eğer user.totp_enabled:
       → response: {requires_2fa: true, totp_challenge_token: "<5dk_jwt>"}
    3. Frontend kullanıcıdan TOTP kodu ister
    4. POST /auth/2fa/verify-challenge (challenge_token + code)
       → response: {access_token, refresh_token, ...} (tam session)

Backup codes:
    Setup'ta 10 random 8-karakter alphanumeric kod üretilir, SHA-256 hash'li
    olarak users.totp_backup_codes JSONB array'inde saklanır. Plaintext SADECE
    setup anında bir kez gösterilir.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_backup_codes,
    generate_totp_secret,
    hash_backup_code,
    totp_provisioning_uri,
    verify_backup_code,
    verify_password,
    verify_totp_code,
)
from app.models.session import Session
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Request/Response models
# =============================================================================


class SetupRequest(BaseModel):
    """Yeni 2FA setup başlat — kullanıcı authenticated olmalı."""

    pass


class SetupResponse(BaseModel):
    secret: str = Field(description="Base32 TOTP secret (yedeklenebilir)")
    otpauth_url: str = Field(
        description=(
            "otpauth://totp/... formatında URL. Frontend bunu QR koda çevirir. "
            "Authenticator app (Google Authenticator, 1Password, Authy) tarar."
        )
    )
    issuer: str = "Nodrat"
    digits: int = 6
    interval_seconds: int = 30


class VerifySetupRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8, description="6 haneli TOTP kodu")


class VerifySetupResponse(BaseModel):
    enabled: bool
    backup_codes: list[str] = Field(
        description=(
            "10 adet plaintext backup kodu — SADECE BU CEVAPTA gösterilir. "
            "Kullanıcı bunları güvenli yerde saklamalı; sonradan re-display "
            "edilemez."
        )
    )
    backup_codes_remaining: int = 10
    message: str


class VerifyChallengeRequest(BaseModel):
    challenge_token: str = Field(description="Login sonrası dönen 5-dk geçerli token")
    code: str = Field(min_length=6, max_length=10, description="TOTP kodu veya backup kod")
    backup_code_used: bool = Field(
        default=False,
        description="True ise code field'i 'XXXX-XXXX' format backup kod kabul edilir",
    )


class TokenResponse(BaseModel):
    """Tam session — TokenResponse auth.py ile aynı schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class DisableRequest(BaseModel):
    password: str = Field(description="Mevcut şifre — güvenlik onayı")
    code: str = Field(description="TOTP kodu veya backup kod (extra security)")


class RegenerateBackupResponse(BaseModel):
    backup_codes: list[str]
    message: str


class StatusResponse(BaseModel):
    enabled: bool
    secret_generated: bool = Field(description="totp_secret VAR ama enabled olmamış olabilir")
    backup_codes_remaining: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/status", response_model=StatusResponse)
async def get_2fa_status(
    user: Annotated[User, Depends(get_current_user)],
) -> StatusResponse:
    """Mevcut 2FA durumu. Frontend setup wizard'ı tetiklemek için kullanır."""
    return StatusResponse(
        enabled=user.totp_enabled,
        secret_generated=user.totp_secret is not None,
        backup_codes_remaining=len(user.totp_backup_codes or []),
    )


@router.post("/setup", response_model=SetupResponse, status_code=status.HTTP_200_OK)
async def setup_2fa(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SetupResponse:
    """Yeni TOTP secret üret + otpauth URI döner.

    Idempotent — eğer zaten enabled ise 409 döner (önce disable et).
    Eğer secret üretilmiş ama enable edilmemişse (verify-setup yapılmamış),
    yeni secret üretilir (eskisi geçersiz olur).
    """
    if user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TOTP_ALREADY_ENABLED",
                "message": "2FA zaten aktif. Önce /auth/2fa/disable ile kapatın.",
            },
        )

    # Yeni secret üret (eski yarım secret'ı geçersiz kılar)
    secret = generate_totp_secret()
    user.totp_secret = secret
    # totp_enabled FALSE kalır — verify-setup ile TRUE olur
    await db.commit()

    logger.info("2fa.setup.initiated user_id=%s", user.id)

    return SetupResponse(
        secret=secret,
        otpauth_url=totp_provisioning_uri(secret, user.email),
    )


@router.post("/verify-setup", response_model=VerifySetupResponse)
async def verify_setup_2fa(
    payload: VerifySetupRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VerifySetupResponse:
    """Setup sırasında ilk TOTP kodu ile doğrula → enabled=true + backup codes.

    Bu endpoint başarılı olduğunda:
    - totp_enabled = TRUE
    - 10 backup kod üretilir, hash'leri DB'ye yazılır
    - Plaintext kodlar SADECE bu cevapta gösterilir
    """
    if user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TOTP_ALREADY_ENABLED", "message": "2FA zaten aktif."},
        )
    if user.totp_secret is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "TOTP_SETUP_NOT_INITIATED",
                "message": "Önce /auth/2fa/setup endpoint'ini çağırın.",
            },
        )

    if not verify_totp_code(user.totp_secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "TOTP_CODE_INVALID",
                "message": (
                    "Girilen TOTP kodu yanlış. Authenticator uygulamanızdaki "
                    "kodu yeniden kontrol edin (kod 30 saniyede yenilenir)."
                ),
            },
        )

    # Enable + backup codes üret
    plaintext_codes = generate_backup_codes()
    hashed_codes = [hash_backup_code(c) for c in plaintext_codes]
    user.totp_enabled = True
    user.totp_backup_codes = hashed_codes
    await db.commit()

    logger.info("2fa.enabled user_id=%s", user.id)

    return VerifySetupResponse(
        enabled=True,
        backup_codes=plaintext_codes,
        backup_codes_remaining=len(plaintext_codes),
        message=(
            "2FA başarıyla aktif edildi. Backup kodlarınızı güvenli bir yerde "
            "saklayın — bunlar SADECE bir kez gösterilir. Authenticator "
            "cihazınızı kaybederseniz hesabınıza erişmek için bu kodlardan "
            "birini kullanabilirsiniz."
        ),
    )


@router.post("/verify-challenge", response_model=TokenResponse)
async def verify_challenge_2fa(
    payload: VerifyChallengeRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Login flow 2FA challenge — challenge_token + TOTP/backup code → tam tokens.

    Bu endpoint /auth/login'in 2FA-required durumunda kullanılır:
    1. POST /auth/login → 200 + {requires_2fa: true, totp_challenge_token: "..."}
    2. Frontend TOTP kodu alır
    3. POST /auth/2fa/verify-challenge → tam access + refresh token

    Challenge token 5 dakika geçerli (security.py create_totp_challenge_token).
    """
    # Challenge token'ı decode et
    try:
        claims = decode_token(payload.challenge_token, expected_type="totp_challenge")
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "CHALLENGE_EXPIRED",
                "message": "TOTP challenge süresi doldu. Lütfen tekrar giriş yapın.",
            },
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "CHALLENGE_INVALID",
                "message": "Geçersiz challenge token.",
            },
        ) from e

    user_id_raw = claims.get("sub")
    try:
        user_id = UUID(str(user_id_raw))
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "CHALLENGE_INVALID", "message": "Token sub formatı hatalı"},
        ) from e

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not user.totp_enabled or user.totp_secret is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_INVALID", "message": "Kullanıcı bulunamadı veya 2FA aktif değil"},
        )

    # TOTP veya backup kod doğrula
    if payload.backup_code_used:
        # Backup code path — one-time use
        match_hash = verify_backup_code(payload.code, user.totp_backup_codes or [])
        if match_hash is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "BACKUP_CODE_INVALID",
                    "message": "Backup kod geçersiz veya zaten kullanılmış.",
                },
            )
        # Kullanılan kodu çıkar (one-time use)
        user.totp_backup_codes = [c for c in user.totp_backup_codes if c != match_hash]
        logger.warning(
            "2fa.backup_code_used user_id=%s remaining=%d",
            user.id,
            len(user.totp_backup_codes),
        )
    else:
        # TOTP path
        if not verify_totp_code(user.totp_secret, payload.code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "TOTP_CODE_INVALID",
                    "message": "TOTP kodu geçersiz.",
                },
            )

    # Başarılı — tam session token'ları üret (auth.py login ile aynı flow)
    settings = get_settings()
    access_min, refresh_days = (
        settings.jwt_access_expire_minutes,
        settings.jwt_refresh_expire_days,
    )

    # Runtime override (auth.py'deki _load_jwt_ttls ile uyumlu)
    from app.api.auth import _load_jwt_ttls
    access_min, refresh_days = await _load_jwt_ttls(db, settings)

    access_token = create_access_token(
        user.id, user.role, user.tier,
        expires_delta=timedelta(minutes=access_min),
    )
    raw_refresh, refresh_hash = create_refresh_token(user.id)

    # Session kaydet
    session = Session(
        user_id=user.id,
        token_hash=refresh_hash,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
            request.client.host if request.client else None
        ),
        expires_at=datetime.now(UTC) + timedelta(days=refresh_days),
    )
    db.add(session)
    user.last_login_at = datetime.now(UTC)
    await db.commit()

    logger.info("2fa.challenge_passed user_id=%s backup=%s", user.id, payload.backup_code_used)

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=access_min * 60,
    )


@router.post("/disable", status_code=status.HTTP_200_OK)
async def disable_2fa(
    payload: DisableRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """2FA'yı kapat — password + TOTP/backup kod gerektirir (defense in depth).

    Sonuç: totp_secret + totp_backup_codes silinir, totp_enabled=FALSE.
    Login flow tekrar password-only olur.
    """
    if not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TOTP_NOT_ENABLED", "message": "2FA zaten aktif değil."},
        )

    # Password kontrolü
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_PASSWORD", "message": "Şifre yanlış."},
        )

    # TOTP veya backup kod
    code_valid = (
        verify_totp_code(user.totp_secret, payload.code)
        if user.totp_secret
        else False
    )
    if not code_valid:
        match_hash = verify_backup_code(payload.code, user.totp_backup_codes or [])
        if match_hash is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "TOTP_CODE_INVALID",
                    "message": "TOTP kodu veya backup kod geçersiz.",
                },
            )

    # Disable
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_backup_codes = []
    await db.commit()

    logger.warning("2fa.disabled user_id=%s", user.id)

    return {
        "enabled": False,
        "message": "2FA başarıyla kapatıldı. Bir daha aktif etmek için /auth/2fa/setup.",
    }


@router.post("/regenerate-backup", response_model=RegenerateBackupResponse)
async def regenerate_backup_codes(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegenerateBackupResponse:
    """Yeni 10 backup kod üret — eskileri tamamen geçersiz olur.

    Use case: kullanıcı backup kodlarını kaybetti VEYA çoğunu kullandı.
    """
    if not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TOTP_NOT_ENABLED", "message": "2FA aktif değil."},
        )

    plaintext_codes = generate_backup_codes()
    user.totp_backup_codes = [hash_backup_code(c) for c in plaintext_codes]
    await db.commit()

    logger.info("2fa.backup_codes_regenerated user_id=%s", user.id)

    return RegenerateBackupResponse(
        backup_codes=plaintext_codes,
        message=(
            "Yeni backup kodları üretildi. Önceki tüm backup kodları geçersizdir. "
            "Bu listeyi güvenli bir yerde saklayın."
        ),
    )
