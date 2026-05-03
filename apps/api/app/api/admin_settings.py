"""Admin runtime settings endpoint'leri (#262/#265 Epic, MVP-1.2).

docs/engineering/api-contracts.md (admin/settings)
docs/engineering/data-model.md (app_settings tablosu)

Endpoints:
    GET    /admin/settings                  — Tüm settings (default + override)
    GET    /admin/settings/{key}            — Tek setting detay
    PUT    /admin/settings/{key}            — Değer güncelle
    DELETE /admin/settings/{key}            — Default'a dön

Default registry: SETTING_REGISTRY (kod tarafında tanımlı).
Override değerler: app_settings tablosu (DB).

require_admin tüm endpoint'lerde. Her değişiklik admin_audit_log'a yazılır.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.core.settings_store import settings_store
from app.models.job import AdminAuditLog
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# SETTING_REGISTRY — known settings (default değerler + meta)
# =============================================================================
# Yeni setting eklenirken:
#  1) Buraya ekle (default + meta)
#  2) İlgili kodda settings_store.get(...) ile çek
#  3) Migration script gerekirse seed yap


SETTING_REGISTRY: dict[str, dict[str, Any]] = {
    # ---- RAG / Reranker ------------------------------------------------
    "rerank.enabled": {
        "default": True,
        "type": "bool",
        "group": "rag",
        "description": (
            "Cross-encoder reranker aktif mi. False → RRF sırası kullanılır "
            "(acil rollback)."
        ),
        "requires_restart": False,
    },
    "rerank.candidate_pool": {
        "default": 50,
        "type": "int",
        "group": "rag",
        "description": "Reranker'a gönderilen aday sayısı (RRF top-N).",
        "min_value": 10,
        "max_value": 200,
        "requires_restart": False,
    },
    "rerank.min_combined_score": {
        "default": 0.15,
        "type": "float",
        "group": "rag",
        "description": (
            "combined_score < eşik → kart drop. 0.10 permisif, 0.20 sıkı, "
            "0.30 agresif. (#251/#253/#259)"
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "rerank.min_query_words": {
        "default": 3,
        "type": "int",
        "group": "rag",
        "description": (
            "Bu kelime sayısının altındaki query'lerde rerank bypass "
            "(NIM cross-encoder kısa query'lerde başarısız). #253"
        ),
        "min_value": 1,
        "max_value": 10,
        "requires_restart": False,
    },
    # ---- Retrieval / Hybrid search -------------------------------------
    "retrieval.min_semantic_score": {
        "default": 0.55,
        "type": "float",
        "group": "retrieval",
        "description": (
            "Cosine sim < eşik → query ile alakasız demek (dense filter). "
            "0.45 permisif, 0.55 varsayılan, 0.65 sıkı."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "retrieval.min_text_score": {
        "default": 0.15,
        "type": "float",
        "group": "retrieval",
        "description": (
            "Trigram similarity eşiği (sparse layer). Title+summary trigram "
            "match'i bu eşiğin altıysa sparse adayda yer almaz."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "retrieval.candidate_pool": {
        "default": 30,
        "type": "int",
        "group": "retrieval",
        "description": "Hybrid search her layer'dan çekilen aday sayısı (RRF input).",
        "min_value": 10,
        "max_value": 200,
        "requires_restart": False,
    },
    # ---- Clustering ----------------------------------------------------
    "clustering.semantic_threshold": {
        "default": 0.85,
        "type": "float",
        "group": "clustering",
        "description": (
            "Cosine sim eşiği — yeni article'ı mevcut cluster'a ekleme "
            "kararı (#247: 0.78 → 0.85, farklı maçlar karışmasın)."
        ),
        "min_value": 0.5,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "clustering.title_trigram_threshold": {
        "default": 0.40,
        "type": "float",
        "group": "clustering",
        "description": (
            "pg_trgm.similarity eşiği — semantic match'e ek title benzerlik "
            "şartı (#247: 0.30 → 0.40)."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "clustering.window_hours": {
        "default": 72,
        "type": "int",
        "group": "clustering",
        "description": (
            "Aktif cluster matching penceresi (saat). Bu süre içinde "
            "last_seen olan cluster'lar arasında match aranır."
        ),
        "min_value": 6,
        "max_value": 168,
        "requires_restart": False,
    },
    # ---- Quota ---------------------------------------------------------
    "quota.window_seconds": {
        "default": 86400,
        "type": "int",
        "group": "quota",
        "description": "Sliding window süresi (saniye). 86400=24h varsayılan.",
        "min_value": 3600,
        "max_value": 604800,
        "requires_restart": False,
    },
    "quota.tier_trial": {
        "default": 10,
        "type": "int",
        "group": "quota",
        "description": "Trial kullanıcısı 24h limiti (kayıtsız anonim).",
        "min_value": 0,
        "max_value": 1000,
        "requires_restart": False,
    },
    "quota.tier_free": {
        "default": 5,
        "type": "int",
        "group": "quota",
        "description": "Free tier 24h limiti.",
        "min_value": 0,
        "max_value": 1000,
        "requires_restart": False,
    },
    "quota.tier_starter": {
        "default": 30,
        "type": "int",
        "group": "quota",
        "description": "Starter tier 24h limiti.",
        "min_value": 0,
        "max_value": 5000,
        "requires_restart": False,
    },
    "quota.tier_pro": {
        "default": 150,
        "type": "int",
        "group": "quota",
        "description": "Pro tier 24h limiti.",
        "min_value": 0,
        "max_value": 10000,
        "requires_restart": False,
    },
    "quota.tier_agency_seat": {
        "default": 500,
        "type": "int",
        "group": "quota",
        "description": "Agency seat tier 24h limiti.",
        "min_value": 0,
        "max_value": 50000,
        "requires_restart": False,
    },
    # ---- Scraping ------------------------------------------------------
    "scraping.fetch_timeout": {
        "default": 15.0,
        "type": "float",
        "group": "scraping",
        "description": (
            "RSS feed + listing fetch timeout (saniye). Büyük feed'ler için "
            "20+ tavsiye (Anadolu Ajansı gibi)."
        ),
        "min_value": 5.0,
        "max_value": 120.0,
        "requires_restart": False,
    },
    "scraping.article_detail_timeout": {
        "default": 20.0,
        "type": "float",
        "group": "scraping",
        "description": "Article detail fetch timeout. AA için 30+ önerilir (#250).",
        "min_value": 5.0,
        "max_value": 120.0,
        "requires_restart": False,
    },
    "scraping.max_attempts": {
        "default": 3,
        "type": "int",
        "group": "scraping",
        "description": "Crawler job retry limiti (DLQ'ya gitmeden önce).",
        "min_value": 1,
        "max_value": 10,
        "requires_restart": False,
    },
    # ---- LLM -----------------------------------------------------------
    "llm.deepseek_chat_model": {
        "default": "deepseek-chat",
        "type": "string",
        "group": "llm",
        "description": (
            "DeepSeek chat model adı. Alternatifler: deepseek-reasoner (R1), "
            "deepseek-coder."
        ),
        "requires_restart": True,
    },
    "llm.nim_rerank_model": {
        "default": "nvidia/rerank-qa-mistral-4b",
        "type": "string",
        "group": "llm",
        "description": (
            "NIM rerank model adı. MVP-1.5'te BGE-reranker-v2-m3'e geçilecek."
        ),
        "requires_restart": True,
    },
    "llm.deepseek_campaign_discount": {
        "default": 0.25,
        "type": "float",
        "group": "llm",
        "description": (
            "DeepSeek kampanya indirim multiplier'ı (input/output cost × bu). "
            "Kampanya bitince 1.0'a çek (31 May 2026)."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "llm.content_temperature": {
        "default": 0.5,
        "type": "float",
        "group": "llm",
        "description": (
            "Content generator chat temperature. Yüksek=yaratıcı, düşük=tutarlı."
        ),
        "min_value": 0.0,
        "max_value": 2.0,
        "requires_restart": False,
    },
}


# =============================================================================
# Pydantic schemas
# =============================================================================


class SettingDTO(BaseModel):
    """Admin GET response item."""

    key: str
    value: Any
    default: Any
    type: str
    group: str
    description: str | None
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list | None = None
    requires_restart: bool
    is_overridden: bool
    updated_at: str | None = None
    updated_by: str | None = None


class SettingListResponse(BaseModel):
    data: list[SettingDTO]
    groups: list[str]


class SettingUpdate(BaseModel):
    value: Any = Field(..., description="Yeni değer (type'a uygun)")


# =============================================================================
# Helpers
# =============================================================================


def _coerce_value(value: Any, type_: str) -> Any:
    """Cast incoming JSON value to declared type."""
    try:
        if type_ == "int":
            return int(value)
        if type_ == "float":
            return float(value)
        if type_ == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        if type_ == "string":
            return str(value)
        return value  # json
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_TYPE",
                "title": "Geçersiz tip",
                "message": f"'{value}' değeri {type_} tipine cast edilemedi: {exc}",
            },
        )


def _validate_range(
    value: Any, *, min_v: float | None, max_v: float | None
) -> None:
    if min_v is not None and isinstance(value, (int, float)):
        if value < min_v:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "OUT_OF_RANGE",
                    "title": "Aralık dışı",
                    "message": f"Minimum {min_v} olmalı",
                },
            )
    if max_v is not None and isinstance(value, (int, float)):
        if value > max_v:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "OUT_OF_RANGE",
                    "title": "Aralık dışı",
                    "message": f"Maksimum {max_v} olmalı",
                },
            )


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    ip: str | None,
    action: str,
    key: str,
    old_value: Any,
    new_value: Any,
) -> None:
    db.add(
        AdminAuditLog(
            actor_id=actor_id,
            action=action,
            target_type="app_setting",
            target_id=None,
            ip_address=ip,
            event_metadata={
                "key": key,
                "old_value": old_value,
                "new_value": new_value,
            },
        )
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=SettingListResponse,
    summary="Tüm runtime settings (default + override)",
)
async def list_settings(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    group: str | None = None,
) -> SettingListResponse:
    overrides = await settings_store.list(db, group=group)
    overrides_by_key = {o.key: o for o in overrides}

    items: list[SettingDTO] = []
    groups: set[str] = set()

    for key, meta in SETTING_REGISTRY.items():
        if group and meta["group"] != group:
            continue
        groups.add(meta["group"])
        ovr = overrides_by_key.get(key)
        current_value = ovr.value if ovr else meta["default"]
        items.append(
            SettingDTO(
                key=key,
                value=current_value,
                default=meta["default"],
                type=meta["type"],
                group=meta["group"],
                description=meta.get("description"),
                min_value=meta.get("min_value"),
                max_value=meta.get("max_value"),
                allowed_values=meta.get("allowed_values"),
                requires_restart=meta.get("requires_restart", False),
                is_overridden=ovr is not None,
                updated_at=ovr.updated_at if ovr else None,
                updated_by=ovr.updated_by if ovr else None,
            )
        )

    items.sort(key=lambda x: (x.group, x.key))
    return SettingListResponse(data=items, groups=sorted(groups))


@router.get(
    "/{key}",
    response_model=SettingDTO,
    summary="Tek setting detayı",
)
async def get_setting(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    key: str = Path(..., description="Setting key (örn. rerank.min_combined_score)"),
) -> SettingDTO:
    if key not in SETTING_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Setting bulunamadı", "key": key},
        )
    meta = SETTING_REGISTRY[key]
    overrides = await settings_store.list(db)
    ovr = next((o for o in overrides if o.key == key), None)
    return SettingDTO(
        key=key,
        value=ovr.value if ovr else meta["default"],
        default=meta["default"],
        type=meta["type"],
        group=meta["group"],
        description=meta.get("description"),
        min_value=meta.get("min_value"),
        max_value=meta.get("max_value"),
        allowed_values=meta.get("allowed_values"),
        requires_restart=meta.get("requires_restart", False),
        is_overridden=ovr is not None,
        updated_at=ovr.updated_at if ovr else None,
        updated_by=ovr.updated_by if ovr else None,
    )


@router.put(
    "/{key}",
    response_model=SettingDTO,
    summary="Setting değer güncelle",
)
async def update_setting(
    request: Request,
    payload: SettingUpdate,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    key: str = Path(...),
) -> SettingDTO:
    if key not in SETTING_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Setting bulunamadı", "key": key},
        )
    meta = SETTING_REGISTRY[key]
    new_value = _coerce_value(payload.value, meta["type"])
    _validate_range(
        new_value, min_v=meta.get("min_value"), max_v=meta.get("max_value")
    )

    # Old value snapshot (audit için)
    old_value = await settings_store.get(db, key, meta["default"])

    await settings_store.set(
        db,
        key=key,
        value=new_value,
        type_=meta["type"],
        group_name=meta["group"],
        user_id=user.id,
    )
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="settings.update",
        key=key,
        old_value=old_value,
        new_value=new_value,
    )
    await db.commit()

    return SettingDTO(
        key=key,
        value=new_value,
        default=meta["default"],
        type=meta["type"],
        group=meta["group"],
        description=meta.get("description"),
        min_value=meta.get("min_value"),
        max_value=meta.get("max_value"),
        allowed_values=meta.get("allowed_values"),
        requires_restart=meta.get("requires_restart", False),
        is_overridden=True,
        updated_at=datetime.now(UTC).isoformat(),
        updated_by=str(user.id),
    )


@router.delete(
    "/{key}",
    response_model=SettingDTO,
    summary="Default değere dön",
)
async def reset_setting(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    key: str = Path(...),
) -> SettingDTO:
    if key not in SETTING_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Setting bulunamadı", "key": key},
        )
    meta = SETTING_REGISTRY[key]
    old_value = await settings_store.get(db, key, meta["default"])
    await settings_store.reset(db, key, user_id=user.id)
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="settings.reset",
        key=key,
        old_value=old_value,
        new_value=meta["default"],
    )
    await db.commit()
    return SettingDTO(
        key=key,
        value=meta["default"],
        default=meta["default"],
        type=meta["type"],
        group=meta["group"],
        description=meta.get("description"),
        min_value=meta.get("min_value"),
        max_value=meta.get("max_value"),
        allowed_values=meta.get("allowed_values"),
        requires_restart=meta.get("requires_restart", False),
        is_overridden=False,
        updated_at=None,
        updated_by=None,
    )
