"""Auth endpoints — register, login, logout, refresh.

docs/engineering/api-contracts.md §3
docs/legal/opinion-integration.md §3.5 (4 KVKK checkbox)
docs/engineering/threat-model.md §2.1
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from app.models.user import Session, User


router = APIRouter()


# =============================================================================
# Pydantic schemas
# =============================================================================


class RegisterRequest(BaseModel):
    """Kayıt isteği — 4 KVKK checkbox + 18+ onayı.

    Legal opinion §3.5: 3 zorunlu + 1 opsiyonel onay AYRI checkbox.
    """

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)
    locale: str = Field(default="tr-TR", max_length=10)

    # 4 KVKK checkbox (3 zorunlu, 1 opsiyonel)
    kvkk_acknowledgment: bool
    """KVKK Aydınlatma Metni okundu — ZORUNLU."""

    data_processing_consent: bool
    """Kişisel veri işleme onayı — ZORUNLU."""

    foreign_transfer_consent: bool
    """Yurt dışı LLM provider transfer onayı — ZORUNLU."""

    marketing_consent: bool = False
    """Pazarlama iletisi — opsiyonel."""

    age_18_plus: bool
    """18+ yaş onayı — ZORUNLU."""

    @field_validator("kvkk_acknowledgment")
    @classmethod
    def kvkk_required(cls, v: bool) -> bool:
        if not v:
            raise ValueError("KVKK Aydınlatma Metni'ni kabul etmek zorunludur.")
        return v

    @field_validator("data_processing_consent")
    @classmethod
    def consent_required(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Kişisel veri işleme onayı zorunludur.")
        return v

    @field_validator("foreign_transfer_consent")
    @classmethod
    def transfer_consent_required(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "Yurt dışı yapay zeka servis sağlayıcılarına veri aktarımı onayı zorunludur."
            )
        return v

    @field_validator("age_18_plus")
    @classmethod
    def age_required(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Hizmet yalnızca 18 yaş ve üzeri kullanıcılar içindir.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: "UserPublic"


class UserPublic(BaseModel):
    """Public user shape — password_hash gibi sensitive alanlar gizli."""

    id: str
    email: str
    full_name: str | None
    role: str
    tier: str
    locale: str
    email_verified: bool


class RegisterResponse(BaseModel):
    user_id: str
    email: str
    verification_email_sent: bool


# =============================================================================
# Helpers
# =============================================================================


def _get_client_ip(request: Request) -> str | None:
    """X-Real-IP veya X-Forwarded-For (Caddy zaten ekliyor)."""
    return (
        request.headers.get("x-real-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResponse,
    summary="Yeni kullanıcı kaydı",
)
async def register(
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    """Kullanıcı kaydı + 4 KVKK consent + 18+ check.

    Schema validation 3 zorunlu KVKK + 18+ onayını zorlar.
    Email duplicate ise 409 CONFLICT.
    """
    now = datetime.now(UTC)

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        locale=payload.locale,
        kvkk_acknowledgment_at=now,
        data_processing_consent_at=now,
        foreign_transfer_consent_at=now,
        marketing_consent_at=now if payload.marketing_consent else None,
    )
    db.add(user)

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EMAIL_TAKEN",
                "title": "E-posta zaten kayıtlı",
                "detail": "Bu e-posta adresi başka bir hesapta kullanılıyor.",
            },
        ) from None

    # TODO: Email verify token gönder (Issue #69 — email templates)
    # _send_verification_email(user.email)

    return RegisterResponse(
        user_id=str(user.id),
        email=user.email,
        verification_email_sent=False,  # Faz 0: email integration sonra
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Giriş yap",
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Email + şifre ile giriş.

    Generic error mesajları (timing attack + email enumeration koruması).
    """
    settings = get_settings()

    result = await db.execute(
        select(User).where(
            User.email == payload.email,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    # Generic error: kullanıcı yok VEYA şifre yanlış (enum koruması)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_CREDENTIALS",
                "title": "Geçersiz e-posta veya şifre",
                "detail": "E-posta veya şifre doğru değil.",
            },
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_DISABLED",
                "title": "Hesap pasif",
                "detail": "Hesabınız pasif durumda. Destekle iletişime geçin.",
            },
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "EMAIL_NOT_VERIFIED",
                "title": "E-posta doğrulanmamış",
                "detail": "Lütfen e-posta adresinize gönderilen bağlantıyla hesabınızı doğrulayın.",
            },
        )

    # Rehash kontrolü (cost factor güncellendiyse)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    # Tokens
    access_token = create_access_token(user.id, user.role, user.tier)
    raw_refresh, refresh_hash = create_refresh_token(user.id)

    # Session kaydet
    session = Session(
        user_id=user.id,
        token_hash=refresh_hash,
        user_agent=request.headers.get("user-agent"),
        ip_address=_get_client_ip(request),
        expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_expire_days),
    )
    db.add(session)

    # Tracking
    user.last_login_at = datetime.now(UTC)
    user.last_login_ip = _get_client_ip(request)

    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.jwt_access_expire_minutes * 60,
        user=UserPublic(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            tier=user.tier,
            locale=user.locale,
            email_verified=user.email_verified,
        ),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Token yenile",
)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Refresh token ile yeni access + yeni refresh token.

    Refresh token rotation — eski refresh kullanılamaz hale gelir.
    """
    settings = get_settings()

    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_EXPIRED", "title": "Refresh token süresi doldu"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "title": "Geçersiz token"},
        ) from None

    # DB'de session var mı + revoked değil mi?
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(
        select(Session).where(
            Session.token_hash == token_hash,
            Session.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "SESSION_REVOKED", "title": "Oturum iptal edilmiş"},
        )

    if session.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "SESSION_EXPIRED", "title": "Oturum süresi doldu"},
        )

    # User'ı al
    user_result = await db.execute(
        select(User).where(
            User.id == session.user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_INVALID", "title": "Kullanıcı geçersiz"},
        )

    # Eski session'ı revoke et (rotation)
    session.revoked_at = datetime.now(UTC)

    # Yeni tokenlar
    new_access = create_access_token(user.id, user.role, user.tier)
    new_raw_refresh, new_refresh_hash = create_refresh_token(user.id)

    # Yeni session
    new_session = Session(
        user_id=user.id,
        token_hash=new_refresh_hash,
        user_agent=request.headers.get("user-agent"),
        ip_address=_get_client_ip(request),
        expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_expire_days),
    )
    db.add(new_session)
    await db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_raw_refresh,
        expires_in=settings.jwt_access_expire_minutes * 60,
        user=UserPublic(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            tier=user.tier,
            locale=user.locale,
            email_verified=user.email_verified,
        ),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Çıkış yap (refresh token revoke)",
)
async def logout(
    payload: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Refresh token'ı revoke et (silent fail — token zaten yoksa OK)."""
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(
        select(Session).where(
            Session.token_hash == token_hash,
            Session.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()

    if session is not None:
        session.revoked_at = datetime.now(UTC)
        await db.commit()
