"""Kümeler ↔ Trendler köprüsü (#1570) — ortak eşleme + canlı trend metrikleri.

Araştırma kümeleri (`research_clusters`, talep sinyali) ve entity trendleri
(`entities ⋈ articles`, arz sinyali) **aynı haber-korpusu entity'sine** çapalı.
Küme anahtarı `cluster_key = '<type>:<tr_ascii_kebab(entity_normalized)>'`
(`core.research_clustering.canonical_cluster_key`). Bu modül o anahtar üzerinden
küme(ler) için **canlı trend metriği** (rel momentum + burst → trend_state) hesaplar.

Eşleme: trend tarafında `entity_type:entity_normalized` → `tr_ascii_kebab` SQL'de
BİREBİR replike edilir (küme anahtarı Python tr_ascii_kebab ile basıldığı için iki
taraf aynı — lossy artefaktlar [combining-dot vb.] dahil tutarlı). Salt-okuma.

A/B/D fikirleri (user ilgi-feed + admin talep×arz + kişiselleştirme) bunu paylaşır.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trends.aggregation import (
    compute_relative_momentum,
    compute_trend_state,
    compute_window_burst,
)

# entity trend tipleri (admin_trends.ENTITY_TREND_TYPES ile hizalı)
_TREND_TYPES = ("person", "org", "place", "event")

# tr_ascii_kebab'in SQL kopyası (core.research_clustering.tr_ascii_kebab ile BİREBİR):
#   translate(TR→ASCII) → lower → [^a-z0-9]+ → '-' → trim('-').
# Küme anahtarı Python tarafında bu fonksiyonla basıldığı için SQL kopyası birebir
# eşleşmeli (aksi halde join sessizce boş döner). Test: test_cluster_link_kebab_parity.
_KEBAB = (
    "trim(both '-' from regexp_replace("
    "lower(translate({col}, 'şŞıİçÇöÖüÜğĞâîû', 'ssiiccoouuggaiu')), "
    "'[^a-z0-9]+', '-', 'g'))"
)
# #1712 — canonical-aware: trend metriği + boşluk-radarı küme anahtarı/etiketi
# Wikidata-temelli canonical'a hizalı (küme resolver ENTITY_DF_SQL ile SENKRON). alias→
# canonical JOIN (entity_aliases UNIQUE(alias_normalized,entity_type) → row çoğalmaz);
# ce yoksa COALESCE ham entity_normalized'a düşer (eşleşmeyen entity eski davranış).
_CANON_JOIN = (
    "LEFT JOIN entity_aliases ea "
    "ON ea.alias_normalized = e.entity_normalized AND ea.entity_type = e.entity_type "
    "LEFT JOIN canonical_entities ce ON ce.id = ea.canonical_id"
)
_NORM_EXPR = "COALESCE(ce.canonical_normalized, e.entity_normalized)"
_NAME_EXPR = "COALESCE(MAX(ce.canonical_name), mode() WITHIN GROUP (ORDER BY e.entity_text))"
# cluster_key = kebab(entity_type) || ':' || kebab(canonical-veya-ham norm) → küme ile birebir
_CKEY_SQL = f"{_KEBAB.format(col='e.entity_type')} || ':' || {_KEBAB.format(col=_NORM_EXPR)}"


@dataclass(frozen=True)
class ClusterTrend:
    """Bir küme anahtarı için canlı trend metrikleri (pencere bazlı)."""

    trend_state: str  # breaking | developing | stable | fading | quiet
    relative_momentum: float | None
    burst_z: float
    article_count: int  # pencere içi distinct haber (cur)
    previous_article_count: int
    unique_sources: int
    spark: tuple[int, ...] = ()  # pencere-içi bucket-başına hacim (sparkline; canlı)


# pencere → (sparkline bucket sayısı, bucket saniyesi) — admin_trends.SPARKLINE_BUCKETS özeti
_BUCKETS: dict[int, tuple[int, int]] = {
    3_600: (6, 600),
    21_600: (6, 3_600),
    86_400: (12, 7_200),
    604_800: (7, 86_400),
}


async def trend_metrics_for_clusters(
    db: AsyncSession,
    cluster_keys: list[str],
    *,
    window_seconds: int,
    now: datetime,
) -> dict[str, ClusterTrend]:
    """Verilen küme anahtarları için canlı trend metrikleri (#1566 mantığıyla).

    `cluster_key` (`<type>:<kebab>`) → trend metriği. Korpus-normalize rel momentum
    (A) + pencere-içi burst (B) → `trend_state` (D). Eşleşmeyen anahtar dict'te YOK
    (çağıran 'quiet'/sessiz gösterir). Boş liste → boş dict (no-op).

    Verimli: yalnız anahtar-eşleşen entity'ler agg + sparkline; korpus baseline
    tek sorgu. ≤~50 anahtar (admin sayfa / user ilgi) için hedefli.
    """
    keys = sorted({k for k in cluster_keys if k})
    if not keys:
        return {}
    win_start = now - timedelta(seconds=window_seconds)
    prev_start = now - timedelta(seconds=2 * window_seconds)
    bucket_count, bucket_seconds = _BUCKETS.get(window_seconds, (12, max(1, window_seconds // 12)))
    base = {
        "win_start": win_start,
        "prev_start": prev_start,
        "now_ts": now,
        "etypes": list(_TREND_TYPES),
    }

    # korpus baseline (A) — pencere içi TOPLAM distinct entity'li haber (trend ile aynı)
    corpus = (
        await db.execute(
            text(
                """
                SELECT
                    count(DISTINCT a.id) FILTER (
                        WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                    ) AS cc,
                    count(DISTINCT a.id) FILTER (
                        WHERE a.published_at >= :prev_start AND a.published_at < :win_start
                    ) AS cp
                FROM articles a JOIN entities e ON e.article_id = a.id
                WHERE a.published_at >= :prev_start AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes
                """
            ).bindparams(bindparam("etypes", expanding=True)),
            base,
        )
    ).first()
    corpus_cur = int(corpus.cc or 0) if corpus else 0
    corpus_prev = int(corpus.cp or 0) if corpus else 0

    # anahtar-eşleşen entity'ler: cur/prev/uniq (kebab WHERE → yalnız ilgili entity'ler)
    agg = (
        await db.execute(
            text(
                f"""
                SELECT {_CKEY_SQL} AS ckey,
                    count(DISTINCT a.id) FILTER (
                        WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                    ) AS cur,
                    count(DISTINCT a.id) FILTER (
                        WHERE a.published_at >= :prev_start AND a.published_at < :win_start
                    ) AS prev,
                    count(DISTINCT a.source_id) FILTER (
                        WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                    ) AS uniq
                FROM entities e JOIN articles a ON a.id = e.article_id
                {_CANON_JOIN}
                WHERE a.published_at >= :prev_start AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes
                  AND ({_CKEY_SQL}) IN :keys
                GROUP BY 1
                """  # noqa: S608 — _CKEY_SQL sabit (kullanıcı girdisi değil); değerler bind
            ).bindparams(bindparam("etypes", expanding=True), bindparam("keys", expanding=True)),
            {**base, "keys": keys},
        )
    ).all()

    # sparkline bucket'ları (B — burst z) yalnız eşleşen anahtarlar için
    spark = (
        await db.execute(
            text(
                f"""
                SELECT {_CKEY_SQL} AS ckey,
                    floor(extract(epoch FROM (a.published_at - :win_start)) / :bsec)::int AS idx,
                    count(DISTINCT a.id) AS cnt
                FROM entities e JOIN articles a ON a.id = e.article_id
                {_CANON_JOIN}
                WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes
                  AND ({_CKEY_SQL}) IN :keys
                GROUP BY 1, 2
                """  # noqa: S608 — _CKEY_SQL sabit; değerler bind
            ).bindparams(bindparam("etypes", expanding=True), bindparam("keys", expanding=True)),
            {**base, "keys": keys, "bsec": bucket_seconds},
        )
    ).all()
    buckets: dict[str, dict[int, int]] = {}
    for s in spark:
        idx = max(0, min(bucket_count - 1, int(s.idx)))
        buckets.setdefault(s.ckey, {})[idx] = buckets.get(s.ckey, {}).get(idx, 0) + int(s.cnt)

    out: dict[str, ClusterTrend] = {}
    for r in agg:
        cur = int(r.cur or 0)
        prev = int(r.prev or 0)
        if cur == 0 and prev == 0:
            continue  # pencerede aktivite yok → 'quiet' (dict'te yer almaz)
        rel = compute_relative_momentum(cur, prev, corpus_cur, corpus_prev)
        blist = [int(buckets.get(r.ckey, {}).get(i, 0)) for i in range(bucket_count)]
        burst = compute_window_burst(blist)
        state = compute_trend_state(cur, prev, rel, burst) if cur > 0 else "quiet"
        out[r.ckey] = ClusterTrend(
            trend_state=state,
            relative_momentum=rel,
            burst_z=burst,
            article_count=cur,
            previous_article_count=prev,
            unique_sources=int(r.uniq or 0),
            spark=tuple(blist),  # bucket-başına hacim → sparkline (zaten hesaplandı)
        )
    return out


# yükselen durumlar (G boşluk radarı — "ilgisiz yükselen" adayları)
_RISING_STATES = frozenset({"breaking", "developing"})
_RISING_RANK = {"breaking": 2, "developing": 1}


@dataclass(frozen=True)
class RisingEntity:
    """Pencerede yükselen (breaking/developing) bir entity + küme anahtarı (G)."""

    cluster_key: str
    entity_name: str
    entity_type: str
    trend_state: str
    relative_momentum: float | None
    article_count: int
    unique_sources: int


async def rising_entities(
    db: AsyncSession,
    *,
    window_seconds: int,
    now: datetime,
    limit: int = 20,
    min_articles: int = 2,
    min_sources: int = 2,
    candidate_pool: int = 100,
) -> list[RisingEntity]:
    """Pencerede YÜKSELEN entity'ler (breaking/developing) + cluster_key (#1570 G).

    Gated agg (cur≥min_articles ∧ kaynak≥min_sources) → en yüksek hacimli
    `candidate_pool` aday → her biri için pencere-içi burst → #1566 trend_state;
    yalnız breaking/developing kalır, hacme göre sıralanıp `limit`'e kesilir.
    `cluster_key` (kebab) eklenir → çağıran research_clusters ile eşleşmeyenleri
    ('ilgisiz yükselen') seçer. Korpus-normalize (rel) confound'suz.
    """
    win_start = now - timedelta(seconds=window_seconds)
    prev_start = now - timedelta(seconds=2 * window_seconds)
    bucket_count, bucket_seconds = _BUCKETS.get(window_seconds, (12, max(1, window_seconds // 12)))
    base = {
        "win_start": win_start,
        "prev_start": prev_start,
        "now_ts": now,
        "etypes": list(_TREND_TYPES),
    }

    corpus = (
        await db.execute(
            text(
                """
                SELECT
                    count(DISTINCT a.id) FILTER (
                        WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                    ) AS cc,
                    count(DISTINCT a.id) FILTER (
                        WHERE a.published_at >= :prev_start AND a.published_at < :win_start
                    ) AS cp
                FROM articles a JOIN entities e ON e.article_id = a.id
                WHERE a.published_at >= :prev_start AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes
                """
            ).bindparams(bindparam("etypes", expanding=True)),
            base,
        )
    ).first()
    corpus_cur = int(corpus.cc or 0) if corpus else 0
    corpus_prev = int(corpus.cp or 0) if corpus else 0

    cand = (
        await db.execute(
            text(
                f"""
                SELECT {_NORM_EXPR} AS norm, e.entity_type AS etype,
                    {_CKEY_SQL} AS ckey,
                    {_NAME_EXPR} AS display,
                    count(DISTINCT a.id) FILTER (
                        WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                    ) AS cur,
                    count(DISTINCT a.id) FILTER (
                        WHERE a.published_at >= :prev_start AND a.published_at < :win_start
                    ) AS prev,
                    count(DISTINCT a.source_id) FILTER (
                        WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                    ) AS uniq
                FROM entities e JOIN articles a ON a.id = e.article_id
                {_CANON_JOIN}
                WHERE a.published_at >= :prev_start AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes
                GROUP BY {_NORM_EXPR}, e.entity_type
                HAVING count(DISTINCT a.id) FILTER (
                           WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                       ) >= :min_articles
                   AND count(DISTINCT a.source_id) FILTER (
                           WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                       ) >= :min_sources
                ORDER BY cur DESC
                LIMIT :pool
                """  # noqa: S608 — _CKEY_SQL sabit; değerler bind
            ).bindparams(bindparam("etypes", expanding=True)),
            {
                **base,
                "min_articles": min_articles,
                "min_sources": min_sources,
                "pool": candidate_pool,
            },
        )
    ).all()
    if not cand:
        return []

    norms = sorted({c.norm for c in cand})
    spark = (
        await db.execute(
            text(
                f"""
                SELECT {_NORM_EXPR} AS norm, e.entity_type AS etype,
                    floor(extract(epoch FROM (a.published_at - :win_start)) / :bsec)::int AS idx,
                    count(DISTINCT a.id) AS cnt
                FROM entities e JOIN articles a ON a.id = e.article_id
                {_CANON_JOIN}
                WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes AND ({_NORM_EXPR}) IN :norms
                GROUP BY 1, 2, 3
                """  # noqa: S608 — _NORM_EXPR sabit; değerler bind
            ).bindparams(bindparam("etypes", expanding=True), bindparam("norms", expanding=True)),
            {**base, "norms": norms, "bsec": bucket_seconds},
        )
    ).all()
    buckets: dict[tuple[str, str], dict[int, int]] = {}
    for s in spark:
        idx = max(0, min(bucket_count - 1, int(s.idx)))
        k = (s.norm, s.etype)
        buckets.setdefault(k, {})[idx] = buckets.get(k, {}).get(idx, 0) + int(s.cnt)

    rising: list[RisingEntity] = []
    for c in cand:
        cur = int(c.cur or 0)
        prev = int(c.prev or 0)
        rel = compute_relative_momentum(cur, prev, corpus_cur, corpus_prev)
        blist = [int(buckets.get((c.norm, c.etype), {}).get(i, 0)) for i in range(bucket_count)]
        state = compute_trend_state(cur, prev, rel, compute_window_burst(blist))
        if state not in _RISING_STATES:
            continue
        rising.append(
            RisingEntity(
                cluster_key=c.ckey,
                entity_name=c.display or c.norm,
                entity_type=c.etype,
                trend_state=state,
                relative_momentum=rel,
                article_count=cur,
                unique_sources=int(c.uniq or 0),
            )
        )
    rising.sort(
        key=lambda r: (
            _RISING_RANK.get(r.trend_state, 0),
            r.relative_momentum or 0,
            r.article_count,
        ),
        reverse=True,
    )
    return rising[:limit]


# =============================================================================
# F (#1579) — küme detayı: trend timeline (sparkline) + haberler + kaynaklar
# =============================================================================


@dataclass(frozen=True)
class SparkPoint:
    bucket_start: str
    article_count: int


@dataclass(frozen=True)
class DetailArticle:
    id: str
    title: str
    url: str | None
    published_at: str | None
    source_name: str | None


@dataclass(frozen=True)
class DetailSource:
    source_name: str | None
    article_count: int


@dataclass(frozen=True)
class ClusterSupplyDetail:
    """Bir küme için arz detayı: trend metriği + timeline + haberler + kaynaklar."""

    trend_state: str
    relative_momentum: float | None
    burst_z: float
    article_count: int
    unique_sources: int
    sparkline: list[SparkPoint]
    articles: list[DetailArticle]
    sources: list[DetailSource]


async def cluster_supply_detail(
    db: AsyncSession,
    cluster_key: str,
    *,
    window_seconds: int,
    now: datetime,
    limit: int = 20,
) -> ClusterSupplyDetail:
    """Küme anahtarı (`<type>:<kebab>`) için arz detayı (#1579 F).

    trend metriği (#1566) + pencere-içi sparkline timeline + son haberler (a.id
    dedup) + kaynak dağılımı — hepsi kebab-match (`_CKEY_SQL = cluster_key`).
    Salt-okuma; haber gövdesi DÖNMEZ (yalnız başlık/URL/kaynak).
    """
    metrics = await trend_metrics_for_clusters(
        db, [cluster_key], window_seconds=window_seconds, now=now
    )
    m = metrics.get(cluster_key)
    win_start = now - timedelta(seconds=window_seconds)
    bucket_count, bucket_seconds = _BUCKETS.get(window_seconds, (12, max(1, window_seconds // 12)))
    base = {
        "win_start": win_start,
        "now_ts": now,
        "etypes": list(_TREND_TYPES),
        "ckey": cluster_key,
    }

    sp = (
        await db.execute(
            text(
                f"""
                SELECT floor(extract(epoch FROM (a.published_at - :win_start)) / :bsec)::int AS idx,
                       count(DISTINCT a.id) AS cnt
                FROM entities e JOIN articles a ON a.id = e.article_id
                {_CANON_JOIN}
                WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes AND ({_CKEY_SQL}) = :ckey
                GROUP BY 1
                """  # noqa: S608 — _CKEY_SQL sabit; değerler bind
            ).bindparams(bindparam("etypes", expanding=True)),
            {**base, "bsec": bucket_seconds},
        )
    ).all()
    bmap = {int(r.idx): int(r.cnt) for r in sp}
    sparkline = [
        SparkPoint(
            bucket_start=(win_start + timedelta(seconds=i * bucket_seconds)).isoformat(),
            article_count=bmap.get(i, 0),
        )
        for i in range(bucket_count)
    ]

    arts = (
        await db.execute(
            text(
                f"""
                SELECT a.id::text AS id, a.title AS title, a.canonical_url AS url,
                       a.published_at AS pub, s.name AS source_name
                FROM entities e JOIN articles a ON a.id = e.article_id
                {_CANON_JOIN}
                LEFT JOIN sources s ON s.id = a.source_id
                WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes AND ({_CKEY_SQL}) = :ckey
                GROUP BY a.id, a.title, a.canonical_url, a.published_at, s.name
                ORDER BY a.published_at DESC
                LIMIT :lim
                """  # noqa: S608 — _CKEY_SQL sabit; değerler bind
            ).bindparams(bindparam("etypes", expanding=True)),
            {**base, "lim": limit},
        )
    ).all()
    articles = [
        DetailArticle(
            id=r.id,
            title=html.unescape(r.title or ""),
            url=r.url,
            published_at=r.pub.isoformat() if r.pub else None,
            source_name=r.source_name,
        )
        for r in arts
    ]

    srcs = (
        await db.execute(
            text(
                f"""
                SELECT s.name AS source_name, count(DISTINCT a.id) AS cnt
                FROM entities e JOIN articles a ON a.id = e.article_id
                {_CANON_JOIN}
                LEFT JOIN sources s ON s.id = a.source_id
                WHERE a.published_at >= :win_start AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes AND ({_CKEY_SQL}) = :ckey
                GROUP BY s.name ORDER BY cnt DESC
                """  # noqa: S608 — _CKEY_SQL sabit; değerler bind
            ).bindparams(bindparam("etypes", expanding=True)),
            base,
        )
    ).all()
    sources = [DetailSource(source_name=r.source_name, article_count=int(r.cnt)) for r in srcs]

    return ClusterSupplyDetail(
        trend_state=m.trend_state if m else "quiet",
        relative_momentum=m.relative_momentum if m else None,
        burst_z=m.burst_z if m else 0.0,
        article_count=m.article_count if m else sum(s.article_count for s in sources),
        unique_sources=m.unique_sources if m else len([s for s in sources if s.source_name]),
        sparkline=sparkline,
        articles=articles,
        sources=sources,
    )


# =============================================================================
# E-lite (#1586) — karşılanmamış ilgi → kapsayan kaynaklar (eyleme dönük boşluk)
# =============================================================================


async def coverage_sources_for_clusters(
    db: AsyncSession,
    cluster_keys: list[str],
    *,
    now: datetime,
    lookback_seconds: int = 2_592_000,  # 30 gün
    top_n: int = 5,
) -> dict[str, list[tuple[str, int]]]:
    """Verilen küme anahtarlarını TARİHSEL (lookback) hangi kaynaklar kapsadı.

    E-lite (#1586): "karşılanmamış ilgi" (yüksek talep, sessiz arz) entity'leri için
    admin'e "bu konuyu hangi kaynaklar yazıyor" sinyali → manuel kaynak ekleme/
    önceliklendirme. Crawler scheduling'e DOKUNMAZ (salt-okuma öneri). Boş liste =
    o entity'yi hiç kaynak kapsamamış (yeni kaynak adayı). {cluster_key: [(kaynak, n)]}.
    """
    keys = sorted({k for k in cluster_keys if k})
    if not keys:
        return {}
    since = now - timedelta(seconds=lookback_seconds)
    rows = (
        await db.execute(
            text(
                f"""
                SELECT {_CKEY_SQL} AS ckey, s.name AS source_name,
                       count(DISTINCT a.id) AS cnt
                FROM entities e JOIN articles a ON a.id = e.article_id
                {_CANON_JOIN}
                LEFT JOIN sources s ON s.id = a.source_id
                WHERE a.published_at >= :since AND a.published_at < :now_ts
                  AND e.entity_type IN :etypes AND ({_CKEY_SQL}) IN :keys
                GROUP BY 1, s.name
                """  # noqa: S608 — _CKEY_SQL sabit; değerler bind
            ).bindparams(bindparam("etypes", expanding=True), bindparam("keys", expanding=True)),
            {
                "since": since,
                "now_ts": now,
                "etypes": list(_TREND_TYPES),
                "keys": keys,
            },
        )
    ).all()
    by_key: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        by_key.setdefault(r.ckey, []).append((r.source_name or "—", int(r.cnt)))
    for k in by_key:
        by_key[k].sort(key=lambda x: x[1], reverse=True)
        by_key[k] = by_key[k][:top_n]
    return by_key
