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

from sqlalchemy.ext.asyncio import AsyncSession

from app.core._retrieval_affinity import apply_l2_affinity_boost  # noqa: F401
from app.core._retrieval_agenda import hybrid_search_agenda_cards  # noqa: F401
from app.core._retrieval_chunks import hybrid_search_chunks  # noqa: F401

# Internal helpers (PR-B/C internal split — T6 #1085).
# Quote/phrase/vector/scoring pure helpers ayrı `_retrieval_*.py` modüllerine
# taşındı (davranış değişmedi; pure refactor). Public surface re-export ile
# `app.core.retrieval` üzerinden korunur — caller'lar etkilenmez.
from app.core._retrieval_fetch import _fetch_candidates
from app.core._retrieval_ner import _ner_idf_match_aids  # noqa: F401  (re-export: admin_rag)
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
    _load_retrieval_settings,  # noqa: F401  (re-export: _retrieval_ner lazy circular-break)
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


# ============================================================================
# L2 retrieval-affinity (#1019 Faz 5) — görünmez, additive, flag-gated
# ============================================================================


# ============================================================================
# Parent-document retrieval (#661 Faz 5.3)
# ============================================================================
