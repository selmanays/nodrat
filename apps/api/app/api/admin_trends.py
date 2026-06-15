"""Admin — Trend Overview (Trend Intelligence Faz 1, #1500).

GDELT-benzeri trend katmanının ilk fazı: **transient / read-only**. Mevcut
`event_clusters` / `event_articles` / `sources` verisinden CANLI SQL ile konu
trend metrikleri hesaplar — persistence YOK (kalıcı `topics` + `trend_snapshots`
Faz 2 ayrı migration PR'ı). `require_admin`; mutation yok → `_audit` gerekmez
(admin_clusters.py read-only deseni).

Flag `trends.enabled` (default OFF) → OFF iken ağır SQL ÇALIŞMAZ, no-op envelope
döner. Prod davranışı flag-OFF = değişmez.

Bu modül `app/api/` aggregator katmanında: cross-domain ORM/tablo okuma serbest
(import-linter yalnız core→modules / shared→modules vb. yasaklar; api→modules
serbest — admin_clusters.py precedent).

Endpoint:
  GET /admin/trends  — pencere içi trend listesi (article_count, momentum,
       unique_source_count, source_diversity, credibility, novelty, trend_state,
       saatlik sparkline; window 1h|6h|24h|7d; sort; pagination)

Not (perf): `event_articles.published_at` üzerinde index YOK (yalnız event_id,
article_id). Pencere taraması seq-scan; v1 ölçeğinde kabul edilebilir. Korpus
büyürse (published_at) ya da (event_id, published_at) index'i Faz 2 migration'da
değerlendirilmeli — bu PR'da migration YOK.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.accounts.deps import require_admin
from app.modules.accounts.models import User
from app.shared.runtime_config.settings_store import settings_store

router = APIRouter()

# =============================================================================
# Sabitler — window / sparkline bucket / sort whitelist / trend_state eşikleri
# =============================================================================

# window → toplam saniye
WINDOW_SECONDS: dict[str, int] = {
    "1h": 3_600,
    "6h": 21_600,
    "24h": 86_400,
    "7d": 604_800,
}

# window → (sparkline bucket sayısı, her bucket saniyesi). count * bucket = window.
SPARKLINE_BUCKETS: dict[str, tuple[int, int]] = {
    "1h": (6, 600),  # 6 × 10dk
    "6h": (6, 3_600),  # 6 × 1sa
    "24h": (12, 7_200),  # 12 × 2sa
    "7d": (7, 86_400),  # 7 × 1gün
}

# sort param → güvenli ORDER BY ifadesi (whitelist; SQL injection yok).
# cur/prev/uniq/rel = aşağıdaki ana sorgunun kolon alias'ları.
_SORT_SQL: dict[str, str] = {
    "momentum": (
        "(cur_count - prev_count)::float / NULLIF(prev_count, 0) DESC NULLS FIRST, cur_count DESC"
    ),
    "article_count": "cur_count DESC",
    "source_count": "unique_sources DESC, cur_count DESC",
    "novelty": "first_seen_at DESC NULLS LAST",
    "credibility": "avg_reliability DESC NULLS LAST, cur_count DESC",
}
VALID_SORTS = frozenset(_SORT_SQL)

# trend_state eşikleri (v1 sabit; Faz 2'de settings'e taşınabilir)
BREAKING_MOMENTUM = 0.5
BREAKING_MIN_ARTICLES = 3
FADING_MOMENTUM = -0.3

# novelty yarı-ömrü (saat): brand-new ≈1.0, 12sa ≈0.5, 24sa ≈0.25
NOVELTY_HALFLIFE_HOURS = 12.0

DEFAULT_WINDOW = "24h"
MAX_LIMIT = 200


# =============================================================================
# Saf hesaplama fonksiyonları (DB'siz, unit-testable)
# =============================================================================


def resolve_window(window: str | None, fallback: str) -> str:
    """Geçerli window döndür; geçersizse ValueError. None → fallback (≥ geçerli)."""
    candidate = window or fallback
    if candidate not in WINDOW_SECONDS:
        raise ValueError(f"invalid window: {candidate!r}")
    return candidate


def compute_momentum(cur: int, prev: int) -> float | None:
    """(cur-prev)/prev. prev=0 & cur>0 → None ('yeni', baseline yok). Aksi 0.0."""
    if prev > 0:
        return round((cur - prev) / prev, 4)
    if cur > 0:
        return None  # yeni — önceki pencerede yok
    return 0.0


def compute_novelty(first_seen_at: datetime | None, now: datetime) -> float:
    """Recency tabanlı novelty [0,1]: 0.5 ** (yaş_saat / yarı-ömür)."""
    if first_seen_at is None:
        return 0.0
    age_hours = max(0.0, (now - first_seen_at).total_seconds() / 3_600.0)
    return round(0.5 ** (age_hours / NOVELTY_HALFLIFE_HOURS), 4)


def compute_source_diversity(unique_sources: int, article_count: int) -> float:
    """Basit v1 yayılım proxy'si: benzersiz_kaynak / toplam_haber, [0,1]."""
    if article_count <= 0:
        return 0.0
    return round(min(1.0, unique_sources / article_count), 4)


def compute_trend_state(
    cur: int, prev: int, momentum: float | None, cluster_status: str | None
) -> str:
    """Deterministik durum: breaking | developing | stable | fading.

    velocity-driven (event_clusters.status lifecycle-driven'a tamamlayıcı —
    cluster.status yalnız okunur, asla yazılmaz)."""
    if cur == 0:
        return "fading" if prev > 0 else "stable"
    if prev == 0:  # cur > 0, baseline yok → yeni patlama
        return "breaking"
    # buradan sonra momentum None değil
    assert momentum is not None
    if momentum >= BREAKING_MOMENTUM and cur >= BREAKING_MIN_ARTICLES:
        return "breaking"
    if momentum > 0:
        return "developing"
    if momentum <= FADING_MOMENTUM:
        return "fading"
    return "stable"


# =============================================================================
# Response şeması
# =============================================================================


class TrendSparkPoint(BaseModel):
    bucket_start: str
    article_count: int


class TrendListItem(BaseModel):
    cluster_id: str
    title: str
    status: str
    trend_state: str
    article_count: int
    previous_article_count: int
    momentum: float | None  # None = yeni (önceki pencerede baseline yok)
    unique_source_count: int
    source_diversity: float
    credibility_score: float | None
    novelty_score: float
    first_seen_at: str | None
    last_seen_at: str | None
    sparkline: list[TrendSparkPoint]


class TrendListResponse(BaseModel):
    enabled: bool
    window: str
    sort: str
    limit: int
    offset: int
    total: int
    data: list[TrendListItem]
    generated_at: str


def build_sparkline(
    bucket_counts: dict[int, int],
    window_start: datetime,
    bucket_count: int,
    bucket_seconds: int,
) -> list[TrendSparkPoint]:
    """bucket_idx→count map'inden sabit uzunlukta (zero-filled) sparkline kur."""
    points: list[TrendSparkPoint] = []
    for i in range(bucket_count):
        bucket_start = window_start + timedelta(seconds=i * bucket_seconds)
        points.append(
            TrendSparkPoint(
                bucket_start=bucket_start.isoformat(),
                article_count=int(bucket_counts.get(i, 0)),
            )
        )
    return points


# =============================================================================
# Endpoint
# =============================================================================


@router.get(
    "",
    response_model=TrendListResponse,
    summary="Trend Overview — canlı haber kümesi metrikleri (Faz 1, read-only)",
)
async def list_trends(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    window: Annotated[str | None, Query(description="1h|6h|24h|7d")] = None,
    sort: Annotated[
        str, Query(description="momentum|article_count|source_count|novelty|credibility")
    ] = "momentum",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TrendListResponse:
    """Pencere içi konu trendleri (transient SQL). Flag OFF → no-op envelope.

    Cross-user içerik DÖNMEZ (haber-korpusu agregasyonu). Mevcut akış/RAG
    path'i DEĞİŞMEZ — yalnız read."""
    if sort not in VALID_SORTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid sort: {sort!r}; allowed: {sorted(VALID_SORTS)}",
        )

    default_window = await settings_store.get(db, "trends.overview.window_default", DEFAULT_WINDOW)
    if default_window not in WINDOW_SECONDS:
        default_window = DEFAULT_WINDOW
    try:
        resolved_window = resolve_window(window, default_window)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    now = datetime.now(UTC)
    generated_at = now.isoformat()

    # ---- Flag OFF → no-op (ağır SQL çalışmaz) --------------------------------
    enabled = await settings_store.get_bool(db, "trends.enabled", False)
    if not enabled:
        return TrendListResponse(
            enabled=False,
            window=resolved_window,
            sort=sort,
            limit=limit,
            offset=offset,
            total=0,
            data=[],
            generated_at=generated_at,
        )

    window_seconds = WINDOW_SECONDS[resolved_window]
    win_start = now - timedelta(seconds=window_seconds)
    prev_start = now - timedelta(seconds=2 * window_seconds)
    bucket_count, bucket_seconds = SPARKLINE_BUCKETS[resolved_window]

    params = {"win_start": win_start, "prev_start": prev_start, "now_ts": now}

    # ---- Toplam (pencere kombinesinde aktivitesi olan distinct cluster) ------
    total_row = await db.execute(
        text(
            """
            SELECT COUNT(DISTINCT ea.event_id) AS total
            FROM event_articles ea
            WHERE ea.published_at >= :prev_start AND ea.published_at < :now_ts
            """
        ),
        params,
    )
    total = int(total_row.scalar() or 0)

    # ---- Ana agregasyon (cluster başına koşullu sayım) -----------------------
    # ORDER BY subquery'nin DIŞINDA: PostgreSQL'de output alias'ı (cur_count vb.)
    # yalnız standalone kullanılabilir; bir İFADE içinde (momentum gibi) alias
    # input-kolon sanılır → "column does not exist". Dış sorguda agg_t kolonları
    # gerçek olduğundan ifade-içi alias çalışır.
    order_by = _SORT_SQL[sort]
    main_sql = text(
        f"""
        SELECT * FROM (
            SELECT
                ec.id              AS cluster_id,
                ec.canonical_title AS title,
                ec.status          AS status,
                ec.first_seen_at   AS first_seen_at,
                ec.last_seen_at    AS last_seen_at,
                COUNT(*) FILTER (
                    WHERE ea.published_at >= :win_start AND ea.published_at < :now_ts
                ) AS cur_count,
                COUNT(*) FILTER (
                    WHERE ea.published_at >= :prev_start AND ea.published_at < :win_start
                ) AS prev_count,
                COUNT(DISTINCT ea.source_id) FILTER (
                    WHERE ea.published_at >= :win_start AND ea.published_at < :now_ts
                ) AS unique_sources,
                AVG(s.reliability_score) FILTER (
                    WHERE ea.published_at >= :win_start AND ea.published_at < :now_ts
                ) AS avg_reliability
            FROM event_articles ea
            JOIN event_clusters ec ON ec.id = ea.event_id
            LEFT JOIN sources s ON s.id = ea.source_id
            WHERE ea.published_at >= :prev_start AND ea.published_at < :now_ts
            GROUP BY ec.id, ec.canonical_title, ec.status, ec.first_seen_at, ec.last_seen_at
        ) AS agg_t
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
        """  # noqa: S608 — order_by sabit whitelist'ten (_SORT_SQL), kullanıcı girdisi değil
    )
    rows = (await db.execute(main_sql, {**params, "limit": limit, "offset": offset})).all()

    # ---- Sparkline (sayfa cluster_id'leri için tek sorgu — N+1 yok) ----------
    cluster_ids = [r.cluster_id for r in rows]
    spark_map: dict[str, dict[int, int]] = {}
    if cluster_ids:
        spark_sql = text(
            """
            SELECT ea.event_id AS cluster_id,
                   floor(
                       extract(epoch FROM (ea.published_at - :win_start)) / :bucket_sec
                   )::int AS bucket_idx,
                   COUNT(*) AS cnt
            FROM event_articles ea
            WHERE ea.event_id IN :ids
              AND ea.published_at >= :win_start AND ea.published_at < :now_ts
            GROUP BY ea.event_id, bucket_idx
            """
        ).bindparams(bindparam("ids", expanding=True))
        spark_rows = (
            await db.execute(
                spark_sql,
                {
                    "win_start": win_start,
                    "now_ts": now,
                    "bucket_sec": bucket_seconds,
                    "ids": cluster_ids,
                },
            )
        ).all()
        for sr in spark_rows:
            idx = max(0, min(bucket_count - 1, int(sr.bucket_idx)))
            spark_map.setdefault(str(sr.cluster_id), {})[idx] = spark_map.get(
                str(sr.cluster_id), {}
            ).get(idx, 0) + int(sr.cnt)

    # ---- Satır serileştirme + saf metrik hesabı ------------------------------
    data: list[TrendListItem] = []
    for r in rows:
        cur = int(r.cur_count or 0)
        prev = int(r.prev_count or 0)
        uniq = int(r.unique_sources or 0)
        momentum = compute_momentum(cur, prev)
        data.append(
            TrendListItem(
                cluster_id=str(r.cluster_id),
                title=r.title,
                status=r.status,
                trend_state=compute_trend_state(cur, prev, momentum, r.status),
                article_count=cur,
                previous_article_count=prev,
                momentum=momentum,
                unique_source_count=uniq,
                source_diversity=compute_source_diversity(uniq, cur),
                credibility_score=(
                    round(float(r.avg_reliability), 4) if r.avg_reliability is not None else None
                ),
                novelty_score=compute_novelty(r.first_seen_at, now),
                first_seen_at=r.first_seen_at.isoformat() if r.first_seen_at else None,
                last_seen_at=r.last_seen_at.isoformat() if r.last_seen_at else None,
                sparkline=build_sparkline(
                    spark_map.get(str(r.cluster_id), {}),
                    win_start,
                    bucket_count,
                    bucket_seconds,
                ),
            )
        )

    return TrendListResponse(
        enabled=True,
        window=resolved_window,
        sort=sort,
        limit=limit,
        offset=offset,
        total=total,
        data=data,
        generated_at=generated_at,
    )
