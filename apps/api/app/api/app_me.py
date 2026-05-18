"""KVKK self-service: profil + veri export + hesap silme (#80).

docs/engineering/api-contracts.md §13 (app/me endpoints)
docs/legal/opinion-integration.md §3.5 (KVKK self-service flow)
docs/legal/kvkk-aydinlatma.md (md.11 hakları — erişim, düzeltme, silme)
docs/engineering/data-model.md §2.1 (users.deleted_at soft delete)

Endpoints:
    GET    /app/me            — Kullanıcı profili (UserMePublic)
    PATCH  /app/me            — Profil güncelle (full_name, locale, marketing)
    GET    /app/me/export     — KVKK md.11 veri taşınabilirlik (JSON export)
    DELETE /app/me            — KVKK md.11 silme talebi (soft delete + 30g)

KVKK uyumu:
    - Soft delete: users.deleted_at = NOW(), is_active=FALSE
    - Refresh tokens revoke (sessions.revoked_at = NOW())
    - admin_audit_log INSERT action='account_delete'
    - takedown_requests INSERT type='privacy_request' (KVKK md.11 dosyası)
    - 30 gün retention sonrası hard delete cron çalışır (placeholder)

Anti-patterns (HARD STOP):
    - Hard delete YASAK — sadece soft delete + audit
    - Email değiştirme YASAK (PATCH'te field yok)
    - Role/tier değiştirme YASAK (admin only)
    - Export'ta password_hash / token_hash YASAK (privacy)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, get_current_user

# S1B (#800): Generation + SavedGeneration tabloları DROP edildi. KVKK export
# + consent revoke artık chat (messages) üzerinden işler. UsageEvent korunur.
from app.models.conversation import Conversation, Message
from app.models.generation import UsageEvent
from app.models.job import AdminAuditLog

# #1016 (Pivot Faz 3b) — araştırma ilgi alanları (Faz 3 küme verisi salt-okuma)
from app.models.research_cluster import MessageCluster, ResearchCluster
from app.models.takedown import TakedownRequest
from app.models.user import Session, User

logger = logging.getLogger(__name__)
router = APIRouter()


# Cap export rows per category — privacy + payload size sanity
EXPORT_CONVERSATIONS_LIMIT = 100  # S1B (#800): chat-only — yeni primary
EXPORT_MESSAGES_PER_CONV_LIMIT = 50  # her sohbet max 50 mesaj (input + output)
EXPORT_USAGE_EVENTS_LIMIT = 100
EXPORT_SESSIONS_LIMIT = 50

# KVKK retention: 30 gün soft → hard delete penceresi
HARD_DELETE_RETENTION_DAYS = 30


# =============================================================================
# Pydantic schemas
# =============================================================================


class UserMePublic(BaseModel):
    """Kendi profili response'u — auth.UserPublic + KVKK timestamp + created_at."""

    id: str
    email: str
    full_name: str | None
    role: str
    tier: str
    locale: str
    email_verified: bool
    is_active: bool
    totp_enabled: bool
    kvkk_acknowledgment_at: datetime | None
    data_processing_consent_at: datetime | None
    foreign_transfer_consent_at: datetime | None
    marketing_consent_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class ProfileUpdateRequest(BaseModel):
    """PATCH /app/me — sadece self-service alanları.

    Email/role/tier YASAK — admin endpoint'inden geçer (#69).
    """

    full_name: str | None = Field(default=None, max_length=120)
    locale: str | None = Field(default=None, min_length=2, max_length=10)
    marketing_consent: bool | None = Field(
        default=None,
        description="True=onay ver (timestamp set), False=onay geri al (NULL).",
    )


class AccountDeleteRequest(BaseModel):
    """DELETE /app/me — confirmation kelimesi zorunlu.

    Şifre tekrar isteme bu endpoint'te ZORUNLU değil (auth zaten geçtiyse
    valid session var). Confirmation 'SIL' veya 'DELETE' olmalı.
    """

    confirmation: str = Field(
        min_length=1,
        max_length=20,
        description="'SIL' veya 'DELETE' — yanlış değer 422 döner.",
    )
    reason: str | None = Field(default=None, max_length=500)


class AccountDeleteResponse(BaseModel):
    """KVKK md.11 silme talebi onay response'u."""

    status: str = "soft_deleted"
    deletion_at: datetime
    """Soft delete timestamp (users.deleted_at)."""

    retention_until: datetime
    """30 gün sonra hard delete cron çalışacak (placeholder)."""

    ticket_id: str | None = None
    """takedown_requests TKD-YYYY-NNNNNN — KVKK dosya numarası."""

    sessions_revoked: int


class ExportSession(BaseModel):
    id: str
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class ExportMessage(BaseModel):
    """Bir mesaj — user veya assistant. S1B (#800) chat-only."""

    id: str
    role: str
    content: str
    sources_used: list[dict[str, Any]] | None
    followup_suggestions: list[str] | None = None  # #961
    edited_content: str | None
    user_action: str | None
    halu_flagged_at: datetime | None
    created_at: datetime


class ExportConversation(BaseModel):
    """Bir sohbet (conversation) + içindeki mesajlar."""

    id: str
    title: str
    summary: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    messages: list[ExportMessage]


class ExportUsageEvent(BaseModel):
    id: str
    event_type: str
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    metadata: dict[str, Any] | None
    created_at: datetime


class ExportResponse(BaseModel):
    """KVKK md.11 veri taşınabilirlik — full JSON export.

    NOT: password_hash, token_hash, totp_secret YASAK (privacy).

    S1B (#800): generations/saved_generations DROP edildi; export artık
    conversations + messages içerir (chat-only mimari).
    """

    user: UserMePublic
    conversations: list[ExportConversation]
    usage_events: list[ExportUsageEvent]
    sessions: list[ExportSession]
    exported_at: datetime
    note: str = (
        "Bu dosya KVKK md.11 (taşınabilirlik) kapsamında üretilmiştir. "
        "Şifreniz, refresh token'larınız ve 2FA secret'ınız güvenlik gereği "
        "dahil edilmemiştir."
    )


# =============================================================================
# Helpers
# =============================================================================


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    action: str,
    target_type: str,
    target_id: UUID,
    metadata: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """admin_audit_log insert — KVKK self-service'te de log tutuyoruz."""
    audit = AdminAuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        event_metadata=metadata or {},
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(audit)


def _to_public(user: User) -> UserMePublic:
    """User ORM → UserMePublic shape."""
    return UserMePublic(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tier=user.tier,
        locale=user.locale,
        email_verified=user.email_verified,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        kvkk_acknowledgment_at=user.kvkk_acknowledgment_at,
        data_processing_consent_at=user.data_processing_consent_at,
        foreign_transfer_consent_at=user.foreign_transfer_consent_at,
        marketing_consent_at=user.marketing_consent_at,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=UserMePublic,
    summary="Kendi profilim (KVKK md.11 erişim hakkı)",
)
async def get_me(
    user: Annotated[User, Depends(get_current_user)],
) -> UserMePublic:
    """Kullanıcının kendi profil bilgisini döner.

    KVKK md.11 (a, c bendi): kendi verisine erişim hakkı.
    """
    return _to_public(user)


@router.patch(
    "",
    response_model=UserMePublic,
    summary="Profil güncelle (full_name, locale, marketing_consent)",
)
async def patch_me(
    payload: ProfileUpdateRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserMePublic:
    """Kendi profilinde sadece izin verilen alanları günceller.

    Yasaklı:
        - email (auth flow'a tabi)
        - role / tier (admin endpoint'i — #69)
        - is_active / deleted_at (account delete endpoint'i)
        - kvkk/data_processing/foreign_transfer consent (registration zorunlu)

    İzinli:
        - full_name
        - locale
        - marketing_consent (timestamp set / NULL)
    """
    changed: dict[str, Any] = {}

    if payload.full_name is not None:
        cleaned = payload.full_name.strip() or None
        if cleaned != user.full_name:
            user.full_name = cleaned
            changed["full_name"] = cleaned

    if payload.locale is not None:
        cleaned_locale = payload.locale.strip()
        if cleaned_locale and cleaned_locale != user.locale:
            user.locale = cleaned_locale
            changed["locale"] = cleaned_locale

    if payload.marketing_consent is not None:
        now = datetime.now(UTC)
        if payload.marketing_consent and user.marketing_consent_at is None:
            user.marketing_consent_at = now
            changed["marketing_consent_at"] = now.isoformat()
        elif not payload.marketing_consent and user.marketing_consent_at is not None:
            user.marketing_consent_at = None
            changed["marketing_consent_at"] = None

    if changed:
        # Self-edit'i de audit'liyoruz — KVKK iz takibi için
        await _audit(
            db,
            actor_id=user.id,
            action="profile.self_update",
            target_type="user",
            target_id=user.id,
            metadata={"changed": changed},
            ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        await db.refresh(user)

    return _to_public(user)


@router.get(
    "/export",
    response_model=ExportResponse,
    summary="Veri export (KVKK md.11 taşınabilirlik)",
)
async def export_me(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExportResponse:
    """Tüm kullanıcı verisini JSON olarak döner.

    Kapsam (S1B #800 chat-only sonrası):
        - Kullanıcı profili (sensitive alanlar HARİÇ)
        - Son 100 conversation + her birinde son 50 mesaj (cap)
        - Son 100 usage_event
        - Aktif/eski oturum metadata (cap 50, token_hash YASAK)

    KVKK md.11 (e bendi): kişisel verilerin yapısal/yaygın bir formatta
    elde edilmesi ve başka bir veri sorumlusuna aktarılması.
    """
    # 1) Conversations (son 100) + her conv için mesajlar
    conv_rows = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
        .limit(EXPORT_CONVERSATIONS_LIMIT)
    )
    convs_orm = list(conv_rows.scalars().all())

    conversations: list[ExportConversation] = []
    total_messages = 0
    for c in convs_orm:
        msg_rows = await db.execute(
            select(Message)
            .where(Message.conversation_id == c.id)
            .order_by(Message.created_at.asc())
            .limit(EXPORT_MESSAGES_PER_CONV_LIMIT)
        )
        msgs = [
            ExportMessage(
                id=str(m.id),
                role=m.role,
                content=m.content or "",
                sources_used=list(m.sources_used) if m.sources_used else None,
                followup_suggestions=(
                    list(m.followup_suggestions) if m.followup_suggestions else None
                ),
                edited_content=m.edited_content,
                user_action=m.user_action,
                halu_flagged_at=m.halu_flagged_at,
                created_at=m.created_at,
            )
            for m in msg_rows.scalars().all()
        ]
        total_messages += len(msgs)
        conversations.append(
            ExportConversation(
                id=str(c.id),
                title=c.title,
                summary=c.summary,
                archived_at=c.archived_at,
                created_at=c.created_at,
                updated_at=c.updated_at,
                messages=msgs,
            )
        )

    # 2) Usage events (son 100)
    ue_rows = await db.execute(
        select(UsageEvent)
        .where(UsageEvent.user_id == user.id)
        .order_by(UsageEvent.created_at.desc())
        .limit(EXPORT_USAGE_EVENTS_LIMIT)
    )
    usage_events = [
        ExportUsageEvent(
            id=str(e.id),
            event_type=e.event_type,
            provider=e.provider,
            model=e.model,
            input_tokens=e.input_tokens,
            output_tokens=e.output_tokens,
            cost_usd=float(e.cost_usd) if e.cost_usd is not None else None,
            metadata=e.event_metadata,
            created_at=e.created_at,
        )
        for e in ue_rows.scalars().all()
    ]

    # 3) Sessions metadata — token_hash GÖNDERİLMEZ
    sess_rows = await db.execute(
        select(Session)
        .where(Session.user_id == user.id)
        .order_by(Session.created_at.desc())
        .limit(EXPORT_SESSIONS_LIMIT)
    )
    sessions = [
        ExportSession(
            id=str(s.id),
            user_agent=s.user_agent,
            ip_address=str(s.ip_address) if s.ip_address is not None else None,
            created_at=s.created_at,
            expires_at=s.expires_at,
            revoked_at=s.revoked_at,
        )
        for s in sess_rows.scalars().all()
    ]

    # 4) Audit log — export talebi loglanır
    await _audit(
        db,
        actor_id=user.id,
        action="data_export",
        target_type="user",
        target_id=user.id,
        metadata={
            "conversations_count": len(conversations),
            "messages_count": total_messages,
            "usage_events_count": len(usage_events),
            "sessions_count": len(sessions),
        },
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()

    return ExportResponse(
        user=_to_public(user),
        conversations=conversations,
        usage_events=usage_events,
        sessions=sessions,
        exported_at=datetime.now(UTC),
    )


@router.delete(
    "",
    response_model=AccountDeleteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Hesap sil (KVKK md.11 silme talebi)",
)
async def delete_me(
    payload: AccountDeleteRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountDeleteResponse:
    """KVKK md.11 silme talebi.

    Akış:
      1. Confirmation kelimesi doğrulama ('SIL' / 'DELETE')
      2. users.is_active = FALSE
      3. users.deleted_at = NOW()
      4. Tüm aktif sessions.revoked_at = NOW()
      5. takedown_requests INSERT (request_type='privacy_request') — KVKK dosyası
      6. admin_audit_log INSERT (action='account_delete')
      7. Hard delete cron 30 gün sonra çalışır (placeholder — #82)

    HARD STOP: Bu endpoint asla hard delete yapmaz. Yalnızca soft.
    """
    confirmation = payload.confirmation.strip().upper()
    if confirmation not in ("SIL", "DELETE"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "CONFIRMATION_REQUIRED",
                "title": "Hesap silme onayı için 'SIL' veya 'DELETE' yazın.",
            },
        )

    if user.deleted_at is not None:
        # Idempotent: tekrar deletion request gelirse önceki state'i döndür
        retention_until = user.deleted_at + timedelta(days=HARD_DELETE_RETENTION_DAYS)
        return AccountDeleteResponse(
            status="already_deleted",
            deletion_at=user.deleted_at,
            retention_until=retention_until,
            ticket_id=None,
            sessions_revoked=0,
        )

    now = datetime.now(UTC)
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent")

    # 1) Soft delete user
    user.is_active = False
    user.deleted_at = now

    # 2) Refresh token revocation
    revoke_stmt = (
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    revoke_result = await db.execute(revoke_stmt)
    sessions_revoked = revoke_result.rowcount or 0

    # 3) takedown_requests dosyası (KVKK md.11 evrak izi)
    description_parts = [
        f"Kullanıcı (id={user.id}, email={user.email}) KVKK md.11 kapsamında "
        f"hesap silme talebinde bulundu (self-service)."
    ]
    if payload.reason:
        description_parts.append(f"Gerekçe: {payload.reason}")
    description = " ".join(description_parts)

    # KVKK final yanıt 30 gün, triaj 24h
    sla_due = now + timedelta(hours=24)
    privacy_record = TakedownRequest(
        request_type="privacy_request",
        requester_email=user.email,
        requester_name=user.full_name,
        authority_claim="KVKK md.11 ilgili kişi (kendi hesabım)",
        description=description,
        evidence_urls=[],
        status="submitted",
        priority="critical",
        sla_due_at=sla_due,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(privacy_record)
    await db.flush()
    ticket_id = privacy_record.ticket_id

    # 4) Audit log
    await _audit(
        db,
        actor_id=user.id,
        action="account_delete",
        target_type="user",
        target_id=user.id,
        metadata={
            "self_service": True,
            "ticket_id": ticket_id,
            "sessions_revoked": sessions_revoked,
            "reason": payload.reason,
        },
        ip=ip,
        user_agent=ua,
    )

    await db.commit()

    retention_until = now + timedelta(days=HARD_DELETE_RETENTION_DAYS)

    logger.info(
        "account.soft_delete user=%s ticket=%s sessions_revoked=%d",
        user.id,
        ticket_id,
        sessions_revoked,
    )

    return AccountDeleteResponse(
        status="soft_deleted",
        deletion_at=now,
        retention_until=retention_until,
        ticket_id=ticket_id,
        sessions_revoked=sessions_revoked,
    )


# =============================================================================
# PMF Survey (#55) — Sean Ellis testi scaffold
# =============================================================================
# 30g aktif user'a "Nodrat olmasaydı nasıl hissederdin?" sorusu.
# Hedef: ≥%40 'very_disappointed' → PMF kanıtı.
#
# Settings flag: pmf_survey.enabled (default false). Default closed; admin
# açtığı zaman frontend popup user'a gösterilir.

PMF_RESPONSES = {
    "very_disappointed",
    "somewhat_disappointed",
    "not_disappointed",
    "already_left",
}
PMF_ELIGIBILITY_DAYS = 30


class PmfSubmitRequest(BaseModel):
    response: str = Field(..., description="4 değerden biri")
    comment: str | None = Field(default=None, max_length=500)


class PmfEligibilityResponse(BaseModel):
    eligible: bool
    reason: str
    """already_submitted | not_old_enough | enabled_off | eligible"""
    days_since_signup: int


@router.get(
    "/pmf-survey/eligibility",
    response_model=PmfEligibilityResponse,
    summary="PMF survey için eligibility check (#55)",
)
async def pmf_eligibility(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PmfEligibilityResponse:
    """User PMF survey doldurabilir mi kontrol et.

    Eligible olması için:
      - settings.pmf_survey.enabled = true
      - signup'tan 30g+ geçmiş
      - daha önce yanıt vermemiş
    """
    days_since = (datetime.now(UTC).date() - user.created_at.date()).days

    # Settings flag check
    try:
        from app.core.settings_store import settings_store

        enabled = await settings_store.get(db, "pmf_survey.enabled", default=False)
    except Exception:
        enabled = False

    if not enabled:
        return PmfEligibilityResponse(
            eligible=False, reason="enabled_off", days_since_signup=days_since
        )

    if days_since < PMF_ELIGIBILITY_DAYS:
        return PmfEligibilityResponse(
            eligible=False,
            reason="not_old_enough",
            days_since_signup=days_since,
        )

    # Daha önce yanıtladı mı (raw SQL — model henüz yok scaffold'da)
    from sqlalchemy import text as _t

    res = await db.execute(
        _t("SELECT 1 FROM pmf_survey_responses WHERE user_id = :uid LIMIT 1"),
        {"uid": user.id},
    )
    if res.scalar_one_or_none():
        return PmfEligibilityResponse(
            eligible=False,
            reason="already_submitted",
            days_since_signup=days_since,
        )

    return PmfEligibilityResponse(eligible=True, reason="eligible", days_since_signup=days_since)


@router.post(
    "/pmf-survey",
    status_code=status.HTTP_201_CREATED,
    summary="PMF survey response gönder (#55)",
)
async def pmf_submit(
    payload: PmfSubmitRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Sean Ellis test response kaydet. Tek seferlik (UNIQUE user_id)."""
    if payload.response not in PMF_RESPONSES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_RESPONSE",
                "title": "Geçersiz yanıt",
                "allowed": sorted(PMF_RESPONSES),
            },
        )

    from sqlalchemy import text as _t

    try:
        await db.execute(
            _t(
                "INSERT INTO pmf_survey_responses (user_id, response, comment) "
                "VALUES (:uid, :resp, :cmt)"
            ),
            {
                "uid": user.id,
                "resp": payload.response,
                "cmt": payload.comment,
            },
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        # UNIQUE constraint violation = already submitted
        if "duplicate key" in str(exc) or "unique" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ALREADY_SUBMITTED",
                    "title": "Zaten yanıt verildi",
                },
            ) from exc
        raise

    logger.info(
        "pmf survey response user=%s response=%s",
        user.id,
        payload.response,
    )
    return {"status": "submitted"}


# =============================================================================
# Model Improvement Consent (KVKK 5. checkbox, #564 + #566)
# =============================================================================
#
# KVKK md.5/2-a açık rıza — kullanıcının üretim verilerinin Nodrat'ın
# kendi yapay zeka modelinin (Trendyol-LLM-7B-chat-v4.1.0 base üzerine
# domain-spesifik fine-tune) eğitiminde kullanımı için ayrı izin.
#
# data_processing ve foreign_transfer onaylarından BAĞIMSIZDIR
# (KVKK md.5 amaca bağlılık prensibi).
#
# Bağlı: docs/legal/kvkk-aydinlatma.md §3 madde 7 + §13 5. checkbox,
#        wiki/decisions/own-slm-strategy.md, wiki/concepts/sft-data-pipeline.md


class ModelImprovementConsentGrantRequest(BaseModel):
    """POST /app/me/consent/model-improvement body."""

    text_version: str = Field(
        default="v0.3",
        max_length=16,
        description="Aydınlatma metin sürümü (TIA audit).",
    )
    text_hash: str | None = Field(
        default=None,
        max_length=64,
        description="Aydınlatma metni SHA-256 hash (immutable kanıt).",
    )


class ModelImprovementConsentStatus(BaseModel):
    """GET /app/me/consent/model-improvement response."""

    is_active: bool
    """granted_at IS NOT NULL AND revoked_at IS NULL"""

    granted_at: datetime | None
    revoked_at: datetime | None
    text_version: str | None


@router.get(
    "/consent/model-improvement",
    response_model=ModelImprovementConsentStatus,
    summary="Model improvement consent durumu",
)
async def get_consent_model_improvement(
    user: Annotated[User, Depends(get_current_user)],
) -> ModelImprovementConsentStatus:
    return ModelImprovementConsentStatus(
        is_active=(
            user.model_improvement_consent_at is not None
            and user.model_improvement_consent_revoked_at is None
        ),
        granted_at=user.model_improvement_consent_at,
        revoked_at=user.model_improvement_consent_revoked_at,
        text_version=user.model_improvement_consent_version,
    )


@router.post(
    "/consent/model-improvement",
    status_code=status.HTTP_200_OK,
    summary="Model improvement consent ver (KVKK md.5/2-a)",
)
async def grant_consent_model_improvement(
    payload: ModelImprovementConsentGrantRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Idempotent — aynı endpoint 2 kez çağrılırsa timestamp güncellenir
    ve revoked_at temizlenir (re-grant)."""
    now = datetime.now(UTC)
    user_agent = request.headers.get("user-agent")
    client_ip = get_client_ip(request)

    user.model_improvement_consent_at = now
    user.model_improvement_consent_revoked_at = None
    user.model_improvement_consent_version = payload.text_version
    user.model_improvement_consent_text_hash = payload.text_hash
    user.model_improvement_consent_ip = client_ip  # type: ignore[assignment]

    await _audit(
        db,
        actor_id=user.id,
        action="consent.model_improvement.grant",
        target_type="user",
        target_id=user.id,
        metadata={
            "text_version": payload.text_version,
            "has_text_hash": payload.text_hash is not None,
        },
        ip=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    return {
        "status": "granted",
        "granted_at": now.isoformat(),
        "text_version": payload.text_version,
    }


@router.delete(
    "/consent/model-improvement",
    status_code=status.HTTP_200_OK,
    summary="Model improvement consent geri çek (KVKK md.11)",
)
async def revoke_consent_model_improvement(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """KVKK md.11 — geri çekme.

    Etki:
      - users.model_improvement_consent_revoked_at = NOW()
      - generations.sft_eligible=false WHERE user_id=X AND sft_eligible=true
      - generations.sft_excluded_reason='consent_revoked'
      - training_samples cascade delete: #567 worker'da apply_async olarak
        tetiklenecek (bu endpoint sadece flag günceller).
    """
    if user.model_improvement_consent_at is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_CONSENT",
                "message": "Geri çekilecek bir model improvement consent yok.",
            },
        )

    now = datetime.now(UTC)
    user_agent = request.headers.get("user-agent")
    client_ip = get_client_ip(request)

    user.model_improvement_consent_revoked_at = now

    # S1B (#800): chat-only — messages.sft_eligible üzerinden çalış (user_id
    # FK yok; conversation üzerinden filtrele)
    affected = await db.execute(
        update(Message)
        .where(
            Message.conversation_id.in_(
                select(Conversation.id).where(Conversation.user_id == user.id)
            )
        )
        .where(Message.sft_eligible.is_(True))
        .values(sft_eligible=False, sft_excluded_reason="consent_revoked")
    )

    await _audit(
        db,
        actor_id=user.id,
        action="consent.model_improvement.revoke",
        target_type="user",
        target_id=user.id,
        metadata={
            "messages_affected": affected.rowcount,
        },
        ip=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    return {
        "status": "revoked",
        "revoked_at": now.isoformat(),
        "messages_affected": affected.rowcount,
    }


# =============================================================================
# #1016 (Pivot Faz 3b) — Araştırma ilgi alanları (GET /app/me/research-interests)
#
# Faz 3 (#1025) GLOBAL kümeleme verisinin SALT-OKUMA özeti — YENİ HESAPLAMA
# YOK. user-scoped: yalnız `MessageCluster.user_id == user.id` → başka
# kullanıcının içeriği sızmaz (küme paylaşımlı, içerik user-scoped).
# deprecated_at NULL → boş/soft-deprecate (S12) edilmiş küme hariç.
# Görünür "Hesabım > ilgi alanların" sayfası = AYRI UI SEANSI; bu sadece
# backend endpoint (UI seansı bunu tüketir). Additive; mevcut akış/cevap
# -üretim path'i DEĞİŞMEZ (chat'e dokunmaz → eval-golden etkilenmez).
# =============================================================================


class ResearchInterestItem(BaseModel):
    cluster_id: str
    canonical_name: str
    cluster_type: str
    item_count: int
    last_at: str | None = None
    parent_cluster_id: str | None = None


class ResearchInterestsResponse(BaseModel):
    interests: list[ResearchInterestItem]
    total: int


@router.get(
    "/research-interests",
    response_model=ResearchInterestsResponse,
    summary="Kullanıcının araştırma ilgi alanları (Faz 3b — salt-okuma)",
)
async def research_interests(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
) -> ResearchInterestsResponse:
    """Kullanıcının içeriğinin bulunduğu GLOBAL araştırma kümeleri +
    per-user ağırlık (kullanıcının o kümedeki sorgu sayısı, son
    aktivite). Faz 3 verisinden türetilir; ek LLM/hesaplama yok.
    """
    limit = max(1, min(limit, 200))
    q = (
        select(
            ResearchCluster.id,
            ResearchCluster.canonical_name,
            ResearchCluster.cluster_type,
            ResearchCluster.parent_cluster_id,
            func.count(MessageCluster.id).label("item_count"),
            func.max(MessageCluster.created_at).label("last_at"),
        )
        .join(MessageCluster, MessageCluster.cluster_id == ResearchCluster.id)
        .where(
            MessageCluster.user_id == user.id,
            ResearchCluster.deprecated_at.is_(None),
        )
        .group_by(
            ResearchCluster.id,
            ResearchCluster.canonical_name,
            ResearchCluster.cluster_type,
            ResearchCluster.parent_cluster_id,
        )
        .order_by(
            func.count(MessageCluster.id).desc(),
            func.max(MessageCluster.created_at).desc(),
        )
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    items = [
        ResearchInterestItem(
            cluster_id=str(r.id),
            canonical_name=r.canonical_name,
            cluster_type=r.cluster_type,
            item_count=int(r.item_count or 0),
            last_at=r.last_at.isoformat() if r.last_at else None,
            parent_cluster_id=(str(r.parent_cluster_id) if r.parent_cluster_id else None),
        )
        for r in rows
    ]
    return ResearchInterestsResponse(interests=items, total=len(items))


# =============================================================================
# #1018 (Pivot Faz 4) — Geçmiş-araştırma LİSTELEME servisi
# (GET /app/me/research-history)
#
# Kullanıcının KENDİ geçmiş araştırmalarını arar/listeler — **CEVAP
# ÜRETMEZ** (LLM/sentez YOK; asistan-tonu reversion engellenir).
# user-scoped: yalnız Conversation.user_id == user.id → cross-user yok.
# Opsiyonel `q` ile başlık/mesaj içinde metin araması. Görünür "araştırma
# geçmişi" UI = AYRI UI SEANSI; bu sadece backend liste servisi.
# Cevap-üretim path'i (chat) DEĞİŞMEZ → eval-golden etkilenmez.
# Plan rev.12 §4 Faz 4 + kullanıcı: "ayrı araç+hizmet, listele, cevaplama".
# =============================================================================


class ResearchHistoryItem(BaseModel):
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    snippet: str | None = None


class ResearchHistoryResponse(BaseModel):
    items: list[ResearchHistoryItem]
    total: int
    query: str | None = None


@router.get(
    "/research-history",
    response_model=ResearchHistoryResponse,
    summary="Geçmiş araştırma listeleme servisi (Faz 4 — cevap ÜRETMEZ)",
)
async def research_history(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = None,
    limit: int = 30,
) -> ResearchHistoryResponse:
    """Kullanıcının kendi geçmiş araştırmaları (conversation = bir
    araştırma birimi). LLM/sentez YOK — yapısal liste döner. `q`
    verilirse başlık VEYA mesaj içeriğinde ILIKE araması.
    """
    limit = max(1, min(limit, 100))
    base = select(Conversation).where(
        Conversation.user_id == user.id,
        Conversation.archived.is_(False),
    )
    qn = (q or "").strip()
    if qn:
        like = f"%{qn}%"
        base = base.where(
            or_(
                Conversation.title.ilike(like),
                exists().where(
                    (Message.conversation_id == Conversation.id) & (Message.content.ilike(like))
                ),
            )
        )
    base = base.order_by(Conversation.updated_at.desc()).limit(limit)
    convs = list((await db.execute(base)).scalars().all())

    items: list[ResearchHistoryItem] = []
    for c in convs:
        cnt = (
            await db.execute(select(func.count(Message.id)).where(Message.conversation_id == c.id))
        ).scalar_one()
        last_a = (
            await db.execute(
                select(Message.content)
                .where(
                    Message.conversation_id == c.id,
                    Message.role == "assistant",
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        items.append(
            ResearchHistoryItem(
                conversation_id=str(c.id),
                title=c.title,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
                message_count=int(cnt or 0),
                snippet=((last_a or "")[:200] or None),
            )
        )
    return ResearchHistoryResponse(items=items, total=len(items), query=(qn or None))
