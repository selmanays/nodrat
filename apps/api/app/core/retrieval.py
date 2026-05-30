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

from app.core._retrieval_affinity import apply_l2_affinity_boost  # noqa: F401
from app.core._retrieval_agenda import hybrid_search_agenda_cards  # noqa: F401
from app.core._retrieval_chunks import hybrid_search_chunks  # noqa: F401

# Internal helpers (PR-B/C internal split — T6 #1085).
# Quote/phrase/vector/scoring pure helpers ayrı `_retrieval_*.py` modüllerine
# taşındı (davranış değişmedi; pure refactor). Public surface re-export ile
# `app.core.retrieval` üzerinden korunur — caller'lar etkilenmez.
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
