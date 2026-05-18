"""Foreign transfer consent endpoints (#470, KVKK m.9).

docs/engineering/api-contracts.md §16 (Consent Endpoints)
docs/legal/kvkk-aydinlatma.md §4.2.1 (TIA — Transfer Impact Assessment)
docs/legal/tos.md §10.4 (avukat formülü, server-side enforcement notu)

Endpoints:
    POST   /app/consent/foreign-transfer    — Açık rıza kaydet (TIA: timestamp + IP + version + hash)
    DELETE /app/consent/foreign-transfer    — Geri çekme (KVKK m.11)
    GET    /app/consent/status              — Mevcut consent durumu

Avukat şartlı onayı (Epic #448 §3.9 N-09 RESOLVED) bu akışın 5 yurt dışı
çağrı noktasında server-side enforced olmasını şart koşar (deps.py
`require_foreign_transfer_consent` dependency ile uygulanır).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import (
    CURRENT_CONSENT_VERSION,
    get_client_ip,
    get_current_user,
)
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# Aydınlatma metni canonical kaynak: docs/legal/kvkk-aydinlatma.md §4.2 yurt dışı transfer.
# Hash, kullanıcının tam olarak hangi metni onayladığını immutable şekilde kayda
# almak için kullanılır (TIA — Transfer Impact Assessment kanıtı).
CONSENT_TEXT_CANONICAL = (
    "Yurt dışı hizmet sağlayıcılarına (Lemon Squeezy MoR ABD, DeepSeek HK, "
    "Anthropic ABD, OpenRouter ABD, NVIDIA NIM ABD, Resend/Postmark ABD) veri "
    "aktarımı gerektiren özellikler, KVKK m.9 kapsamında açık rıza vermem "
    "halinde kullanılabilir. Açık rızamı geri çektiğimde ilgili özellikler "
    "kullanıma kapatılır."
)


def _consent_text_hash(version: str) -> str:
    """SHA-256 hash — version + canonical text. TIA immutable kanıt."""
    payload = f"{version}::{CONSENT_TEXT_CANONICAL}".encode()
    return hashlib.sha256(payload).hexdigest()


class ConsentGrantRequest(BaseModel):
    """POST /app/consent/foreign-transfer body."""

    consent_text_version: str = Field(
        default=CURRENT_CONSENT_VERSION,
        max_length=16,
        description="Aydınlatma metin sürümü (örn. 'v0.2'). Server'ın güncel sürümü ile karşılaştırılır.",
    )


class ConsentGrantResponse(BaseModel):
    consent_at: datetime
    version: str
    revoked: bool


class ConsentStatusResponse(BaseModel):
    has_consent: bool
    consent_at: datetime | None
    version: str | None
    revoked_at: datetime | None
    current_version: str
    needs_re_consent: bool
    """User v0.1 onayladı, server v0.2'ye yükseldi → re-consent gerek."""


class ConsentRevokeResponse(BaseModel):
    revoked_at: datetime
    message: str


@router.get("/status", response_model=ConsentStatusResponse)
async def get_consent_status(
    user: Annotated[User, Depends(get_current_user)],
) -> ConsentStatusResponse:
    """Kullanıcının mevcut foreign transfer consent durumu.

    Frontend bu endpoint'i sayfa yüklerken çağırır — eğer `needs_re_consent=true`
    veya `has_consent=false` ise checkbox modal'ı gösterilir.
    """
    has_consent = (
        user.foreign_transfer_consent_at is not None
        and user.foreign_transfer_consent_revoked_at is None
    )
    needs_re_consent = (
        has_consent and user.foreign_transfer_consent_version != CURRENT_CONSENT_VERSION
    )
    return ConsentStatusResponse(
        has_consent=has_consent,
        consent_at=user.foreign_transfer_consent_at,
        version=user.foreign_transfer_consent_version,
        revoked_at=user.foreign_transfer_consent_revoked_at,
        current_version=CURRENT_CONSENT_VERSION,
        needs_re_consent=needs_re_consent,
    )


@router.post(
    "/foreign-transfer",
    response_model=ConsentGrantResponse,
    status_code=status.HTTP_200_OK,
)
async def grant_foreign_transfer_consent(
    body: ConsentGrantRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentGrantResponse:
    """KVKK m.9 yurt dışı transfer açık rıza kaydet.

    TIA kayıtları (avukat şartı, kvkk-aydinlatma.md §4.2.1):
        (i)   timestamp (now UTC)
        (ii)  IP (X-Forwarded-For / X-Real-IP / client.host)
        (iii) version (request body)
        (iv)  text_hash (SHA-256 of version + canonical text)
        (v)   user_id (auth context)

    Idempotent: Daha önce verilen consent'in re-grant edilmesi (örn. yeni metin
    sürümü için) timestamp + version + ip + hash günceller, revoked_at'i temizler.

    Eğer kullanıcı request body'de eski sürüm (örn. 'v0.1') gönderirse server
    bunu kabul eder ama needs_re_consent flag'i true kalır (status endpoint'inde
    görülür). Production tipik akış: frontend her zaman CURRENT_CONSENT_VERSION
    gönderir.
    """
    # Server'ın bilmediği versiyon → reddet (frontend güncel değil).
    # Geriye dönük uyumluluk için 'v0.1' kabul edilir (legacy register flow).
    if body.consent_text_version not in (CURRENT_CONSENT_VERSION, "v0.1"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "unknown_consent_version",
                "message": f"Bilinmeyen aydınlatma metin sürümü: {body.consent_text_version}",
                "current_version": CURRENT_CONSENT_VERSION,
            },
        )

    now = datetime.now(UTC)
    user.foreign_transfer_consent_at = now
    user.foreign_transfer_consent_version = body.consent_text_version
    user.foreign_transfer_consent_ip = get_client_ip(request)
    user.foreign_transfer_consent_text_hash = _consent_text_hash(body.consent_text_version)
    user.foreign_transfer_consent_revoked_at = None  # re-grant clears revocation
    await db.commit()

    logger.info(
        "consent.granted user_id=%s version=%s ip=%s",
        user.id,
        body.consent_text_version,
        user.foreign_transfer_consent_ip,
    )
    return ConsentGrantResponse(
        consent_at=now,
        version=body.consent_text_version,
        revoked=False,
    )


@router.delete(
    "/foreign-transfer",
    response_model=ConsentRevokeResponse,
)
async def revoke_foreign_transfer_consent(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentRevokeResponse:
    """KVKK m.11 — yurt dışı transfer açık rızasını geri çek.

    Sonuç: 5 akış (LS checkout/portal, LLM, email, embedding fallback) kullanıcı
    için 403 döner. Kullanıcı re-grant edebilir (POST /foreign-transfer).

    Geri çekme TIA kayıtlarını silmez — sadece `revoked_at` set edilir (audit).
    """
    if (
        user.foreign_transfer_consent_at is None
        or user.foreign_transfer_consent_revoked_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "no_active_consent",
                "message": "Geri çekilecek aktif bir açık rıza kaydı bulunamadı.",
            },
        )

    now = datetime.now(UTC)
    user.foreign_transfer_consent_revoked_at = now
    await db.commit()

    logger.info(
        "consent.revoked user_id=%s previously_granted_at=%s",
        user.id,
        user.foreign_transfer_consent_at,
    )
    return ConsentRevokeResponse(
        revoked_at=now,
        message=(
            "Açık rıza geri çekildi. Yapay zeka üretimi, e-posta ve ödeme "
            "özelliklerine erişim kapatıldı. Tekrar onaylamak için "
            "/app/consent sayfasını ziyaret edebilirsiniz."
        ),
    )
