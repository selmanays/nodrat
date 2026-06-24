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
from sqlalchemy import and_, bindparam, case, exists, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.job import AdminAuditLog
from app.modules.accounts.deps import (
    get_client_ip,
    get_current_user,
    require_foreign_transfer_consent,
)
from app.modules.accounts.models import Session, User
from app.modules.billing.models import UsageEvent

# S1B (#800): Generation + SavedGeneration tabloları DROP edildi. KVKK export
# + consent revoke artık research (messages) üzerinden işler. UsageEvent korunur.
from app.modules.conversations.models import Conversation, Message
from app.modules.generations.artifacts import REVISION_INTENTS, add_revision
from app.modules.generations.models import (
    Artifact,
    ArtifactCluster,
    ArtifactRevision,
    ResearchCluster,
    UserClusterSubscription,
)
from app.modules.generations.subscriptions import unsubscribe as unsubscribe_cluster_svc
from app.modules.legal.models import TakedownRequest
from app.modules.trends.cluster_link import (  # #1570 talep×arz, #1745 keşif
    rising_entities,
    trend_metrics_for_clusters,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Cap export rows per category — privacy + payload size sanity
EXPORT_CONVERSATIONS_LIMIT = 100  # S1B (#800): research-only — yeni primary
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
    """Bir mesaj — user veya assistant. S1B (#800) research-only."""

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
    conversations + messages içerir (research-only mimari).
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

    Kapsam (S1B #800 research-only sonrası):
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
        from app.shared.runtime_config.settings_store import settings_store

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

    # S1B (#800): research-only — messages.sft_eligible üzerinden çalış (user_id
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

    # KVKK m.11 "etkin geri çekme" (sft-data-pipeline §KVKK propagation, locked):
    # consent revoke → ZATEN curate edilmiş training_samples'ı SİL (message + artefakt
    # yolları; user_id global). Önceki kod yalnız sft_eligible flag'liyordu → revoke
    # öncesi curate edilmiş satırlar DB'de kalıyordu (boşluk). #567 worker hiç inşa
    # edilmemişti; inline DELETE (kullanıcı-tetikli, hacim küçük).
    purged = await db.execute(
        text("DELETE FROM training_samples WHERE user_id = :uid"), {"uid": user.id}
    )

    await _audit(
        db,
        actor_id=user.id,
        action="consent.model_improvement.revoke",
        target_type="user",
        target_id=user.id,
        metadata={
            "messages_affected": affected.rowcount,
            "training_samples_purged": purged.rowcount,
        },
        ip=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    return {
        "status": "revoked",
        "revoked_at": now.isoformat(),
        "messages_affected": affected.rowcount,
        "training_samples_purged": purged.rowcount,
    }


# =============================================================================
# Faz 2b (küme-merkezli abonelik) — AÇIK abonelikler.
# GET /app/me/clusters + POST /app/me/clusters/{id}/unsubscribe. Explicit-abonelik
# yüzeyi (frontend Faz 4 bunu tüketir). user-scoped; salt-okuma + soft-unsubscribe.
# (#1671/#1681 — eski message_clusters-türevi /research-interests endpoint'i
#  İlgi Alanları→Kümeler birleştirmesiyle kaldırıldı; bu yüzey onun yerine geçti.)
# =============================================================================


class SubscribedClusterItem(BaseModel):
    cluster_id: str
    canonical_name: str
    cluster_type: str
    subscribed_at: str
    source: str
    parent_cluster_id: str | None = None
    trend_state: str | None = None  # breaking|developing|stable|fading|quiet
    relative_momentum: float | None = None
    article_count_window: int | None = None
    spark: list[int] = []  # son 24s bucket-başına haber hacmi (sparkline; canlı)


class MyClustersResponse(BaseModel):
    clusters: list[SubscribedClusterItem]
    total: int


@router.get(
    "/clusters",
    response_model=MyClustersResponse,
    summary="Abone olunan kümeler + canlı trend (Faz 2b)",
)
async def my_clusters(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 100,
) -> MyClustersResponse:
    """Kullanıcının AÇIK abone olduğu (canlı) kümeler + per-küme trend durumu.
    Salt-okuma; ek LLM/hesaplama yok. trends.enabled OFF → trend alanları null.
    """
    limit = max(1, min(limit, 200))
    q = (
        select(
            ResearchCluster.id,
            ResearchCluster.cluster_key,
            ResearchCluster.canonical_name,
            ResearchCluster.cluster_type,
            ResearchCluster.parent_cluster_id,
            UserClusterSubscription.subscribed_at,
            UserClusterSubscription.source,
        )
        .join(
            UserClusterSubscription,
            UserClusterSubscription.cluster_id == ResearchCluster.id,
        )
        .where(
            UserClusterSubscription.user_id == user.id,
            UserClusterSubscription.unsubscribed_at.is_(None),
            ResearchCluster.deprecated_at.is_(None),
        )
        .order_by(UserClusterSubscription.subscribed_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    items = [
        SubscribedClusterItem(
            cluster_id=str(r.id),
            canonical_name=r.canonical_name,
            cluster_type=r.cluster_type,
            subscribed_at=r.subscribed_at.isoformat(),
            source=r.source,
            parent_cluster_id=(str(r.parent_cluster_id) if r.parent_cluster_id else None),
        )
        for r in rows
    ]

    from app.shared.runtime_config.settings_store import settings_store

    if items and await settings_store.get_bool(db, "trends.enabled", False):
        keys = [r.cluster_key for r in rows]
        metrics = await trend_metrics_for_clusters(
            db, keys, window_seconds=86_400, now=datetime.now(UTC)
        )
        for item, ckey in zip(items, keys, strict=True):
            m = metrics.get(ckey)
            if m is not None:
                item.trend_state = m.trend_state
                item.relative_momentum = m.relative_momentum
                item.article_count_window = m.article_count
                item.spark = list(m.spark)
            else:
                item.trend_state = "quiet"
                item.article_count_window = 0

    return MyClustersResponse(clusters=items, total=len(items))


# =============================================================================
# Faz 4 — proaktif KEŞİF radarı (#1745): kullanıcının abone OLMADIĞI yükselenler.
# rising_entities() motoru (admin boşluk-radarıyla ortak) reuse; abone kümeler
# dışlanır. Salt-okuma; trends.enabled OFF → boş. cluster_id varsa abone olunabilir,
# yoksa (küme henüz mintlenmemiş) kart "ara" aksiyonuyla sorgu başlatır.
# =============================================================================

_DISCOVER_WINDOW = {"6h": 21_600, "24h": 86_400, "7d": 604_800}


class DiscoverRisingItem(BaseModel):
    cluster_key: str
    entity_name: str
    entity_type: str
    trend_state: str
    relative_momentum: float | None = None
    article_count: int
    cluster_id: str | None = None  # küme mintlenmişse abone olunabilir; yoksa "ara"


class DiscoverRisingResponse(BaseModel):
    data: list[DiscoverRisingItem]
    generated_at: str


@router.get(
    "/discover/rising",
    response_model=DiscoverRisingResponse,
    summary="Keşif radarı — takip etmediğin yükselen konular (#1745)",
)
async def discover_rising(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    window: str = "24h",
    limit: int = 15,
) -> DiscoverRisingResponse:
    """Kullanıcının ABONE OLMADIĞI yükselen (breaking/developing) konular. rising_entities()
    reuse; abone cluster_key'leri dışlanır. trends.enabled OFF → boş (no-op)."""
    from app.shared.runtime_config.settings_store import settings_store

    now = datetime.now(UTC)
    if not await settings_store.get_bool(db, "trends.enabled", False):
        return DiscoverRisingResponse(data=[], generated_at=now.isoformat())

    limit = max(1, min(limit, 50))
    wsec = _DISCOVER_WINDOW.get(window, 86_400)
    # Abone-dışlama sonrası limit'i doldurmak için fazladan çek.
    rising = await rising_entities(db, window_seconds=wsec, now=now, limit=limit + 30)

    sub_keys = set(
        (
            await db.execute(
                select(ResearchCluster.cluster_key)
                .join(
                    UserClusterSubscription,
                    UserClusterSubscription.cluster_id == ResearchCluster.id,
                )
                .where(
                    UserClusterSubscription.user_id == user.id,
                    UserClusterSubscription.unsubscribed_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    fresh = [r for r in rising if r.cluster_key not in sub_keys][:limit]

    # Mevcut (mintlenmiş) küme cluster_id'si → "abone ol" aksiyonu için (yoksa "ara").
    id_map: dict[str, str] = {}
    keys = [r.cluster_key for r in fresh]
    if keys:
        id_map = {
            k: str(cid)
            for k, cid in (
                await db.execute(
                    select(ResearchCluster.cluster_key, ResearchCluster.id).where(
                        ResearchCluster.cluster_key.in_(keys),
                        ResearchCluster.deprecated_at.is_(None),
                    )
                )
            ).all()
        }

    data = [
        DiscoverRisingItem(
            cluster_key=r.cluster_key,
            entity_name=r.entity_name,
            entity_type=r.entity_type,
            trend_state=r.trend_state,
            relative_momentum=r.relative_momentum,
            article_count=r.article_count,
            cluster_id=id_map.get(r.cluster_key),
        )
        for r in fresh
    ]
    return DiscoverRisingResponse(data=data, generated_at=now.isoformat())


@router.post(
    "/clusters/{cluster_id}/unsubscribe",
    summary="Kümeden çık (soft; opt-out kalıcı) — Faz 2b",
)
async def unsubscribe_my_cluster(
    cluster_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    """Kullanıcıyı kümeden çıkar (soft-delete; satır korunur → tekrar sorgu
    otomatik yeniden abone YAPMAZ). Canlı abonelik yoksa no-op."""
    changed = await unsubscribe_cluster_svc(db, user.id, cluster_id)
    await db.commit()
    return {"unsubscribed": changed}


# =============================================================================
# Faz 3b (küme-merkezli abonelik) — artefakt geçmişi + revizyon.
# GET /app/me/clusters/{id}/artifacts (kümenin geçmiş üretimleri) +
# GET /app/me/artifacts/{id} (revizyon zinciri) + POST .../revise (yeni revizyon).
# user-scoped; LLM quick-action'lar (3b-2) add_revision'ı içerik üreterek çağırır.
# =============================================================================


class ArtifactListItem(BaseModel):
    artifact_id: str
    artifact_type: str
    created_at: str
    revision_count: int
    head_preview: str | None = None
    # Bu artefaktı üreten araştırma sorusu (initial revizyon effective_query) —
    # küme detayında "hangi soru bu kartı üretti" görünür (founder talebi #1699).
    question: str | None = None
    # #1762 — bu kümede artefaktın rolü: 'primary' (cevabın baskın öznesi) |
    # 'secondary' (cevapta adı geçen, başka bir kümeye birincil olan). Legacy
    # artefakt (junction satırı yok) → 'primary' (artifacts.cluster_id eşleşmesi).
    role: str = "primary"


class ClusterArtifactsResponse(BaseModel):
    cluster_id: str
    artifacts: list[ArtifactListItem]
    total: int


class RevisionItem(BaseModel):
    revision_seq: int
    revision_intent: str
    content: str
    created_at: str
    accepted_at: str | None = None


class ArtifactDetailResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    cluster_id: str
    head_revision_seq: int | None = None
    # Bu artefaktı üreten araştırma sorusu (initial revizyon effective_query) —
    # canvas'ta "Soru: …" olarak görünür (founder talebi #1699).
    question: str | None = None
    revisions: list[RevisionItem]


class ReviseBody(BaseModel):
    content: str
    intent: str = "edit"


class QuickActionBody(BaseModel):
    """Faz 3b-2 — LLM quick-action revizyonu. content YOK (LLM üretir)."""

    intent: str  # quick_shorter | quick_rewrite | quick_longer | multi_share


@router.get(
    "/clusters/{cluster_id}/artifacts",
    response_model=ClusterArtifactsResponse,
    summary="Kümenin (kullanıcıya ait) geçmiş üretimleri (Faz 3b)",
)
async def cluster_artifacts(
    cluster_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
) -> ClusterArtifactsResponse:
    """Kullanıcının bu kümedeki artefaktları (en güncel revizyon önizlemesi +
    revizyon sayısı). user-scoped; salt-okuma."""
    limit = max(1, min(limit, 200))
    rev_count = (
        select(func.count(ArtifactRevision.id))
        .where(ArtifactRevision.artifact_id == Artifact.id)
        .correlate(Artifact)
        .scalar_subquery()
    )
    # Üreten soru = initial revizyon (seq=1) effective_query (#1699).
    init_question = (
        select(ArtifactRevision.effective_query)
        .where(
            ArtifactRevision.artifact_id == Artifact.id,
            ArtifactRevision.revision_seq == 1,
        )
        .correlate(Artifact)
        .scalar_subquery()
    )
    # #1762 — çoklu-küme üyeliği: artefakt bu kümeye birincil (artifacts.cluster_id)
    # VEYA ikincil (artifact_clusters junction) olarak bağlı olabilir. role: birincil
    # küme → 'primary'; junction'dan gelen → ac.role ('secondary'). Legacy (junction
    # satırı yok) → cluster_id eşleşmesiyle 'primary'. UNIQUE(artifact_id,cluster_id)
    # → fan-out yok. Flag OFF iken junction boş → bugünkü sonuç birebir.
    role_expr = case(
        (Artifact.cluster_id == cluster_id, "primary"),
        else_=func.coalesce(ArtifactCluster.role, "secondary"),
    ).label("role")
    q = (
        select(
            Artifact.id,
            Artifact.artifact_type,
            Artifact.created_at,
            ArtifactRevision.content.label("head_content"),
            rev_count.label("revision_count"),
            init_question.label("question"),
            role_expr,
        )
        .outerjoin(ArtifactRevision, ArtifactRevision.id == Artifact.head_revision_id)
        .outerjoin(
            ArtifactCluster,
            and_(
                ArtifactCluster.artifact_id == Artifact.id,
                ArtifactCluster.cluster_id == cluster_id,
            ),
        )
        .where(
            Artifact.user_id == user.id,
            or_(Artifact.cluster_id == cluster_id, ArtifactCluster.id.isnot(None)),
        )
        .order_by(Artifact.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    items = [
        ArtifactListItem(
            artifact_id=str(r.id),
            artifact_type=r.artifact_type,
            created_at=r.created_at.isoformat(),
            revision_count=int(r.revision_count or 0),
            head_preview=(r.head_content[:280] if r.head_content else None),
            question=r.question,
            role=r.role or "primary",
        )
        for r in rows
    ]
    return ClusterArtifactsResponse(cluster_id=str(cluster_id), artifacts=items, total=len(items))


@router.get(
    "/artifacts/{artifact_id}",
    response_model=ArtifactDetailResponse,
    summary="Artefakt + revizyon zinciri (Faz 3b)",
)
async def artifact_detail(
    artifact_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArtifactDetailResponse:
    art = (
        await db.execute(
            select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user.id)
        )
    ).scalar_one_or_none()
    if art is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact_not_found")
    revs = (
        (
            await db.execute(
                select(ArtifactRevision)
                .where(ArtifactRevision.artifact_id == artifact_id)
                .order_by(ArtifactRevision.revision_seq)
            )
        )
        .scalars()
        .all()
    )
    head_seq = next((rv.revision_seq for rv in revs if rv.id == art.head_revision_id), None)
    # Üreten soru = initial revizyon (seq=1) effective_query (#1699).
    question = next((rv.effective_query for rv in revs if rv.revision_seq == 1), None)
    return ArtifactDetailResponse(
        artifact_id=str(art.id),
        artifact_type=art.artifact_type,
        cluster_id=str(art.cluster_id),
        head_revision_seq=head_seq,
        question=question,
        revisions=[
            RevisionItem(
                revision_seq=rv.revision_seq,
                revision_intent=rv.revision_intent,
                content=rv.content,
                created_at=rv.created_at.isoformat(),
                accepted_at=rv.accepted_at.isoformat() if rv.accepted_at else None,
            )
            for rv in revs
        ],
    )


@router.post(
    "/artifacts/{artifact_id}/revise",
    summary="Artefaktı revize et — yeni revizyon (Faz 3b; direkt-edit/serbest-metin)",
)
async def revise_artifact(
    artifact_id: UUID,
    body: ReviseBody,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Yeni revizyon ekle (canvas direkt-edit / serbest-metin içeriği). LLM
    quick-action üretimi Faz 3b-2. Ownership: artefakt kullanıcıya ait olmalı."""
    content = (body.content or "").strip()
    if not content or len(content) > 10000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_content"
        )
    art = (
        await db.execute(
            select(Artifact.id).where(Artifact.id == artifact_id, Artifact.user_id == user.id)
        )
    ).scalar_one_or_none()
    if art is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact_not_found")
    intent = body.intent if body.intent in REVISION_INTENTS else "freetext"
    new_seq = await add_revision(
        db, artifact_id=artifact_id, content=content, revision_intent=intent
    )
    await db.commit()
    return {"revision_seq": new_seq}


@router.post(
    "/artifacts/{artifact_id}/quick-action",
    summary="Artefakt LLM quick-action revizyonu — Faz 3b-2 (kısalt/yeniden-yaz/uzat/thread)",
)
async def artifact_quick_action(
    artifact_id: UUID,
    body: QuickActionBody,
    # KVKK m.9: yurt-dışı LLM çağrısı → server-side açık rıza ZORUNLU (#470,
    # avukat şartı). require_foreign_transfer_consent get_current_user'ı sarar.
    user: Annotated[User, Depends(require_foreign_transfer_consent)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    """Mevcut head içeriğini intent'e göre LLM ile revize et → yeni revizyon.

    Flag-gated (`artifacts.revisions.llm.enabled`, default False). Yalnız LLM
    quick-action intent'leri (quick_shorter/quick_rewrite/quick_longer/
    multi_share); canvas direkt-edit/freetext = ayrı endpoint (revise, 3b-1).

    Sıra önemli (artifacts.py FOR UPDATE lock notu): head içeriği LOCK'SUZ okunur
    → LLM üretilir (yavaş) → SONRA add_revision (kısa lock). Lock LLM latency'si
    boyunca tutulmaz. Ownership: artefakt kullanıcıya ait olmalı."""
    from app.modules.generations.artifact_quick_actions import (
        generate_quick_action_revision,
    )
    from app.prompts.artifact_revision import LLM_QUICK_INTENTS
    from app.shared.runtime_config.settings_store import settings_store

    if body.intent not in LLM_QUICK_INTENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_quick_action_intent"
        )
    if not await settings_store.get_bool(db, "artifacts.revisions.llm.enabled", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="llm_revisions_disabled")

    # Ownership + head içeriği (lock'suz; LLM yavaş → lock'u add_revision'a sakla).
    head = (
        await db.execute(
            select(ArtifactRevision.content, ArtifactRevision.sources_used)
            .join(Artifact, Artifact.head_revision_id == ArtifactRevision.id)
            .where(Artifact.id == artifact_id, Artifact.user_id == user.id)
        )
    ).first()
    if head is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact_not_found")

    try:
        revised = await generate_quick_action_revision(
            db,
            head_content=head.content,
            sources_used=head.sources_used,
            intent=body.intent,
            user_id=user.id,
        )
    except Exception as exc:
        logger.warning("artifact quick-action LLM failed (artifact=%s): %s", artifact_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="revision_generation_failed"
        ) from exc

    revised = (revised or "").strip()
    if not revised:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="revision_empty")
    revised = revised[:10000]  # direct-edit guard (1298) ile tutarlı içerik tavanı

    # sources_used'ı yeni revizyona TAŞI — revizyon yeni kaynak üretmez (retrieval
    # yok), head'in kaynak listesi olduğu gibi devralınır. Aksi halde zincirlenen
    # quick-action'larda provenance NULL'a düşer (Faz 1b DPO curator için önemli).
    # Eşzamanlılık notu: add_revision FOR UPDATE ile seq'i serialize eder (crash-safe),
    # ancak parent her zaman GÜNCEL head'e bağlanır — iki eşzamanlı quick-action'da
    # B'nin parent'ı A'nın revizyonu olur (lineer zincir; tek-kullanıcı akışında risk yok).
    new_seq = await add_revision(
        db,
        artifact_id=artifact_id,
        content=revised,
        revision_intent=body.intent,
        sources_used=head.sources_used,
    )
    await db.commit()
    return {"revision_seq": new_seq, "content": revised}


# =============================================================================
# #1018 (Pivot Faz 4) — Geçmiş-araştırma LİSTELEME servisi
# (GET /app/me/research-history)
#
# Kullanıcının KENDİ geçmiş araştırmalarını arar/listeler — **CEVAP
# ÜRETMEZ** (LLM/sentez YOK; asistan-tonu reversion engellenir).
# user-scoped: yalnız Conversation.user_id == user.id → cross-user yok.
# Opsiyonel `q` ile başlık/mesaj içinde metin araması. Görünür "araştırma
# geçmişi" UI = AYRI UI SEANSI; bu sadece backend liste servisi.
# Cevap-üretim path'i (research) DEĞİŞMEZ → eval-golden etkilenmez.
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


# =============================================================================
# #1581 (C) — Trend-alert bildirimleri (GET/POST /app/me/notifications)
# =============================================================================
#
# user_notifications (raw-SQL-only) — user-scoped (yalnız user_id == user.id).
# Beat detect_trend_alerts yazar (kullanıcının breaking ilgi kümeleri). Salt
# kullanıcının kendi bildirimleri; cross-user yok. Per-user opt-out v2.


class NotificationItem(BaseModel):
    id: str
    type: str
    cluster_key: str | None = None
    title: str
    trend_state: str | None = None
    article_count: int | None = None
    created_at: str
    read: bool


class NotificationsResponse(BaseModel):
    notifications: list[NotificationItem]
    unread_count: int


class MarkReadBody(BaseModel):
    ids: list[str] | None = None  # None/boş → tümünü okundu işaretle


@router.get(
    "/notifications",
    response_model=NotificationsResponse,
    summary="Kullanıcının bildirimleri (#1581 C — trend-alert, salt kendi)",
)
async def my_notifications(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 30,
    unread_only: bool = False,
) -> NotificationsResponse:
    """Kullanıcının kendi bildirimleri (en yeni önce) + okunmamış sayısı.
    user-scoped (`user_id == user.id`); başka kullanıcının bildirimi DÖNMEZ."""
    limit = max(1, min(limit, 100))
    where = "WHERE user_id = :uid" + (" AND read_at IS NULL" if unread_only else "")
    rows = (
        await db.execute(
            text(
                f"""
                SELECT id::text AS id, type, cluster_key, title, trend_state,
                       article_count, created_at, read_at
                FROM user_notifications {where}
                ORDER BY created_at DESC LIMIT :lim
                """  # noqa: S608 — `where` sabit string (kullanıcı girdisi değil); değerler bind
            ),
            {"uid": user.id, "lim": limit},
        )
    ).all()
    notifications = [
        NotificationItem(
            id=r.id,
            type=r.type,
            cluster_key=r.cluster_key,
            title=r.title,
            trend_state=r.trend_state,
            article_count=r.article_count,
            created_at=r.created_at.isoformat() if r.created_at else "",
            read=r.read_at is not None,
        )
        for r in rows
    ]
    unread = (
        await db.execute(
            text(
                "SELECT count(*) FROM user_notifications WHERE user_id = :uid AND read_at IS NULL"
            ),
            {"uid": user.id},
        )
    ).scalar()
    return NotificationsResponse(notifications=notifications, unread_count=int(unread or 0))


@router.post(
    "/notifications/read",
    summary="Bildirimleri okundu işaretle (#1581 C — salt kendi)",
)
async def mark_notifications_read(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: MarkReadBody,
) -> dict:
    """Verilen id'leri (yoksa tümünü) okundu işaretler. user-scoped."""
    if body.ids:
        stmt = text(
            "UPDATE user_notifications SET read_at = now() "
            "WHERE user_id = :uid AND read_at IS NULL AND id::text IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        await db.execute(stmt, {"uid": user.id, "ids": body.ids})
    else:
        await db.execute(
            text(
                "UPDATE user_notifications SET read_at = now() "
                "WHERE user_id = :uid AND read_at IS NULL"
            ),
            {"uid": user.id},
        )
    await db.commit()
    unread = (
        await db.execute(
            text(
                "SELECT count(*) FROM user_notifications WHERE user_id = :uid AND read_at IS NULL"
            ),
            {"uid": user.id},
        )
    ).scalar()
    return {"unread_count": int(unread or 0)}
