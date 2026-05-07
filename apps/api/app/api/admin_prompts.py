"""Admin LLM prompts endpoint'leri (#270 PR-B, MVP-1.2).

docs/engineering/api-contracts.md (admin/prompts)
docs/engineering/data-model.md (app_prompts + app_prompt_history)

Endpoints:
    GET    /admin/prompts                    — Bilinen prompts list
    GET    /admin/prompts/{name}             — Detay (current + meta)
    GET    /admin/prompts/{name}/history     — Version history
    PUT    /admin/prompts/{name}             — Yeni versiyon
    DELETE /admin/prompts/{name}             — Default'a dön (history korunur)
    POST   /admin/prompts/{name}/restore     — Geçmiş bir version'ı current yap

require_admin tüm endpoint'lerde. Audit log her değişiklikte.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.core.prompts_store import prompts_store
from app.models.job import AdminAuditLog
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# PROMPT_REGISTRY — known prompts + default fallback
# =============================================================================
# Yeni prompt eklenirken:
#  1) Buraya ekle (default kod modülünden import edilir)
#  2) İlgili kodda prompts_store.get(...) ile çek


def _default_query_planner() -> str:
    from app.prompts.query_planner import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _default_agenda_card() -> str:
    from app.prompts.agenda_card import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _default_content_generator() -> str:
    from app.prompts.content_generator import SYSTEM_PROMPT_X_POST

    return SYSTEM_PROMPT_X_POST


PROMPT_REGISTRY: dict[str, dict[str, Any]] = {
    "query_planner": {
        "default_factory": _default_query_planner,
        "description": (
            "Kullanıcı isteğini intent + topic + timeframe + output_type'a "
            "ayrıştıran planner prompt. JSON output."
        ),
        "model_hint": "deepseek-v4-flash",
    },
    "agenda_card": {
        "default_factory": _default_agenda_card,
        "description": (
            "Cluster + article'lardan agenda card (özet + key_points + "
            "importance + country) üretim prompt'u."
        ),
        "model_hint": "deepseek-v4-flash",
    },
    "content_generator": {
        "default_factory": _default_content_generator,
        "description": (
            "X post / thread / blog draft üretim system prompt'u. "
            "Citation + 25 kelime quote cap içerir."
        ),
        "model_hint": "deepseek-v4-flash",
    },
}


# =============================================================================
# Pydantic schemas
# =============================================================================


class PromptDTO(BaseModel):
    name: str
    version: int
    content: str
    default: str
    description: str | None
    model_hint: str | None
    is_overridden: bool
    updated_at: str | None
    updated_by: str | None


class PromptListResponse(BaseModel):
    data: list[PromptDTO]


class PromptHistoryItem(BaseModel):
    id: str
    name: str
    version: int
    content: str
    updated_by: str | None
    created_at: str


class PromptHistoryResponse(BaseModel):
    data: list[PromptHistoryItem]


class PromptUpdate(BaseModel):
    content: str = Field(..., min_length=10, max_length=20000)
    description: str | None = None
    model_hint: str | None = None


# =============================================================================
# Helpers
# =============================================================================


def _resolve_default(name: str) -> str:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "title": "Prompt bulunamadı",
                "name": name,
            },
        )
    factory = PROMPT_REGISTRY[name]["default_factory"]
    try:
        return factory()
    except Exception as exc:  # pragma: no cover
        logger.error("prompt default load fail name=%s err=%s", name, exc)
        return ""


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    ip: str | None,
    action: str,
    name: str,
    old_version: int | None,
    new_version: int | None,
) -> None:
    db.add(
        AdminAuditLog(
            actor_id=actor_id,
            action=action,
            target_type="app_prompt",
            target_id=None,
            ip_address=ip,
            event_metadata={
                "prompt_name": name,
                "old_version": old_version,
                "new_version": new_version,
            },
        )
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=PromptListResponse,
    summary="Tüm bilinen LLM prompts",
)
async def list_prompts(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptListResponse:
    overrides = await prompts_store.list(db)
    overrides_by_name = {o.name: o for o in overrides}
    items: list[PromptDTO] = []
    for name, meta in PROMPT_REGISTRY.items():
        ovr = overrides_by_name.get(name)
        default_content = _resolve_default(name)
        items.append(
            PromptDTO(
                name=name,
                version=ovr.version if ovr else 0,
                content=ovr.content if ovr else default_content,
                default=default_content,
                description=ovr.description if ovr and ovr.description else meta.get("description"),
                model_hint=ovr.model_hint if ovr and ovr.model_hint else meta.get("model_hint"),
                is_overridden=ovr is not None,
                updated_at=ovr.updated_at if ovr else None,
                updated_by=ovr.updated_by if ovr else None,
            )
        )
    return PromptListResponse(data=items)


@router.get(
    "/{name}",
    response_model=PromptDTO,
    summary="Tek prompt detayı",
)
async def get_prompt(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
) -> PromptDTO:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )
    meta = PROMPT_REGISTRY[name]
    overrides = await prompts_store.list(db)
    ovr = next((o for o in overrides if o.name == name), None)
    default_content = _resolve_default(name)
    return PromptDTO(
        name=name,
        version=ovr.version if ovr else 0,
        content=ovr.content if ovr else default_content,
        default=default_content,
        description=ovr.description if ovr and ovr.description else meta.get("description"),
        model_hint=ovr.model_hint if ovr and ovr.model_hint else meta.get("model_hint"),
        is_overridden=ovr is not None,
        updated_at=ovr.updated_at if ovr else None,
        updated_by=ovr.updated_by if ovr else None,
    )


@router.get(
    "/{name}/history",
    response_model=PromptHistoryResponse,
    summary="Prompt version history",
)
async def get_prompt_history(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
    limit: int = 20,
) -> PromptHistoryResponse:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )
    rows = await prompts_store.history(db, name, limit=min(limit, 100))
    return PromptHistoryResponse(
        data=[
            PromptHistoryItem(
                id=r.id,
                name=r.name,
                version=r.version,
                content=r.content,
                updated_by=r.updated_by,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


@router.put(
    "/{name}",
    response_model=PromptDTO,
    summary="Prompt güncelle (yeni versiyon)",
)
async def update_prompt(
    request: Request,
    payload: PromptUpdate,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
) -> PromptDTO:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )

    # Old version snapshot (audit için)
    old_overrides = await prompts_store.list(db)
    old_ovr = next((o for o in old_overrides if o.name == name), None)
    old_version = old_ovr.version if old_ovr else 0

    new_version = await prompts_store.set(
        db,
        name=name,
        content=payload.content,
        description=payload.description,
        model_hint=payload.model_hint,
        user_id=user.id,
    )
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="prompts.update",
        name=name,
        old_version=old_version,
        new_version=new_version,
    )
    await db.commit()

    meta = PROMPT_REGISTRY[name]
    return PromptDTO(
        name=name,
        version=new_version,
        content=payload.content,
        default=_resolve_default(name),
        description=payload.description or meta.get("description"),
        model_hint=payload.model_hint or meta.get("model_hint"),
        is_overridden=True,
        updated_at=datetime.now(UTC).isoformat(),
        updated_by=str(user.id),
    )


@router.delete(
    "/{name}",
    response_model=PromptDTO,
    summary="Default'a dön (history korunur)",
)
async def reset_prompt(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
) -> PromptDTO:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )

    old_overrides = await prompts_store.list(db)
    old_ovr = next((o for o in old_overrides if o.name == name), None)
    old_version = old_ovr.version if old_ovr else 0

    await prompts_store.reset(db, name)
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="prompts.reset",
        name=name,
        old_version=old_version,
        new_version=None,
    )
    await db.commit()

    meta = PROMPT_REGISTRY[name]
    default_content = _resolve_default(name)
    return PromptDTO(
        name=name,
        version=0,
        content=default_content,
        default=default_content,
        description=meta.get("description"),
        model_hint=meta.get("model_hint"),
        is_overridden=False,
        updated_at=None,
        updated_by=None,
    )


@router.post(
    "/{name}/restore/{version}",
    response_model=PromptDTO,
    summary="Geçmiş bir versiyonu current yap (yeni version üretir)",
)
async def restore_prompt(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
    version: int = Path(..., ge=1),
) -> PromptDTO:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )

    # History'den fetch
    row = (
        await db.execute(
            sa_text(
                """
                SELECT content FROM app_prompt_history
                WHERE name = :n AND version = :v
                """
            ),
            {"n": name, "v": version},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "title": "Version bulunamadı",
                "version": version,
            },
        )

    new_version = await prompts_store.set(
        db,
        name=name,
        content=row[0],
        user_id=user.id,
    )
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="prompts.restore",
        name=name,
        old_version=version,
        new_version=new_version,
    )
    await db.commit()

    meta = PROMPT_REGISTRY[name]
    return PromptDTO(
        name=name,
        version=new_version,
        content=row[0],
        default=_resolve_default(name),
        description=meta.get("description"),
        model_hint=meta.get("model_hint"),
        is_overridden=True,
        updated_at=datetime.now(UTC).isoformat(),
        updated_by=str(user.id),
    )
