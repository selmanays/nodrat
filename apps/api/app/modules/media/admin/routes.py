"""Admin media (image) viewer + reprocess (#304 MVP-1.4 PR-4).

NIM VLM ile işlenmiş haber görsellerinin listesi, metadata + status filter,
reprocess action.

Endpoints:
    GET    /admin/media              — paginated list with filters
    POST   /admin/media/{id}/reprocess — re-enqueue VLM task
    GET    /admin/media/stats         — 4'lü stat (toplam/processed/failed/pending)

docs/engineering/data-model.md §3.5 (article_images)
docs/engineering/architecture.md §3.1 (image_vlm_queue)
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_admin
from app.models.article import Article, ArticleImage
from app.models.user import User
from app.modules.sources.models import Source

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Pydantic schemas
# =============================================================================


class MediaImageDTO(BaseModel):
    id: UUID
    article_id: UUID
    article_title: str | None = None
    article_url: str | None = None
    source_id: UUID
    source_name: str | None = None
    original_url: str
    alt_text: str | None = None
    caption: str | None = None
    vlm_caption: str | None = None
    ocr_text: str | None = None
    depicts: list[str] | None = None
    status: str
    error_message: str | None = None
    """#477 — fail nedeni (status='failed' iken). Eskiden Celery result'ta gizliydi."""
    position: int | None = None
    created_at: datetime
    processed_at: datetime | None = None


class MediaListResponse(BaseModel):
    data: list[MediaImageDTO]
    total: int
    limit: int
    offset: int


class MediaStatsResponse(BaseModel):
    total: int
    processed: int
    failed: int
    pending: int
    skipped: int
    last_24h_processed: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/stats",
    response_model=MediaStatsResponse,
    summary="Görsel işleme istatistikleri",
)
async def media_stats(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MediaStatsResponse:
    # PostgreSQL FILTER clause ile tek query'de 5'li sayım
    counts_row = (
        await db.execute(
            select(
                func.count(ArticleImage.id).label("total"),
                func.count(case((ArticleImage.status == "processed", 1))).label("processed"),
                func.count(case((ArticleImage.status == "failed", 1))).label("failed"),
                func.count(case((ArticleImage.status == "pending", 1))).label("pending"),
                func.count(case((ArticleImage.status == "skipped", 1))).label("skipped"),
            ).select_from(ArticleImage)
        )
    ).mappings().first() or {}

    # Son 24 saatte işlenen — interval tek bir SQL string ile
    last_24h = (
        await db.execute(
            select(func.count(ArticleImage.id))
            .select_from(ArticleImage)
            .where(ArticleImage.processed_at > text("NOW() - INTERVAL '24 hours'"))
        )
    ).scalar_one_or_none() or 0

    return MediaStatsResponse(
        total=int(counts_row.get("total") or 0),
        processed=int(counts_row.get("processed") or 0),
        failed=int(counts_row.get("failed") or 0),
        pending=int(counts_row.get("pending") or 0),
        skipped=int(counts_row.get("skipped") or 0),
        last_24h_processed=int(last_24h),
    )


@router.get(
    "",
    response_model=MediaListResponse,
    summary="Görsel listesi (filter + pagination)",
)
async def list_media(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_id: UUID | None = Query(None, description="Kaynak filtresi"),
    status_filter: str | None = Query(
        None,
        alias="status",
        description="pending | processed | failed | skipped",
    ),
    date_from: date | None = Query(None, description="created_at >= ISO 8601"),
    date_to: date | None = Query(None, description="created_at < ISO 8601"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MediaListResponse:
    # Base query — Article.canonical_url + Source.name join
    stmt = (
        select(
            ArticleImage,
            Article.title,
            Article.canonical_url,
            Source.name,
        )
        .outerjoin(Article, ArticleImage.article_id == Article.id)
        .outerjoin(Source, ArticleImage.source_id == Source.id)
    )

    count_stmt = select(func.count()).select_from(ArticleImage)

    if source_id is not None:
        stmt = stmt.where(ArticleImage.source_id == source_id)
        count_stmt = count_stmt.where(ArticleImage.source_id == source_id)
    if status_filter is not None:
        stmt = stmt.where(ArticleImage.status == status_filter)
        count_stmt = count_stmt.where(ArticleImage.status == status_filter)
    if date_from is not None:
        d = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
        stmt = stmt.where(ArticleImage.created_at >= d)
        count_stmt = count_stmt.where(ArticleImage.created_at >= d)
    if date_to is not None:
        d = datetime.combine(date_to, datetime.min.time(), tzinfo=UTC)
        stmt = stmt.where(ArticleImage.created_at < d)
        count_stmt = count_stmt.where(ArticleImage.created_at < d)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(ArticleImage.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).all()

    items: list[MediaImageDTO] = []
    for row in rows:
        img: ArticleImage = row[0]
        items.append(
            MediaImageDTO(
                id=img.id,
                article_id=img.article_id,
                article_title=row[1] if len(row) > 1 else None,
                article_url=row[2] if len(row) > 2 else None,
                source_id=img.source_id,
                source_name=row[3] if len(row) > 3 else None,
                original_url=img.original_url,
                alt_text=img.alt_text,
                caption=img.caption,
                vlm_caption=img.vlm_caption,
                ocr_text=img.ocr_text,
                depicts=img.depicts,
                status=img.status,
                error_message=img.error_message,
                position=img.position,
                created_at=img.created_at,
                processed_at=img.processed_at,
            )
        )

    return MediaListResponse(data=items, total=total, limit=limit, offset=offset)


@router.post(
    "/{image_id}/reprocess",
    response_model=MediaImageDTO,
    summary="Görseli yeniden işle (VLM queue'ya re-enqueue)",
)
async def reprocess_image(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    image_id: UUID = Path(..., description="article_image id"),
) -> MediaImageDTO:
    img = await db.get(ArticleImage, image_id)
    if img is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found")

    img.status = "pending"
    img.processed_at = None
    img.error_message = None  # #477 — yeniden dene öncesi temizle
    await db.commit()
    await db.refresh(img)

    # Dispatch VLM task
    try:
        from app.modules.media.tasks.image_vlm import process_article_image_vlm

        process_article_image_vlm.apply_async(args=[str(img.id)])
    except Exception as exc:
        logger.exception("dispatch image_vlm reprocess failed img=%s err=%s", img.id, exc)

    return MediaImageDTO(
        id=img.id,
        article_id=img.article_id,
        source_id=img.source_id,
        original_url=img.original_url,
        alt_text=img.alt_text,
        caption=img.caption,
        vlm_caption=img.vlm_caption,
        ocr_text=img.ocr_text,
        depicts=img.depicts,
        status=img.status,
        error_message=img.error_message,
        position=img.position,
        created_at=img.created_at,
        processed_at=img.processed_at,
    )
