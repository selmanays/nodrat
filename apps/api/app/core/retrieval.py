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
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# #691 — NER entity scoring overhaul (IDF threshold + multi-entity AND)
# ---------------------------------------------------------------------------
# Faz 6 NER pipeline'ı 9 article entity'liyken ölçüldü (recall@5 45.5%→63.6%).
# NER backfill ile 4391 article entity'li → ILIKE '%X%' 20+ article match →
# her birine aynı K=30 RRF bonus → sinyal sulandı, kazanım silindi.
# Çözüm: entity rarity (df) tabanlı filtre + multi-entity AND match.
NER_DF_THRESHOLD = 30  # df < N → "nadir" entity (boost eligibility; ~%0.67 of 4436 corpus)
NER_BOOST_K_MULTI = 20  # 2+ rare entity intersect → en güçlü boost (Faz 6'dan üst)
NER_BOOST_K_SINGLE_RARE = 30  # tek rare entity → Faz 6 eski seviye
NER_FETCH_PER_ENTITY_LIMIT = 100  # her entity için max article (df sayımı için)
NER_FINAL_AIDS_CAP = 30  # rerank pipeline'a giden max article


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
) -> tuple[set[str], str, dict[str, int]]:
    """
    Query entity'leri için article id seti döndür — IDF + multi-entity AND.

    DB tarafı: her entity için exact match → ILIKE fallback.
    Pure logic `_resolve_ner_target_aids`'e delege edilir.

    Returns: (target_aids, mode, df_map)
    """
    aids_per_ent: dict[str, set[str]] = {}
    df_map: dict[str, int] = {}

    for ent in query_entities[:5]:
        ent_norm = ent.lower().strip()
        if len(ent_norm) < 3:
            continue
        try:
            # 1. Exact match first (en güvenilir — "Karşıyaka" = "Karşıyaka")
            exact_rows = (
                await db.execute(
                    sa_text(
                        """
                        SELECT DISTINCT article_id::text AS aid
                        FROM entities
                        WHERE entity_normalized = :ent_norm
                        LIMIT :lim
                        """
                    ),
                    {"ent_norm": ent_norm, "lim": NER_FETCH_PER_ENTITY_LIMIT},
                )
            ).mappings().all()

            if exact_rows:
                aids = {r["aid"] for r in exact_rows}
            else:
                # 2. ILIKE fallback ("Karşıyaka" → "Karşıyaka SK" eşleşmesi için)
                ilike_rows = (
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
                            "lim": NER_FETCH_PER_ENTITY_LIMIT,
                        },
                    )
                ).mappings().all()
                aids = {r["aid"] for r in ilike_rows}

            if aids:
                aids_per_ent[ent] = aids
                df_map[ent] = len(aids)
        except Exception as exc:
            logger.warning("ner idf lookup failed for %r: %s", ent, exc)

    target, mode = _resolve_ner_target_aids(aids_per_ent, df_map)
    # #696 (B5) — Mode telemetri (process-local counter, /admin/rag/ner-stats)
    try:
        from app.core import ner_stats
        ner_stats.record(mode)
    except Exception:
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
_QUOTE_CHARS_TO_STRIP: tuple[str, ...] = (
    "'",          # ASCII apostrof (chr 39)
    "‘",     # ' LEFT SINGLE QUOTATION MARK
    "’",     # ’ RIGHT SINGLE QUOTATION MARK
    "‚",     # ‚ SINGLE LOW-9 QUOTATION MARK
    "‛",     # ‛ SINGLE HIGH-REVERSED-9
    "′",     # ′ PRIME
    "ʼ",     # ʼ MODIFIER LETTER APOSTROPHE
    "ʹ",     # ʹ MODIFIER LETTER PRIME
    '"',          # ASCII çift tırnak (chr 34)
    "“",     # " LEFT DOUBLE QUOTATION MARK
    "”",     # " RIGHT DOUBLE QUOTATION MARK  ← Bianet vakası buraydı
    "„",     # „ DOUBLE LOW-9 QUOTATION MARK
    "‟",     # ‟ DOUBLE HIGH-REVERSED-9
    "″",     # ″ DOUBLE PRIME
    "«",     # « LEFT-POINTING GUILLEMET
    "»",     # » RIGHT-POINTING GUILLEMET
    "‹",     # ‹ SINGLE LEFT-POINTING ANGLE QUOTATION
    "›",     # › SINGLE RIGHT-POINTING ANGLE QUOTATION
    "`",          # backtick (chr 96) — bazı kaynaklarda yer alıyor
)

# SQL tarafında aynı strip için CASE/REPLACE chain inşa edilebilsin diye
# UTF-8 hex temsillerini export ediyoruz (sa.text içinde format string kullanılacak).
_QUOTE_CHARS_FOR_SQL: list[str] = list(_QUOTE_CHARS_TO_STRIP)


def strip_quote_variants(text: str) -> str:
    """Tüm major quote varyantlarını metinden kaldır (Python tarafı).

    Kullanıcı sorgusu ve normalize edilmiş chunk text karşılaştırılırken
    iki taraf da aynı strip işlemini geçmeli, aksi halde phrase match
    patlar (#647 Bianet "Toprakaltı" vakası).
    """
    if not text:
        return ""
    s = text
    for q in _QUOTE_CHARS_TO_STRIP:
        if q in s:
            s = s.replace(q, "")
    return s


def normalize_tr_query(text: str) -> str:
    """Türkçe sorgu normalize: lowercase + tüm quote varyantları temizle +
    whitespace collapse.

    Single + double quote varyantları (smart, low-9, guillemets, prime)
    silinir ki Bianet/Hürriyet/T24 gibi smart-quote kullanan kaynaklarda
    phrase match'i deterministik olsun (#647).

    Trigram benzerliği büyük/küçük harf duyarlı değil ama tırnak işareti
    ayrıştırıyor. 'CHP'li', '"Toprakaltı" sergisi', "İmamoğlu'nun davası"
    artık tutarlı şekilde normalize ediliyor.

    Public API (#397 MVP-2.1) — handler tarafında bir kez çağrılıp
    hybrid_search_* fonksiyonlarına `pre_normalized` olarak geçirilebilir.
    """
    if not text:
        return ""
    s = strip_quote_variants(text.lower())
    return " ".join(s.split())


# Backward-compat alias (#397 — eski private isim için)
_normalize_tr_query = normalize_tr_query


def _build_sql_quote_strip(column_expr: str) -> str:
    """Verilen column expression'a tüm quote varyantlarını silen REPLACE chain'i sar.

    Örn: _build_sql_quote_strip("c.chunk_text") →
      REPLACE(REPLACE(REPLACE(c.chunk_text, '\\u2018', ''), '\\u2019', ''), ...)

    SQL tarafında Python `strip_quote_variants` ile birebir aynı set'i kaldırır.
    Hybrid search SQL'leri bu fonksiyonu kullanarak Python normalize ile
    deterministik şekilde eşleşir (#647 root fix).
    """
    expr = column_expr
    for q in _QUOTE_CHARS_FOR_SQL:
        # SQL string literal escaping: ASCII single quote ('') iki kez yazılır.
        # Diğer Unicode chars için doğrudan literal kullanılır (UTF-8 db'de).
        if q == "'":
            sql_literal = "''''"
        else:
            sql_literal = "'" + q + "'"
        expr = f"REPLACE({expr}, {sql_literal}, '')"
    return expr


def _parse_pgvector_text(s: str | None) -> list[float] | None:
    """pgvector '[0.1,0.2,...]' text temsilini list[float]'a çevirir (#398).

    Aynı pattern raptor.py'de _parse_vector olarak kullanılıyor; burada
    retrieval.py'a yerel kopya — module bağımlılığı eklememek için.
    None / parse fail → None (caller embed_fn fallback eder).
    """
    if not s:
        return None
    try:
        inner = s.strip("[] \n")
        out = [float(x) for x in inner.split(",") if x.strip()]
        # 1024-dim olmayanları reddet (uyumsuz vektör)
        if len(out) != 1024:
            return None
        return out
    except (ValueError, AttributeError):
        return None


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
    now = datetime.now(UTC)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
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
        since = (
            custom_since
            if custom_since is not None
            else datetime.now(UTC) - timedelta(days=7)
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
    if (
        candidate_pool is None
        or min_semantic_score is None
        or min_text_score is None
    ):
        try:
            from app.core.settings_store import settings_store

            if candidate_pool is None:
                candidate_pool = await settings_store.get_int(
                    db, "retrieval.candidate_pool", 30
                )
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
    title_norm_sql = f"LOWER({_build_sql_quote_strip('ac.title')})"
    summary_norm_sql = f"LOWER({_build_sql_quote_strip('LEFT(ac.summary, 500)')})"
    canon_norm_sql = f"LOWER({_build_sql_quote_strip('ec.canonical_title')})"
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
    timeframe_from: datetime | None = None,
    timeframe_to: datetime | None = None,
    min_semantic_score: float = 0.50,
    rerank: bool = True,
    pre_normalized: str | None = None,
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

    # #198 — Türkçe normalize (apostrof + lowercase)
    # #397 — handler tarafında pre-normalized geçirildiyse re-normalize etme
    norm_query = pre_normalized if pre_normalized is not None else normalize_tr_query(cleaned)
    if not norm_query or len(norm_query) < 2:
        return []
    text_threshold = max(0.10, _phrase_match_threshold(norm_query))
    phrase_pattern = f"%{norm_query}%"
    # #200 — n-gram phrase'ler (kısmi eşleşme)
    phrase_grams_patterns = [f"%{g}%" for g in _phrase_grams(norm_query)]

    has_dense = query_vector is not None and len(query_vector) == 1024
    # #652 Faz 2 — eğer planner spesifik tarih çıkardıysa timeframe_from/to
    # kullan; yoksa since_hours window'una düş.
    use_timeframe = timeframe_from is not None and timeframe_to is not None
    since = datetime.now(UTC) - timedelta(hours=since_hours)

    # Sparse — normalized chunk_text + article-level metadata (title + subtitle)
    # üzerinde phrase + n-gram match (#647 root fix: quote variants normalize +
    # subtitle-only entity'leri chunk'a düşmemiş olsa bile yakalama).
    chunk_text_norm = f"LOWER({_build_sql_quote_strip('c.chunk_text')})"
    # Article-level metadata: title + subtitle birleştirilir (subtitle nullable),
    # böylece "Toprakaltı" gibi sadece subtitle'da geçen entity'ler her chunk'a
    # ait bir lexical sinyal olarak retrieve edilir.
    meta_concat_sql = (
        "COALESCE(a.title, '') || ' ' || COALESCE(a.subtitle, '')"
    )
    meta_norm = f"LOWER({_build_sql_quote_strip(meta_concat_sql)})"
    # #652 Faz 2 — date filter clause (planner spesifik tarih çıkardıysa)
    # Eğer use_timeframe ise BETWEEN, yoksa since_hours window'u
    if use_timeframe:
        date_clause = (
            "c.published_at IS NULL OR "
            "(c.published_at >= :tf_from AND c.published_at <= :tf_to)"
        )
    else:
        date_clause = "c.published_at IS NULL OR c.published_at >= :since"

    sparse_rows = []
    try:
        sparse_rows = (
            await db.execute(
                sa_text(
                    f"""
                    WITH norm AS (
                        SELECT c.id, c.article_id, c.published_at,
                               {chunk_text_norm} AS t_norm,
                               {meta_norm} AS m_norm
                        FROM article_chunks c
                        JOIN articles a ON a.id = c.article_id
                        WHERE {date_clause}
                    )
                    SELECT n.id, n.article_id,
                           GREATEST(
                               similarity(n.t_norm, :q),
                               similarity(n.m_norm, :q)
                           ) AS text_score,
                           (n.t_norm ILIKE :phrase OR n.m_norm ILIKE :phrase) AS phrase_match,
                           (
                               SELECT COUNT(*)::int FROM unnest(CAST(:phrase_grams AS text[])) g
                               WHERE n.t_norm ILIKE g OR n.m_norm ILIKE g
                           ) AS gram_match_count
                    FROM norm n
                    WHERE n.t_norm % :q
                       OR n.m_norm % :q
                       OR n.t_norm ILIKE :phrase
                       OR n.m_norm ILIKE :phrase
                       OR EXISTS (
                           SELECT 1 FROM unnest(CAST(:phrase_grams AS text[])) g
                           WHERE n.t_norm ILIKE g OR n.m_norm ILIKE g
                       )
                    ORDER BY phrase_match DESC, gram_match_count DESC, text_score DESC
                    LIMIT :pool
                    """
                ),
                {
                    "q": norm_query,
                    "phrase": phrase_pattern,
                    "phrase_grams": phrase_grams_patterns or [""],
                    "since": since,
                    "tf_from": timeframe_from,
                    "tf_to": timeframe_to,
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
            ).mappings().all()
        except Exception as exc:
            logger.warning("chunks dense failed: %s", exc)

    # #661 Faz 5.2 — Article-level summary embedding dense search.
    # Title + subtitle + first paragraph embed'i ile sorgu vector'ünü kıyasla.
    # Top-N article'ları RRF'e bonus stream olarak ekle — niş bilgi article
    # gövdesinde olsa bile article ana teması ile semantic match yakalanır.
    summary_article_ids: list[str] = []
    summary_scores: dict[str, float] = {}
    if has_dense:
        try:
            summary_rows = (
                await db.execute(
                    sa_text(
                        f"""
                        SELECT a.id::text AS article_id,
                               1.0 - ((a.summary_embedding <=> (:vec)::vector) / 2.0) AS sum_score
                        FROM articles a
                        WHERE a.summary_embedding IS NOT NULL
                          AND a.status = 'cleaned'
                          AND ({dense_date_clause.replace('c.', 'a.')})
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
            ).mappings().all()
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
            ).mappings().all()
        except Exception as exc:
            logger.warning("summary chunk fetch failed: %s", exc)

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

    if ner_query_entities:
        target_aids, ner_mode, ner_df_map = await _ner_idf_match_aids(
            db, ner_query_entities
        )
        if target_aids:
            aid_list = list(target_aids)[:NER_FINAL_AIDS_CAP]
            aid_in = ", ".join(f"'{aid}'::uuid" for aid in aid_list)
            try:
                ner_chunk_rows = (
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
                ).mappings().all()
                logger.info(
                    "ner_idf_match q_ents=%d df=%s mode=%s aids=%d chunks=%d",
                    len(ner_query_entities),
                    {k: v for k, v in ner_df_map.items()},
                    ner_mode,
                    len(target_aids),
                    len(ner_chunk_rows),
                )
            except Exception as exc:
                logger.warning("ner chunk fetch failed: %s", exc)

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

    # #661 Faz 5.2 — Summary article'ların ilk chunk'larını RRF'e ekle.
    # Niş bilgi article gövdesinde olsa bile summary embed (title + subtitle
    # + first paragraph) sorgu ile semantic match → article retrieval'a
    # giriyor. Parent-doc retrieval ile sibling chunks da context'e gelir.
    for rank, row in enumerate(summary_chunk_rows, start=1):
        cid = str(row["id"])
        # Summary stream skoru biraz daha düşük weight (K=80) ki sparse/dense
        # dominantlığı korunsun
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (80 + rank)

    # #691 Faz 6.1 — NER entity match RRF (mode-aware weight).
    # multi_and (rare entity intersect): K=20 en güçlü (Faz 6 K=30'tan üst)
    # multi_and_common (common entity intersect, dar küme): K=20
    # single_rare: K=30 (Faz 6 eski seviye)
    # no_match: chunks zaten boş, geçilir
    if ner_chunk_rows:
        if ner_mode in ("multi_and", "multi_and_common"):
            ner_k = NER_BOOST_K_MULTI
        elif ner_mode == "single_rare":
            ner_k = NER_BOOST_K_SINGLE_RARE
        else:
            ner_k = None
        if ner_k is not None:
            for rank, row in enumerate(ner_chunk_rows, start=1):
                cid = str(row["id"])
                rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (ner_k + rank)

    if not rrf:
        return []

    # NOT: Entity boost rerank.py pipeline'ına bırakıldı (#660 revert).
    # Hybrid_search RRF'e entegrasyon Trump 6 Mayıs gibi vakaları geriletti —
    # entity (Trump) birçok rakip article'da da var → non-target rakipler
    # de boost alıyor. RRF doğal dense+sparse sıralaması daha güvenilir;
    # entity bonus rerank pipeline'ında (CE enabled iken) yardımcı olur.
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

    # #661 Faz 5.3 — Parent-document retrieval (RAGFlow tier).
    # Top-K chunk match'i sonrası, AYNI article'ın TÜM chunks'larını LLM
    # context'ine dahil et. Niş bilgi article ortasında olsa bile çevreleyen
    # paragraflar context'e taşınır → answer extraction kalitesi yükselir.
    # Default ON; flag ile kapatılabilir.
    try:
        parent_doc_enabled = await _load_parent_doc_setting()
    except Exception:
        parent_doc_enabled = True

    if parent_doc_enabled and results:
        try:
            results = await _expand_parent_documents(
                db=db, primary_results=results, max_chunks_per_article=5,
                final_top_k=top_k * 2,
            )
            logger.info(
                "parent_doc expansion: %d → %d chunks",
                len(set(str(r.get("article_id")) for r in results[:top_k])),
                len(results),
            )
        except Exception as exc:
            logger.warning("parent_doc expansion failed: %s", exc)

    return results


# ============================================================================
# Parent-document retrieval (#661 Faz 5.3)
# ============================================================================


async def _load_parent_doc_setting() -> bool:
    """retrieval.parent_doc_enabled — default ON (Faz 5.3)."""
    try:
        from app.core.db import get_session_factory
        from app.core.settings_store import settings_store

        factory = get_session_factory()
        async with factory() as db:
            return await settings_store.get_bool(
                db, "retrieval.parent_doc_enabled", True
            )
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
    ).mappings().all()

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
