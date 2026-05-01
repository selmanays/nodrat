"""FastAPI dependency'leri — auth, role enforcement.

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
from app.models.user import User


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
