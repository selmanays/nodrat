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

from app.core._retrieval_affinity import apply_l2_affinity_boost  # noqa: F401
from app.core._retrieval_agenda import hybrid_search_agenda_cards  # noqa: F401

# Internal helpers (PR-B/C internal split — T6 #1085).
# Quote/phrase/vector/scoring pure helpers ayrı `_retrieval_*.py` modüllerine
# taşındı (davranış değişmedi; pure refactor). Public surface re-export ile
# `app.core.retrieval` üzerinden korunur — caller'lar etkilenmez.
from app.core._retrieval_fetch import _fetch_candidates
from app.core._retrieval_ner import (
    _ner_idf_match_aids,
)
from app.core._retrieval_parent import _expand_parent_documents, _load_parent_doc_setting
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
from app.core._retrieval_settings import (
    _load_retrieval_settings,
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

# RRF (Reciprocal Rank Fusion) defaults — #198 hybrid stream


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


# ============================================================================
# Parent-document retrieval (#661 Faz 5.3)
# ============================================================================
