"""Admin — araştırma kümesi gözlem endpoint'leri (#1017 Pivot Faz 3c).

Faz 3 (#1025) GLOBAL kümeleme verisinin admin gözlemi: salt-okuma,
require_admin. admin_users/admin_audit pattern reuse (pagination +
require_admin). YENİ HESAPLAMA YOK — yalnız research_clusters /
message_clusters okur. Read-only → mutation yok → _audit gerekmez
(admin_users list deseni; GET'leri audit'lemek norm değil).

Endpoint'ler:
  GET /admin/clusters                  — global küme listesi (paginated;
       member_count, distinct_users, last_at, deprecated)
  GET /admin/clusters/users/{user_id}  — per-user drill-down: bir
       kullanıcının içeriğinin bulunduğu kümeler + per-user ağırlık

Admin UI ekranları = AYRI UI SEANSI; bu yalnız backend. Mevcut akış/
cevap-üretim path'i DEĞİŞMEZ (research'e dokunmaz). Faz 7 rename olursa
buradaki JOIN'ler de güncellenecek (S10/S13 grep checklist).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_admin
from app.models.user import User
from app.modules.generations.models import MessageCluster, ResearchCluster

router = APIRouter()


class ClusterListItem(BaseModel):
    cluster_id: str
    cluster_key: str
    canonical_name: str
    cluster_type: str
    parent_cluster_id: str | None = None
    member_count: int
    distinct_users: int
    last_at: str | None = None
    deprecated: bool


class ClusterListResponse(BaseModel):
    data: list[ClusterListItem]
    total: int
    limit: int
    offset: int


class UserClusterItem(BaseModel):
    cluster_id: str
    canonical_name: str
    cluster_type: str
    item_count: int
    last_at: str | None = None


class UserClustersResponse(BaseModel):
    user_id: str
    clusters: list[UserClusterItem]
    total: int


@router.get(
    "",
    response_model=ClusterListResponse,
    summary="Global araştırma kümesi listesi (Faz 3c — salt-okuma)",
)
async def list_clusters(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_deprecated: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClusterListResponse:
    """GLOBAL küme düğümleri + toplulaştırılmış istatistik (üye sayısı,
    distinct kullanıcı, son aktivite). Cross-user içerik DÖNMEZ — yalnız
    sayım/metadata (admin gözlem). Faz 3 verisinden; ek hesaplama yok.
    """
    cond = []
    if not include_deprecated:
        cond.append(ResearchCluster.deprecated_at.is_(None))

    total = (
        await db.execute(select(func.count()).select_from(ResearchCluster).where(*cond))
    ).scalar_one()

    q = (
        select(
            ResearchCluster.id,
            ResearchCluster.cluster_key,
            ResearchCluster.canonical_name,
            ResearchCluster.cluster_type,
            ResearchCluster.parent_cluster_id,
            ResearchCluster.deprecated_at,
            func.count(MessageCluster.id).label("member_count"),
            func.count(func.distinct(MessageCluster.user_id)).label("distinct_users"),
            func.max(MessageCluster.created_at).label("last_at"),
        )
        .outerjoin(MessageCluster, MessageCluster.cluster_id == ResearchCluster.id)
        .where(*cond)
        .group_by(
            ResearchCluster.id,
            ResearchCluster.cluster_key,
            ResearchCluster.canonical_name,
            ResearchCluster.cluster_type,
            ResearchCluster.parent_cluster_id,
            ResearchCluster.deprecated_at,
        )
        .order_by(
            func.count(MessageCluster.id).desc(),
            ResearchCluster.updated_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(q)).all()
    data = [
        ClusterListItem(
            cluster_id=str(r.id),
            cluster_key=r.cluster_key,
            canonical_name=r.canonical_name,
            cluster_type=r.cluster_type,
            parent_cluster_id=(str(r.parent_cluster_id) if r.parent_cluster_id else None),
            member_count=int(r.member_count or 0),
            distinct_users=int(r.distinct_users or 0),
            last_at=r.last_at.isoformat() if r.last_at else None,
            deprecated=r.deprecated_at is not None,
        )
        for r in rows
    ]
    return ClusterListResponse(data=data, total=int(total or 0), limit=limit, offset=offset)


@router.get(
    "/users/{user_id}",
    response_model=UserClustersResponse,
    summary="Bir kullanıcının küme drill-down'ı (Faz 3c — salt-okuma)",
)
async def user_clusters(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[UUID, Path()],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> UserClustersResponse:
    """Belirli kullanıcının içeriğinin bulunduğu kümeler + per-user
    ağırlık (o kullanıcının küme içi sorgu sayısı, son aktivite).
    `MessageCluster.user_id == user_id` ile path-user'a kilitli."""
    q = (
        select(
            ResearchCluster.id,
            ResearchCluster.canonical_name,
            ResearchCluster.cluster_type,
            func.count(MessageCluster.id).label("item_count"),
            func.max(MessageCluster.created_at).label("last_at"),
        )
        .join(MessageCluster, MessageCluster.cluster_id == ResearchCluster.id)
        .where(MessageCluster.user_id == user_id)
        .group_by(
            ResearchCluster.id,
            ResearchCluster.canonical_name,
            ResearchCluster.cluster_type,
        )
        .order_by(
            func.count(MessageCluster.id).desc(),
            func.max(MessageCluster.created_at).desc(),
        )
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    clusters = [
        UserClusterItem(
            cluster_id=str(r.id),
            canonical_name=r.canonical_name,
            cluster_type=r.cluster_type,
            item_count=int(r.item_count or 0),
            last_at=r.last_at.isoformat() if r.last_at else None,
        )
        for r in rows
    ]
    return UserClustersResponse(user_id=str(user_id), clusters=clusters, total=len(clusters))
