"""retrieval runtime settings + RRF default constants (P5 B4, v3).

app/core/retrieval.py'den ÇIKARILAN (behavior-preserving pure move). #696 B7+C8:
`_load_retrieval_settings` her hybrid_search başında runtime-tunable config (NER + RRF)
döndürür — hardcoded RRF_* default'lar settings_store ile override edilebilir. NER_*
default'lar `_retrieval_ner`'den import edilir. Mantık değişmedi → recall sabit.
"""

from __future__ import annotations

from app.core._retrieval_ner import (
    NER_BOOST_K_MULTI,
    NER_BOOST_K_SINGLE_RARE,
    NER_DF_THRESHOLD,
    NER_FETCH_PER_ENTITY_LIMIT,
    NER_FINAL_AIDS_CAP,
)

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
