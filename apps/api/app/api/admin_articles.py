"""Admin article management endpoints (#66).

docs/engineering/api-contracts.md §5
docs/engineering/data-model.md §3.4 + §3.5

Endpoints:
    GET    /admin/articles                — Liste (filter: source, status, search)
    GET    /admin/articles/{id}           — Detay + images
    POST   /admin/articles/{id}/reprocess — Yeniden fetch + clean (status reset)
    GET    /admin/articles/stats           — Özet sayaçlar (status × kaynak)

require_admin (super_admin) tüm endpoint'lerde.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cleaning import STATUS_DISCOVERED
from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.models.article import Article, ArticleImage
from app.models.job import AdminAuditLog
from app.models.source import Source
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Pydantic schemas
# ============================================================================


class ArticleSummary(BaseModel):
    id: UUID
    source_id: UUID
    source_name: str | None
    canonical_url: str
    title: str
    author: str | None
    published_at: datetime | None
    status: str
    language: str
    extraction_confidence: float | None
    text_length: int
    has_images: bool
    created_at: datetime


class ArticleSummaryListResponse(BaseModel):
    data: list[ArticleSummary]
    total: int
    limit: int
    offset: int


class ArticleImagePublic(BaseModel):
    """Article image metadata (NIM VLM process & discard, #304 PR-1).

    Storage kolonları (storage_url, sha256_hash, file_size...) kaldırıldı.
    VLM kolonları (vlm_caption, ocr_text, depicts) eklendi.
    """

    id: UUID
    original_url: str
    alt_text: str | None
    caption: str | None
    vlm_caption: str | None
    ocr_text: str | None
    depicts: list[str] | None
    discovered_from: str | None
    status: str
    position: int | None
    processed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArticleDetailResponse(BaseModel):
    id: UUID
    source_id: UUID
    source_name: str | None
    source_slug: str | None
    canonical_url: str
    source_url: str
    title: str
    subtitle: str | None
    author: str | None
    published_at: datetime | None
    fetched_at: datetime
    crawled_at: datetime
    raw_html_storage_path: str | None
    body_html: str | None
    clean_text: str | None
    language: str
    content_hash: str
    title_hash: str
    extraction_confidence: float | None
    status: str
    created_at: datetime
    updated_at: datetime
    images: list[ArticleImagePublic]


class ReprocessResponse(BaseModel):
    article_id: UUID
    status: str
    dispatched_task: str | None


class ArticleStat(BaseModel):
    status: str
    count: int


class ArticleStatsResponse(BaseModel):
    by_status: list[ArticleStat]
    total: int
    by_source: list[dict[str, Any]]
    embedded_count: int


# ============================================================================
# Helpers
# ============================================================================


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    action: str,
    target_type: str,
    target_id: UUID,
    metadata: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
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


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    response_model=ArticleSummaryListResponse,
    summary="Article listesi (admin)",
)
async def list_articles(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_id: Annotated[UUID | None, Query()] = None,
    article_status: Annotated[str | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(description="Title arama")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ArticleSummaryListResponse:
    base_stmt = select(Article).order_by(Article.created_at.desc())

    if source_id:
        base_stmt = base_stmt.where(Article.source_id == source_id)
    if article_status:
        base_stmt = base_stmt.where(Article.status == article_status)
    if q:
        # Türkçe titre case-insensitive ilike
        base_stmt = base_stmt.where(Article.title.ilike(f"%{q}%"))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    paged = base_stmt.limit(limit).offset(offset)
    articles = list((await db.execute(paged)).scalars().all())

    # Source isimlerini batch al
    source_ids = {a.source_id for a in articles}
    sources_map: dict[UUID, str] = {}
    if source_ids:
        rows = (
            await db.execute(select(Source.id, Source.name).where(Source.id.in_(source_ids)))
        ).all()
        sources_map = {row[0]: row[1] for row in rows}

    # has_images bilgisi için subquery
    if articles:
        article_ids = [a.id for a in articles]
        img_rows = (
            await db.execute(
                select(ArticleImage.article_id, func.count(ArticleImage.id))
                .where(ArticleImage.article_id.in_(article_ids))
                .group_by(ArticleImage.article_id)
            )
        ).all()
        img_count_map: dict[UUID, int] = {row[0]: row[1] for row in img_rows}
    else:
        img_count_map = {}

    summaries = [
        ArticleSummary(
            id=a.id,
            source_id=a.source_id,
            source_name=sources_map.get(a.source_id),
            canonical_url=a.canonical_url,
            title=a.title,
            author=a.author,
            published_at=a.published_at,
            status=a.status,
            language=a.language,
            extraction_confidence=(
                float(a.extraction_confidence) if a.extraction_confidence is not None else None
            ),
            text_length=len(a.clean_text or ""),
            has_images=bool(img_count_map.get(a.id, 0)),
            created_at=a.created_at,
        )
        for a in articles
    ]

    return ArticleSummaryListResponse(data=summaries, total=total, limit=limit, offset=offset)


@router.get(
    "/stats",
    response_model=ArticleStatsResponse,
    summary="Özet sayaçlar",
)
async def article_stats(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArticleStatsResponse:
    by_status_rows = (
        await db.execute(select(Article.status, func.count(Article.id)).group_by(Article.status))
    ).all()
    by_status = [ArticleStat(status=row[0], count=row[1]) for row in by_status_rows]
    total = sum(r.count for r in by_status)

    by_source_rows = (
        await db.execute(
            select(Source.name, Source.slug, func.count(Article.id))
            .select_from(Article)
            .join(Source, Article.source_id == Source.id)
            .group_by(Source.name, Source.slug)
            .order_by(func.count(Article.id).desc())
            .limit(20)
        )
    ).all()
    by_source = [{"name": row[0], "slug": row[1], "count": row[2]} for row in by_source_rows]

    embedded_count_row = await db.execute(
        text("SELECT COUNT(DISTINCT article_id) FROM article_chunks WHERE embedding IS NOT NULL")
    )
    embedded_count = int(embedded_count_row.scalar() or 0)

    return ArticleStatsResponse(
        by_status=by_status,
        total=total,
        by_source=by_source,
        embedded_count=embedded_count,
    )


@router.get(
    "/{article_id}",
    response_model=ArticleDetailResponse,
    summary="Article detay + images",
)
async def get_article(
    article_id: Annotated[UUID, Path()],
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArticleDetailResponse:
    stmt = select(Article).where(Article.id == article_id).options(selectinload(Article.images))
    article = (await db.execute(stmt)).scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail={"code": "ARTICLE_NOT_FOUND"})

    source = await db.get(Source, article.source_id)
    return ArticleDetailResponse(
        id=article.id,
        source_id=article.source_id,
        source_name=source.name if source else None,
        source_slug=source.slug if source else None,
        canonical_url=article.canonical_url,
        source_url=article.source_url,
        title=article.title,
        subtitle=article.subtitle,
        author=article.author,
        published_at=article.published_at,
        fetched_at=article.fetched_at,
        crawled_at=article.crawled_at,
        raw_html_storage_path=article.raw_html_storage_path,
        body_html=article.body_html,
        clean_text=article.clean_text,
        language=article.language,
        content_hash=article.content_hash,
        title_hash=article.title_hash,
        extraction_confidence=(
            float(article.extraction_confidence)
            if article.extraction_confidence is not None
            else None
        ),
        status=article.status,
        created_at=article.created_at,
        updated_at=article.updated_at,
        images=[ArticleImagePublic.model_validate(i) for i in article.images],
    )


@router.post(
    "/{article_id}/reprocess",
    response_model=ReprocessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Article yeniden fetch + clean",
)
async def reprocess_article(
    article_id: Annotated[UUID, Path()],
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReprocessResponse:
    """status'u discovered'a sıfırla + article_fetch_detail dispatch."""
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail={"code": "ARTICLE_NOT_FOUND"})

    # #904 — yalnız 'discarded' (gerçek kalıcı) terminal; reprocess edilmez.
    # 'quarantine' reprocess EDİLEBİLİR (aşağıda discovered'a reset edilir).
    if article.status == "discarded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DISCARDED_NOT_REPROCESSABLE"},
        )

    # Reset state machine (failed/cleaned/fetched → discovered)
    article.status = STATUS_DISCOVERED
    article.body_html = None
    article.clean_text = None
    article.extraction_confidence = None
    article.updated_at = datetime.now(UTC)

    await _audit(
        db,
        actor_id=admin.id,
        action="article.reprocess",
        target_type="article",
        target_id=article.id,
        metadata={"source_id": str(article.source_id)},
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    dispatched: str | None = None
    try:
        from app.workers.tasks.articles import article_fetch_detail

        article_fetch_detail.apply_async(args=[str(article.id)])
        dispatched = "tasks.articles.fetch_detail"
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("dispatch reprocess failed art=%s err=%s", article.id, exc)

    await db.commit()

    return ReprocessResponse(
        article_id=article.id,
        status=article.status,
        dispatched_task=dispatched,
    )
