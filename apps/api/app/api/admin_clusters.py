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

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.accounts.deps import require_admin
from app.modules.accounts.models import User
from app.modules.generations.models import MessageCluster, ResearchCluster
from app.modules.trends.cluster_link import (
    cluster_supply_detail,
    rising_entities,
    trend_metrics_for_clusters,
)
from app.shared.runtime_config.settings_store import settings_store

router = APIRouter()

# window → saniye (admin_trends.WINDOW_SECONDS özeti; api→api coupling'i önlemek için local)
_WINDOW_SECONDS = {"1h": 3_600, "6h": 21_600, "24h": 86_400, "7d": 604_800}


class ClusterListItem(BaseModel):
    cluster_id: str
    cluster_key: str
    canonical_name: str
    cluster_type: str
    parent_cluster_id: str | None = None
    member_count: int  # talep: küme içi mesaj sayısı
    distinct_users: int  # talep: ilgilenen kullanıcı sayısı
    last_at: str | None = None
    deprecated: bool
    # arz (#1570): aynı entity'nin canlı trend durumu (trends.enabled OFF → null)
    trend_state: str | None = None  # breaking|developing|stable|fading|quiet
    relative_momentum: float | None = None  # korpus-normalize
    article_count_window: int | None = None  # pencere içi haber sayısı


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
    window: Annotated[str, Query(description="trend penceresi: 1h|6h|24h|7d")] = "24h",
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

    # arz zenginleştirme (#1570 — talep×arz): trends.enabled açıksa sayfadaki
    # kümelerin AYNI entity'sinin canlı trend durumu (korpus-normalize). Hedefli
    # (yalnız sayfa anahtarları). OFF → trend alanları null (yalnız talep görünür).
    trends_on = await settings_store.get_bool(db, "trends.enabled", False)
    if trends_on and data:
        wsec = _WINDOW_SECONDS.get(window, 86_400)
        metrics = await trend_metrics_for_clusters(
            db,
            [d.cluster_key for d in data],
            window_seconds=wsec,
            now=datetime.now(UTC),
        )
        for d in data:
            m = metrics.get(d.cluster_key)
            if m is not None:
                d.trend_state = m.trend_state
                d.relative_momentum = m.relative_momentum
                d.article_count_window = m.article_count
            else:
                d.trend_state = "quiet"  # pencerede aktivite yok = sessiz
                d.article_count_window = 0

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


# =============================================================================
# #1570 (G) — Boşluk radarı: talep × arz uyumsuzluğu
# =============================================================================


class GapUnmetItem(BaseModel):
    """Karşılanmamış ilgi: yüksek talep (kullanıcı) ama sessiz/sabit arz (haber az)."""

    canonical_name: str
    cluster_type: str
    distinct_users: int
    member_count: int
    trend_state: str | None = None
    article_count_window: int | None = None


class GapRisingItem(BaseModel):
    """İlgisiz yükselen: haberde breaking/developing ama küme yok (editöryel fırsat)."""

    entity_name: str
    entity_type: str
    trend_state: str
    relative_momentum: float | None = None
    article_count: int


class GapsResponse(BaseModel):
    window: str
    enabled: bool
    unmet_demand: list[GapUnmetItem]
    rising_no_demand: list[GapRisingItem]
    generated_at: str


@router.get(
    "/gaps",
    response_model=GapsResponse,
    summary="Boşluk radarı — talep×arz uyumsuzluğu (G, salt-okuma)",
)
async def cluster_gaps(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    window: Annotated[str, Query(description="1h|6h|24h|7d")] = "24h",
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
) -> GapsResponse:
    """İki boşluk: (1) **karşılanmamış ilgi** — çok kullanıcı ilgileniyor ama trend
    sessiz/sabit (haberde az) · (2) **ilgisiz yükselen** — haberde breaking/developing
    ama hiç küme yok (kimse araştırmamış → editöryel fırsat). trends.enabled OFF →
    boş (no-op). Salt-okuma; içerik DÖNMEZ (yalnız ad/sayım/durum)."""
    now = datetime.now(UTC)
    generated_at = now.isoformat()
    enabled = await settings_store.get_bool(db, "trends.enabled", False)
    if not enabled:
        return GapsResponse(
            window=window,
            enabled=False,
            unmet_demand=[],
            rising_no_demand=[],
            generated_at=generated_at,
        )
    wsec = _WINDOW_SECONDS.get(window, 86_400)

    # (1) karşılanmamış ilgi — en yüksek talepli kümeler, trend sessiz/sabit/fading
    demand_q = (
        select(
            ResearchCluster.cluster_key,
            ResearchCluster.canonical_name,
            ResearchCluster.cluster_type,
            func.count(MessageCluster.id).label("member_count"),
            func.count(func.distinct(MessageCluster.user_id)).label("distinct_users"),
        )
        .outerjoin(MessageCluster, MessageCluster.cluster_id == ResearchCluster.id)
        .where(ResearchCluster.deprecated_at.is_(None))
        .group_by(
            ResearchCluster.cluster_key,
            ResearchCluster.canonical_name,
            ResearchCluster.cluster_type,
        )
        .having(func.count(func.distinct(MessageCluster.user_id)) >= 1)
        .order_by(
            func.count(func.distinct(MessageCluster.user_id)).desc(),
            func.count(MessageCluster.id).desc(),
        )
        .limit(60)  # aday havuzu (trend ile süzülecek)
    )
    drows = (await db.execute(demand_q)).all()
    metrics = await trend_metrics_for_clusters(
        db, [r.cluster_key for r in drows], window_seconds=wsec, now=now
    )
    unmet: list[GapUnmetItem] = []
    for r in drows:
        m = metrics.get(r.cluster_key)
        state = m.trend_state if m else "quiet"
        if state in ("breaking", "developing"):  # arz YÜKSEK → boşluk değil
            continue
        unmet.append(
            GapUnmetItem(
                canonical_name=r.canonical_name,
                cluster_type=r.cluster_type,
                distinct_users=int(r.distinct_users or 0),
                member_count=int(r.member_count or 0),
                trend_state=state,
                article_count_window=(m.article_count if m else 0),
            )
        )
        if len(unmet) >= limit:
            break

    # (2) ilgisiz yükselen — breaking/developing entity'ler, küme YOK
    rising = await rising_entities(db, window_seconds=wsec, now=now, limit=limit * 3)
    existing: set[str] = set()
    keys = [r.cluster_key for r in rising]
    if keys:
        ex = await db.execute(
            select(ResearchCluster.cluster_key).where(
                ResearchCluster.cluster_key.in_(keys),
                ResearchCluster.deprecated_at.is_(None),
            )
        )
        existing = {row[0] for row in ex}
    rising_nd = [
        GapRisingItem(
            entity_name=r.entity_name,
            entity_type=r.entity_type,
            trend_state=r.trend_state,
            relative_momentum=r.relative_momentum,
            article_count=r.article_count,
        )
        for r in rising
        if r.cluster_key not in existing
    ][:limit]

    return GapsResponse(
        window=window,
        enabled=True,
        unmet_demand=unmet,
        rising_no_demand=rising_nd,
        generated_at=generated_at,
    )


# =============================================================================
# #1579 (F) — Küme detayı: talep (üye/kullanıcı) + arz (trend timeline + haberler)
# =============================================================================


class DetailSparkPoint(BaseModel):
    bucket_start: str
    article_count: int


class DetailArticleItem(BaseModel):
    id: str
    title: str
    url: str | None = None
    published_at: str | None = None
    source_name: str | None = None


class DetailSourceItem(BaseModel):
    source_name: str | None = None
    article_count: int


class ClusterDetailResponse(BaseModel):
    cluster_id: str
    cluster_key: str
    canonical_name: str
    cluster_type: str
    parent_cluster_id: str | None = None
    deprecated: bool
    member_count: int  # talep
    distinct_users: int  # talep
    # arz (#1570/#1579) — trends.enabled OFF → null/boş
    trend_state: str | None = None
    relative_momentum: float | None = None
    article_count_window: int | None = None
    unique_sources_window: int | None = None
    window: str
    sparkline: list[DetailSparkPoint]
    articles: list[DetailArticleItem]
    sources: list[DetailSourceItem]
    generated_at: str


@router.get(
    "/{cid}",
    response_model=ClusterDetailResponse,
    summary="Küme detayı — talep + trend timeline/haberler (F, salt-okuma)",
)
async def cluster_detail(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cid: Annotated[UUID, Path()],
    window: Annotated[str, Query(description="1h|6h|24h|7d")] = "24h",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ClusterDetailResponse:
    """Bir kümenin TALEP (üye/distinct kullanıcı/hiyerarşi) + ARZ (aynı entity'nin
    trend durumu + pencere-içi timeline + son haberler + kaynak dağılımı, kebab-
    match) detayı. trends.enabled OFF → arz null/boş. Salt-okuma; haber gövdesi yok."""
    now = datetime.now(UTC)
    row = (
        await db.execute(
            select(
                ResearchCluster.id,
                ResearchCluster.cluster_key,
                ResearchCluster.canonical_name,
                ResearchCluster.cluster_type,
                ResearchCluster.parent_cluster_id,
                ResearchCluster.deprecated_at,
                func.count(MessageCluster.id).label("member_count"),
                func.count(func.distinct(MessageCluster.user_id)).label("distinct_users"),
            )
            .outerjoin(MessageCluster, MessageCluster.cluster_id == ResearchCluster.id)
            .where(ResearchCluster.id == cid)
            .group_by(
                ResearchCluster.id,
                ResearchCluster.cluster_key,
                ResearchCluster.canonical_name,
                ResearchCluster.cluster_type,
                ResearchCluster.parent_cluster_id,
                ResearchCluster.deprecated_at,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="cluster not found")

    detail = ClusterDetailResponse(
        cluster_id=str(row.id),
        cluster_key=row.cluster_key,
        canonical_name=row.canonical_name,
        cluster_type=row.cluster_type,
        parent_cluster_id=(str(row.parent_cluster_id) if row.parent_cluster_id else None),
        deprecated=row.deprecated_at is not None,
        member_count=int(row.member_count or 0),
        distinct_users=int(row.distinct_users or 0),
        window=window,
        sparkline=[],
        articles=[],
        sources=[],
        generated_at=now.isoformat(),
    )

    if await settings_store.get_bool(db, "trends.enabled", False):
        wsec = _WINDOW_SECONDS.get(window, 86_400)
        sup = await cluster_supply_detail(
            db, row.cluster_key, window_seconds=wsec, now=now, limit=limit
        )
        detail.trend_state = sup.trend_state
        detail.relative_momentum = sup.relative_momentum
        detail.article_count_window = sup.article_count
        detail.unique_sources_window = sup.unique_sources
        detail.sparkline = [
            DetailSparkPoint(bucket_start=p.bucket_start, article_count=p.article_count)
            for p in sup.sparkline
        ]
        detail.articles = [
            DetailArticleItem(
                id=a.id,
                title=a.title,
                url=a.url,
                published_at=a.published_at,
                source_name=a.source_name,
            )
            for a in sup.articles
        ]
        detail.sources = [
            DetailSourceItem(source_name=s.source_name, article_count=s.article_count)
            for s in sup.sources
        ]
    return detail
