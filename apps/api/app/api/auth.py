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
from app.email.service import (
    consume_email_verify_token,
    consume_password_reset_token,
    create_email_verify_token,
    create_password_reset_token,
    send_email_verify,
    send_password_reset,
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


class TwoFactorChallengeResponse(BaseModel):
    """#56 — Login sonrası 2FA gerekiyorsa dönen response.

    Frontend kullanıcıdan TOTP kodu ister, sonra POST /auth/2fa/verify-challenge
    endpoint'ine challenge_token + code gönderir → tam access/refresh token alır.
    """

    requires_2fa: bool = True
    totp_challenge_token: str = Field(
        description="5 dakika geçerli challenge token. /auth/2fa/verify-challenge'a gönderilir."
    )
    backup_codes_available: bool = Field(
        description="True ise kullanıcı backup kod alternatifini görebilir"
    )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserPublic


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


async def _load_jwt_ttls(db, settings) -> tuple[int, int]:
    """#271 — JWT TTL runtime override (admin paneli)."""
    access = settings.jwt_access_expire_minutes
    refresh = settings.jwt_refresh_expire_days
    try:
        from app.core.settings_store import settings_store

        access = await settings_store.get_int(
            db, "auth.jwt_access_expire_minutes", access
        )
        refresh = await settings_store.get_int(
            db, "auth.jwt_refresh_expire_days", refresh
        )
    except Exception:  # pragma: no cover
        pass
    return access, refresh


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
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    """Kullanıcı kaydı + 4 KVKK consent + 18+ check.

    Schema validation 3 zorunlu KVKK + 18+ onayını zorlar.
    Email duplicate ise 409 CONFLICT.

    #470: Foreign transfer consent için TIA metadata (version + IP + text_hash)
    register anında kayıt — KVKK m.9 audit trail.
    """
    # Lazy imports — circular import risk yok ama aynı zamanda app_consent
    # modülüne ait sabitleri burada da kullanmak için.
    from app.api.app_consent import _consent_text_hash
    from app.core.deps import CURRENT_CONSENT_VERSION, get_client_ip

    now = datetime.now(UTC)
    client_ip = get_client_ip(request)
    consent_text_hash = _consent_text_hash(CURRENT_CONSENT_VERSION)

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        locale=payload.locale,
        kvkk_acknowledgment_at=now,
        data_processing_consent_at=now,
        foreign_transfer_consent_at=now,
        # #470 — TIA metadata
        foreign_transfer_consent_version=CURRENT_CONSENT_VERSION,
        foreign_transfer_consent_ip=client_ip,
        foreign_transfer_consent_text_hash=consent_text_hash,
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

    # User zaten kaydedildi (önceki commit). Email verification token üret +
    # mail gönder (#68). Hata durumunda kayıt iptal olmasın — kullanıcı sonra
    # /auth/verify-resend endpoint'i ile tekrar isteyebilir.
    settings = get_settings()
    verification_sent = False
    try:
        raw_token = await create_email_verify_token(db, user)
        verify_url = f"{settings.next_public_app_url}/verify-email?token={raw_token}"
        log_entry = await send_email_verify(db, user, verify_url)
        await db.commit()
        verification_sent = log_entry.status == "sent"
    except Exception:
        # Sadece token + log_entry rollback olur (user zaten committed)
        await db.rollback()
        verification_sent = False

    return RegisterResponse(
        user_id=str(user.id),
        email=user.email,
        verification_email_sent=verification_sent,
    )


@router.post(
    "/login",
    response_model=TokenResponse | TwoFactorChallengeResponse,
    summary="Giriş yap (2FA aktifse challenge döner)",
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse | TwoFactorChallengeResponse:
    """Email + şifre ile giriş.

    Generic error mesajları (timing attack + email enumeration koruması).

    #56 — Eğer user.totp_enabled=TRUE: tam token yerine TwoFactorChallengeResponse
    döner. Frontend TOTP kodu alıp /auth/2fa/verify-challenge'a gönderir.
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
        await db.commit()

    # #56 — 2FA challenge: password OK ama TOTP gerekiyor
    if user.totp_enabled:
        from app.core.security import create_totp_challenge_token

        challenge_token = create_totp_challenge_token(user.id)
        return TwoFactorChallengeResponse(
            totp_challenge_token=challenge_token,
            backup_codes_available=len(user.totp_backup_codes or []) > 0,
        )

    # #271 — runtime JWT TTL override
    access_min, refresh_days = await _load_jwt_ttls(db, settings)

    # Tokens
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
        ip_address=_get_client_ip(request),
        expires_at=datetime.now(UTC) + timedelta(days=refresh_days),
    )
    db.add(session)

    # Tracking
    user.last_login_at = datetime.now(UTC)
    user.last_login_ip = _get_client_ip(request)

    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=access_min * 60,
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

    # #271 — runtime JWT TTL override
    access_min, refresh_days = await _load_jwt_ttls(db, settings)

    # Yeni tokenlar
    new_access = create_access_token(
        user.id, user.role, user.tier,
        expires_delta=timedelta(minutes=access_min),
    )
    new_raw_refresh, new_refresh_hash = create_refresh_token(user.id)

    # Yeni session
    new_session = Session(
        user_id=user.id,
        token_hash=new_refresh_hash,
        user_agent=request.headers.get("user-agent"),
        ip_address=_get_client_ip(request),
        expires_at=datetime.now(UTC) + timedelta(days=refresh_days),
    )
    db.add(new_session)
    await db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_raw_refresh,
        expires_in=access_min * 60,
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


# =============================================================================
# Email verification endpoints (#68)
# =============================================================================


class VerifyTokenRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=128)


class VerifyResponse(BaseModel):
    user_id: str
    email: str
    email_verified: bool


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="E-posta doğrulama (token kullan)",
)
async def verify_email(
    payload: VerifyTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VerifyResponse:
    """Email verify token'ı işle. Tek kullanım — token consume edilir."""
    user = await consume_email_verify_token(db, payload.token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_OR_EXPIRED_TOKEN",
                "title": "Geçersiz veya süresi dolmuş bağlantı",
                "detail": "Bu doğrulama bağlantısı geçersiz ya da kullanılmış. "
                "Hesap ayarlarından yeni bir doğrulama maili talep edin.",
            },
        )
    await db.commit()
    return VerifyResponse(
        user_id=str(user.id),
        email=user.email,
        email_verified=True,
    )


class VerifyResendRequest(BaseModel):
    email: EmailStr


class GenericOkResponse(BaseModel):
    ok: bool = True
    detail: str | None = None


@router.post(
    "/verify-resend",
    response_model=GenericOkResponse,
    summary="Doğrulama e-postasını yeniden gönder",
)
async def verify_resend(
    payload: VerifyResendRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenericOkResponse:
    """Email enumeration koruması: kullanıcı yoksa bile 200 dön.

    Idempotent — istek başarılıysa her zaman 200, içerik aynı.
    """
    settings = get_settings()
    result = await db.execute(
        select(User).where(
            User.email == payload.email,
            User.deleted_at.is_(None),
            User.email_verified.is_(False),
        )
    )
    user = result.scalar_one_or_none()

    # Sadece email_verified=False olan user için gönder. Aksi halde silent OK
    # (enumeration koruması — saldırgan kayıtlı email öğrenemez).
    if user is not None:
        try:
            raw_token = await create_email_verify_token(db, user)
            verify_url = f"{settings.next_public_app_url}/verify-email?token={raw_token}"
            await send_email_verify(db, user, verify_url)
            await db.commit()
        except Exception:
            await db.rollback()

    return GenericOkResponse(
        detail="E-posta gönderildi (kayıtlı ise). Lütfen gelen kutunu kontrol et.",
    )


# =============================================================================
# Password reset endpoints (#68)
# =============================================================================


class PasswordResetRequest(BaseModel):
    email: EmailStr


@router.post(
    "/password-reset-request",
    response_model=GenericOkResponse,
    summary="Şifre sıfırlama maili iste",
)
async def password_reset_request(
    payload: PasswordResetRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenericOkResponse:
    """Email enumeration koruması: kullanıcı yoksa bile 200 dön."""
    settings = get_settings()

    result = await db.execute(
        select(User).where(
            User.email == payload.email,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()

    if user is not None:
        try:
            client_ip = _get_client_ip(request)
            raw_token = await create_password_reset_token(
                db, user, request_ip=client_ip
            )
            reset_url = f"{settings.next_public_app_url}/reset-password?token={raw_token}"
            await send_password_reset(db, user, reset_url, request_ip=client_ip)
            await db.commit()
        except Exception:
            await db.rollback()

    return GenericOkResponse(
        detail="Eğer hesap mevcutsa şifre sıfırlama bağlantısı e-posta ile gönderildi.",
    )


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=128)
    new_password: str = Field(..., min_length=12, max_length=128)
    """Register endpoint ile aynı politika — min 12 karakter (#138 follow-up)."""

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        # Basit kontrol — production'da zxcvbn vb. kullanılabilir
        if len(v) < 12:
            raise ValueError("Şifre en az 12 karakter olmalı")
        return v


@router.post(
    "/password-reset",
    response_model=GenericOkResponse,
    summary="Yeni şifre belirle (reset token ile)",
)
async def password_reset(
    payload: PasswordResetConfirmRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenericOkResponse:
    """Reset token + yeni şifre. Tek kullanım — token consume edilir."""
    user = await consume_password_reset_token(db, payload.token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_OR_EXPIRED_TOKEN",
                "title": "Geçersiz veya süresi dolmuş bağlantı",
                "detail": "Bu sıfırlama bağlantısı geçersiz ya da kullanılmış. "
                "Yeni bir sıfırlama talebi oluşturun.",
            },
        )

    # Şifreyi güncelle
    user.password_hash = hash_password(payload.new_password)

    # Tüm aktif refresh token'ları revoke et (security best practice —
    # şifre değişince eski oturumlar kapanmalı)
    await db.execute(
        select(Session).where(
            Session.user_id == user.id,
            Session.revoked_at.is_(None),
        )
    )
    # SQLAlchemy update statement
    from sqlalchemy import update

    await db.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )

    await db.commit()
    return GenericOkResponse(detail="Şifreniz başarıyla güncellendi.")
