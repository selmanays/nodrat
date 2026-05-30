"""retrieval NER subsystem — entity-IDF match + pure target-resolution (P5 B1, v3).

app/core/retrieval.py'den ÇIKARILAN (behavior-preserving pure move; 9-step iç parçalama).
`_resolve_ner_target_aids` (saf logic; test_retrieval 10 test) + `_ner_idf_match_aids`
(async DB entity-IDF). NER config sabitleri burada; retrieval re-import eder.
`_load_retrieval_settings` lazy import (circular-break — retrieval onu tutar).
"""

from __future__ import annotations

import logging

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

NER_DF_THRESHOLD = 30  # df < N → "nadir" entity (boost eligibility; ~%0.67 of 4436 corpus)
NER_BOOST_K_MULTI = 5  # 2+ rare entity intersect → EN güçlü (#718 final: 1/6≈0.167, sparse+gram+phrase combo'yu garantili geçer)
NER_BOOST_K_SINGLE_RARE = 15  # tek rare entity (#718 final: 1/16≈0.063, Faz 6 K=30'tan 4x güçlü)
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
        from app.core.retrieval import _load_retrieval_settings  # lazy (circular-break)

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
