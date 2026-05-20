"""Style profile endpoints (#52, Faz 5).

docs/engineering/api-contracts.md §12.1-12.3
PRD §5

Endpoints:
    POST   /app/style-profiles              — Profil oluştur (samples opsiyonel) → analyze
    GET    /app/style-profiles              — Kullanıcının profilleri
    GET    /app/style-profiles/{id}         — Tek profil detay
    DELETE /app/style-profiles/{id}         — Sil
    POST   /app/style-profiles/{id}/samples — Yeni örnek ekle
    POST   /app/style-profiles/{id}/reanalyze — Manuel reanalyze (status='failed' sonrası)

Pro+ tier paywall: features.style_profiles + slot quota (Pro=3, Agency=10).
PII redaction sample.text üzerinde import sırasında uygulanır (KVKK).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.pii import redact
from app.core.plan_features import resolve_user_plan_features
from app.models.style_profile import StyleProfile, StyleSample
from app.models.user import User
from app.prompts.style_analyzer import (
    MAX_SAMPLE_CHARS,
    MAX_SAMPLES,
    MAX_TOTAL_CHARS,
    MIN_SAMPLES,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Models
# =============================================================================


class SampleInput(BaseModel):
    text: str = Field(min_length=20, max_length=MAX_SAMPLE_CHARS)
    source_url: str | None = Field(default=None, max_length=2000)


class ProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    source_type: str = Field(pattern="^(manual|csv_import|public_account)$")
    samples: list[SampleInput] = Field(default_factory=list, max_length=MAX_SAMPLES)


class SampleResponse(BaseModel):
    id: str
    text: str
    source_url: str | None
    char_count: int
    created_at: datetime


class StyleProfileItem(BaseModel):
    id: str
    name: str
    source_type: str
    status: str
    style_summary: str | None
    rules_json: dict[str, Any]
    sample_count: int
    error_message: str | None
    analyzed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StyleProfilesListResponse(BaseModel):
    data: list[StyleProfileItem]
    quota: dict[str, Any]


class StyleProfileDetail(StyleProfileItem):
    samples: list[SampleResponse]


class SampleCreateResponse(BaseModel):
    sample: SampleResponse
    sample_count: int
    will_reanalyze: bool


# =============================================================================
# Helpers
# =============================================================================


def _to_item(profile: StyleProfile) -> StyleProfileItem:
    return StyleProfileItem(
        id=str(profile.id),
        name=profile.name,
        source_type=profile.source_type,
        status=profile.status,
        style_summary=profile.style_summary,
        rules_json=profile.rules_json or {},
        sample_count=profile.sample_count,
        error_message=profile.error_message,
        analyzed_at=profile.analyzed_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _to_sample(sample: StyleSample) -> SampleResponse:
    return SampleResponse(
        id=str(sample.id),
        text=sample.text,
        source_url=sample.source_url,
        char_count=sample.char_count,
        created_at=sample.created_at,
    )


def _check_paywall(features: dict[str, Any], plan_code: str) -> None:
    if not features.get("style_profiles", False):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "STYLE_PROFILES_REQUIRES_PRO",
                "message": (
                    "Stil profilleri Pro tier'da kullanıma açıktır. "
                    "Planınızı yükselterek bu özelliği kullanabilirsiniz."
                ),
                "current_plan": plan_code,
            },
        )


async def _check_slot_quota(db: AsyncSession, user: User, slots_allowed: int) -> int:
    """Mevcut profil sayısı slot quota'sını aşıyor mu?"""
    count = (
        await db.execute(select(func.count(StyleProfile.id)).where(StyleProfile.user_id == user.id))
    ).scalar_one()
    if count >= slots_allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STYLE_PROFILES_SLOT_FULL",
                "message": (
                    f"Plan stil profili kotanız dolu ({count}/{slots_allowed}). "
                    f"Yeni profil için mevcut bir profili silin veya planı yükseltin."
                ),
                "used": count,
                "limit": slots_allowed,
            },
        )
    return count


def _redact_sample_text(text: str) -> tuple[str, int]:
    """KVKK — sample import'ta PII redaction (e-posta/telefon/IBAN/TC)."""
    result = redact(text)
    return result.text, result.total_redactions


def _dispatch_analyze(profile_id: UUID) -> None:
    """Celery task'i tetikle — failure log'lanır, kullanıcıya yansıtılmaz."""
    try:
        from app.modules.style_profiles.tasks.style_profile import analyze_style_profile

        analyze_style_profile.apply_async(args=[str(profile_id)])
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "style_profile.analyze dispatch failed pid=%s err=%s",
            profile_id,
            exc,
        )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "",
    response_model=StyleProfileItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    payload: ProfileCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StyleProfileItem:
    """Yeni stil profili oluştur. Samples verilirse hemen analyze tetiklenir."""
    features, plan_code = await resolve_user_plan_features(db, user)
    _check_paywall(features, plan_code)

    slots_allowed = int(features.get("style_profiles_slots", 0) or 0)
    await _check_slot_quota(db, user, slots_allowed)

    # Toplam karakter bütçesi
    total_chars = sum(len(s.text) for s in payload.samples)
    if total_chars > MAX_TOTAL_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SAMPLES_TOO_LONG",
                "message": (
                    f"Toplam örnek metin karakter limitini aşıyor "
                    f"({total_chars}>{MAX_TOTAL_CHARS}). "
                    "Daha kısa örnekler ekleyin."
                ),
            },
        )

    profile = StyleProfile(
        user_id=user.id,
        name=payload.name.strip(),
        source_type=payload.source_type,
        status="pending",
    )
    db.add(profile)
    await db.flush()

    # Sample'ları redact + persist
    redacted_total = 0
    for s in payload.samples:
        clean, redacted = _redact_sample_text(s.text)
        redacted_total += redacted
        db.add(
            StyleSample(
                style_profile_id=profile.id,
                text=clean,
                source_url=s.source_url,
                char_count=len(clean),
            )
        )

    profile.sample_count = len(payload.samples)
    if len(payload.samples) >= MIN_SAMPLES:
        profile.status = "analyzing"

    await db.commit()
    await db.refresh(profile)

    if redacted_total > 0:
        logger.info(
            "style_profile.create user=%s pid=%s redacted=%d",
            user.id,
            profile.id,
            redacted_total,
        )

    if profile.status == "analyzing":
        _dispatch_analyze(profile.id)

    return _to_item(profile)


@router.get("", response_model=StyleProfilesListResponse)
async def list_profiles(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StyleProfilesListResponse:
    features, plan_code = await resolve_user_plan_features(db, user)
    profiles = (
        (
            await db.execute(
                select(StyleProfile)
                .where(StyleProfile.user_id == user.id)
                .order_by(StyleProfile.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    slots_allowed = int(features.get("style_profiles_slots", 0) or 0)
    return StyleProfilesListResponse(
        data=[_to_item(p) for p in profiles],
        quota={
            "style_profiles_enabled": bool(features.get("style_profiles", False)),
            "used": len(profiles),
            "limit": slots_allowed,
            "plan_code": plan_code,
        },
    )


@router.get("/{profile_id}", response_model=StyleProfileDetail)
async def get_profile(
    profile_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StyleProfileDetail:
    profile = await _load_owned_profile(db, profile_id, user.id)

    samples = (
        (
            await db.execute(
                select(StyleSample)
                .where(StyleSample.style_profile_id == profile.id)
                .order_by(StyleSample.created_at)
            )
        )
        .scalars()
        .all()
    )

    item = _to_item(profile)
    return StyleProfileDetail(
        **item.model_dump(),
        samples=[_to_sample(s) for s in samples],
    )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    profile = await _load_owned_profile(db, profile_id, user.id)
    await db.delete(profile)
    await db.commit()


@router.post(
    "/{profile_id}/samples",
    response_model=SampleCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_sample(
    profile_id: Annotated[UUID, Path()],
    payload: SampleInput,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SampleCreateResponse:
    profile = await _load_owned_profile(db, profile_id, user.id)

    # Toplam sample sayısı limit'i
    if profile.sample_count >= MAX_SAMPLES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SAMPLE_LIMIT_REACHED",
                "message": f"Bu profile en fazla {MAX_SAMPLES} örnek eklenebilir.",
            },
        )

    clean, redacted = _redact_sample_text(payload.text)
    sample = StyleSample(
        style_profile_id=profile.id,
        text=clean,
        source_url=payload.source_url,
        char_count=len(clean),
    )
    db.add(sample)
    profile.sample_count += 1
    profile.updated_at = datetime.now(UTC)

    will_reanalyze = profile.sample_count >= MIN_SAMPLES and profile.status in {
        "pending",
        "failed",
    }
    if will_reanalyze:
        profile.status = "analyzing"
        profile.error_message = None

    await db.commit()
    await db.refresh(sample)

    if redacted > 0:
        logger.info(
            "style_profile.add_sample user=%s pid=%s redacted=%d",
            user.id,
            profile_id,
            redacted,
        )

    if will_reanalyze:
        _dispatch_analyze(profile_id)

    return SampleCreateResponse(
        sample=_to_sample(sample),
        sample_count=profile.sample_count,
        will_reanalyze=will_reanalyze,
    )


@router.post("/{profile_id}/reanalyze", response_model=StyleProfileItem)
async def reanalyze(
    profile_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StyleProfileItem:
    profile = await _load_owned_profile(db, profile_id, user.id)

    if profile.sample_count < MIN_SAMPLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INSUFFICIENT_SAMPLES",
                "message": (f"En az {MIN_SAMPLES} örnek gerekiyor (şu an {profile.sample_count})."),
            },
        )
    if profile.status == "analyzing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_ANALYZING",
                "message": "Profil zaten analiz ediliyor; bitince güncellenir.",
            },
        )

    profile.status = "analyzing"
    profile.error_message = None
    profile.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(profile)

    _dispatch_analyze(profile.id)
    return _to_item(profile)


# =============================================================================
# Internals
# =============================================================================


async def _load_owned_profile(db: AsyncSession, profile_id: UUID, user_id: Any) -> StyleProfile:
    profile = await db.get(StyleProfile, profile_id)
    if profile is None or profile.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "STYLE_PROFILE_NOT_FOUND",
                "message": "Stil profili bulunamadı.",
            },
        )
    return profile
