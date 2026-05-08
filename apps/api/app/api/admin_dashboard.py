"""Admin dashboard hourly metrics — Özet sayfası chart kartları için.

Son 6 saatte saatlik kırılım: yeni haberler, tamamlanan işler, içerik üretimi,
provider çağrıları + LLM çağrıları için 7g/30g/3a aralık seçimi.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
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


class ProviderSeries(BaseModel):
    provider: str
    buckets: list[HourlyBucket]


class DashboardHourlyResponse(BaseModel):
    articles: list[HourlyBucket]
    jobs: list[HourlyBucket]
    generations: list[HourlyBucket]
    provider_calls: list[HourlyBucket]
    provider_calls_by_provider: list[ProviderSeries]


class ProviderCallsRangeResponse(BaseModel):
    period: str
    bucket: str  # "hour" | "day" | "week"
    series: list[ProviderSeries]


SeriesKey = Literal["articles", "jobs", "generations", "provider_calls"]

_QUERIES: dict[SeriesKey, str] = {
    "articles": (
        "SELECT date_trunc('hour', fetched_at) AS h, COUNT(*) AS c "
        "FROM articles WHERE fetched_at >= :since GROUP BY h"
    ),
    "jobs": (
        "SELECT date_trunc('hour', updated_at) AS h, COUNT(*) AS c "
        "FROM articles "
        "WHERE updated_at >= :since AND status = 'cleaned' "
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


def _fill_hourly(rows: list[tuple[datetime, int]], hours_back: int) -> list[HourlyBucket]:
    """Eksik saatleri 0 ile doldur, kronolojik sırayla döndür."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    by_hour = {row[0]: int(row[1]) for row in rows}
    out: list[HourlyBucket] = []
    for i in range(hours_back, -1, -1):
        ts = now - timedelta(hours=i)
        out.append(HourlyBucket(hour=ts, count=by_hour.get(ts, 0)))
    return out


def _fill_buckets_generic(
    rows: list[tuple[datetime, int]],
    *,
    bucket: str,
    count: int,
) -> list[HourlyBucket]:
    """bucket: 'hour' | 'day' | 'week'. Bugünden geriye doğru `count` adet bucket."""
    now = datetime.now(timezone.utc)
    if bucket == "hour":
        anchor = now.replace(minute=0, second=0, microsecond=0)
        delta = timedelta(hours=1)
    elif bucket == "day":
        anchor = now.replace(hour=0, minute=0, second=0, microsecond=0)
        delta = timedelta(days=1)
    elif bucket == "week":
        # ISO week start = Monday
        weekday = now.weekday()
        anchor = (now - timedelta(days=weekday)).replace(hour=0, minute=0, second=0, microsecond=0)
        delta = timedelta(weeks=1)
    else:
        raise ValueError(f"unknown bucket: {bucket}")

    by_ts = {row[0]: int(row[1]) for row in rows}
    out: list[HourlyBucket] = []
    for i in range(count - 1, -1, -1):
        ts = anchor - delta * i
        out.append(HourlyBucket(hour=ts, count=by_ts.get(ts, 0)))
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
        rows = (await db.execute(text(sql), {"since": since})).all()
        series[key] = _fill_hourly([(r[0], r[1]) for r in rows], hours_back=hours_back)

    by_provider_rows = (
        await db.execute(
            text(
                "SELECT provider, date_trunc('hour', created_at) AS h, "
                "COUNT(*) AS c FROM provider_call_logs "
                "WHERE created_at >= :since GROUP BY provider, h"
            ),
            {"since": since},
        )
    ).all()
    by_provider: dict[str, list[tuple[datetime, int]]] = {}
    for prov, h, c in by_provider_rows:
        by_provider.setdefault(prov, []).append((h, int(c)))

    provider_series = [
        ProviderSeries(
            provider=prov,
            buckets=_fill_hourly(rows, hours_back=hours_back),
        )
        for prov, rows in sorted(
            by_provider.items(),
            key=lambda kv: -sum(c for _, c in kv[1]),
        )
    ]

    return DashboardHourlyResponse(
        articles=series["articles"],
        jobs=series["jobs"],
        generations=series["generations"],
        provider_calls=series["provider_calls"],
        provider_calls_by_provider=provider_series,
    )


@router.get(
    "/provider-calls",
    response_model=ProviderCallsRangeResponse,
    summary="Provider çağrıları — 7g / 30g / 3a aralık seçimi",
)
async def provider_calls_range(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Annotated[
        Literal["7d", "30d", "3m"],
        Query(description="7d=7 gün, 30d=30 gün, 3m=3 ay"),
    ] = "7d",
) -> ProviderCallsRangeResponse:
    if period == "7d":
        bucket = "day"
        bucket_count = 7
        since = datetime.now(timezone.utc) - timedelta(days=bucket_count)
    elif period == "30d":
        bucket = "day"
        bucket_count = 30
        since = datetime.now(timezone.utc) - timedelta(days=bucket_count)
    else:  # 3m
        bucket = "week"
        bucket_count = 13
        since = datetime.now(timezone.utc) - timedelta(weeks=bucket_count)

    rows = (
        await db.execute(
            text(
                "SELECT provider, date_trunc(:bucket, created_at) AS h, "
                "COUNT(*) AS c FROM provider_call_logs "
                "WHERE created_at >= :since GROUP BY provider, h"
            ),
            {"bucket": bucket, "since": since},
        )
    ).all()
    by_provider: dict[str, list[tuple[datetime, int]]] = {}
    for prov, h, c in rows:
        by_provider.setdefault(prov, []).append((h, int(c)))

    series = [
        ProviderSeries(
            provider=prov,
            buckets=_fill_buckets_generic(bucket_rows, bucket=bucket, count=bucket_count),
        )
        for prov, bucket_rows in sorted(
            by_provider.items(),
            key=lambda kv: -sum(c for _, c in kv[1]),
        )
    ]

    return ProviderCallsRangeResponse(period=period, bucket=bucket, series=series)
