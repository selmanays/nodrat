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
# cluster_key = kebab(entity_type) || ':' || kebab(entity_normalized)
_CKEY_SQL = (
    f"{_KEBAB.format(col='e.entity_type')} || ':' || {_KEBAB.format(col='e.entity_normalized')}"
)


@dataclass(frozen=True)
class ClusterTrend:
    """Bir küme anahtarı için canlı trend metrikleri (pencere bazlı)."""

    trend_state: str  # breaking | developing | stable | fading | quiet
    relative_momentum: float | None
    burst_z: float
    article_count: int  # pencere içi distinct haber (cur)
    previous_article_count: int
    unique_sources: int


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
        )
    return out
