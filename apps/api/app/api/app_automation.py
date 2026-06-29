"""Otomasyon Stüdyosu kullanıcı API'si (Faz 5.3a, #1791).

Kullanıcının otomasyon kurallarını yönetmesi (CRUD) + ONAY KUYRUĞU (pending koşumlar
→ approve/reject). Mount: `/app/me/automation`. Çift flag-gate (automation.enabled +
automation.studio.enabled) → kapalıysa 403 (UI gizli, deploy no-op). Tümü user-scoped
(kullanıcı yalnız kendi kural/koşumlarını görür/yönetir).

automation = ÜST orkestratör; bu router app/api aggregator'da yaşar (app/api→automation
ALLOWED — boundary OK). Kural oluşturma yabancı-LLM ÇAĞIRMAZ → consent gerektirmez;
üretim (Faz 5.2b içerik beat) consent/kota kapılarını uygular.

Onay semantiği: koşum 'pending' (5.2b oto-üretim sonrası) → approve→'posted' (kabul;
artefakt küme feed'inde görünür olur) | reject→'rejected'. Founder vizyonu "onay
kuyruğu" = yayından ÖNCE gözden geçir → otomasyon artefaktı onaylanana kadar feed'de
GÖRÜNMEZ (cluster_artifacts feed filtresi, app_me.py).
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.accounts.deps import get_current_user
from app.modules.accounts.models import User
from app.shared.runtime_config.settings_store import settings_store

router = APIRouter()

_VALID_STATES = {"breaking", "developing"}
_VALID_MODES = {"approval_queue", "full_auto"}
_VALID_RULE_STATUS = {"active", "paused"}
_VALID_ARTIFACT_TYPES = {"post", "thread", "canvas"}  # ARTIFACT_TYPE_LABEL (frontend) paritesi
_RULES_LIMIT = 200  # list_rules satır tavanı (list_runs paritesi — sınırsız response yok)


async def _ensure_studio(db: AsyncSession) -> None:
    """Çift flag-gate: master + stüdyo açık değilse 403 (UI gizli, no-op)."""
    if not await settings_store.get_bool(db, "automation.enabled", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="automation_disabled")
    if not await settings_store.get_bool(db, "automation.studio.enabled", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="automation_studio_disabled")


# ---------------------------------------------------------------------------
# Şemalar
# ---------------------------------------------------------------------------
class RuleCreate(BaseModel):
    cluster_id: uuid.UUID
    states: list[str] = Field(default_factory=lambda: ["breaking"])
    window_seconds: int = Field(default=86_400, ge=3600, le=604_800)
    artifact_type: str = "post"
    mode: str = "approval_queue"


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    status: str | None = None  # 'active' | 'paused'
    states: list[str] | None = None
    mode: str | None = None


class RuleItem(BaseModel):
    rule_id: str
    cluster_id: str
    cluster_name: str | None
    enabled: bool
    status: str
    mode: str
    states: list[str]
    last_triggered_at: str | None
    created_at: str


class RuleListResponse(BaseModel):
    rules: list[RuleItem]
    total: int


class RunItem(BaseModel):
    run_id: str
    cluster_id: str
    cluster_name: str | None
    status: str
    artifact_id: str | None
    artifact_preview: str | None
    triggered_at: str


class RunListResponse(BaseModel):
    runs: list[RunItem]
    total: int


# ---------------------------------------------------------------------------
# Kural CRUD
# ---------------------------------------------------------------------------
@router.get("/rules", response_model=RuleListResponse, summary="Otomasyon kurallarım")
async def list_rules(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RuleListResponse:
    await _ensure_studio(db)
    rows = (
        await db.execute(
            text(
                """
                SELECT ar.id::text AS rule_id, ar.cluster_id::text AS cluster_id,
                       rc.canonical_name AS cluster_name, ar.enabled AS enabled,
                       ar.status AS status, ar.mode AS mode,
                       ar.trigger_config AS tc, ar.last_triggered_at AS last_triggered_at,
                       ar.created_at AS created_at
                FROM automation_rules ar
                JOIN research_clusters rc ON rc.id = ar.cluster_id
                WHERE ar.user_id = :uid AND ar.deleted_at IS NULL
                ORDER BY ar.created_at DESC
                LIMIT :lim
                """
            ),
            {"uid": user.id, "lim": _RULES_LIMIT},
        )
    ).all()
    items = [
        RuleItem(
            rule_id=r.rule_id,
            cluster_id=r.cluster_id,
            cluster_name=r.cluster_name,
            enabled=r.enabled,
            status=r.status,
            mode=r.mode,
            states=list((r.tc or {}).get("states") or ["breaking"]),
            last_triggered_at=r.last_triggered_at.isoformat() if r.last_triggered_at else None,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]
    return RuleListResponse(rules=items, total=len(items))


@router.post(
    "/rules",
    response_model=RuleItem,
    status_code=status.HTTP_201_CREATED,
    summary="Otomasyon kuralı oluştur",
)
async def create_rule(
    payload: RuleCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RuleItem:
    await _ensure_studio(db)
    states = [s for s in payload.states if s in _VALID_STATES]
    if not states:
        raise HTTPException(422, detail="invalid_states")
    if payload.mode not in _VALID_MODES:
        raise HTTPException(422, detail="invalid_mode")
    if payload.artifact_type not in _VALID_ARTIFACT_TYPES:
        # states/mode ile aynı fail-fast: sessiz coercion yerine açık 422 (#denetim2)
        raise HTTPException(422, detail="invalid_artifact_type")
    # küme var + canlı mı?
    cluster = (
        await db.execute(
            text(
                "SELECT canonical_name FROM research_clusters "
                "WHERE id = :c AND deprecated_at IS NULL"
            ),
            {"c": payload.cluster_id},
        )
    ).first()
    if cluster is None:
        raise HTTPException(404, detail="cluster_not_found")
    # abonelik kapısı: yalnız ABONE olunan kümeye kural kurulabilir (vizyon: "abone
    # olduğun kümeye kural koyarsın"; UI zaten yalnız abone kümeleri sunar — burası
    # sunucu-tarafı zorlama, doğrudan-API atlamasını kapatır). #denetim-1/2.
    sub = (
        await db.execute(
            text(
                "SELECT 1 FROM user_cluster_subscriptions "
                "WHERE user_id = :u AND cluster_id = :c AND unsubscribed_at IS NULL"
            ),
            {"u": user.id, "c": payload.cluster_id},
        )
    ).first()
    if sub is None:
        raise HTTPException(403, detail="not_subscribed")
    rid = uuid.uuid4()
    tc = {"states": states, "window_seconds": payload.window_seconds}
    ac = {"artifact_type": payload.artifact_type, "generate_artifact": True}
    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO automation_rules
                        (id, user_id, cluster_id, trigger_config, action_config, mode, enabled)
                    VALUES (:i, :u, :c, CAST(:tc AS jsonb), CAST(:ac AS jsonb), :m, true)
                    RETURNING created_at
                    """
                ),
                {
                    "i": rid,
                    "u": user.id,
                    "c": payload.cluster_id,
                    "tc": json.dumps(tc),
                    "ac": json.dumps(ac),
                    "m": payload.mode,
                },
            )
        ).first()
        await db.commit()
    except Exception as exc:
        await db.rollback()
        # küme başına tek canlı kural (uq_automation_rules_user_cluster_live)
        if "uq_automation_rules_user_cluster_live" in str(exc) or "duplicate" in str(exc).lower():
            raise HTTPException(409, detail="rule_already_exists") from exc
        raise
    return RuleItem(
        rule_id=str(rid),
        cluster_id=str(payload.cluster_id),
        cluster_name=cluster.canonical_name,
        enabled=True,
        status="active",
        mode=payload.mode,
        states=states,
        last_triggered_at=None,
        created_at=row.created_at.isoformat() if row and row.created_at else "",
    )


async def _owned_rule(db: AsyncSession, user_id: uuid.UUID, rule_id: uuid.UUID):
    return (
        await db.execute(
            text(
                "SELECT id FROM automation_rules "
                "WHERE id = :r AND user_id = :u AND deleted_at IS NULL"
            ),
            {"r": rule_id, "u": user_id},
        )
    ).first()


@router.patch("/rules/{rule_id}", summary="Kuralı güncelle (duraklat/sürdür/aç-kapa)")
async def update_rule(
    rule_id: uuid.UUID,
    payload: RuleUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    await _ensure_studio(db)
    if await _owned_rule(db, user.id, rule_id) is None:
        raise HTTPException(404, detail="rule_not_found")
    sets, params = [], {"r": rule_id, "u": user.id}
    if payload.enabled is not None:
        sets.append("enabled = :en")
        params["en"] = payload.enabled
    if payload.status is not None:
        if payload.status not in _VALID_RULE_STATUS:
            raise HTTPException(422, detail="invalid_status")
        sets.append("status = :st")
        params["st"] = payload.status
    if payload.mode is not None:
        if payload.mode not in _VALID_MODES:
            raise HTTPException(422, detail="invalid_mode")
        sets.append("mode = :m")
        params["m"] = payload.mode
    if payload.states is not None:
        states = [s for s in payload.states if s in _VALID_STATES]
        if not states:
            raise HTTPException(422, detail="invalid_states")
        sets.append("trigger_config = jsonb_set(trigger_config, '{states}', CAST(:js AS jsonb))")
        params["js"] = json.dumps(states)
    if not sets:
        raise HTTPException(422, detail="empty_update")
    sets.append("updated_at = NOW()")
    # `sets` yalnız SABİT kolon-atama string'leri (kullanıcı girdisi DEĞİL — tüm
    # değerler bound param); SQL-injection yok (S608 false-positive).
    clause = ", ".join(sets)
    await db.execute(
        text(f"UPDATE automation_rules SET {clause} WHERE id = :r AND user_id = :u"),  # noqa: S608
        params,
    )
    await db.commit()
    return {"updated": True}


@router.delete("/rules/{rule_id}", summary="Kuralı sil (soft)")
async def delete_rule(
    rule_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    await _ensure_studio(db)
    if await _owned_rule(db, user.id, rule_id) is None:
        raise HTTPException(404, detail="rule_not_found")
    await db.execute(
        text(
            "UPDATE automation_rules SET deleted_at = NOW(), updated_at = NOW() "
            "WHERE id = :r AND user_id = :u"
        ),
        {"r": rule_id, "u": user.id},
    )
    await db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Onay kuyruğu
# ---------------------------------------------------------------------------
@router.get("/runs", response_model=RunListResponse, summary="Onay kuyruğu (pending koşumlar)")
async def list_runs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str = "pending",
    limit: int = 50,
) -> RunListResponse:
    await _ensure_studio(db)
    limit = max(1, min(limit, 200))
    rows = (
        await db.execute(
            text(
                """
                SELECT r.id::text AS run_id, r.cluster_id::text AS cluster_id,
                       rc.canonical_name AS cluster_name, r.status AS status,
                       r.artifact_id::text AS artifact_id, r.triggered_at AS triggered_at,
                       (SELECT rev.content FROM artifact_revisions rev
                        WHERE rev.artifact_id = r.artifact_id
                        ORDER BY rev.revision_seq DESC LIMIT 1) AS preview
                FROM automation_runs r
                JOIN automation_rules ar ON ar.id = r.rule_id
                JOIN research_clusters rc ON rc.id = r.cluster_id
                WHERE ar.user_id = :uid AND r.status = :st
                  AND ar.deleted_at IS NULL
                ORDER BY r.triggered_at DESC
                LIMIT :lim
                """
            ),
            {"uid": user.id, "st": status_filter, "lim": limit},
        )
    ).all()
    items = [
        RunItem(
            run_id=r.run_id,
            cluster_id=r.cluster_id,
            cluster_name=r.cluster_name,
            status=r.status,
            artifact_id=r.artifact_id,
            artifact_preview=(r.preview[:280] if r.preview else None),
            triggered_at=r.triggered_at.isoformat(),
        )
        for r in rows
    ]
    return RunListResponse(runs=items, total=len(items))


async def _pending_run(db: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID):
    return (
        await db.execute(
            text(
                """
                SELECT r.id FROM automation_runs r
                JOIN automation_rules ar ON ar.id = r.rule_id
                WHERE r.id = :r AND ar.user_id = :u AND r.status = 'pending'
                  AND ar.deleted_at IS NULL
                """
            ),
            {"r": run_id, "u": user_id},
        )
    ).first()


@router.post("/runs/{run_id}/approve", summary="Koşumu onayla (artefakt feed'de görünür)")
async def approve_run(
    run_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    await _ensure_studio(db)
    if await _pending_run(db, user.id, run_id) is None:
        raise HTTPException(404, detail="pending_run_not_found")
    # Defense-in-depth: UPDATE'in kendisi de owner + pending ile sınırlı (pre-check
    # tek savunma katmanı olmasın — cross-user state-geçişi imkânsız).
    await db.execute(
        text(
            "UPDATE automation_runs SET status = 'posted', reviewed_at = NOW() "
            "WHERE id = :r AND status = 'pending' "
            "AND rule_id IN "
            "(SELECT id FROM automation_rules WHERE user_id = :u AND deleted_at IS NULL)"
        ),
        {"r": run_id, "u": user.id},
    )
    await db.commit()
    return {"status": "posted"}


@router.post("/runs/{run_id}/reject", summary="Koşumu reddet")
async def reject_run(
    run_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    await _ensure_studio(db)
    if await _pending_run(db, user.id, run_id) is None:
        raise HTTPException(404, detail="pending_run_not_found")
    await db.execute(
        text(
            "UPDATE automation_runs SET status = 'rejected', reviewed_at = NOW() "
            "WHERE id = :r AND status = 'pending' "
            "AND rule_id IN "
            "(SELECT id FROM automation_rules WHERE user_id = :u AND deleted_at IS NULL)"
        ),
        {"r": run_id, "u": user.id},
    )
    await db.commit()
    return {"status": "rejected"}
