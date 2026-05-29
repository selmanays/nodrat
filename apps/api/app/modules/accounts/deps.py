"""Accounts modülü auth/role dependency surface — FastAPI auth, role enforcement.

T7-7 (v104): `app/core/deps.py`'den taşındı (accounts modülü auth/identity
kanonik evi). T8-21 (v107-v111): `User`+`Session` de `accounts/models.py`'ye
taşındı → `from app.modules.accounts.models import User` artık tam intra-module
(sibling); core/ User import etmez → `core/* must not import modules/*` temiz.

docs/engineering/api-contracts.md §0 (routing)
docs/engineering/threat-model.md §2 (authn/z)
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import decode_token
from app.modules.accounts.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(code: str, title: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "title": title},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(code: str, title: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": code, "title": title},
    )


async def get_current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Authorization: Bearer <access_token> doğrula → User döner.

    401 cases:
        - Header eksik
        - Token süresi doldu
        - Token geçersiz
        - User yok / deleted / inactive
    """
    if creds is None or not creds.credentials:
        raise _unauthorized("AUTH_REQUIRED", "Yetkilendirme gerekli")

    try:
        claims = decode_token(creds.credentials, expected_type="access")
    except jwt.ExpiredSignatureError as e:
        raise _unauthorized("TOKEN_EXPIRED", "Access token süresi doldu") from e
    except jwt.InvalidTokenError as e:
        raise _unauthorized("TOKEN_INVALID", "Geçersiz token") from e

    user_id_raw = claims.get("sub")
    if not user_id_raw:
        raise _unauthorized("TOKEN_INVALID", "Token sub eksik")

    try:
        user_id = UUID(str(user_id_raw))
    except (ValueError, TypeError) as e:
        raise _unauthorized("TOKEN_INVALID", "Token sub formatı hatalı") from e

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise _unauthorized("USER_INVALID", "Kullanıcı bulunamadı veya pasif")

    # Request'e attach et — audit log için
    request.state.user_id = user.id
    request.state.user_role = user.role
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Sadece super_admin geçer — diğer tüm role'ler 403."""
    if user.role != "super_admin":
        raise _forbidden("FORBIDDEN_NOT_ADMIN", "Bu endpoint için admin yetkisi gerekir")
    return user


# Aydınlatma metin sürümü — bu issue (#470) launch ile v0.2 (LS MoR pivot sonrası).
# Yeni metin sürümü çıkarsa burası bumpı olur ve user'lardan re-consent istenir.
CURRENT_CONSENT_VERSION = "v0.2"


async def require_foreign_transfer_consent(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """KVKK m.9 — yurt dışı veri aktarımı için açık rıza zorunlu (#470).

    Avukat şartlı onayı (Epic #448 §3.9 N-09 RESOLVED): server-side enforcement
    zorunlu. Aşağıdaki 5 akışta bu dependency kullanılır:
      1. POST /app/billing/checkout (LS hosted checkout — #53)
      2. GET /app/billing/portal-url (LS Customer Portal — #53)
      3. POST /app/generate (LLM provider çağrısı)
      4. send_email worker (Resend / Postmark — yurt dışı)
      5. Embedding fallback (NIM bge-m3 yurt dışı çağrı — local primary fail durumunda)

    403 response format (api-contracts.md §16.3):
        {
          "error": "foreign_transfer_consent_required",
          "message": "Bu özelliği kullanmak için yurt dışı veri transferi açık rızası gerekli.",
          "consent_url": "/app/consent",
          "metin_versiyon": "v0.2"
        }

    Geçer durumlar:
        foreign_transfer_consent_at NOT NULL AND foreign_transfer_consent_revoked_at IS NULL

    KS-2 acceptance: Backend gate ile bu dependency'i import eden tüm akışlar
    kullanıcı consent'i olmadan yurt dışı çağrı yapamaz (R-LGL-13 mitigation).
    """
    if (
        user.foreign_transfer_consent_at is None
        or user.foreign_transfer_consent_revoked_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "foreign_transfer_consent_required",
                "message": (
                    "Bu özelliği kullanmak için yurt dışı veri transferi "
                    "açık rızası gerekli. /app/consent sayfasından onaylayın."
                ),
                "consent_url": "/app/consent",
                "metin_versiyon": CURRENT_CONSENT_VERSION,
            },
        )
    return user


def get_client_ip(request: Request) -> str | None:
    """X-Forwarded-For / X-Real-IP üzerinden client IP."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None
