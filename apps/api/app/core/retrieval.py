"""Vector retrieval (#22) — pgvector + freshness + RRF + NER scoring.

PRD §2.7 (retrieval score)
docs/engineering/data-model.md §4.1 (article_chunks)

Mevcut algoritma (#198/#647/#667/#691):
  1. Query embedding üret (bge-m3 free | e5 paid — provider registry)
  2. Sparse (BM25/text) + dense (cosine) candidate'leri çek
  3. RRF (Reciprocal Rank Fusion) ile fusion (K_RRF=60)
     - Sparse stream: K=60 + phrase boost (+0.05) + n-gram boost (+0.025 each)
     - Dense stream: K=60
     - Summary stream: K=80 (#661 Faz 5.2 — title + subtitle + lead embed)
     - NER stream: K=20 (multi_and) | K=30 (single_rare) (#691 Faz 6.1, PR #693)
  4. (Opsiyonel) LLM rerank — top-N candidate'i cross-encoder ile yeniden sırala
  5. Parent-doc retrieval — article başına en iyi N chunk'ı topla

Retrieval modes:
  - current  : son 24h → 48h → 72h fallback (PRD §2.9)
  - weekly   : Faz 2 (out of scope MVP-1 cut-list)
  - archive  : Faz 2

NOT: "final_score = semantic*W1 + freshness*W2 + ..." formülü #198 ÖNCESI
sistem; artık RRF + boost'lar kullanılıyor. Sadece freshness_decay + compute_final_score
helper'ları agenda_cards path'inde sıralama assist için var (test'ler bunlara dayalı).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

# Internal helpers (PR-B/C internal split — T6 #1085).
# Quote/phrase/vector/scoring pure helpers ayrı `_retrieval_*.py` modüllerine
# taşındı (davranış değişmedi; pure refactor). Public surface re-export ile
# `app.core.retrieval` üzerinden korunur — caller'lar etkilenmez.
from app.core._retrieval_phrase import (
    _QUOTE_CHARS_FOR_SQL,
    _QUOTE_CHARS_TO_STRIP,
    _TR_NOISE_WORDS,
    _build_sql_quote_strip,
    _phrase_grams,
    _phrase_match_threshold,
    normalize_tr_query,
    strip_quote_variants,
)
from app.core._retrieval_scoring import (
    CURRENT_MODE_FALLBACKS_HOURS,
    WEIGHTS_CURRENT,
    WEIGHTS_DEFAULT,
    RetrievalMode,
    RetrievalReport,
    RetrievedChunk,
    compute_final_score,
    freshness_decay,
)
from app.core._retrieval_vector import (
    _parse_pgvector_text,
    _vector_to_pg_literal,
)

# Re-export public + private surface for backward-compat (T6 P5 PR-B/C internal split).
# Caller'lar `from app.core.retrieval import X` ile bu sembolleri ÇALIŞMAYA DEVAM eder.
# `__all__` aynı zamanda ruff F401 unused-import'u önler.
__all__ = [
    "CURRENT_MODE_FALLBACKS_HOURS",
    "WEIGHTS_CURRENT",
    "WEIGHTS_DEFAULT",
    "_QUOTE_CHARS_FOR_SQL",
    "_QUOTE_CHARS_TO_STRIP",
    "_TR_NOISE_WORDS",
    "RetrievalMode",
    "RetrievalReport",
    "RetrievedChunk",
    "_build_sql_quote_strip",
    "_normalize_tr_query",
    "_parse_pgvector_text",
    "_phrase_grams",
    "_phrase_match_threshold",
    "_vector_to_pg_literal",
    "compute_final_score",
    "freshness_decay",
    "normalize_tr_query",
    "strip_quote_variants",
]

# Backward-compat alias (#397 — eski private isim için)
_normalize_tr_query = normalize_tr_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# #691 — NER entity scoring overhaul (IDF threshold + multi-entity AND)
# ---------------------------------------------------------------------------
# Faz 6 NER pipeline'ı 9 article entity'liyken ölçüldü (recall@5 45.5%→63.6%).
# NER backfill ile 4391 article entity'li → ILIKE '%X%' 20+ article match →
# her birine aynı K=30 RRF bonus → sinyal sulandı, kazanım silindi.
# Çözüm: entity rarity (df) tabanlı filtre + multi-entity AND match.
# Default değerler — settings_store override edebilir (#696 B7+C8).
# Admin /settings retrieval group üzerinden runtime tunable.
NER_DF_THRESHOLD = 30  # df < N → "nadir" entity (boost eligibility; ~%0.67 of 4436 corpus)
NER_BOOST_K_MULTI = 5  # 2+ rare entity intersect → EN güçlü (#718 final: 1/6≈0.167, sparse+gram+phrase combo'yu garantili geçer)
NER_BOOST_K_SINGLE_RARE = 15  # tek rare entity (#718 final: 1/16≈0.063, Faz 6 K=30'tan 4x güçlü)
NER_FETCH_PER_ENTITY_LIMIT = 100  # her entity için max article (df sayımı için)
NER_FINAL_AIDS_CAP = 30  # rerank pipeline'a giden max article

# RRF (Reciprocal Rank Fusion) defaults — #198 hybrid stream
RRF_K = 60.0  # sparse + dense base K
RRF_K_SUMMARY = 80.0  # #661 Faz 5.2 summary stream (zayıf weight)
RRF_PHRASE_BOOST = 0.05  # #198 exact phrase match
RRF_PHRASE_BOOST_NER_MODE = 0.03  # #718 mode-aware: NER multi_and varsa sparse phrase boost düşer
RRF_GRAM_BOOST = 0.025  # #200 n-gram per match (capped 0.10)


async def _load_retrieval_settings(db) -> dict[str, float]:
    """#696 B7+C8 — Runtime tunable retrieval config (NER + RRF).

    Settings store L1 cache ile DB hit ~100µs; her hybrid_search çağrısının
    başında bir defa çağırılır. UI'dan değiştirilince Redis pub/sub ile L1
    invalidate olur, sonraki sorgu yeni değeri görür.

    Hardcoded sabitler default olarak kullanılır; settings_store override
    edebilir.
    """
    from app.shared.runtime_config.settings_store import settings_store

    return {
        "ner_df_threshold": await settings_store.get_int(
            db, "retrieval.ner_df_threshold", NER_DF_THRESHOLD
        ),
        "ner_k_multi": await settings_store.get_int(db, "retrieval.ner_k_multi", NER_BOOST_K_MULTI),
        "ner_k_single_rare": await settings_store.get_int(
            db, "retrieval.ner_k_single_rare", NER_BOOST_K_SINGLE_RARE
        ),
        "ner_fetch_per_entity_limit": await settings_store.get_int(
            db, "retrieval.ner_fetch_per_entity_limit", NER_FETCH_PER_ENTITY_LIMIT
        ),
        "ner_final_aids_cap": await settings_store.get_int(
            db, "retrieval.ner_final_aids_cap", NER_FINAL_AIDS_CAP
        ),
        "rrf_k": await settings_store.get_float(db, "retrieval.rrf_k", RRF_K),
        "rrf_k_summary": await settings_store.get_float(
            db, "retrieval.rrf_k_summary", RRF_K_SUMMARY
        ),
        "rrf_phrase_boost": await settings_store.get_float(
            db, "retrieval.rrf_phrase_boost", RRF_PHRASE_BOOST
        ),
        "rrf_phrase_boost_ner_mode": await settings_store.get_float(
            db, "retrieval.rrf_phrase_boost_ner_mode", RRF_PHRASE_BOOST_NER_MODE
        ),
        "rrf_gram_boost": await settings_store.get_float(
            db, "retrieval.rrf_gram_boost", RRF_GRAM_BOOST
        ),
    }


def _resolve_ner_target_aids(
    aids_per_ent: dict[str, set[str]],
    df_map: dict[str, int],
    df_threshold: int = NER_DF_THRESHOLD,
) -> tuple[set[str], str]:
    """Pure logic: aids_per_ent + df_map → (target_aids, mode).

    Mantık (priority order):
    1. 2+ rare entity (df<threshold) → intersect → "multi_and"
       Boş intersect → en nadir tek entity → "single_rare"
    2. 1 rare entity → "single_rare"
    3. 0 rare, 2+ common entity → AND intersect dar (<threshold) → "multi_and_common"
    4. Hiçbiri → "no_match"
    """
    if not aids_per_ent:
        return set(), "no_match"

    rare = [e for e in aids_per_ent if df_map.get(e, 0) < df_threshold]

    if len(rare) >= 2:
        target = set.intersection(*[aids_per_ent[e] for e in rare])
        if target:
            return target, "multi_and"
        # Intersect boş → en nadir entity tek başına
        target = aids_per_ent[min(rare, key=lambda e: df_map[e])]
        return target, "single_rare"
    elif len(rare) == 1:
        return aids_per_ent[rare[0]], "single_rare"
    else:
        # Hiç rare yok — multi-entity AND ile narrow (Karşıyaka + Bursaspor)
        all_ents = list(aids_per_ent.keys())
        if len(all_ents) >= 2:
            intersect = set.intersection(*[aids_per_ent[e] for e in all_ents])
            if 0 < len(intersect) < df_threshold:
                return intersect, "multi_and_common"

    return set(), "no_match"


async def _ner_idf_match_aids(
    db: AsyncSession,
    query_entities: list[str],
    *,
    config: dict[str, float] | None = None,
) -> tuple[set[str], str, dict[str, int]]:
    """
    Query entity'leri için article id seti döndür — IDF + multi-entity AND.

    DB tarafı: her entity için exact match → ILIKE fallback.
    Pure logic `_resolve_ner_target_aids`'e delege edilir.

    `config` opsiyonel (test ile geçici overrider'lar); None ise
    `_load_retrieval_settings(db)` ile DB-backed runtime config okunur.

    Returns: (target_aids, mode, df_map)
    """
    if config is None:
        config = await _load_retrieval_settings(db)
    fetch_limit = int(config.get("ner_fetch_per_entity_limit", NER_FETCH_PER_ENTITY_LIMIT))
    df_threshold = int(config.get("ner_df_threshold", NER_DF_THRESHOLD))

    aids_per_ent: dict[str, set[str]] = {}
    df_map: dict[str, int] = {}

    for ent in query_entities[:5]:
        ent_norm = ent.lower().strip()
        if len(ent_norm) < 3:
            continue
        try:
            # 1. Exact match first (en güvenilir — "Karşıyaka" = "Karşıyaka")
            exact_rows = (
                (
                    await db.execute(
                        sa_text(
                            """
                        SELECT DISTINCT article_id::text AS aid
                        FROM entities
                        WHERE entity_normalized = :ent_norm
                        LIMIT :lim
                        """
                        ),
                        {"ent_norm": ent_norm, "lim": fetch_limit},
                    )
                )
                .mappings()
                .all()
            )

            if exact_rows:
                aids = {r["aid"] for r in exact_rows}
            else:
                # 2. ILIKE fallback ("Karşıyaka" → "Karşıyaka SK" eşleşmesi için)
                ilike_rows = (
                    (
                        await db.execute(
                            sa_text(
                                """
                            SELECT DISTINCT article_id::text AS aid
                            FROM entities
                            WHERE entity_normalized ILIKE :pattern
                            LIMIT :lim
                            """
                            ),
                            {
                                "pattern": f"%{ent_norm}%",
                                "lim": fetch_limit,
                            },
                        )
                    )
                    .mappings()
                    .all()
                )
                aids = {r["aid"] for r in ilike_rows}

            if aids:
                aids_per_ent[ent] = aids
                df_map[ent] = len(aids)
        except Exception as exc:
            logger.warning("ner idf lookup failed for %r: %s", ent, exc)

    target, mode = _resolve_ner_target_aids(
        aids_per_ent,
        df_map,
        df_threshold=df_threshold,
    )
    # #696 (B5) — Mode telemetri (process-local counter, /admin/rag/ner-stats)
    try:
        from app.shared.observability import ner_stats

        ner_stats.record(mode)
    except Exception:  # noqa: S110
        pass
    return target, mode, df_map


# ---------------------------------------------------------------------------
# Türkçe sorgu normalize (#198)
# ---------------------------------------------------------------------------

# Türkçe için stop-token (kısa fonksiyon kelimesi). Çıktıda korunur ama
# trigram threshold'u hesaplanırken gerçek kelime sayısı bu listeyi atlar.
_TR_STOPWORDS = {"ve", "ile", "için", "bir", "bu", "şu", "mı", "mi", "mu", "mü"}


# #647 — Kök sebep: SQL REPLACE chain'i sadece chr(39) ve U+2019 siliyordu.
# Bianet "Toprakaltı" (curly double quote) → sparse phrase match patladı.
# Tüm major quote varyantları (single/double, asciiUTF, smart, low-9, guillemets)
# tek noktadan normalize edilir. Hem Python tarafında (normalize_tr_query) hem de
# SQL tarafında aynı fonksiyon kullanılır → eşleşme deterministik.


# Vector serialization
# ============================================================================


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
        where_clauses.append("(c.published_at IS NULL OR c.published_at >= :since)")
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
                else datetime.now(UTC) - timedelta(hours=hours)
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
        since = custom_since if custom_since is not None else datetime.now(UTC) - timedelta(days=7)
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
    candidate_pool: int | None = None,
    min_semantic_score: float | None = None,
    min_text_score: float | None = None,
    rerank: bool = True,
    levels: tuple[str, ...] | None = ("daily",),
    timeframe_from: datetime | None = None,
    timeframe_to: datetime | None = None,
    geographic_focus: str | None = None,
    pre_normalized: str | None = None,
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
        pre_normalized: handler tarafından normalize edilmiş query (#397 MVP-2.1).
            None ise lokal `normalize_tr_query` çağrısı yapılır (backward-compat).

    Returns:
        list[dict] — agenda card row + retrieval metadata
        Boş liste → "kart yok / alakasız" demek
    """
    cleaned_query = (query_text or "").strip()
    if not cleaned_query:
        return []

    # #198 — Türkçe normalize: apostrof + lowercase
    # #397 — handler tarafında pre-normalized geçirildiyse re-normalize etme
    norm_query = pre_normalized if pre_normalized is not None else normalize_tr_query(cleaned_query)
    if not norm_query or len(norm_query) < 2:
        return []

    # #270 — runtime override (admin paneli)
    if candidate_pool is None or min_semantic_score is None or min_text_score is None:
        try:
            from app.shared.runtime_config.settings_store import settings_store

            if candidate_pool is None:
                candidate_pool = await settings_store.get_int(db, "retrieval.candidate_pool", 30)
            if min_semantic_score is None:
                min_semantic_score = await settings_store.get_float(
                    db, "retrieval.min_semantic_score", 0.55
                )
            if min_text_score is None:
                min_text_score = await settings_store.get_float(
                    db, "retrieval.min_text_score", 0.15
                )
        except Exception as exc:  # pragma: no cover
            logger.debug("retrieval settings load fallback: %s", exc)
            candidate_pool = candidate_pool or 30
            min_semantic_score = min_semantic_score or 0.55
            min_text_score = min_text_score or 0.15

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

    # #205/#213 — timeframe filter: first_seen_at (olayın ilk gözlem zamanı).
    # last_seen_at YANLIŞTI — eski cluster'a yeni article eklenince update
    # oluyordu, "son 2 saat" filtresine dünkü olay sızıyordu.
    timeframe_clause = ""
    timeframe_params: dict = {}
    if timeframe_from is not None:
        timeframe_clause += " AND ec.first_seen_at >= :tf_from"
        timeframe_params["tf_from"] = timeframe_from
    if timeframe_to is not None:
        timeframe_clause += " AND ec.first_seen_at <= :tf_to"
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
    # trigram match + n-gram phrase match (quote-bağımsız, #647 root fix)
    sparse_rows = []
    # #927 Faz-A — C-locale `LOWER()` Türkçe büyük harfi (İŞÇÖÜĞI)
    # küçültmez; agenda-card sparse path Türkçe-entity'yi (Özgür Özel,
    # Çin, İzmir) trigram/ILIKE'de kaçırıyordu. #939 RESCUE/FILTER
    # (retrieval.py:1681/1684) pattern'i birebir: LOWER(<expr> COLLATE
    # "tr-TR-x-icu"). Python parametre (:q/:phrase) zaten .lower() →
    # değişmez; RRF/operatör/parent-doc DEĞİŞMEZ. (V2 bu yolu ölçmez —
    # D2; prod-trace smoke ile doğrulanır.)
    title_norm_sql = f'LOWER({_build_sql_quote_strip("ac.title")} COLLATE "tr-TR-x-icu")'
    summary_norm_sql = (
        f'LOWER({_build_sql_quote_strip("LEFT(ac.summary, 500)")} COLLATE "tr-TR-x-icu")'
    )
    canon_norm_sql = f'LOWER({_build_sql_quote_strip("ec.canonical_title")} COLLATE "tr-TR-x-icu")'
    sparse_sql = sa_text(
        f"""
        WITH norm AS (
            SELECT ac.id AS aid, ec.id AS eid,
                   {title_norm_sql} AS t_norm,
                   {summary_norm_sql} AS s_norm,
                   {canon_norm_sql} AS c_norm
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
            (
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
            )
            .mappings()
            .all()
        )
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
                (
                    await db.execute(
                        dense_sql,
                        {
                            "vec": vec_lit,
                            "pool": candidate_pool,
                            **timeframe_params,
                            **geo_params,
                        },
                    )
                )
                .mappings()
                .all()
            )
        except Exception as exc:
            logger.warning("hybrid dense layer failed: %s", exc)

    # RRF fusion (Reciprocal Rank Fusion) — #696 B7+C8: runtime tunable
    _retr_cfg_agenda = await _load_retrieval_settings(db)
    K_RRF = float(_retr_cfg_agenda["rrf_k"])
    GRAM_BOOST = float(_retr_cfg_agenda["rrf_gram_boost"])

    # #718 — NER ENTITY EXTRACT'i sparse loop'tan ÖNCE çalıştır (mode bilinmeli).
    # Mode-aware phrase boost: NER multi_and tetiklendiyse phrase boost düşer
    # (niş entity sorgularda yaygın "kaç bitti" gibi cards'larının üste çıkmasını önle).
    # NER RRF stream bonus EKLEME işi yine sparse/dense loop'tan sonra.
    try:
        from app.core.rerank import _extract_entity_candidates

        _ner_query_entities = _extract_entity_candidates(norm_query, min_len=3)
    except Exception as _ner_exc:
        logger.warning("ner entity extract failed: %s", _ner_exc)
        _ner_query_entities = []

    _ner_card_ids: list[str] = []
    _ner_mode = "no_match"
    _ner_df_map: dict[str, int] = {}
    if _ner_query_entities:
        try:
            _ner_target_aids, _ner_mode, _ner_df_map = await _ner_idf_match_aids(
                db,
                _ner_query_entities,
                config=_retr_cfg_agenda,
            )
            if _ner_target_aids:
                _aid_list = list(_ner_target_aids)[: int(_retr_cfg_agenda["ner_final_aids_cap"])]
                _aid_in = ", ".join(f"'{a}'::uuid" for a in _aid_list)
                # article_id → event_articles → agenda_cards JOIN
                _ner_card_rows = (
                    (
                        await db.execute(
                            sa_text(
                                f"""
                            SELECT DISTINCT ac.id::text AS card_id
                            FROM agenda_cards ac
                            JOIN event_articles ea ON ea.event_id = ac.event_id
                            WHERE ea.article_id IN ({_aid_in})
                            """
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
                _ner_card_ids = [r["card_id"] for r in _ner_card_rows]
                logger.info(
                    "ner_idf_match_cards q_ents=%d df=%s mode=%s aids=%d cards=%d",
                    len(_ner_query_entities),
                    dict(_ner_df_map.items()),
                    _ner_mode,
                    len(_ner_target_aids),
                    len(_ner_card_ids),
                )
        except Exception as exc:
            logger.warning("ner cards mapping failed: %s", exc)

    # #718 mode-aware phrase boost — NER multi_and tetiklendiyse sparse phrase boost
    # daha düşük olsun (yaygın bigram "kaç bitti" Şampiyonlar Ligi cards'ını taşımasın).
    _ner_active = _ner_mode in ("multi_and", "multi_and_common") and bool(_ner_card_ids)
    if _ner_active:
        PHRASE_BOOST = float(_retr_cfg_agenda.get("rrf_phrase_boost_ner_mode", 0.03))
    else:
        PHRASE_BOOST = float(_retr_cfg_agenda["rrf_phrase_boost"])

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

    # NER stream RRF boost (mode-aware K — #714 + #718 K=10 default for multi_and)
    if _ner_card_ids:
        if _ner_mode in ("multi_and", "multi_and_common"):
            _ner_k = float(_retr_cfg_agenda["ner_k_multi"])
        elif _ner_mode == "single_rare":
            _ner_k = float(_retr_cfg_agenda["ner_k_single_rare"])
        else:
            _ner_k = None
        if _ner_k is not None:
            for rank, cid in enumerate(_ner_card_ids, start=1):
                rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (_ner_k + rank)
                score_meta.setdefault(cid, {})["ner_mode"] = _ner_mode

    if not rrf:
        return []

    # Top-K sıralaması
    sorted_ids = sorted(rrf.keys(), key=lambda x: rrf[x], reverse=True)[:top_k]

    # Full agenda card data fetch
    # #398 MVP-2.1 — embedding::text de getir; citation validation
    # source fragment'ları yeniden embed etmek zorunda kalmasın.
    in_clause = ", ".join(f"'{cid}'::uuid" for cid in sorted_ids)
    full_sql = sa_text(
        f"""
        SELECT ac.id, ac.title, ac.summary, ac.key_points,
               ac.content_angles, ac.source_refs, ac.status,
               ac.importance_score, ac.freshness_score, ac.event_id,
               ac.country, ac.level,
               ac.embedding::text AS embedding_text
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
        # #398 — embedding_text'i parse edip 'embedding' alanına koy.
        # Hata durumunda None → citation validation embed_fn fallback eder.
        row["embedding"] = _parse_pgvector_text(row.get("embedding_text"))
        # embedding_text alanını dict'te bırak (debug/audit için), ama None'lı
        # ise düşürebiliriz; şimdilik sade kalsın.
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

    # #181 (cross-encoder rerank) + #758 (cross-encoder kaldırıldı, settings.reranker_enabled
    # silindi). Aktif rerank: LLM rerank (rerank_rows içinde, #756 telemetri).
    if rerank and len(results) > 1:
        from app.core.rerank import rerank_rows

        results = await rerank_rows(
            query=cleaned_query,
            rows=results,
            top_k=top_k,
            db=db,  # LLM rerank telemetri için (track_provider_call)
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
    timeframe_from: datetime | None = None,
    timeframe_to: datetime | None = None,
    min_semantic_score: float = 0.50,
    rerank: bool = True,
    pre_normalized: str | None = None,
    parent_doc_override: bool | None = None,
    critical_entities: list[str] | None = None,
) -> list[dict]:
    """Article chunk hybrid retrieval — PR-D agenda boş ise fallback (PR-E).

    Article-level metadata içerir (singleton cluster article'ları için kritik).
    Generator'a 'supplementary_chunks' olarak gider.

    Args:
        pre_normalized: handler tarafında normalize edilmiş query (#397 MVP-2.1).
            None ise lokal `normalize_tr_query` çağrısı yapılır (backward-compat).
        timeframe_from / timeframe_to: #652 Faz 2 — self-query date filter.
            Spesifik tarih aralığı (planner'dan gelir, "6 Mayıs Trump" gibi).
            Eğer set ise since_hours yerine BETWEEN filter uygulanır.
    """
    cleaned = (query_text or "").strip()
    if not cleaned:
        return []

    # Phase timing — bottleneck telemetry (#781 sonrası kalıcı, env DEBUG_TIMING=1 ile)
    import os as _os
    import time as _time_mod

    _ph = {"_start": _time_mod.perf_counter()}
    _debug_timing = _os.environ.get("DEBUG_TIMING", "0") == "1"

    def _ph_tick(name: str) -> None:
        if _debug_timing:
            _ph[name] = _time_mod.perf_counter() - _ph["_start"]

    # #198 — Türkçe normalize (apostrof + lowercase)
    # #397 — handler tarafında pre-normalized geçirildiyse re-normalize etme
    norm_query = pre_normalized if pre_normalized is not None else normalize_tr_query(cleaned)
    if not norm_query or len(norm_query) < 2:
        return []

    # #784 — Redis retrieval cache (1h TTL). Cache hit → tüm pipeline atlanır.
    # Cache key: norm_query + retrieval parametreleri (top_k, pool, since,
    # timeframe, critical_entities). Hata fail-silent.
    try:
        from app.core.retrieval_cache import get_cached_retrieval, set_cached_retrieval

        _cached = await get_cached_retrieval(
            norm_query=norm_query,
            top_k=top_k,
            candidate_pool=candidate_pool,
            since_hours=since_hours,
            timeframe_from=timeframe_from,
            timeframe_to=timeframe_to,
            critical_entities=critical_entities,
        )
        if _cached is not None:
            logger.info(
                "retrieval_cache HIT query='%s..' top_k=%d (n=%d)",
                norm_query[:50],
                top_k,
                len(_cached),
            )
            return _cached
    except Exception as _exc:
        logger.warning("retrieval_cache lookup failed: %s", _exc)

    text_threshold = max(0.10, _phrase_match_threshold(norm_query))
    phrase_pattern = f"%{norm_query}%"
    # #200 — n-gram phrase'ler (kısmi eşleşme)
    phrase_grams_patterns = [f"%{g}%" for g in _phrase_grams(norm_query)]

    has_dense = query_vector is not None and len(query_vector) == 1024
    # #652 Faz 2 — eğer planner spesifik tarih çıkardıysa timeframe_from/to
    # kullan; yoksa since_hours window'una düş.
    use_timeframe = timeframe_from is not None and timeframe_to is not None
    since = datetime.now(UTC) - timedelta(hours=since_hours)

    # Sparse — normalized chunk_text (stored generated column, #781 hız fix:
    # önceki inline LOWER+REPLACE chain GIN trigram index'i bypass ediyordu,
    # full table scan 14s alıyordu). Şimdi c.chunk_text_norm + GIN trigram
    # index ile ~200ms.
    # Article-level metadata: title + subtitle (subtitle nullable) — inline
    # hesaplanır (articles tablosunda generated col yok), zaten az satır.
    meta_concat_sql = "COALESCE(a.title, '') || ' ' || COALESCE(a.subtitle, '')"
    meta_norm = f"LOWER({_build_sql_quote_strip(meta_concat_sql)})"
    # #652 Faz 2 — date filter clause (planner spesifik tarih çıkardıysa)
    # Eğer use_timeframe ise BETWEEN, yoksa since_hours window'u
    if use_timeframe:
        date_clause = (
            "c.published_at IS NULL OR (c.published_at >= :tf_from AND c.published_at <= :tf_to)"
        )
    else:
        date_clause = "c.published_at IS NULL OR c.published_at >= :since"

    _ph_tick("setup")
    sparse_rows = []
    # #782 hız: tsvector + OR-based to_tsquery (PostgreSQL FTS).
    # Önceki trigram `c.chunk_text_norm % :q` uzun query'lerde 13K satır match,
    # heap recheck 5+ sn. tsvector inverted index ile word-level match — 50ms.
    # OR semantics (websearch AND yerine) — Türkçe suffix variant'larda match
    # için: "maçının" ≠ "maç" stemmer yok, ama ts_rank skoru overlap'i ödüllendirir.
    # ILIKE phrase + meta_norm trigram yedek (exact phrase recall koruması).
    # Build OR tsquery: word1 | word2 | word3 (PostgreSQL tsquery syntax)
    # Special chars (& | ! ( ) :) temizlenir.
    import re as _re

    _safe_words = [
        w
        for w in _re.split(r"\s+", norm_query.strip())
        if w and len(w) >= 2 and not _re.search(r"[&|!():*\"]", w)
    ]
    _ts_or_query = " | ".join(_safe_words) if _safe_words else norm_query
    try:
        sparse_rows = (
            (
                await db.execute(
                    sa_text(
                        f"""
                    SELECT c.id, c.article_id,
                           GREATEST(
                               ts_rank(c.chunk_text_tsv, to_tsquery('simple', :tsq)),
                               similarity({meta_norm}, :q)
                           ) AS text_score,
                           (c.chunk_text_norm ILIKE :phrase OR {meta_norm} ILIKE :phrase) AS phrase_match,
                           (
                               SELECT COUNT(*)::int FROM unnest(CAST(:phrase_grams AS text[])) g
                               WHERE c.chunk_text_norm ILIKE g OR {meta_norm} ILIKE g
                           ) AS gram_match_count
                    FROM article_chunks c
                    JOIN articles a ON a.id = c.article_id
                    WHERE ({date_clause})
                      AND (
                        c.chunk_text_tsv @@ to_tsquery('simple', :tsq)
                        OR c.chunk_text_norm ILIKE :phrase
                        OR {meta_norm} % :q
                        OR {meta_norm} ILIKE :phrase
                      )
                    ORDER BY phrase_match DESC, gram_match_count DESC, text_score DESC
                    LIMIT :pool
                    """
                    ),
                    {
                        "q": norm_query,
                        "tsq": _ts_or_query,
                        "phrase": phrase_pattern,
                        "phrase_grams": phrase_grams_patterns or [""],
                        "since": since,
                        "tf_from": timeframe_from,
                        "tf_to": timeframe_to,
                        "pool": candidate_pool,
                    },
                )
            )
            .mappings()
            .all()
        )
    except Exception as exc:
        logger.warning("chunks sparse failed: %s", exc)

    _ph_tick("sparse")
    # Dense
    dense_rows = []
    if has_dense:
        vec_lit = "[" + ",".join(f"{v:.7f}" for v in query_vector) + "]"
        # #652 Faz 2 — same date filter applied to dense path
        if use_timeframe:
            dense_date_clause = (
                "(c.published_at IS NULL OR "
                "(c.published_at >= :tf_from AND c.published_at <= :tf_to))"
            )
        else:
            dense_date_clause = "(c.published_at IS NULL OR c.published_at >= :since)"
        try:
            dense_rows = (
                (
                    await db.execute(
                        sa_text(
                            f"""
                        SELECT c.id,
                               c.article_id,
                               1.0 - ((c.embedding <=> (:vec)::vector) / 2.0) AS semantic_score
                        FROM article_chunks c
                        WHERE c.embedding IS NOT NULL
                          AND {dense_date_clause}
                        ORDER BY c.embedding <=> (:vec)::vector
                        LIMIT :pool
                        """
                        ),
                        {
                            "vec": vec_lit,
                            "since": since,
                            "tf_from": timeframe_from,
                            "tf_to": timeframe_to,
                            "pool": candidate_pool,
                        },
                    )
                )
                .mappings()
                .all()
            )
        except Exception as exc:
            logger.warning("chunks dense failed: %s", exc)

    _ph_tick("dense")
    # #661 Faz 5.2 — Article-level summary embedding dense search.
    # Title + subtitle + first paragraph embed'i ile sorgu vector'ünü kıyasla.
    # Top-N article'ları RRF'e bonus stream olarak ekle — niş bilgi article
    # gövdesinde olsa bile article ana teması ile semantic match yakalanır.
    summary_article_ids: list[str] = []
    summary_scores: dict[str, float] = {}
    if has_dense:
        try:
            summary_rows = (
                (
                    await db.execute(
                        sa_text(
                            f"""
                        SELECT a.id::text AS article_id,
                               1.0 - ((a.summary_embedding <=> (:vec)::vector) / 2.0) AS sum_score
                        FROM articles a
                        WHERE a.summary_embedding IS NOT NULL
                          AND a.status = 'cleaned'
                          AND ({dense_date_clause.replace("c.", "a.")})
                        ORDER BY a.summary_embedding <=> (:vec)::vector
                        LIMIT :pool
                        """
                        ),
                        {
                            "vec": vec_lit,
                            "since": since,
                            "tf_from": timeframe_from,
                            "tf_to": timeframe_to,
                            "pool": candidate_pool,
                        },
                    )
                )
                .mappings()
                .all()
            )
            for r in summary_rows:
                aid = str(r["article_id"])
                summary_article_ids.append(aid)
                summary_scores[aid] = float(r["sum_score"])
            logger.debug(
                "summary_emb top=%d (best=%.3f, worst=%.3f)",
                len(summary_rows),
                summary_rows[0]["sum_score"] if summary_rows else 0.0,
                summary_rows[-1]["sum_score"] if summary_rows else 0.0,
            )
        except Exception as exc:
            logger.warning("summary_emb search failed: %s", exc)

    # #661 Faz 5.2 — Summary article'ların chunks'larını fetch et ve RRF'e
    # additional stream olarak ekle. Niş bilgi article gövdesinde olsa bile
    # article ana teması ile semantic match → article'ın ilk chunks'ı RRF'e.
    summary_chunk_rows: list[dict] = []
    if summary_article_ids:
        top_summary_aids = summary_article_ids[:30]  # top-30 article
        aid_in = ", ".join(f"'{aid}'::uuid" for aid in top_summary_aids)
        try:
            summary_chunk_rows = (
                (
                    await db.execute(
                        sa_text(
                            f"""
                        SELECT DISTINCT ON (c.article_id)
                               c.id, c.article_id, c.chunk_index
                        FROM article_chunks c
                        WHERE c.article_id IN ({aid_in})
                          AND c.embedding IS NOT NULL
                        ORDER BY c.article_id, c.chunk_index
                        """
                        )
                    )
                )
                .mappings()
                .all()
            )
        except Exception as exc:
            logger.warning("summary chunk fetch failed: %s", exc)

    _ph_tick("summary")
    # #691 Faz 6.1 — NER entity match stream (IDF + multi-entity AND overhaul).
    # Backfill sonrası `ILIKE %X%` 20+ article match (cap dolu) sinyali sulardı.
    # Şimdi entity rarity (df) tabanlı filtre + multi-entity intersect:
    #   - 2+ rare entity (df<30) intersect → K=20 (en güçlü)
    #   - 1 rare entity → K=30 (Faz 6 eski seviye)
    #   - Hiç rare yok ama 2+ common entity intersect dar (<30) → K=20
    #   - Hiçbiri → boost yok
    ner_chunk_rows: list[dict] = []
    ner_mode = "no_match"
    ner_df_map: dict[str, int] = {}
    try:
        from app.core.rerank import _extract_entity_candidates

        # min_len=3 (F-16 gibi tire entity için)
        ner_query_entities = _extract_entity_candidates(cleaned, min_len=3)
    except Exception:
        ner_query_entities = []

    # #696 B7+C8 — Runtime tunable config (settings_store)
    _retr_cfg = await _load_retrieval_settings(db)

    if ner_query_entities:
        target_aids, ner_mode, ner_df_map = await _ner_idf_match_aids(
            db,
            ner_query_entities,
            config=_retr_cfg,
        )
        if target_aids:
            aid_list = list(target_aids)[: int(_retr_cfg["ner_final_aids_cap"])]
            aid_in = ", ".join(f"'{aid}'::uuid" for aid in aid_list)
            try:
                ner_chunk_rows = (
                    (
                        await db.execute(
                            sa_text(
                                f"""
                            SELECT DISTINCT ON (c.article_id)
                                   c.id, c.article_id, c.chunk_index
                            FROM article_chunks c
                            WHERE c.article_id IN ({aid_in})
                              AND c.embedding IS NOT NULL
                            ORDER BY c.article_id, c.chunk_index
                            """
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
                logger.info(
                    "ner_idf_match q_ents=%d df=%s mode=%s aids=%d chunks=%d",
                    len(ner_query_entities),
                    dict(ner_df_map.items()),
                    ner_mode,
                    len(target_aids),
                    len(ner_chunk_rows),
                )
            except Exception as exc:
                logger.warning("ner chunk fetch failed: %s", exc)

    # RRF + phrase boost (#198) + n-gram boost (#200) — runtime tunable
    K_RRF = float(_retr_cfg["rrf_k"])
    K_SUMMARY = float(_retr_cfg["rrf_k_summary"])
    GRAM_BOOST = float(_retr_cfg["rrf_gram_boost"])
    # #718 mode-aware phrase boost (NER multi_and varsa düşür)
    _ner_active_chunks = ner_mode in ("multi_and", "multi_and_common") and bool(ner_chunk_rows)
    if _ner_active_chunks:
        PHRASE_BOOST = float(_retr_cfg.get("rrf_phrase_boost_ner_mode", 0.03))
    else:
        PHRASE_BOOST = float(_retr_cfg["rrf_phrase_boost"])
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

    # #661 Faz 5.2 — Summary article'ların ilk chunk'larını RRF'e ekle.
    # Summary stream skoru daha düşük weight (default K=80) ki sparse/dense
    # dominantlığı korunsun
    for rank, row in enumerate(summary_chunk_rows, start=1):
        cid = str(row["id"])
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K_SUMMARY + rank)

    # #691 Faz 6.1 — NER entity match RRF (mode-aware weight, runtime tunable).
    if ner_chunk_rows:
        if ner_mode in ("multi_and", "multi_and_common"):
            ner_k = float(_retr_cfg["ner_k_multi"])
        elif ner_mode == "single_rare":
            ner_k = float(_retr_cfg["ner_k_single_rare"])
        else:
            ner_k = None
        if ner_k is not None:
            for rank, row in enumerate(ner_chunk_rows, start=1):
                cid = str(row["id"])
                rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (ner_k + rank)

    _ph_tick("ner")
    # #778 Faz 3 — Per-chunk keyword + question match stream (RagFlow adaptation).
    # Chunk'a LLM ile atanmış keywords / question_keywords (BM25 high weight).
    # Strong RRF weight (K=15) — NER multi-and ile single_rare arasında.
    # Bu stream "bahis çocuk" tipi sorgular için kritik: chunk'ın anahtar
    # kavramları array overlap ile yakalanır, doğru article top'a çıkar.
    keyword_chunk_rows: list[dict] = []
    try:
        from app.shared.runtime_config.settings_store import settings_store as _kw_ss

        kw_enabled = await _kw_ss.get_bool(db, "retrieval.keyword_stream_enabled", True)
    except Exception:
        kw_enabled = True

    if kw_enabled:
        # Sorgu kelimelerini lowercase + min 3 char filter (Türkçe kısaltma vb. atla)
        query_words = [w.lower().strip(".,!?;:") for w in norm_query.split() if len(w) >= 3]
        # Q1 (#787) — Per-word ILIKE pattern listesi: question_keywords array
        # elementleri içinde kaç farklı user-query kelimesi geçtiğini sayar.
        # Evergreen: hardcoded entity yok, sadece kelime overlap.
        query_word_patterns = [f"%{w}%" for w in query_words]
        if query_words:
            try:
                kw_rows = (
                    (
                        await db.execute(
                            sa_text(f"""
                        SELECT c.id::text AS id, c.article_id::text AS article_id,
                               (
                                 SELECT COUNT(*)::int FROM unnest(c.keywords) k
                                 WHERE LOWER(k) = ANY(CAST(:qwords AS varchar[]))
                               ) AS kw_match,
                               EXISTS (
                                 SELECT 1 FROM unnest(c.question_keywords) qk
                                 WHERE LOWER(qk) ILIKE :phrase
                                    OR LOWER(qk) % :norm_query
                               ) AS q_match,
                               -- Q1 (#787): question_keywords array içinde
                               -- kaç farklı user-query kelimesi geçiyor.
                               -- Generic word-overlap — hardcoded liste yok.
                               -- "Rodos kaç ana kent" → q_word_overlap=3
                               -- (chunk Q "Rodos kentlerin birleşmesi..." içinde
                               -- "rodos", "kent", "kuruldu/kaç" matchler).
                               (
                                 SELECT COUNT(DISTINCT w)::int
                                 FROM unnest(c.question_keywords) qk
                                 CROSS JOIN unnest(CAST(:qword_patterns AS varchar[])) AS w
                                 WHERE LOWER(qk) LIKE w
                               ) AS q_word_overlap
                        FROM article_chunks c
                        JOIN articles a ON a.id = c.article_id
                        WHERE ({date_clause})
                          AND (
                            c.keywords && CAST(:qwords AS varchar[])
                            OR EXISTS (
                              SELECT 1 FROM unnest(c.question_keywords) qk
                              WHERE LOWER(qk) ILIKE :phrase
                                 OR LOWER(qk) % :norm_query
                                 -- Q1 (#787): herhangi bir query kelimesi
                                 -- question'da geçen chunk'lar surface edilir
                                 OR EXISTS (
                                   SELECT 1 FROM unnest(CAST(:qword_patterns AS varchar[])) w
                                   WHERE LOWER(qk) LIKE w
                                 )
                            )
                          )
                        ORDER BY q_match DESC, q_word_overlap DESC, kw_match DESC, c.published_at DESC NULLS LAST
                        LIMIT :pool
                    """),
                            {
                                "qwords": query_words,
                                "qword_patterns": query_word_patterns,
                                "phrase": phrase_pattern,
                                "norm_query": norm_query,
                                "since": since,
                                "tf_from": timeframe_from,
                                "tf_to": timeframe_to,
                                "pool": candidate_pool,
                            },
                        )
                    )
                    .mappings()
                    .all()
                )
                keyword_chunk_rows = [dict(r) for r in kw_rows]
            except Exception as exc:
                logger.warning("chunks keyword stream failed: %s", exc)

    if keyword_chunk_rows:
        # K=15 — strong weight (full phrase question_keyword match)
        # K=18 — q_word_overlap >= 3 (3+ query kelimesi question'larda — yüksek sinyal)
        # K=22 — q_word_overlap == 2
        # K=20 — keyword direct match >= 2
        # K=30 — single keyword / single question word
        # Generic kelime-overlap, hardcoded liste yok.
        for rank, row in enumerate(keyword_chunk_rows, start=1):
            cid = str(row["id"])
            q_match = bool(row.get("q_match"))
            kw_match = int(row.get("kw_match") or 0)
            q_overlap = int(row.get("q_word_overlap") or 0)
            # Tier'lı RRF K — RagFlow question_kwd 6x weight pattern
            if q_match:
                k_value = 15.0
            elif q_overlap >= 3:
                k_value = 18.0  # yüksek question-word overlap
            elif kw_match >= 2:
                k_value = 20.0
            elif q_overlap >= 2:
                k_value = 22.0
            else:
                k_value = 30.0
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (k_value + rank)

    if not rrf:
        return []

    # #778 Faz 4 — Critical entities MUST_MATCH filter (RagFlow adaptation).
    # Sorgudaki en discriminative kelimeler (planner çıkışı) chunk'ın
    # title/text/keywords içinde geçmiyorsa elenir. Soft fallback: filter
    # sonrası 0 sonuç kalırsa filter atlanır (orijinal RRF döner).
    rrf_pre_filter_size = len(rrf)
    if critical_entities:
        try:
            from app.shared.runtime_config.settings_store import settings_store as _ce_ss

            ce_enabled = await _ce_ss.get_bool(db, "retrieval.critical_entity_filter_enabled", True)
        except Exception:
            ce_enabled = True

        if ce_enabled:
            # Lowercase normalize
            ce_lower = [e.lower().strip() for e in critical_entities if e.strip()]
            if ce_lower:
                # İki aşamalı yaklaşım (RagFlow MUST_MATCH adaptasyonu):
                #
                # 1) RESCUE stream — RRF dışında ama TÜM critical entity'leri
                #    içeren article'ları surface et (recall artışı).
                #    Bu olmadan filter sadece var olan candidate'ları daraltır;
                #    target article hiç bir stream'e düşmediyse kaybedilir.
                #
                # 2) FILTER — RRF sonrası kalan candidate'lar ARASINDAN sadece
                #    en az 1 critical entity'yi geçenleri tut (precision artışı).
                #
                # Recall + precision dengesi: tüm entity'ler title/text/keyword'de
                # geçen article'lar boost (K=12 strongest stream), tek entity
                # geçenler korunur.
                cand_ids = list(rrf.keys())
                try:
                    # ---- STAGE 1: RESCUE — ALL entities article'da olmalı ----
                    # NOT: Tier'lı OR + match_count denendi (#791, 2026-05-14)
                    # niche_007/009 düzeltmedi (rescue yine yetmiyor), niche_003
                    # (#5→#7) ve niche_004 (#1→#6) regresyona soktu. Geniş rescue
                    # rakip article'lara boost veriyor → precision kaybı.
                    # ALL condition korundu (sıkı, niş entity için doğru).
                    where_clauses = []
                    params: dict[str, object] = {
                        "since": since,
                        "pool": min(candidate_pool, 30),
                    }
                    # #939 — PostgreSQL C-locale LOWER() Türkçe büyük
                    # harfleri (Ö Ü Ç Ş Ğ İ) küçültmez → `:ent` Python
                    # .lower() ile küçük ("özgür özel"), SQL tarafı C-locale
                    # → "Özgür Özel" (büyük kalır) → ASLA eşleşmez. Türkçe
                    # entity exact-match (RESCUE) tamamen çöküyordu (prod
                    # kanıt: 5/5 haber False → tr-collation True). ICU
                    # `tr-TR-x-icu` collation prod'da mevcut+test edildi.
                    for i, ent in enumerate(ce_lower):
                        pkey = f"ent_{i}"
                        where_clauses.append(f"""
                            (
                              LOWER(COALESCE(a.title, '') || ' ' || COALESCE(a.subtitle, '') || ' ' || COALESCE(a.clean_text, '') COLLATE "tr-TR-x-icu") LIKE :{pkey}
                              OR EXISTS (
                                SELECT 1 FROM unnest(COALESCE(c.keywords, ARRAY[]::varchar[])) k
                                WHERE LOWER(k COLLATE "tr-TR-x-icu") LIKE :{pkey}
                              )
                            )
                        """)
                        params[pkey] = f"%{ent}%"

                    # date filter (since_hours + timeframe overlay)
                    rescue_date_clause = date_clause  # reuse the outer date_clause
                    rescue_sql = f"""
                        SELECT c.id::text AS id, c.article_id::text AS article_id
                        FROM article_chunks c
                        JOIN articles a ON a.id = c.article_id
                        WHERE ({rescue_date_clause})
                          AND {" AND ".join(where_clauses)}
                        ORDER BY c.published_at DESC NULLS LAST
                        LIMIT :pool
                    """
                    # Add timeframe params if used
                    if timeframe_from is not None:
                        params["tf_from"] = timeframe_from
                    if timeframe_to is not None:
                        params["tf_to"] = timeframe_to

                    rescue_rows = (await db.execute(sa_text(rescue_sql), params)).mappings().all()
                    rescue_ids = [r["id"] for r in rescue_rows]
                    # K=12 — must-match en güçlü stream
                    rescue_added = 0
                    for rank, cid in enumerate(rescue_ids, start=1):
                        before = rrf.get(cid, 0.0)
                        rrf[cid] = before + 1.0 / (12 + rank)
                        if before == 0.0:
                            rescue_added += 1

                    # ---- STAGE 2: FILTER — RRF candidate'ları arasından
                    # en az 1 entity geçenleri tut ----
                    cand_ids = list(rrf.keys())
                    if cand_ids:
                        in_cands = ", ".join(f"'{cid}'::uuid" for cid in cand_ids)
                        match_rows = (
                            (
                                await db.execute(
                                    sa_text(f"""
                                SELECT c.id::text AS id
                                FROM article_chunks c
                                JOIN articles a ON a.id = c.article_id
                                WHERE c.id IN ({in_cands})
                                  AND (
                                    -- #939 — C-locale LOWER Türkçe büyük
                                    -- harf küçültmez; tr-collation şart
                                    -- (RESCUE ile aynı kök, FILTER eşi).
                                    LOWER(COALESCE(a.title, '') || ' ' || COALESCE(a.subtitle, '') || ' ' || COALESCE(a.clean_text, '') COLLATE "tr-TR-x-icu") ~* CAST(:ce_pattern AS text)
                                    OR EXISTS (
                                      SELECT 1 FROM unnest(COALESCE(c.keywords, ARRAY[]::varchar[])) k
                                      WHERE LOWER(k COLLATE "tr-TR-x-icu") = ANY(CAST(:ce_lower AS varchar[]))
                                    )
                                  )
                            """),
                                    {
                                        "ce_pattern": "(" + "|".join(ce_lower) + ")",
                                        "ce_lower": ce_lower,
                                    },
                                )
                            )
                            .mappings()
                            .all()
                        )
                        matched_ids = {r["id"] for r in match_rows}
                        filtered_rrf = {cid: s for cid, s in rrf.items() if cid in matched_ids}
                        if filtered_rrf:
                            rrf = filtered_rrf
                            logger.info(
                                "critical_entity MUST_MATCH: rescue_added=%d "
                                "filter %d → %d candidates (entities=%s)",
                                rescue_added,
                                rrf_pre_filter_size,
                                len(rrf),
                                ce_lower,
                            )
                        else:
                            logger.info(
                                "critical_entity soft fallback (0 match after filter) "
                                "rescue_added=%d entities=%s — original RRF preserved",
                                rescue_added,
                                ce_lower,
                            )
                except Exception as exc:
                    logger.warning("critical_entity must_match failed: %s", exc)

    # NOT: Entity boost rerank.py pipeline'ına bırakıldı (#660 revert).
    # Hybrid_search RRF'e entegrasyon Trump 6 Mayıs gibi vakaları geriletti —
    # entity (Trump) birçok rakip article'da da var → non-target rakipler
    # de boost alıyor. RRF doğal dense+sparse sıralaması daha güvenilir;
    # entity bonus rerank pipeline'ında (CE enabled iken) yardımcı olur.
    _ph_tick("critical_entity")
    sorted_ids = sorted(rrf.keys(), key=lambda x: rrf[x], reverse=True)[:top_k]
    in_clause = ", ".join(f"'{cid}'::uuid" for cid in sorted_ids)

    full_rows = (
        (
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
        )
        .mappings()
        .all()
    )

    by_id = {str(r["chunk_id"]): dict(r) for r in full_rows}
    results = []
    for cid in sorted_ids:
        if cid in by_id:
            row = by_id[cid]
            # #712 B1 — Inspector UI için RRF skoru row'a ekle (cards path ile parity).
            row["_rrf_score"] = rrf[cid]
            results.append(row)

    logger.info(
        "hybrid_chunks dense=%d sparse=%d fused=%d pre_rerank=%d",
        len(dense_rows),
        len(sparse_rows),
        len(rrf),
        len(results),
    )

    _ph_tick("full_rows")
    # #181 — Cross-encoder rerank stage
    if rerank and len(results) > 1:
        from app.core.rerank import rerank_rows

        # #712 B1 — Pre-rerank order'ı sakla, sonra rerank_score ekle
        {str(r.get("chunk_id") or r.get("id")): i for i, r in enumerate(results)}
        results = await rerank_rows(
            query=cleaned,
            rows=results,
            top_k=top_k,
            db=db,  # LLM rerank telemetri için (track_provider_call)
        )
        # rerank_rows içinde row'a `_rerank_score` ekleniyor; doğrulama için tekrar set et
        for r in results:
            if "_rerank_score" not in r:
                r["_rerank_score"] = 0.0

    # #661 Faz 5.3 — Parent-document retrieval (RAGFlow tier).
    # Top-K chunk match'i sonrası, AYNI article'ın TÜM chunks'larını LLM
    # context'ine dahil et. Niş bilgi article ortasında olsa bile çevreleyen
    # paragraflar context'e taşınır → answer extraction kalitesi yükselir.
    # Default ON; flag ile kapatılabilir.
    # #712 B1 — Inspector için parent_doc bypass: expanded chunks rerank'tan
    # geçmediği için _rerank_score=0 olur, inspector UI yanıltıcı görünür.
    if parent_doc_override is not None:
        parent_doc_enabled = parent_doc_override
    else:
        try:
            parent_doc_enabled = await _load_parent_doc_setting()
        except Exception:
            parent_doc_enabled = True

    _ph_tick("rerank")
    if parent_doc_enabled and results:
        try:
            results = await _expand_parent_documents(
                db=db,
                primary_results=results,
                max_chunks_per_article=5,
                final_top_k=top_k * 2,
            )
            logger.info(
                "parent_doc expansion: %d → %d chunks",
                len({str(r.get("article_id")) for r in results[:top_k]}),
                len(results),
            )
        except Exception as exc:
            logger.warning("parent_doc expansion failed: %s", exc)

    _ph_tick("parent_doc")
    if _debug_timing and len(_ph) > 1:
        phases = [
            "setup",
            "sparse",
            "dense",
            "summary",
            "ner",
            "critical_entity",
            "full_rows",
            "rerank",
            "parent_doc",
        ]
        deltas = []
        prev = 0.0
        for p in phases:
            if p in _ph:
                cur = _ph[p]
                deltas.append(f"{p}={int((cur - prev) * 1000)}ms")
                prev = cur
        total_ms = int((_time_mod.perf_counter() - _ph["_start"]) * 1000)
        print(f"[hybrid_chunks {total_ms}ms] " + " ".join(deltas), flush=True)

    # #784 — Cache write (fail-silent)
    try:
        await set_cached_retrieval(
            norm_query=norm_query,
            top_k=top_k,
            candidate_pool=candidate_pool,
            since_hours=since_hours,
            timeframe_from=timeframe_from,
            timeframe_to=timeframe_to,
            critical_entities=critical_entities,
            results=results,
        )
    except Exception as _exc:
        logger.warning("retrieval_cache write failed: %s", _exc)

    return results


# ============================================================================
# L2 retrieval-affinity (#1019 Faz 5) — görünmez, additive, flag-gated
# ============================================================================


async def apply_l2_affinity_boost(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    chunks: list[dict],
) -> list[dict]:
    """Kullanıcının yüksek-affinity araştırma kümelerine ait entity'lerle
    eşleşen sonuçlara ADDITIVE `_rrf_score` boost (#1019 Faz 5).

    Retrieval CORE ve Redis cache'inden SONRA, research-path'inde (kullanıcı
    bağlamı mevcut) çağrılır → base RRF cache user-agnostik kalır
    (S11: cache cross-user sızması YOK).

    İnvaryant:
      - flag kapalı | user_id None | affinity boş | eşleşme yok → chunks
        DEĞİŞMEDEN döner (byte-identical, #854).
      - ASLA down-rank (S6): yalnız eşleşen article chunk'ına +boost;
        diğer satırlar DOKUNULMAZ (negatif düzeltme YOK).
      - User-scoped (S11): yalnız message_clusters.user_id=:uid.
      - Deprecated küme hariç (S12): research_clusters.deprecated_at IS NULL.
      - Cevap prompt'u / citation / halü / freshness ETKİLENMEZ — yalnız
        retrieved chunk listesinin sırası (recall sinyali).
    """
    if user_id is None or not chunks:
        return chunks

    from app.shared.runtime_config.settings_store import settings_store

    if not await settings_store.get_bool(db, "research.l2_affinity_enabled", False):
        return chunks
    boost = await settings_store.get_float(db, "research.l2_affinity_boost", 0.05)
    if boost <= 0:
        return chunks

    # 1) Affinity küme adları — user-scoped (S11), deprecated hariç (S12)
    name_rows = (
        (
            await db.execute(
                sa_text(
                    """
                    SELECT rc.canonical_name AS name
                    FROM message_clusters mc
                    JOIN research_clusters rc ON rc.id = mc.cluster_id
                    WHERE mc.user_id = :uid
                      AND rc.deprecated_at IS NULL
                    GROUP BY rc.canonical_name
                    ORDER BY SUM(mc.mention_count) DESC
                    LIMIT 25
                    """
                ),
                {"uid": str(user_id)},
            )
        )
        .scalars()
        .all()
    )
    # Türkçe-güvenli Python normalize (C-locale SQL LOWER tuzağından kaç — #939)
    affinity = {normalize_tr_query(n) for n in name_rows if n}
    affinity.discard("")
    if not affinity:
        return chunks

    aids = {str(c["article_id"]) for c in chunks if c.get("article_id")}
    if not aids:
        return chunks

    # 2) Aday article entity'leri (haber-korpusu çapası S11); Python-tarafı
    #    normalize ile kesiştir (collation-güvenli)
    ent_rows = (
        await db.execute(
            sa_text(
                """
                SELECT article_id::text AS aid, entity_normalized AS ent
                FROM entities
                WHERE article_id::text = ANY(:aids)
                """
            ),
            {"aids": list(aids)},
        )
    ).all()
    matched_aids = {aid for aid, ent in ent_rows if ent and normalize_tr_query(ent) in affinity}
    if not matched_aids:
        return chunks

    # 3) ADDITIVE boost (S6: yalnız +, asla -); eşleşmeyen satır DOKUNULMAZ
    for c in chunks:
        if str(c.get("article_id")) in matched_aids:
            c["_rrf_score"] = float(c.get("_rrf_score", 0.0) or 0.0) + boost

    # Stable re-sort (Python sorted kararlı → eşit skor göreli sıra korunur)
    return sorted(chunks, key=lambda c: float(c.get("_rrf_score", 0.0) or 0.0), reverse=True)


# ============================================================================
# Parent-document retrieval (#661 Faz 5.3)
# ============================================================================


async def _load_parent_doc_setting() -> bool:
    """retrieval.parent_doc_enabled — default ON (Faz 5.3)."""
    try:
        from app.core.db import get_session_factory
        from app.shared.runtime_config.settings_store import settings_store

        factory = get_session_factory()
        async with factory() as db:
            return await settings_store.get_bool(db, "retrieval.parent_doc_enabled", True)
    except Exception:
        return True


async def _expand_parent_documents(
    *,
    db: AsyncSession,
    primary_results: list[dict],
    max_chunks_per_article: int = 5,
    final_top_k: int = 30,
) -> list[dict]:
    """Top-K chunk match → article'ın TÜM chunks'larını dahil et.

    Mantık:
      1. primary_results'taki unique article_id'leri çıkar
      2. Her article için max_chunks_per_article chunks fetch
      3. Original primary chunks öne sırala, parent chunks devamına ekle
      4. final_top_k cap (LLM context budget)

    Niş bilgi article gövdesinde olsa bile primary chunk match → parent chunks
    context'e geliyor → answer extraction kalitesi yükselir.
    """
    if not primary_results:
        return primary_results

    # Primary chunk article_id'leri (sıralı, unique)
    seen_chunk_ids: set[str] = set()
    primary_article_ids: list[str] = []
    primary_aid_set: set[str] = set()
    for r in primary_results:
        cid = str(r.get("chunk_id") or r.get("id"))
        if cid:
            seen_chunk_ids.add(cid)
        aid = str(r.get("article_id"))
        if aid and aid not in primary_aid_set:
            primary_aid_set.add(aid)
            primary_article_ids.append(aid)

    if not primary_article_ids:
        return primary_results

    # Top-3 article'ın diğer chunks'larını fetch (LLM context budget)
    top_articles = primary_article_ids[:3]
    aid_in = ", ".join(f"'{aid}'::uuid" for aid in top_articles)

    sibling_rows = (
        (
            await db.execute(
                sa_text(
                    f"""
                SELECT c.id AS chunk_id,
                       c.article_id,
                       c.chunk_index,
                       c.chunk_text,
                       c.published_at,
                       a.title AS article_title,
                       a.canonical_url AS article_canonical_url,
                       s.name AS source_name,
                       s.slug AS source_slug
                FROM article_chunks c
                JOIN articles a ON a.id = c.article_id
                JOIN sources s ON s.id = a.source_id
                WHERE c.article_id IN ({aid_in})
                ORDER BY c.article_id, c.chunk_index
                """
                )
            )
        )
        .mappings()
        .all()
    )

    # Group by article
    siblings_by_aid: dict[str, list[dict]] = {}
    for r in sibling_rows:
        cid = str(r["chunk_id"])
        if cid in seen_chunk_ids:
            continue  # primary'de zaten var
        aid = str(r["article_id"])
        siblings_by_aid.setdefault(aid, []).append(dict(r))

    # Merge: primary chunks öne, sibling chunks devamına (article-grouped)
    output: list[dict] = list(primary_results)
    for aid in top_articles:
        siblings = siblings_by_aid.get(aid, [])
        # Her article max_chunks_per_article kadar sibling
        output.extend(siblings[:max_chunks_per_article])
        if len(output) >= final_top_k:
            break

    return output[:final_top_k]
