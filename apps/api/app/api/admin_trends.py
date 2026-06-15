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

import html
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.accounts.deps import require_admin
from app.modules.accounts.models import User
from app.modules.trends.aggregation import (  # PR-2c: paylaşılan scoring (tek kaynak)
    compute_momentum,
    compute_novelty,
    compute_source_diversity,
    compute_trend_state,
)
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

DEFAULT_WINDOW = "24h"
MAX_LIMIT = 200

# PR-2c (#1505): scoring tek doğruluk kaynağı = app.modules.trends.aggregation
# (compute_momentum/novelty/source_diversity/trend_state buradan import edilir —
# Faz 2 worker ile paylaşılır). resolve_window admin-spesifik kalır.


# =============================================================================
# Saf hesaplama fonksiyonları (DB'siz, unit-testable)
# =============================================================================


def resolve_window(window: str | None, fallback: str) -> str:
    """Geçerli window döndür; geçersizse ValueError. None → fallback (≥ geçerli)."""
    candidate = window or fallback
    if candidate not in WINDOW_SECONDS:
        raise ValueError(f"invalid window: {candidate!r}")
    return candidate


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
    source: str = "live"  # PR-2c: "snapshot" (kalıcı) | "live" (transient cluster SQL)


# sort → snapshot-read ORDER BY (latest-snapshot-per-topic CTE kolonları)
_SNAPSHOT_SORT_SQL: dict[str, str] = {
    "momentum": "l.velocity_1h DESC NULLS LAST, l.article_count DESC",
    "article_count": "l.article_count DESC",
    "source_count": "l.unique_source_count DESC, l.article_count DESC",
    "novelty": "l.novelty_score DESC NULLS LAST",
    "credibility": "l.credibility_score DESC NULLS LAST, l.article_count DESC",
}


async def _read_topic_trends(
    db: AsyncSession,
    win_start: datetime,
    now: datetime,
    sort: str,
    bucket_count: int,
    bucket_seconds: int,
    limit: int,
    offset: int,
    min_articles: int,
    min_sources: int,
) -> tuple[list[TrendListItem], int] | None:
    """Snapshot-öncelikli okuma: pencere içinde topic snapshot'ı varsa kalıcı
    store'dan topic trendleri (worker'ın precompute ettiği per-bucket metrikler +
    son bucket'lardan sparkline). Snapshot yoksa None → caller canlı path'e düşer.

    #1516 evidence gate: son snapshot'ta article_count < min_articles veya
    unique_source_count < min_sources olan topic'ler listeye girmez. Hiç snapshot
    yoksa None (canlı fallback); snapshot var ama hiçbiri gate'i geçmezse boş liste
    (canlı path'e DÜŞMEZ — worker çalışmışken ham-başlık cluster göstermeyiz).
    """
    any_snap = int(
        (
            await db.execute(
                text(
                    "SELECT COUNT(DISTINCT subject_id) FROM trend_snapshots "
                    "WHERE subject_type = 'topic' AND bucket_start >= :ws AND bucket_start < :now"
                ),
                {"ws": win_start, "now": now},
            )
        ).scalar()
        or 0
    )
    if any_snap == 0:
        return None  # hiç snapshot yok → canlı fallback

    gate_params = {
        "ws": win_start,
        "now": now,
        "min_articles": min_articles,
        "min_sources": min_sources,
    }
    total = int(
        (
            await db.execute(
                text(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (s.subject_id)
                            s.subject_id, s.article_count, s.unique_source_count
                        FROM trend_snapshots s
                        WHERE s.subject_type = 'topic'
                          AND s.bucket_start >= :ws AND s.bucket_start < :now
                        ORDER BY s.subject_id, s.bucket_start DESC
                    )
                    SELECT count(*) FROM latest
                    WHERE article_count >= :min_articles
                      AND unique_source_count >= :min_sources
                    """
                ),
                gate_params,
            )
        ).scalar()
        or 0
    )

    order_by = _SNAPSHOT_SORT_SQL[sort]
    rows = (
        await db.execute(
            text(
                f"""
                WITH latest AS (
                    SELECT DISTINCT ON (s.subject_id)
                        s.subject_id, s.article_count, s.unique_source_count,
                        s.source_diversity, s.credibility_score, s.novelty_score,
                        s.trend_state, s.velocity_1h
                    FROM trend_snapshots s
                    WHERE s.subject_type = 'topic'
                      AND s.bucket_start >= :ws AND s.bucket_start < :now
                    ORDER BY s.subject_id, s.bucket_start DESC
                )
                SELECT l.*, t.label, t.first_seen_at, t.last_seen_at
                FROM latest l JOIN topics t ON t.id = l.subject_id
                WHERE l.article_count >= :min_articles
                  AND l.unique_source_count >= :min_sources
                ORDER BY {order_by}
                LIMIT :lim OFFSET :off
                """  # noqa: S608 — order_by sabit whitelist (_SNAPSHOT_SORT_SQL)
            ),
            {**gate_params, "lim": limit, "off": offset},
        )
    ).all()

    ids = [r.subject_id for r in rows]
    spark_map: dict[str, dict[int, int]] = {}
    if ids:
        sp = (
            await db.execute(
                text(
                    """
                    SELECT subject_id, bucket_start, article_count
                    FROM trend_snapshots
                    WHERE subject_type = 'topic' AND subject_id IN :ids
                      AND bucket_start >= :ws AND bucket_start < :now
                    """
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": ids, "ws": win_start, "now": now},
            )
        ).all()
        for s in sp:
            idx = int((s.bucket_start - win_start).total_seconds() // bucket_seconds)
            idx = max(0, min(bucket_count - 1, idx))
            key = str(s.subject_id)
            spark_map.setdefault(key, {})[idx] = spark_map.get(key, {}).get(idx, 0) + int(
                s.article_count
            )

    data: list[TrendListItem] = []
    for r in rows:
        cur = int(r.article_count or 0)
        v1 = float(r.velocity_1h) if r.velocity_1h is not None else None
        prev = max(0, int(cur - v1)) if v1 is not None else 0
        momentum = compute_momentum(cur, prev) if v1 is not None else None
        state = r.trend_state or "stable"
        data.append(
            TrendListItem(
                cluster_id=str(r.subject_id),  # subject = topic id
                title=html.unescape(r.label or ""),  # #1516 HTML entity decode
                status=state,
                trend_state=state,
                article_count=cur,
                previous_article_count=prev,
                momentum=momentum,
                unique_source_count=int(r.unique_source_count or 0),
                source_diversity=(
                    float(r.source_diversity) if r.source_diversity is not None else 0.0
                ),
                credibility_score=(
                    float(r.credibility_score) if r.credibility_score is not None else None
                ),
                novelty_score=float(r.novelty_score) if r.novelty_score is not None else 0.0,
                first_seen_at=r.first_seen_at.isoformat() if r.first_seen_at else None,
                last_seen_at=r.last_seen_at.isoformat() if r.last_seen_at else None,
                sparkline=build_sparkline(
                    spark_map.get(str(r.subject_id), {}), win_start, bucket_count, bucket_seconds
                ),
            )
        )
    return data, total


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

    # ---- #1516: evidence gate eşikleri (runtime-tunable; 0 = gate kapalı) -----
    # Ana listeye girmek için pencerede en az min_articles haber VE min_sources
    # distinct kaynak gerekir → 0-haber/0-kaynak ve tek-haber gürültüsü gizlenir.
    min_articles = await settings_store.get_int(db, "trends.gate.min_articles", 2)
    min_sources = await settings_store.get_int(db, "trends.gate.min_sources", 2)

    # ---- PR-2c: snapshot-öncelikli okuma --------------------------------------
    # trends.snapshots.enabled ON + pencerede topic snapshot'ı varsa kalıcı
    # store'dan topic trendleri (worker precompute). Yoksa canlı cluster path'e
    # düşülür (Faz 1 davranışı korunur → worker kapalıyken/boşken aynı).
    if await settings_store.get_bool(db, "trends.snapshots.enabled", False):
        snap = await _read_topic_trends(
            db,
            win_start,
            now,
            sort,
            bucket_count,
            bucket_seconds,
            limit,
            offset,
            min_articles,
            min_sources,
        )
        if snap is not None:
            snap_data, snap_total = snap
            return TrendListResponse(
                enabled=True,
                window=resolved_window,
                sort=sort,
                limit=limit,
                offset=offset,
                total=snap_total,
                data=snap_data,
                generated_at=generated_at,
                source="snapshot",
            )

    params = {"win_start": win_start, "prev_start": prev_start, "now_ts": now}
    gate_params = {**params, "min_articles": min_articles, "min_sources": min_sources}

    # ---- Toplam (#1516: evidence gate'i geçen distinct cluster) --------------
    # Mevcut pencerede [win_start, now] en az min_articles haber VE min_sources
    # distinct kaynak içeren cluster sayısı (main query'deki cur_count/uniq ile
    # tutarlı). 0-haber/tek-haber cluster'ları toplam dışında bırakır.
    total_row = await db.execute(
        text(
            """
            SELECT count(*) AS total FROM (
                SELECT ea.event_id
                FROM event_articles ea
                WHERE ea.published_at >= :win_start AND ea.published_at < :now_ts
                GROUP BY ea.event_id
                HAVING COUNT(*) >= :min_articles
                   AND COUNT(DISTINCT ea.source_id) >= :min_sources
            ) g
            """
        ),
        gate_params,
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
        WHERE cur_count >= :min_articles AND unique_sources >= :min_sources
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
        """  # noqa: S608 — order_by sabit whitelist'ten (_SORT_SQL), kullanıcı girdisi değil
    )
    rows = (await db.execute(main_sql, {**gate_params, "limit": limit, "offset": offset})).all()

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
                title=html.unescape(r.title or ""),  # #1516 HTML entity decode
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
