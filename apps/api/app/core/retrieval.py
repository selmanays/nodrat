"""Vector retrieval (#22) — pgvector + freshness + reliability scoring.

PRD §2.7 (final retrieval score)
docs/engineering/data-model.md §4.1 (article_chunks)

Algoritma:
  1. Query embedding üret (NIM)
  2. Top-K candidate'i pgvector cosine_similarity ile çek (3-5x of needed)
  3. Final score:
     final_score = semantic*0.50 + freshness*0.25 + importance*0.15 + reliability*0.10
     (current mod: semantic*0.45 + freshness*0.35 + importance*0.10 + reliability*0.10)
  4. Sort by final_score desc, top-K döndür

Retrieval modes:
  - current  : son 24h → 48h → 72h fallback (PRD §2.9)
  - weekly   : Faz 2 (out of scope MVP-1 cut-list)
  - archive  : Faz 2

Kabul: latency hedef <200ms p50 (DB + embed call dahil değil — sadece SQL).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Türkçe sorgu normalize (#198)
# ---------------------------------------------------------------------------

# Türkçe için stop-token (kısa fonksiyon kelimesi). Çıktıda korunur ama
# trigram threshold'u hesaplanırken gerçek kelime sayısı bu listeyi atlar.
_TR_STOPWORDS = {"ve", "ile", "için", "bir", "bu", "şu", "mı", "mi", "mu", "mü"}


def _normalize_tr_query(text: str) -> str:
    """Türkçe sorgu normalize: lowercase + apostrof temizle + whitespace collapse.

    'CHP'li' → 'chpli', 'CHPli' → 'chpli', 'CHP’li' → 'chpli'

    Trigram benzerliği büyük/küçük harf duyarlı değil ama apostrof ayrıştırıyor.
    Aynı entity'nin farklı yazımları (CHP/CHP'li/CHP'nin) artık aynı normalize
    edilmiş forma çevrilir.
    """
    if not text:
        return ""
    # Unicode apostrof varyantları (', ', `, '’', 'ʼ')
    s = text.lower()
    for quote in ("'", "’", "ʼ", "`"):
        s = s.replace(quote, "")
    # Whitespace collapse
    return " ".join(s.split())


def _phrase_match_threshold(query: str) -> float:
    """Trigram filter eşiği — kısa query'lerde daha gevşek.

    'CHP' (3 char) gibi kısa query'ler postgres trigram ile dezavantajlı;
    eşiği düşürürüz. 'izmir çevre yolu' (16 char) için standart 0.15.
    """
    n = len(query)
    if n <= 3:
        return 0.05
    if n <= 6:
        return 0.10
    return 0.15


# Türkçe yardımcı kelimeler — phrase boost için anlamsız (gürültü).
# Tek başına geçen bu kelimelerin phrase match'i atlanır.
_TR_NOISE_WORDS = {
    "mi", "mı", "mu", "mü",
    "ne", "neden", "nasıl", "kim", "kime",
    "bu", "şu", "o", "bir",
    "ve", "ile", "için", "ama", "fakat", "ya", "yani",
    "çok", "az", "daha",
}


def _phrase_grams(query: str, n_min: int = 2, n_max: int = 4) -> list[str]:
    """Sorguyu 2/3/4-gram phrase'lere böler — her biri ayrı ILIKE match.

    'izmir çevre yolu ücretli mi olacak' →
        ['izmir çevre', 'çevre yolu', 'yolu ücretli', 'ücretli mi', 'mi olacak',
         'izmir çevre yolu', 'çevre yolu ücretli', 'yolu ücretli mi',
         'ücretli mi olacak',
         'izmir çevre yolu ücretli', 'çevre yolu ücretli mi',
         'yolu ücretli mi olacak']

    Sadece "noise" kelimelerden oluşan grup'lar (örn. 'mi olacak') filtrelenir.
    En az 1 anlamlı kelime içermeli + min 5 char.

    Args:
        query: normalize edilmiş query (lowercase, apostrofsuz)
        n_min/n_max: gram boyut sınırları (varsayılan 2-4)
    """
    if not query:
        return []
    words = [w for w in query.split() if w]
    if len(words) < n_min:
        return []

    grams: list[str] = []
    seen: set[str] = set()
    upper_n = min(n_max, len(words))
    for n in range(n_min, upper_n + 1):
        for i in range(len(words) - n + 1):
            chunk = words[i : i + n]
            # En az 1 anlamlı kelime şart
            if all(w in _TR_NOISE_WORDS for w in chunk):
                continue
            phrase = " ".join(chunk)
            if len(phrase) < 5:
                continue
            if phrase in seen:
                continue
            seen.add(phrase)
            grams.append(phrase)
    return grams


RetrievalMode = Literal["current", "weekly", "archive"]


# Score weight presets
WEIGHTS_DEFAULT = {
    "semantic": 0.50,
    "freshness": 0.25,
    "importance": 0.15,
    "reliability": 0.10,
}
WEIGHTS_CURRENT = {
    "semantic": 0.45,
    "freshness": 0.35,
    "importance": 0.10,
    "reliability": 0.10,
}

# Current mode time fallback levels (saat)
CURRENT_MODE_FALLBACKS_HOURS = (24, 48, 72)


@dataclass
class RetrievedChunk:
    """Tek arama sonucu — caller bu listeyle agenda card / generation yapar."""

    chunk_id: UUID
    article_id: UUID
    source_id: UUID
    chunk_index: int
    chunk_text: str
    article_title: str
    article_canonical_url: str
    source_name: str | None
    source_slug: str | None
    source_reliability: float
    published_at: datetime | None

    semantic_score: float
    """Cosine similarity (0..1) — pgvector 1 - cosine_distance"""

    freshness_score: float
    """Time-decay score (0..1)"""

    importance_score: float
    """Article-level importance — MVP-1: 0.5 placeholder, Faz 2 sonu calc"""

    reliability_score: float
    """Source reliability (0..1)"""

    final_score: float


@dataclass
class RetrievalReport:
    """Tüm arama sonucu + telemetri."""

    chunks: list[RetrievedChunk]
    mode_used: str
    """current_24h / current_48h / current_72h / weekly / archive"""

    candidate_count: int
    """SQL'den dönen aday sayısı (rerank öncesi)"""

    weights_used: dict[str, float]


# ============================================================================
# Score helpers
# ============================================================================


def freshness_decay(published_at: datetime | None, *, half_life_hours: float = 24.0) -> float:
    """Time-decay score: yeni → 1, eski → 0.

    Half-life modeli: half_life_hours geçtikçe skor /2.
    None published_at → 0.5 (orta).
    """
    if published_at is None:
        return 0.5
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    delta_hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
    if half_life_hours <= 0:
        return 1.0
    decay = math.pow(0.5, delta_hours / half_life_hours)
    return max(0.0, min(1.0, decay))


def compute_final_score(
    *,
    semantic: float,
    freshness: float,
    importance: float,
    reliability: float,
    weights: dict[str, float],
) -> float:
    return (
        semantic * weights["semantic"]
        + freshness * weights["freshness"]
        + importance * weights["importance"]
        + reliability * weights["reliability"]
    )


# ============================================================================
# Vector serialization
# ============================================================================


def _vector_to_pg_literal(vector: list[float]) -> str:
    """pgvector literal: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"


# ============================================================================
# SQL retrieval
# ============================================================================


async def _fetch_candidates(
    db: AsyncSession,
    *,
    query_vector: list[float],
    since: datetime | None,
    candidate_limit: int,
    source_id: UUID | None = None,
) -> list[dict]:
    """pgvector cosine similarity + JOIN sources.

    cosine_distance: 0 (identical) → 2 (opposite); semantic_score = 1 - cosine_distance/2
    pgvector <=> operator returns cosine distance (0 to 2).

    Note: hidden in raw SQL since article_chunks ORM model not defined yet.
    """
    vec_lit = _vector_to_pg_literal(query_vector)
    params: dict = {"vec": vec_lit, "limit": candidate_limit}
    where_clauses = ["c.embedding IS NOT NULL"]

    if since is not None:
        where_clauses.append(
            "(c.published_at IS NULL OR c.published_at >= :since)"
        )
        params["since"] = since

    if source_id is not None:
        where_clauses.append("c.source_id = :source_id")
        params["source_id"] = str(source_id)

    where_sql = " AND ".join(where_clauses)

    sql = sa_text(
        f"""
        SELECT
            c.id AS chunk_id,
            c.article_id,
            c.source_id,
            c.chunk_index,
            c.chunk_text,
            c.published_at,
            a.title AS article_title,
            a.canonical_url AS article_canonical_url,
            s.name AS source_name,
            s.slug AS source_slug,
            s.reliability_score AS source_reliability,
            (c.embedding <=> (:vec)::vector) AS distance
        FROM article_chunks c
        JOIN articles a ON a.id = c.article_id
        JOIN sources s ON s.id = c.source_id
        WHERE {where_sql}
        ORDER BY c.embedding <=> (:vec)::vector
        LIMIT :limit
        """
    )

    rows = (await db.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


# ============================================================================
# Public API
# ============================================================================


async def search(
    db: AsyncSession,
    *,
    query_vector: list[float],
    mode: RetrievalMode = "current",
    top_k: int = 10,
    candidate_multiplier: int = 5,
    source_id: UUID | None = None,
    custom_since: datetime | None = None,
    min_semantic_score: float = 0.55,
) -> RetrievalReport:
    """Top-K chunks için search.

    Args:
        query_vector: embedded user query (NIM çıktısı)
        mode: 'current' (default), 'weekly', 'archive'
        top_k: nihai döndürülecek sayı (default 10)
        candidate_multiplier: SQL'den top_k * mult kadar aday çekilir, sonra rerank
        source_id: opsiyonel kaynak filtresi
        custom_since: opsiyonel time filter override

    Returns:
        RetrievalReport (chunks + mode_used + candidate_count + weights)
    """
    if not query_vector:
        return RetrievalReport(
            chunks=[],
            mode_used=mode,
            candidate_count=0,
            weights_used=WEIGHTS_DEFAULT,
        )

    weights = WEIGHTS_CURRENT if mode == "current" else WEIGHTS_DEFAULT
    candidate_limit = max(top_k * candidate_multiplier, top_k)

    # Mode-specific time filter + fallback
    fallback_used: str = mode

    if mode == "current":
        # 24h → 48h → 72h fallback
        for hours in CURRENT_MODE_FALLBACKS_HOURS:
            since = (
                custom_since
                if custom_since is not None
                else datetime.now(timezone.utc) - timedelta(hours=hours)
            )
            rows = await _fetch_candidates(
                db,
                query_vector=query_vector,
                since=since,
                candidate_limit=candidate_limit,
                source_id=source_id,
            )
            if rows:
                fallback_used = f"current_{hours}h"
                break
        else:
            rows = []
    elif mode == "weekly":
        since = (
            custom_since
            if custom_since is not None
            else datetime.now(timezone.utc) - timedelta(days=7)
        )
        rows = await _fetch_candidates(
            db,
            query_vector=query_vector,
            since=since,
            candidate_limit=candidate_limit,
            source_id=source_id,
        )
    else:  # archive
        rows = await _fetch_candidates(
            db,
            query_vector=query_vector,
            since=custom_since,
            candidate_limit=candidate_limit,
            source_id=source_id,
        )

    # Score + rerank
    enriched: list[RetrievedChunk] = []
    for row in rows:
        # cosine_distance 0..2 → semantic 0..1 (cos distance / 2 reversed)
        cos_dist = float(row.get("distance") or 0)
        semantic = max(0.0, min(1.0, 1.0 - (cos_dist / 2.0)))

        published_at = row.get("published_at")
        freshness = freshness_decay(published_at)

        # importance MVP-1 placeholder — Faz 2 sonu source reliability * recency benzeri
        importance = 0.5

        reliability = float(row.get("source_reliability") or 0.7)

        final = compute_final_score(
            semantic=semantic,
            freshness=freshness,
            importance=importance,
            reliability=reliability,
            weights=weights,
        )

        enriched.append(
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                article_id=row["article_id"],
                source_id=row["source_id"],
                chunk_index=row["chunk_index"],
                chunk_text=row["chunk_text"],
                article_title=row["article_title"],
                article_canonical_url=row["article_canonical_url"],
                source_name=row["source_name"],
                source_slug=row["source_slug"],
                source_reliability=reliability,
                published_at=published_at,
                semantic_score=round(semantic, 4),
                freshness_score=round(freshness, 4),
                importance_score=round(importance, 4),
                reliability_score=round(reliability, 4),
                final_score=round(final, 4),
            )
        )

    # #157 — Halüsinasyon koruması: alakasız sonuçları filtrele.
    # Cosine sim < min_semantic_score → query ile gerçekten alakasız demek.
    # Empty result halinde insufficiency'e gider (PRD §3.4).
    if min_semantic_score > 0:
        before_count = len(enriched)
        enriched = [c for c in enriched if c.semantic_score >= min_semantic_score]
        filtered_out = before_count - len(enriched)
        if filtered_out > 0:
            import logging
            logging.getLogger(__name__).info(
                "retrieval.filtered_low_relevance count=%d threshold=%.2f",
                filtered_out,
                min_semantic_score,
            )

    enriched.sort(key=lambda c: c.final_score, reverse=True)
    top = enriched[:top_k]

    return RetrievalReport(
        chunks=top,
        mode_used=fallback_used,
        candidate_count=len(rows),
        weights_used=weights,
    )


# =============================================================================
# Hybrid search (#171 PR-E) — dense (cosine) + sparse (trigram) RRF fusion
# =============================================================================


async def hybrid_search_agenda_cards(
    db: AsyncSession,
    *,
    query_text: str,
    query_vector: list[float] | None,
    top_k: int = 10,
    candidate_pool: int = 30,
    min_semantic_score: float = 0.55,
    min_text_score: float = 0.15,
    rerank: bool = True,
    levels: tuple[str, ...] | None = ("daily",),
    timeframe_from: datetime | None = None,
    timeframe_to: datetime | None = None,
    geographic_focus: str | None = None,
) -> list[dict]:
    """Agenda card hybrid retrieval (PR-E).

    Strategy:
      1. Dense: cosine similarity (agenda_cards.embedding)
      2. Sparse: trigram similarity (title + summary, gin_trgm_ops index)
      3. RRF fusion: rank-based reciprocal sum
      4. Top-K döndür (top_k)

    Args:
        query_text: raw user query (planner topic_query enriched)
        query_vector: 1024-dim embedding (None ise sadece sparse)
        top_k: nihai döndürülecek kart sayısı
        candidate_pool: her layer'dan çekilecek aday (RRF input)
        min_semantic_score: dense filter eşiği (cosine_score)
        min_text_score: sparse filter eşiği (trigram similarity)

    Returns:
        list[dict] — agenda card row + retrieval metadata
        Boş liste → "kart yok / alakasız" demek
    """
    cleaned_query = (query_text or "").strip()
    if not cleaned_query:
        return []

    # #198 — Türkçe normalize: apostrof + lowercase
    norm_query = _normalize_tr_query(cleaned_query)
    if not norm_query or len(norm_query) < 2:
        return []

    has_dense = query_vector is not None and len(query_vector) == 1024

    # #182 — level filter (daily/weekly/monthly hierarchy)
    levels_tuple = tuple(levels) if levels else ("daily", "weekly", "monthly")
    level_placeholders = ", ".join(f"'{lvl}'" for lvl in levels_tuple)

    # #198 — dinamik trigram eşiği (kısa query'lerde daha gevşek)
    text_threshold = max(min_text_score, _phrase_match_threshold(norm_query))
    # ILIKE pattern — full sorgu için exact substring
    phrase_pattern = f"%{norm_query}%"
    # #200 — query'yi 2/3/4-gram phrase'lere böl (kısmi eşleşme için)
    phrase_grams = _phrase_grams(norm_query)
    # SQL ARRAY parametresi — her gram için ILIKE check
    phrase_grams_patterns = [f"%{g}%" for g in phrase_grams] if phrase_grams else []

    # #205 — timeframe filter clause (opsiyonel, plan.timeframes'ten geliyor)
    timeframe_clause = ""
    timeframe_params: dict = {}
    if timeframe_from is not None:
        timeframe_clause += " AND ec.last_seen_at >= :tf_from"
        timeframe_params["tf_from"] = timeframe_from
    if timeframe_to is not None:
        timeframe_clause += " AND ec.last_seen_at <= :tf_to"
        timeframe_params["tf_to"] = timeframe_to

    # #210 — geographic_focus filter (ISO 2-char). Sadece o ülkenin
    # kartlarını al; NULL veya farklı ülke ise reddet.
    # NOT: NULL kartlar = henüz re-rate olmamış; refresh_active_cards
    # tetiklendikçe dolar. Şimdilik dahil edilmez (false positive yok).
    geo_clause = ""
    geo_params: dict = {}
    if geographic_focus:
        geo_clause = " AND ac.country = :geo"
        geo_params["geo"] = geographic_focus.upper()

    # Sparse query — title + summary + canonical_title üzerinde
    # trigram match + n-gram phrase match (apostrof-bağımsız)
    sparse_rows = []
    sparse_sql = sa_text(
        f"""
        WITH norm AS (
            SELECT ac.id AS aid, ec.id AS eid,
                   LOWER(REPLACE(REPLACE(ac.title, '''', ''), '’', '')) AS t_norm,
                   LOWER(REPLACE(REPLACE(LEFT(ac.summary, 500), '''', ''), '’', '')) AS s_norm,
                   LOWER(REPLACE(REPLACE(ec.canonical_title, '''', ''), '’', '')) AS c_norm
            FROM agenda_cards ac
            JOIN event_clusters ec ON ec.id = ac.event_id
            WHERE ec.status IN ('active', 'developing', 'cooling')
              AND ac.level IN ({level_placeholders})
              {timeframe_clause}
              {geo_clause}
        )
        SELECT n.aid AS id,
               GREATEST(
                   similarity(n.t_norm, :q),
                   similarity(n.s_norm, :q),
                   similarity(n.c_norm, :q)
               ) AS text_score,
               (n.t_norm ILIKE :phrase OR n.s_norm ILIKE :phrase OR n.c_norm ILIKE :phrase)
                   AS phrase_match,
               -- #200 — n-gram phrase match sayısı (her bigram/trigram için)
               (
                   SELECT COUNT(*)::int FROM unnest(CAST(:phrase_grams AS text[])) g
                   WHERE n.t_norm ILIKE g OR n.s_norm ILIKE g OR n.c_norm ILIKE g
               ) AS gram_match_count
        FROM norm n
        WHERE n.t_norm % :q
           OR n.s_norm % :q
           OR n.c_norm % :q
           OR n.t_norm ILIKE :phrase OR n.s_norm ILIKE :phrase OR n.c_norm ILIKE :phrase
           OR EXISTS (
              SELECT 1 FROM unnest(CAST(:phrase_grams AS text[])) g
              WHERE n.t_norm ILIKE g OR n.s_norm ILIKE g OR n.c_norm ILIKE g
           )
        ORDER BY phrase_match DESC, gram_match_count DESC, text_score DESC
        LIMIT :pool
        """
    )
    try:
        sparse_rows = (
            await db.execute(
                sparse_sql,
                {
                    "q": norm_query,
                    "phrase": phrase_pattern,
                    "phrase_grams": phrase_grams_patterns or [""],
                    "pool": candidate_pool,
                    **timeframe_params,
                    **geo_params,
                },
            )
        ).mappings().all()
    except Exception as exc:
        logger.warning("hybrid sparse layer failed: %s", exc)

    # Dense query (PR-D mevcut path) + #205 timeframe filter
    dense_rows = []
    if has_dense:
        vec_lit = "[" + ",".join(f"{v:.7f}" for v in query_vector) + "]"
        dense_sql = sa_text(
            f"""
            SELECT ac.id,
                   1.0 - ((ac.embedding <=> (:vec)::vector) / 2.0) AS semantic_score
            FROM agenda_cards ac
            JOIN event_clusters ec ON ec.id = ac.event_id
            WHERE ec.status IN ('active', 'developing', 'cooling')
              AND ac.level IN ({level_placeholders})
              AND ac.embedding IS NOT NULL
              {timeframe_clause}
              {geo_clause}
            ORDER BY ac.embedding <=> (:vec)::vector
            LIMIT :pool
            """
        )
        try:
            dense_rows = (
                await db.execute(
                    dense_sql,
                    {
                        "vec": vec_lit,
                        "pool": candidate_pool,
                        **timeframe_params,
                        **geo_params,
                    },
                )
            ).mappings().all()
        except Exception as exc:
            logger.warning("hybrid dense layer failed: %s", exc)

    # RRF fusion (Reciprocal Rank Fusion) — k=60 standart
    K_RRF = 60.0
    PHRASE_BOOST = 0.05  # #198 — exact full phrase match → +0.05
    GRAM_BOOST = 0.025  # #200 — her n-gram phrase match → +0.025
    rrf: dict[str, float] = {}
    score_meta: dict[str, dict] = {}

    for rank, row in enumerate(sparse_rows, start=1):
        ts = float(row["text_score"])
        is_phrase = bool(row.get("phrase_match", False))
        gram_count = int(row.get("gram_match_count", 0) or 0)
        # #198/#200 — phrase ya da n-gram match olanları trigram threshold'a takılmadan al
        if not is_phrase and gram_count == 0 and ts < text_threshold:
            continue
        cid = str(row["id"])
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K_RRF + rank)
        if is_phrase:
            rrf[cid] += PHRASE_BOOST
            score_meta.setdefault(cid, {})["phrase_match"] = True
        if gram_count > 0:
            rrf[cid] += min(gram_count * GRAM_BOOST, 0.10)  # max +0.10 cap
            score_meta.setdefault(cid, {})["gram_match_count"] = gram_count
        score_meta.setdefault(cid, {})["text_score"] = ts

    for rank, row in enumerate(dense_rows, start=1):
        if float(row["semantic_score"]) < min_semantic_score:
            continue
        cid = str(row["id"])
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K_RRF + rank)
        score_meta.setdefault(cid, {})["semantic_score"] = float(row["semantic_score"])

    if not rrf:
        return []

    # Top-K sıralaması
    sorted_ids = sorted(rrf.keys(), key=lambda x: rrf[x], reverse=True)[:top_k]

    # Full agenda card data fetch
    in_clause = ", ".join(f"'{cid}'::uuid" for cid in sorted_ids)
    full_sql = sa_text(
        f"""
        SELECT ac.id, ac.title, ac.summary, ac.key_points,
               ac.content_angles, ac.source_refs, ac.status,
               ac.importance_score, ac.freshness_score, ac.event_id
        FROM agenda_cards ac
        WHERE ac.id IN ({in_clause})
        """
    )
    full_rows = (await db.execute(full_sql)).mappings().all()
    by_id = {str(r["id"]): dict(r) for r in full_rows}

    results = []
    for cid in sorted_ids:
        if cid not in by_id:
            continue
        row = by_id[cid]
        row["_rrf_score"] = rrf[cid]
        row["_score_meta"] = score_meta.get(cid, {})
        results.append(row)

    logger.info(
        "hybrid_agenda dense=%d sparse=%d fused=%d pre_rerank=%d",
        len(dense_rows),
        len(sparse_rows),
        len(rrf),
        len(results),
    )

    # #181 — Cross-encoder rerank stage (toggle: settings.reranker_enabled)
    if rerank and len(results) > 1:
        from app.core.rerank import rerank_rows

        results = await rerank_rows(
            query=cleaned_query,
            rows=results,
            top_k=top_k,
        )
    return results


async def hybrid_search_chunks(
    db: AsyncSession,
    *,
    query_text: str,
    query_vector: list[float] | None,
    top_k: int = 10,
    candidate_pool: int = 30,
    since_hours: int = 168,
    min_semantic_score: float = 0.50,
    rerank: bool = True,
) -> list[dict]:
    """Article chunk hybrid retrieval — PR-D agenda boş ise fallback (PR-E).

    Article-level metadata içerir (singleton cluster article'ları için kritik).
    Generator'a 'supplementary_chunks' olarak gider.
    """
    cleaned = (query_text or "").strip()
    if not cleaned:
        return []

    # #198 — Türkçe normalize (apostrof + lowercase)
    norm_query = _normalize_tr_query(cleaned)
    if not norm_query or len(norm_query) < 2:
        return []
    text_threshold = max(0.10, _phrase_match_threshold(norm_query))
    phrase_pattern = f"%{norm_query}%"
    # #200 — n-gram phrase'ler (kısmi eşleşme)
    phrase_grams_patterns = [f"%{g}%" for g in _phrase_grams(norm_query)]

    has_dense = query_vector is not None and len(query_vector) == 1024
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    # Sparse — normalized chunk_text + phrase + n-gram match
    sparse_rows = []
    try:
        sparse_rows = (
            await db.execute(
                sa_text(
                    """
                    WITH norm AS (
                        SELECT c.id, c.article_id, c.published_at,
                               LOWER(REPLACE(REPLACE(c.chunk_text, '''', ''), '’', '')) AS t_norm
                        FROM article_chunks c
                        JOIN articles a ON a.id = c.article_id
                        WHERE c.published_at IS NULL OR c.published_at >= :since
                    )
                    SELECT n.id, n.article_id,
                           similarity(n.t_norm, :q) AS text_score,
                           n.t_norm ILIKE :phrase AS phrase_match,
                           (
                               SELECT COUNT(*)::int FROM unnest(CAST(:phrase_grams AS text[])) g
                               WHERE n.t_norm ILIKE g
                           ) AS gram_match_count
                    FROM norm n
                    WHERE n.t_norm % :q
                       OR n.t_norm ILIKE :phrase
                       OR EXISTS (SELECT 1 FROM unnest(CAST(:phrase_grams AS text[])) g WHERE n.t_norm ILIKE g)
                    ORDER BY phrase_match DESC, gram_match_count DESC, text_score DESC
                    LIMIT :pool
                    """
                ),
                {
                    "q": norm_query,
                    "phrase": phrase_pattern,
                    "phrase_grams": phrase_grams_patterns or [""],
                    "since": since,
                    "pool": candidate_pool,
                },
            )
        ).mappings().all()
    except Exception as exc:
        logger.warning("chunks sparse failed: %s", exc)

    # Dense
    dense_rows = []
    if has_dense:
        vec_lit = "[" + ",".join(f"{v:.7f}" for v in query_vector) + "]"
        try:
            dense_rows = (
                await db.execute(
                    sa_text(
                        """
                        SELECT c.id,
                               c.article_id,
                               1.0 - ((c.embedding <=> (:vec)::vector) / 2.0) AS semantic_score
                        FROM article_chunks c
                        WHERE c.embedding IS NOT NULL
                          AND (c.published_at IS NULL OR c.published_at >= :since)
                        ORDER BY c.embedding <=> (:vec)::vector
                        LIMIT :pool
                        """
                    ),
                    {"vec": vec_lit, "since": since, "pool": candidate_pool},
                )
            ).mappings().all()
        except Exception as exc:
            logger.warning("chunks dense failed: %s", exc)

    # RRF + phrase boost (#198) + n-gram boost (#200)
    K_RRF = 60.0
    PHRASE_BOOST = 0.05
    GRAM_BOOST = 0.025
    rrf: dict[str, float] = {}
    for rank, row in enumerate(sparse_rows, start=1):
        ts = float(row["text_score"])
        is_phrase = bool(row.get("phrase_match", False))
        gram_count = int(row.get("gram_match_count", 0) or 0)
        if not is_phrase and gram_count == 0 and ts < text_threshold:
            continue
        cid = str(row["id"])
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K_RRF + rank)
        if is_phrase:
            rrf[cid] += PHRASE_BOOST
        if gram_count > 0:
            rrf[cid] += min(gram_count * GRAM_BOOST, 0.10)
    for rank, row in enumerate(dense_rows, start=1):
        if float(row["semantic_score"]) < min_semantic_score:
            continue
        cid = str(row["id"])
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K_RRF + rank)

    if not rrf:
        return []

    sorted_ids = sorted(rrf.keys(), key=lambda x: rrf[x], reverse=True)[:top_k]
    in_clause = ", ".join(f"'{cid}'::uuid" for cid in sorted_ids)

    full_rows = (
        await db.execute(
            sa_text(
                f"""
                SELECT c.id AS chunk_id,
                       c.article_id,
                       c.chunk_text,
                       c.published_at,
                       a.title AS article_title,
                       a.canonical_url AS article_canonical_url,
                       s.name AS source_name,
                       s.slug AS source_slug
                FROM article_chunks c
                JOIN articles a ON a.id = c.article_id
                JOIN sources s ON s.id = a.source_id
                WHERE c.id IN ({in_clause})
                """
            )
        )
    ).mappings().all()

    by_id = {str(r["chunk_id"]): dict(r) for r in full_rows}
    results = [by_id[cid] for cid in sorted_ids if cid in by_id]

    logger.info(
        "hybrid_chunks dense=%d sparse=%d fused=%d pre_rerank=%d",
        len(dense_rows),
        len(sparse_rows),
        len(rrf),
        len(results),
    )

    # #181 — Cross-encoder rerank stage
    if rerank and len(results) > 1:
        from app.core.rerank import rerank_rows

        results = await rerank_rows(
            query=cleaned,
            rows=results,
            top_k=top_k,
        )
    return results
