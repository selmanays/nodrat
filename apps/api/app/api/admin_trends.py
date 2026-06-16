"""Admin — Trend Overview (entity-merkezli, #1518/#1520).

GDELT-benzeri trend katmanının okuma yüzeyi: **entity-merkezli, canlı, read-only**.
`entities ⋈ articles` üzerinden kişi/kurum/yer/olay entity'lerinin yayın-zamanına
göre hacim / momentum / kaynak çeşitliliği / birleşik skorunu hesaplar (persistence
YOK — kalıcı snapshot katmanı ayrı, dormant Faz-2 worker'da). `require_admin`;
mutation yok → `_audit` gerekmez (admin_clusters.py read-only deseni).

Flag `trends.enabled` (default OFF) → OFF iken ağır SQL ÇALIŞMAZ, no-op envelope
döner. Prod davranışı flag-OFF = değişmez. Evidence gate (`trends.gate.min_articles`
/ `min_sources`, default 2) tek-haber/tek-kaynak gürültüsünü ana listeden eler.

Bu modül `app/api/` aggregator katmanında: cross-domain ORM/tablo okuma serbest
(import-linter yalnız core→modules / shared→modules vb. yasaklar; api→modules
serbest — admin_clusters.py precedent).

Endpoint:
  GET /admin/trends — pencere içi entity trend listesi (entity adı + entity_type,
       birleşik skor, article_count, momentum, unique_source_count,
       source_diversity, credibility, novelty, trend_state, saatlik sparkline;
       window 1h|6h|24h|7d; sort; pagination).

Not (perf): `articles.published_at` taraması pencere için seq-scan olabilir; v1
admin ölçeğinde kabul. Korpus büyürse index follow-up.
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
from app.modules.trends.aggregation import (  # paylaşılan scoring (tek kaynak)
    compute_momentum,
    compute_novelty,
    compute_source_diversity,
    compute_trend_score,
    compute_trend_state,
)
from app.shared.runtime_config.settings_store import settings_store

router = APIRouter()

# =============================================================================
# Sabitler — window / sparkline bucket / sort whitelist
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

# Geçerli sort anahtarları (entity path Python tarafında sıralar — bkz _entity_sort_key).
VALID_SORTS = frozenset(
    {"score", "momentum", "article_count", "source_count", "novelty", "credibility"}
)

# entity aggregation'da dikkate alınan NER tipleri (gürültülü money/number/misc dışarıda)
ENTITY_TREND_TYPES = ("person", "org", "place", "event")

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


# =============================================================================
# Response şeması
# =============================================================================


class TrendSparkPoint(BaseModel):
    bucket_start: str
    article_count: int


class TrendListItem(BaseModel):
    cluster_id: str  # entity subject key: "entity_type:entity_normalized"
    title: str  # entity gösterim adı (mode() entity_text)
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
    entity_type: str | None = None  # person|org|place|event rozeti
    trend_score: float | None = None  # birleşik skor [0,1]


class TrendListResponse(BaseModel):
    enabled: bool
    window: str
    sort: str
    limit: int
    offset: int
    total: int
    data: list[TrendListItem]
    generated_at: str
    source: str = "entity"  # canlı entity-aggregation (tek okuma yolu)


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


# sort → entity path Python sıralama anahtarı (reverse=True; novelty tie-breaker).
def _entity_sort_key(sort: str):
    keys = {
        "score": lambda x: (x["score"], x["novelty"]),
        "momentum": lambda x: (
            x["momentum"] if x["momentum"] is not None else float("inf"),
            x["cur"],
        ),
        "article_count": lambda x: (x["cur"], x["uniq"]),
        "source_count": lambda x: (x["uniq"], x["cur"]),
        "novelty": lambda x: (x["novelty"], x["cur"]),
        "credibility": lambda x: (
            x["reliability"] if x["reliability"] is not None else -1.0,
            x["cur"],
        ),
    }
    return keys.get(sort, keys["score"])


async def _read_entity_trends(
    db: AsyncSession,
    win_start: datetime,
    prev_start: datetime,
    now: datetime,
    sort: str,
    bucket_count: int,
    bucket_seconds: int,
    limit: int,
    offset: int,
    min_articles: int,
    min_sources: int,
    canonicalize: bool = False,
) -> tuple[list[TrendListItem], int]:
    """Entity-merkezli canlı trend okuma (tek okuma yolu).

    `entities ⋈ articles` üzerinden `entity_normalized + entity_type` bazında
    agregasyon + evidence gate (≥min_articles haber & ≥min_sources kaynak).
    Gated entity'ler Python'a çekilir (≤~1k satır); momentum/novelty/birleşik skor
    aggregation.compute_* ile hesaplanır (tek kaynak), sıralanıp sayfalanır.
    Sparkline yalnız sayfadaki entity'ler için tek sorguda.

    #1540 canonicalize=True: `entity_aliases`/`canonical_entities` JOIN ile varyant
    yüzey biçimleri (CHP↔Cumhuriyet Halk Partisi) tek canonical kimlikte gruplanır
    (label=canonical_name). Eşleşmeyen entity kendi entity_normalized'ıyla kalır.
    `entities` tablosu dokunulmaz (orijinaller korunur).

    Label = canonical_name (varsa) | `mode() entity_text`. Tek haber breaking olmaz
    (gate cur≥2; compute_trend_state prev=0→cur≥3). Perf: published_at seq-scan, v1 kabul.
    """
    # #1540 — canonical gruplama: alias join + canonical_normalized grup anahtarı.
    if canonicalize:
        norm_expr = "COALESCE(ce.canonical_normalized, e.entity_normalized)"
        name_expr = "COALESCE(MAX(ce.canonical_name), mode() WITHIN GROUP (ORDER BY e.entity_text))"
        canon_join = (
            "LEFT JOIN entity_aliases ea "
            "ON ea.alias_normalized = e.entity_normalized AND ea.entity_type = e.entity_type "
            "LEFT JOIN canonical_entities ce ON ce.id = ea.canonical_id "
        )
    else:
        norm_expr = "e.entity_normalized"
        name_expr = "mode() WITHIN GROUP (ORDER BY e.entity_text)"
        canon_join = ""
    agg_sql = text(
        f"""
        SELECT * FROM (
            SELECT
                {norm_expr} AS norm,
                e.entity_type AS etype,
                {name_expr} AS display_name,
                COUNT(DISTINCT a.id) FILTER (
                    WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                ) AS cur_count,
                COUNT(DISTINCT a.id) FILTER (
                    WHERE a.published_at >= :prev_start AND a.published_at < :win_start
                ) AS prev_count,
                COUNT(DISTINCT a.source_id) FILTER (
                    WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                ) AS unique_sources,
                AVG(s.reliability_score) FILTER (
                    WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                ) AS avg_reliability,
                MAX(a.published_at) FILTER (
                    WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                ) AS last_seen_at,
                MIN(a.published_at) AS first_seen_at
            FROM entities e
            JOIN articles a ON a.id = e.article_id
            LEFT JOIN sources s ON s.id = a.source_id
            {canon_join}
            WHERE a.published_at >= :prev_start AND a.published_at < :now_ts
              AND e.entity_type IN :etypes
            GROUP BY {norm_expr}, e.entity_type
        ) agg
        WHERE cur_count >= :min_articles AND unique_sources >= :min_sources
        """  # noqa: S608 — norm/name/join sabit string'ler (canonicalize bool), kullanıcı girdisi değil
    ).bindparams(bindparam("etypes", expanding=True))
    rows = (
        await db.execute(
            agg_sql,
            {
                "win_start": win_start,
                "prev_start": prev_start,
                "now_ts": now,
                "min_articles": min_articles,
                "min_sources": min_sources,
                "etypes": list(ENTITY_TREND_TYPES),
            },
        )
    ).all()

    enriched: list[dict] = []
    for r in rows:
        cur = int(r.cur_count or 0)
        prev = int(r.prev_count or 0)
        uniq = int(r.unique_sources or 0)
        momentum = compute_momentum(cur, prev)
        novelty = compute_novelty(r.first_seen_at, now)
        recency = compute_novelty(r.last_seen_at, now)  # son aktivite recency'si
        reliability = float(r.avg_reliability) if r.avg_reliability is not None else None
        enriched.append(
            {
                "norm": r.norm,
                "etype": r.etype,
                "display_name": r.display_name or r.norm,
                "cur": cur,
                "prev": prev,
                "uniq": uniq,
                "momentum": momentum,
                "novelty": novelty,
                "diversity": compute_source_diversity(uniq, cur),
                "reliability": reliability,
                "score": compute_trend_score(cur, prev, uniq, reliability, recency),
                "trend_state": compute_trend_state(cur, prev, momentum),
                "first_seen_at": r.first_seen_at,
                "last_seen_at": r.last_seen_at,
            }
        )

    enriched.sort(key=_entity_sort_key(sort), reverse=True)
    total = len(enriched)
    page = enriched[offset : offset + limit]

    spark_map: dict[tuple[str, str], dict[int, int]] = {}
    if page:
        norms = list({p["norm"] for p in page})
        etypes = list({p["etype"] for p in page})
        spark_sql = text(
            f"""
            SELECT {norm_expr} AS norm, e.entity_type AS etype,
                   floor(
                       extract(epoch FROM (a.published_at - :win_start)) / :bucket_sec
                   )::int AS bucket_idx,
                   COUNT(DISTINCT a.id) AS cnt
            FROM entities e
            JOIN articles a ON a.id = e.article_id
            {canon_join}
            WHERE {norm_expr} IN :norms AND e.entity_type IN :etypes
              AND a.published_at >= :win_start AND a.published_at < :now_ts
            GROUP BY {norm_expr}, e.entity_type, bucket_idx
            """  # noqa: S608 — norm_expr/canon_join sabit string'ler, kullanıcı girdisi değil
        ).bindparams(bindparam("norms", expanding=True), bindparam("etypes", expanding=True))
        sp = (
            await db.execute(
                spark_sql,
                {
                    "norms": norms,
                    "etypes": etypes,
                    "win_start": win_start,
                    "now_ts": now,
                    "bucket_sec": bucket_seconds,
                },
            )
        ).all()
        for s in sp:
            idx = max(0, min(bucket_count - 1, int(s.bucket_idx)))
            k = (s.norm, s.etype)
            spark_map.setdefault(k, {})[idx] = spark_map.get(k, {}).get(idx, 0) + int(s.cnt)

    data: list[TrendListItem] = []
    for x in page:
        fs = x["first_seen_at"]
        ls = x["last_seen_at"]
        data.append(
            TrendListItem(
                cluster_id=f"{x['etype']}:{x['norm']}",
                title=html.unescape(x["display_name"]),
                status=x["trend_state"],
                trend_state=x["trend_state"],
                article_count=x["cur"],
                previous_article_count=x["prev"],
                momentum=x["momentum"],
                unique_source_count=x["uniq"],
                source_diversity=x["diversity"],
                credibility_score=x["reliability"],
                novelty_score=x["novelty"],
                first_seen_at=fs.isoformat() if fs else None,
                last_seen_at=ls.isoformat() if ls else None,
                sparkline=build_sparkline(
                    spark_map.get((x["norm"], x["etype"]), {}),
                    win_start,
                    bucket_count,
                    bucket_seconds,
                ),
                entity_type=x["etype"],
                trend_score=x["score"],
            )
        )
    return data, total


# =============================================================================
# Endpoint
# =============================================================================


@router.get(
    "",
    response_model=TrendListResponse,
    summary="Trend Overview — entity-merkezli canlı trend metrikleri (read-only)",
)
async def list_trends(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    window: Annotated[str | None, Query(description="1h|6h|24h|7d")] = None,
    sort: Annotated[
        str,
        Query(description="score|momentum|article_count|source_count|novelty|credibility"),
    ] = "score",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TrendListResponse:
    """Pencere içi entity trendleri (canlı SQL). Flag OFF → no-op envelope.

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

    # ---- Evidence gate eşikleri (runtime-tunable; 0 = gate kapalı) -----------
    # Ana listeye girmek için pencerede en az min_articles haber VE min_sources
    # distinct kaynak gerekir → 0-haber/0-kaynak ve tek-haber gürültüsü gizlenir.
    min_articles = await settings_store.get_int(db, "trends.gate.min_articles", 2)
    min_sources = await settings_store.get_int(db, "trends.gate.min_sources", 2)
    # #1540 — varyant birleştirme (CHP↔Cumhuriyet Halk Partisi). OFF = ham
    # entity_normalized bazında (eski davranış).
    canonicalize = await settings_store.get_bool(db, "trends.canonical_entities.enabled", False)

    # ---- Entity-merkezli canlı agregasyon (tek okuma yolu) -------------------
    data, total = await _read_entity_trends(
        db,
        win_start,
        prev_start,
        now,
        sort,
        bucket_count,
        bucket_seconds,
        limit,
        offset,
        min_articles,
        min_sources,
        canonicalize,
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
        source="entity",
    )


# =============================================================================
# Trend detail (drill-down) — #1552
# =============================================================================


class TrendDetailArticle(BaseModel):
    id: str
    title: str
    url: str | None
    published_at: str | None
    source_name: str | None


class TrendDetailSource(BaseModel):
    source_name: str | None
    article_count: int


class TrendDetailVariant(BaseModel):
    entity_normalized: str
    surface_form: str
    article_count: int


class TrendDetailResponse(BaseModel):
    key: str
    entity_name: str
    entity_type: str
    window: str
    canonical: bool  # canonical grup mu (varyantlar birleşik)
    total_articles: int
    unique_sources: int
    variants: list[TrendDetailVariant]
    sources: list[TrendDetailSource]
    articles: list[TrendDetailArticle]
    sparkline: list[TrendSparkPoint]
    generated_at: str


@router.get(
    "/detail",
    response_model=TrendDetailResponse,
    summary="Trend detay — entity'nin haberleri / kaynakları / varyantları (read-only)",
)
async def trend_detail(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    key: Annotated[
        str, Query(description="entity subject anahtarı: 'entity_type:entity_normalized'")
    ],
    window: Annotated[str | None, Query(description="1h|6h|24h|7d")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> TrendDetailResponse:
    """Bir entity (canonical veya ham) için drill-down: pencere içi haberler,
    kaynak dağılımı, varyant yüzey biçimleri, zaman-serisi. require_admin, read-only."""
    if not await settings_store.get_bool(db, "trends.enabled", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trends disabled")
    etype, sep, norm = key.partition(":")
    if not sep or etype not in ENTITY_TREND_TYPES or not norm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid key: {key!r}; beklenen 'entity_type:entity_normalized'",
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
    win_start = now - timedelta(seconds=WINDOW_SECONDS[resolved_window])
    bucket_count, bucket_seconds = SPARKLINE_BUCKETS[resolved_window]
    canonicalize = await settings_store.get_bool(db, "trends.canonical_entities.enabled", False)

    # ---- Grup norm'larını çöz (canonical ise alias set) ----------------------
    group_norms: list[str] = [norm]
    display_name = html.unescape(norm)
    is_canonical = False
    if canonicalize:
        crow = (
            await db.execute(
                text(
                    "SELECT id, canonical_name FROM canonical_entities "
                    "WHERE canonical_normalized = :n AND entity_type = :t"
                ),
                {"n": norm, "t": etype},
            )
        ).first()
        if crow is not None:
            is_canonical = True
            display_name = html.unescape(crow.canonical_name)
            alias_rows = (
                await db.execute(
                    text("SELECT alias_normalized FROM entity_aliases WHERE canonical_id = :cid"),
                    {"cid": crow.id},
                )
            ).all()
            group_norms = [r.alias_normalized for r in alias_rows] or [norm]

    params = {"t": etype, "norms": group_norms, "ws": win_start, "now_ts": now}

    # ---- Haberler (a.id ile dedup; çoklu varyant aynı makalede → tek) --------
    art_rows = (
        await db.execute(
            text(
                """
                SELECT a.id::text AS id, a.title AS title, a.canonical_url AS url,
                       a.published_at AS pub, s.name AS source_name
                FROM entities e
                JOIN articles a ON a.id = e.article_id
                LEFT JOIN sources s ON s.id = a.source_id
                WHERE e.entity_type = :t AND e.entity_normalized IN :norms
                  AND a.published_at >= :ws AND a.published_at < :now_ts
                GROUP BY a.id, a.title, a.canonical_url, a.published_at, s.name
                ORDER BY a.published_at DESC
                LIMIT :lim
                """
            ).bindparams(bindparam("norms", expanding=True)),
            {**params, "lim": limit},
        )
    ).all()
    articles = [
        TrendDetailArticle(
            id=r.id,
            title=html.unescape(r.title or ""),
            url=r.url,
            published_at=r.pub.isoformat() if r.pub else None,
            source_name=r.source_name,
        )
        for r in art_rows
    ]

    # ---- Kaynak dağılımı -----------------------------------------------------
    src_rows = (
        await db.execute(
            text(
                """
                SELECT s.name AS source_name, COUNT(DISTINCT a.id) AS cnt
                FROM entities e
                JOIN articles a ON a.id = e.article_id
                LEFT JOIN sources s ON s.id = a.source_id
                WHERE e.entity_type = :t AND e.entity_normalized IN :norms
                  AND a.published_at >= :ws AND a.published_at < :now_ts
                GROUP BY s.name ORDER BY cnt DESC
                """
            ).bindparams(bindparam("norms", expanding=True)),
            params,
        )
    ).all()
    sources = [
        TrendDetailSource(source_name=r.source_name, article_count=int(r.cnt)) for r in src_rows
    ]
    total_articles = sum(s.article_count for s in sources)
    unique_sources = len([s for s in sources if s.source_name])

    # ---- Varyant yüzey biçimleri (canonical grup için) -----------------------
    var_rows = (
        await db.execute(
            text(
                """
                SELECT e.entity_normalized AS norm,
                       mode() WITHIN GROUP (ORDER BY e.entity_text) AS surface,
                       COUNT(DISTINCT a.id) AS cnt
                FROM entities e
                JOIN articles a ON a.id = e.article_id
                WHERE e.entity_type = :t AND e.entity_normalized IN :norms
                  AND a.published_at >= :ws AND a.published_at < :now_ts
                GROUP BY e.entity_normalized ORDER BY cnt DESC
                """
            ).bindparams(bindparam("norms", expanding=True)),
            params,
        )
    ).all()
    variants = [
        TrendDetailVariant(
            entity_normalized=r.norm,
            surface_form=html.unescape(r.surface or r.norm),
            article_count=int(r.cnt),
        )
        for r in var_rows
    ]

    # ---- Sparkline (grup) ----------------------------------------------------
    spark_rows = (
        await db.execute(
            text(
                """
                SELECT floor(
                           extract(epoch FROM (a.published_at - :ws)) / :bucket_sec
                       )::int AS bucket_idx,
                       COUNT(DISTINCT a.id) AS cnt
                FROM entities e
                JOIN articles a ON a.id = e.article_id
                WHERE e.entity_type = :t AND e.entity_normalized IN :norms
                  AND a.published_at >= :ws AND a.published_at < :now_ts
                GROUP BY bucket_idx
                """
            ).bindparams(bindparam("norms", expanding=True)),
            {**params, "bucket_sec": bucket_seconds},
        )
    ).all()
    bucket_map = {max(0, min(bucket_count - 1, int(r.bucket_idx))): int(r.cnt) for r in spark_rows}
    sparkline = build_sparkline(bucket_map, win_start, bucket_count, bucket_seconds)

    return TrendDetailResponse(
        key=key,
        entity_name=display_name,
        entity_type=etype,
        window=resolved_window,
        canonical=is_canonical,
        total_articles=total_articles,
        unique_sources=unique_sources,
        variants=variants,
        sources=sources,
        articles=articles,
        sparkline=sparkline,
        generated_at=now.isoformat(),
    )
