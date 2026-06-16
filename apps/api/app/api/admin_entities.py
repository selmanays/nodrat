"""Admin — entity canonicalization yönetimi (merge/split/manuel alias) — #1554.

Entity canonical gruplarını (`canonical_entities` + `entity_aliases`) admin'in
elle yönetmesi: birleştir (merge), varyant ayır (split), manuel alias ekle/çıkar.
Deterministik builder'ın çözemediği belirsiz vakaları (örn. "2026 Dünya Kupası"
→ FIFA; okçuluk yüzünden otomatik birleşmez) admin karara bağlar.

Mutation → `AdminAuditLog` + alias `source='admin'` → builder bunları **EZMEZ**.
`entities` tablosu DOKUNULMAZ. Raw SQL (canonical tablolar raw-SQL-only). require_admin.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.job import AdminAuditLog
from app.modules.accounts.deps import require_admin
from app.modules.accounts.models import User

router = APIRouter()

_TYPES = ("person", "org", "place", "event")
MAX_LIMIT = 200


def _norm(s: str) -> str:
    """entity_normalized biçimine yaklaş (lower + trim). Admin girdisi temiz varsayılır."""
    return s.strip().lower()


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    ip: Any,
    action: str,
    target_id: UUID | None,
    meta: dict[str, Any],
) -> None:
    db.add(
        AdminAuditLog(
            actor_id=actor_id,
            action=action,
            target_type="canonical_entity",
            target_id=target_id,
            ip_address=ip,
            event_metadata=meta,
        )
    )


async def _recompute_alias_counts(db: AsyncSession) -> None:
    await db.execute(
        text(
            "UPDATE canonical_entities c SET alias_count = "
            "(SELECT count(*) FROM entity_aliases a WHERE a.canonical_id = c.id)"
        )
    )


# =============================================================================
# Response / request şeması
# =============================================================================


class CanonicalRow(BaseModel):
    id: str
    canonical_name: str
    entity_type: str
    canonical_normalized: str
    alias_count: int
    source: str
    status: str


class AliasRow(BaseModel):
    alias_normalized: str
    entity_type: str
    source: str
    confidence: float


class CanonicalListResponse(BaseModel):
    data: list[CanonicalRow]
    total: int


class CanonicalDetailResponse(BaseModel):
    canonical: CanonicalRow
    aliases: list[AliasRow]


class CreateCanonicalBody(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=300)
    entity_type: str
    aliases: list[str] = Field(default_factory=list)


class AddAliasesBody(BaseModel):
    aliases: list[str] = Field(min_length=1)


class MergeBody(BaseModel):
    source_id: str  # bu canonical'a taşınacak kaynak canonical id


# =============================================================================
# Helpers
# =============================================================================


async def _get_canonical(db: AsyncSession, cid: UUID) -> CanonicalRow:
    row = (
        await db.execute(
            text(
                "SELECT id, canonical_name, entity_type, canonical_normalized, "
                "alias_count, source, status FROM canonical_entities WHERE id = :id"
            ),
            {"id": cid},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="canonical not found")
    return CanonicalRow(
        id=str(row.id),
        canonical_name=row.canonical_name,
        entity_type=row.entity_type,
        canonical_normalized=row.canonical_normalized,
        alias_count=int(row.alias_count),
        source=row.source,
        status=row.status,
    )


async def _detail(db: AsyncSession, cid: UUID) -> CanonicalDetailResponse:
    canon = await _get_canonical(db, cid)
    arows = (
        await db.execute(
            text(
                "SELECT alias_normalized, entity_type, source, confidence "
                "FROM entity_aliases WHERE canonical_id = :id ORDER BY alias_normalized"
            ),
            {"id": cid},
        )
    ).all()
    aliases = [
        AliasRow(
            alias_normalized=a.alias_normalized,
            entity_type=a.entity_type,
            source=a.source,
            confidence=float(a.confidence),
        )
        for a in arows
    ]
    return CanonicalDetailResponse(canonical=canon, aliases=aliases)


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/canonical", response_model=CanonicalListResponse, summary="Canonical entity listesi")
async def list_canonical(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[str | None, Query()] = None,
    entity_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CanonicalListResponse:
    where: list[str] = []
    params: dict[str, Any] = {}
    if entity_type in _TYPES:
        where.append("entity_type = :etype")
        params["etype"] = entity_type
    if search:
        where.append("canonical_normalized ILIKE :q")
        params["q"] = f"%{search.lower()}%"
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    total = int(
        (
            await db.execute(text(f"SELECT count(*) FROM canonical_entities{wsql}"), params)  # noqa: S608
        ).scalar()
        or 0
    )
    rows = (
        await db.execute(
            text(
                f"SELECT id, canonical_name, entity_type, canonical_normalized, "  # noqa: S608
                f"alias_count, source, status FROM canonical_entities{wsql} "
                f"ORDER BY alias_count DESC, canonical_name LIMIT :lim OFFSET :off"
            ),
            {**params, "lim": limit, "off": offset},
        )
    ).all()
    data = [
        CanonicalRow(
            id=str(r.id),
            canonical_name=r.canonical_name,
            entity_type=r.entity_type,
            canonical_normalized=r.canonical_normalized,
            alias_count=int(r.alias_count),
            source=r.source,
            status=r.status,
        )
        for r in rows
    ]
    return CanonicalListResponse(data=data, total=total)


@router.get(
    "/canonical/{cid}",
    response_model=CanonicalDetailResponse,
    summary="Canonical detay + alias'lar",
)
async def canonical_detail(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cid: UUID,
) -> CanonicalDetailResponse:
    return await _detail(db, cid)


async def _upsert_alias(db: AsyncSession, alias: str, etype: str, cid: UUID) -> None:
    # admin override: source='admin' (builder ON CONFLICT bunu EZMEZ)
    await db.execute(
        text(
            "INSERT INTO entity_aliases "
            "(alias_normalized, entity_type, canonical_id, confidence, source) "
            "VALUES (:a, :t, :cid, 1.000, 'admin') "
            "ON CONFLICT (alias_normalized, entity_type) "
            "DO UPDATE SET canonical_id = :cid, source = 'admin', confidence = 1.000"
        ),
        {"a": alias, "t": etype, "cid": cid},
    )


@router.post(
    "/canonical",
    response_model=CanonicalDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Canonical oluştur (+ alias'lar)",
)
async def create_canonical(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    body: CreateCanonicalBody,
) -> CanonicalDetailResponse:
    if body.entity_type not in _TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid entity_type; allowed: {list(_TYPES)}",
        )
    cnorm = _norm(body.canonical_name)
    cid = (
        await db.execute(
            text(
                "INSERT INTO canonical_entities "
                "(canonical_name, entity_type, canonical_normalized, source, status) "
                "VALUES (:name, :t, :cnorm, 'admin', 'active') "
                "ON CONFLICT (canonical_normalized, entity_type) "
                "DO UPDATE SET canonical_name = EXCLUDED.canonical_name, "
                "source = 'admin', updated_at = now() RETURNING id"
            ),
            {"name": body.canonical_name, "t": body.entity_type, "cnorm": cnorm},
        )
    ).scalar()
    for a in {_norm(x) for x in body.aliases if x.strip()}:
        await _upsert_alias(db, a, body.entity_type, cid)
    await _recompute_alias_counts(db)
    await _audit(
        db,
        actor_id=admin.id,
        ip=request.client.host if request.client else None,
        action="canonical.create",
        target_id=cid,
        meta={"canonical_name": body.canonical_name, "entity_type": body.entity_type},
    )
    await db.commit()
    return await _detail(db, cid)


@router.post(
    "/canonical/{cid}/aliases",
    response_model=CanonicalDetailResponse,
    summary="Canonical'a alias ekle (manuel/merge varyant)",
)
async def add_aliases(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    cid: UUID,
    body: AddAliasesBody,
) -> CanonicalDetailResponse:
    canon = await _get_canonical(db, cid)
    added = sorted({_norm(x) for x in body.aliases if x.strip()})
    for a in added:
        await _upsert_alias(db, a, canon.entity_type, cid)
    await _recompute_alias_counts(db)
    await _audit(
        db,
        actor_id=admin.id,
        ip=request.client.host if request.client else None,
        action="canonical.add_aliases",
        target_id=cid,
        meta={"aliases": added},
    )
    await db.commit()
    return await _detail(db, cid)


@router.delete(
    "/canonical/{cid}/aliases/{alias}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Alias ayır (split out) — varyant eşlemesini kaldır",
)
async def remove_alias(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    cid: UUID,
    alias: str,
) -> None:
    canon = await _get_canonical(db, cid)
    res = await db.execute(
        text(
            "DELETE FROM entity_aliases WHERE canonical_id = :cid "
            "AND alias_normalized = :a AND entity_type = :t"
        ),
        {"cid": cid, "a": _norm(alias), "t": canon.entity_type},
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alias not found")
    await _recompute_alias_counts(db)
    await _audit(
        db,
        actor_id=admin.id,
        ip=request.client.host if request.client else None,
        action="canonical.remove_alias",
        target_id=cid,
        meta={"alias": _norm(alias)},
    )
    await db.commit()


@router.post(
    "/canonical/{cid}/merge",
    response_model=CanonicalDetailResponse,
    summary="İki canonical'ı birleştir — kaynak hedefe taşınır",
)
async def merge_canonical(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    cid: UUID,
    body: MergeBody,
) -> CanonicalDetailResponse:
    try:
        source_id = UUID(body.source_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid source_id"
        ) from exc
    if source_id == cid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="cannot merge into self"
        )
    target = await _get_canonical(db, cid)
    source = await _get_canonical(db, source_id)
    if target.entity_type != source.entity_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="entity_type mismatch"
        )
    # kaynak alias'larını hedefe taşı (source='admin' → builder korur); sonra kaynağı sil
    # (FK CASCADE: önce taşıdığımız için kaynakta alias kalmaz, cascade no-op).
    await db.execute(
        text(
            "UPDATE entity_aliases SET canonical_id = :tgt, source = 'admin' "
            "WHERE canonical_id = :src"
        ),
        {"tgt": cid, "src": source_id},
    )
    await db.execute(text("DELETE FROM canonical_entities WHERE id = :src"), {"src": source_id})
    await _recompute_alias_counts(db)
    await _audit(
        db,
        actor_id=admin.id,
        ip=request.client.host if request.client else None,
        action="canonical.merge",
        target_id=cid,
        meta={
            "source_id": str(source_id),
            "source_name": source.canonical_name,
            "target_name": target.canonical_name,
        },
    )
    await db.commit()
    return await _detail(db, cid)
