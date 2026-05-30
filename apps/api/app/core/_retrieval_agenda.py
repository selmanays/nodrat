"""retrieval agenda-cards hybrid search — RRF + NER + rerank (P5 B6, v3).

app/core/retrieval.py'den ÇIKARILAN (behavior-preserving pure move). Agenda-cards
(daily/weekly suite) için sparse+dense RRF fusion + NER IDF boost + phrase/gram boost
+ semantic rerank. Mantık değişmedi → recall/ranking by-construction sabit.

PUBLIC: admin_rag + modules/public/search + retrieval_benchmark
`from app.core.retrieval import hybrid_search_agenda_cards` ile erişir → retrieval.py
re-export eder (# noqa: F401).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core._retrieval_ner import _ner_idf_match_aids
from app.core._retrieval_phrase import (
    _build_sql_quote_strip,
    _phrase_grams,
    _phrase_match_threshold,
    normalize_tr_query,
)
from app.core._retrieval_settings import _load_retrieval_settings
from app.core._retrieval_vector import _parse_pgvector_text

logger = logging.getLogger(__name__)


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
