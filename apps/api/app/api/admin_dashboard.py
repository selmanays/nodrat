"""Admin dashboard hourly metrics — Özet sayfası chart kartları için.

Son 6 saatte saatlik kırılım: yeni haberler, tamamlanan işler, içerik üretimi,
provider çağrıları.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_admin
from app.models.user import User


router = APIRouter()


class HourlyBucket(BaseModel):
    hour: datetime
    count: int


class DashboardHourlyResponse(BaseModel):
    articles: list[HourlyBucket]
    jobs: list[HourlyBucket]
    generations: list[HourlyBucket]
    provider_calls: list[HourlyBucket]


SeriesKey = Literal["articles", "jobs", "generations", "provider_calls"]

_QUERIES: dict[SeriesKey, str] = {
    "articles": (
        "SELECT date_trunc('hour', fetched_at) AS h, COUNT(*) AS c "
        "FROM articles WHERE fetched_at >= :since GROUP BY h"
    ),
    "jobs": (
        "SELECT date_trunc('hour', finished_at) AS h, COUNT(*) AS c "
        "FROM crawler_jobs "
        "WHERE finished_at >= :since AND status IN ('succeeded', 'failed') "
        "GROUP BY h"
    ),
    "generations": (
        "SELECT date_trunc('hour', created_at) AS h, COUNT(*) AS c "
        "FROM generations WHERE created_at >= :since GROUP BY h"
    ),
    "provider_calls": (
        "SELECT date_trunc('hour', created_at) AS h, COUNT(*) AS c "
        "FROM provider_call_logs WHERE created_at >= :since GROUP BY h"
    ),
}


def _fill_buckets(
    rows: list[tuple[datetime, int]], hours_back: int
) -> list[HourlyBucket]:
    """Eksik saatleri 0 ile doldur, kronolojik sırayla döndür."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    by_hour = {row[0]: int(row[1]) for row in rows}
    out: list[HourlyBucket] = []
    for i in range(hours_back, -1, -1):
        ts = now - timedelta(hours=i)
        out.append(HourlyBucket(hour=ts, count=by_hour.get(ts, 0)))
    return out


@router.get(
    "/hourly",
    response_model=DashboardHourlyResponse,
    summary="Son 6 saatlik özet metrikler (saatlik kırılım)",
)
async def dashboard_hourly(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardHourlyResponse:
    hours_back = 5  # son 6 saat = current + 5 önceki
    since = datetime.now(timezone.utc) - timedelta(hours=hours_back + 1)

    series: dict[SeriesKey, list[HourlyBucket]] = {}
    for key, sql in _QUERIES.items():
        rows = (
            await db.execute(text(sql), {"since": since})
        ).all()
        series[key] = _fill_buckets(
            [(r[0], r[1]) for r in rows], hours_back=hours_back
        )

    return DashboardHourlyResponse(
        articles=series["articles"],
        jobs=series["jobs"],
        generations=series["generations"],
        provider_calls=series["provider_calls"],
    )
