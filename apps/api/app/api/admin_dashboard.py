"""Admin dashboard hourly metrics — Özet sayfası chart kartları için.

Son 6 saatte saatlik kırılım: yeni haberler, tamamlanan işler, içerik üretimi,
provider çağrıları + LLM çağrıları için 7g/30g/3a aralık seçimi.

#432 — MVP-2.1 delta endpoint (`/admin/dashboard/mvp-2-1-delta`):
PR #418 (2026-05-08) öncesi ve sonrası 7-günlük pencerede pipeline performans
metriklerini karşılaştırır (Epic #391 acceptance #4-#6).
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


def _fill_hourly(
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
        anchor = (now - timedelta(days=weekday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
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
        rows = (
            await db.execute(text(sql), {"since": since})
        ).all()
        series[key] = _fill_hourly(
            [(r[0], r[1]) for r in rows], hours_back=hours_back
        )

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
            buckets=_fill_buckets_generic(
                bucket_rows, bucket=bucket, count=bucket_count
            ),
        )
        for prov, bucket_rows in sorted(
            by_provider.items(),
            key=lambda kv: -sum(c for _, c in kv[1]),
        )
    ]

    return ProviderCallsRangeResponse(
        period=period, bucket=bucket, series=series
    )


# =============================================================================
# #432 — MVP-2.1 delta endpoint (Epic #391 acceptance #4-#6)
# =============================================================================


# PR #418 (Content Generator v1.0 → v1.1.0) production deploy timestamp.
# Pre window = [cutoff - window_days, cutoff)
# Post window = [cutoff, cutoff + window_days)
MVP_2_1_DEFAULT_CUTOFF = datetime(2026, 5, 8, 23, 30, tzinfo=timezone.utc)


class WindowMetrics(BaseModel):
    window_start: datetime
    window_end: datetime
    sample_count: int
    avg_input_tokens: float | None
    avg_output_tokens: float | None
    cache_hit_ratio: float | None
    avg_cost_usd_per_req: float | None
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    halu_flag_rate: float | None
    insufficient_data_rate: float | None
    completed_generation_count: int


class Mvp21DeltaResponse(BaseModel):
    cutoff_at: datetime
    window_days: int
    pre: WindowMetrics
    post: WindowMetrics
    delta_pct: dict[str, float | None]
    note: str


# DeepSeek Content Generator + Query Planner çağrıları sadece chat operation.
# Embedding (local_bge_m3, NIM) ve rerank (NIM) hariç tutulur — MVP-2.1
# optimization scope LLM çağrılarına odaklı.
_PROVIDER_METRICS_SQL = """
SELECT
    COUNT(*)::int                                    AS sample_count,
    AVG(input_tokens)::float                         AS avg_input_tokens,
    AVG(output_tokens)::float                        AS avg_output_tokens,
    SUM(COALESCE(cached_tokens, 0))::float           AS sum_cached,
    SUM(COALESCE(input_tokens, 0))::float            AS sum_input,
    AVG(cost_usd)::float                             AS avg_cost_usd,
    PERCENTILE_DISC(0.5)
        WITHIN GROUP (ORDER BY latency_ms)::int      AS p50_latency_ms,
    PERCENTILE_DISC(0.95)
        WITHIN GROUP (ORDER BY latency_ms)::int      AS p95_latency_ms
FROM provider_call_logs
WHERE created_at >= :start
  AND created_at <  :end
  AND operation = 'chat'
  AND success = TRUE
"""

# Halü ve insufficient_data oranları generations tablosundan.
# Sadece kullanıcıya sunulmuş Content Generator çıktıları (status completed
# veya insufficient_data) sayılır.
_GENERATION_QUALITY_SQL = """
SELECT
    COUNT(*) FILTER (
        WHERE status IN ('completed', 'insufficient_data')
    )::int                                                 AS total,
    COUNT(*) FILTER (WHERE halu_flagged_at IS NOT NULL)::int
                                                           AS halu_count,
    COUNT(*) FILTER (
        WHERE status = 'insufficient_data'
    )::int                                                 AS insuff_count
FROM generations
WHERE created_at >= :start
  AND created_at <  :end
  AND output_type IN ('x_post', 'x_thread', 'summary', 'headline')
"""


async def _window_metrics(
    db: AsyncSession,
    *,
    start: datetime,
    end: datetime,
) -> WindowMetrics:
    prov_row = (
        await db.execute(text(_PROVIDER_METRICS_SQL), {"start": start, "end": end})
    ).one()
    gen_row = (
        await db.execute(
            text(_GENERATION_QUALITY_SQL), {"start": start, "end": end}
        )
    ).one()

    sum_input = prov_row.sum_input or 0.0
    sum_cached = prov_row.sum_cached or 0.0
    cache_hit_ratio = (sum_cached / sum_input) if sum_input > 0 else None

    total_gen = gen_row.total or 0
    halu_rate = (gen_row.halu_count / total_gen) if total_gen > 0 else None
    insuff_rate = (gen_row.insuff_count / total_gen) if total_gen > 0 else None

    return WindowMetrics(
        window_start=start,
        window_end=end,
        sample_count=prov_row.sample_count or 0,
        avg_input_tokens=prov_row.avg_input_tokens,
        avg_output_tokens=prov_row.avg_output_tokens,
        cache_hit_ratio=cache_hit_ratio,
        avg_cost_usd_per_req=prov_row.avg_cost_usd,
        p50_latency_ms=prov_row.p50_latency_ms,
        p95_latency_ms=prov_row.p95_latency_ms,
        halu_flag_rate=halu_rate,
        insufficient_data_rate=insuff_rate,
        completed_generation_count=total_gen,
    )


def _delta_pct(pre_val: float | None, post_val: float | None) -> float | None:
    """Yüzdesel değişim. None değer veya pre=0 → None."""
    if pre_val is None or post_val is None or pre_val == 0:
        return None
    return round(((post_val - pre_val) / pre_val) * 100, 2)


@router.get(
    "/mvp-2-1-delta",
    response_model=Mvp21DeltaResponse,
    summary="MVP-2.1 epic #391 — pre/post 7-day pipeline metrics comparison",
)
async def mvp_2_1_delta(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cutoff_at: Annotated[
        datetime | None,
        Query(
            description=(
                "Pre/post pencere ayraç noktası. Default: 2026-05-08T23:30Z "
                "(PR #418 deploy)."
            ),
        ),
    ] = None,
    window_days: Annotated[
        int,
        Query(ge=1, le=30, description="Pencere genişliği (gün)."),
    ] = 7,
) -> Mvp21DeltaResponse:
    """MVP-2.1 epic #391 acceptance #4-#6 ölçümü.

    Pre = [cutoff - window_days, cutoff)
    Post = [cutoff, cutoff + window_days), now ile sınırlı.

    Sadece `provider_call_logs.operation = 'chat'` LLM çağrıları sayılır
    (embedding/rerank hariç). Halü oranı ve insufficient_data oranı
    `generations` tablosunda Content Generator çıktıları için hesaplanır.
    """
    cutoff = cutoff_at or MVP_2_1_DEFAULT_CUTOFF
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    pre_start = cutoff - timedelta(days=window_days)
    pre_end = cutoff
    post_start = cutoff
    # cutoff henüz gelmemiş ise post window boş kalır (post_start == post_end).
    # Aksi halde cutoff + window_days veya now (hangisi daha erkense).
    post_end = max(post_start, min(cutoff + timedelta(days=window_days), now))

    pre = await _window_metrics(db, start=pre_start, end=pre_end)
    post = await _window_metrics(db, start=post_start, end=post_end)

    delta_pct: dict[str, float | None] = {
        "avg_input_tokens": _delta_pct(pre.avg_input_tokens, post.avg_input_tokens),
        "avg_output_tokens": _delta_pct(
            pre.avg_output_tokens, post.avg_output_tokens
        ),
        "cache_hit_ratio": _delta_pct(pre.cache_hit_ratio, post.cache_hit_ratio),
        "avg_cost_usd_per_req": _delta_pct(
            pre.avg_cost_usd_per_req, post.avg_cost_usd_per_req
        ),
        "p50_latency_ms": _delta_pct(
            pre.p50_latency_ms, post.p50_latency_ms
        ),
        "p95_latency_ms": _delta_pct(
            pre.p95_latency_ms, post.p95_latency_ms
        ),
        "halu_flag_rate": _delta_pct(pre.halu_flag_rate, post.halu_flag_rate),
    }

    note = (
        "Acceptance hedefleri (Epic #391): "
        "avg_input_tokens ≤ -25%, p95_latency_ms ≤ -8%, "
        "avg_cost_usd_per_req ≤ -20%, halu_flag_rate ≤ +0% (regression yok)."
    )

    return Mvp21DeltaResponse(
        cutoff_at=cutoff,
        window_days=window_days,
        pre=pre,
        post=post,
        delta_pct=delta_pct,
        note=note,
    )
