"""Cross-encoder rerank wrapper (#181).

hybrid_search_* fonksiyonları RRF top-50 üretir, bu modül onu cross-encoder
ile rerank edip top-K döndürür.

Toggle: settings.reranker_enabled (False → no-op, original sıra korunur).

Provider abstraction: registry.route_for_tier(operation="rerank", tier="free")
Şu an NIM nv-rerankqa-mistral-4b-v3 (multilingual cross-encoder).
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.providers.base import RerankResult
from app.providers.registry import registry

logger = logging.getLogger(__name__)


def _build_passage(row: dict) -> str:
    """Agenda card / chunk row'undan passage metni oluştur."""
    title = str(row.get("title") or row.get("article_title") or "")[:200]
    summary = str(row.get("summary") or row.get("chunk_text") or "")[:600]
    if title and summary:
        return f"{title}\n\n{summary}"
    return title or summary


async def _load_rerank_settings(settings: Any) -> tuple[bool, int, float]:
    """Load runtime-tunable rerank settings (DB override → fallback).

    Returns: (enabled, min_query_words, min_combined_score)
    #266 — admin paneli üzerinden tune edilebilir.
    """
    enabled = settings.reranker_enabled
    min_query_words = settings.rerank_min_query_words
    min_combined = settings.rerank_min_combined_score
    try:
        from app.core.db import get_session_factory
        from app.core.settings_store import settings_store

        factory = get_session_factory()
        async with factory() as db:
            enabled = await settings_store.get_bool(
                db, "rerank.enabled", enabled
            )
            min_query_words = await settings_store.get_int(
                db, "rerank.min_query_words", min_query_words
            )
            min_combined = await settings_store.get_float(
                db, "rerank.min_combined_score", min_combined
            )
    except Exception as exc:  # pragma: no cover — config DB miss → fallback
        logger.debug("rerank settings load fallback: %s", exc)
    return enabled, min_query_words, min_combined


async def rerank_rows(
    *,
    query: str,
    rows: list[dict],
    top_k: int = 10,
) -> list[dict]:
    """RRF sonrası rerank stage.

    Args:
        query: User query (raw text)
        rows: hybrid_search çıktısı (her dict'te 'id', 'title', 'summary' var)
        top_k: Nihai döndürülecek sonuç sayısı

    Returns:
        Reranked rows (her row'a `_rerank_score` eklenir).
        Reranker disabled veya hata ise original sıra korunur.
    """
    settings = get_settings()

    # #266 — runtime-tunable settings (DB override → fallback hardcoded)
    enabled, min_query_words, min_combined = await _load_rerank_settings(
        settings
    )
    if not enabled:
        return rows[:top_k]

    if not rows or not query.strip():
        return rows[:top_k]

    # #253 — Cross-encoder kısa query'lerde başarısız (NIM rerank-qa "CHP",
    # "İmamoğlu" gibi tek-term'leri sürekli negatif logit'e işaretliyor →
    # alakalı CHP haberleri drop ediliyordu). Kısa query'ler için RRF sırasını
    # koru — RRF zaten title trigram + n-gram phrase match yapıyor.
    if len(query.split()) <= min_query_words - 1:
        logger.info(
            "rerank skip: short query (words=%d, min=%d)",
            len(query.split()),
            min_query_words,
        )
        return rows[:top_k]

    try:
        provider = registry.route_for_tier(operation="rerank", tier="free")
    except (RuntimeError, NotImplementedError) as exc:
        logger.warning("rerank provider unavailable, skip: %s", exc)
        return rows[:top_k]

    passages = [_build_passage(r) for r in rows]

    # #190 — cost_tracker entegrasyonu (admin RAG observability)
    factory = None
    try:
        from app.core.db import get_session_factory

        factory = get_session_factory()
    except Exception:  # pragma: no cover
        factory = None

    try:
        if factory is not None:
            from app.core.cost_tracker import track_provider_call

            async with factory() as db:
                async with track_provider_call(
                    db=db,
                    provider=provider.name,
                    operation="rerank",
                ) as tracker:
                    results = await provider.rerank(
                        query=query,
                        documents=passages,
                        top_k=min(top_k, len(passages)),
                    )
                    tracker.record(
                        input_tokens=len(query.split())
                        + sum(len(p.split()) for p in passages),
                        output_tokens=0,
                        cost_usd=0.0,
                        model=getattr(
                            provider, "_default_model", "nim_rerank"
                        ),
                    )
                await db.commit()
        else:
            results = await provider.rerank(
                query=query,
                documents=passages,
                top_k=min(top_k, len(passages)),
            )
    except Exception as exc:  # pragma: no cover
        logger.warning("rerank call failed, fallback to RRF order: %s", exc)
        return rows[:top_k]

    if not results:
        return rows[:top_k]

    # Index → rerank score map
    score_by_idx = {r.index: r.score for r in results}

    # #251/#259 — Combined ranking: alaka ön-koşullu importance boost.
    #   logit > 0 (cross-encoder pozitif sinyal):
    #     0.65 × sigmoid(logit) + 0.35 × importance
    #   logit ≤ 0 (alakasız):
    #     linear penalty × importance — tamamen sıfırlamak yerine kademeli
    #     skala. logit=-NEG_FLOOR ile drop, logit=0 ile yüksek puan.
    #     Önceki sürüm sadece sigmoid kullanıyordu → "Otomotiv ihracat"
    #     gibi orta-alakalı + high-imp kartlar Türkiye-ekonomi sorgusunda
    #     top'a çıkamıyordu (logit=-10 → 0 → drop).
    #   Adana sel (logit=-16, imp=0.85) ise factor=0.2 ile threshold altı.
    import math as _math

    RERANK_W = 0.65
    IMP_W = 0.35
    NEG_FLOOR = 20.0  # logit=-20 → tamamen sıfır
    MIN_COMBINED = min_combined

    def _combined(idx: int) -> float:
        logit = score_by_idx.get(idx, 0.0)
        try:
            imp = float(rows[idx].get("importance_score") or 0.5)
        except (TypeError, ValueError):
            imp = 0.5
        if logit > 0:
            sig = 1.0 / (1.0 + _math.exp(-logit))
            return RERANK_W * sig + IMP_W * imp
        # logit ≤ 0: linear penalty
        # logit=-20 → factor=0,  logit=-10 → factor=0.5,  logit=0 → factor=1
        factor = max(0.0, 1.0 + logit / NEG_FLOOR)
        return factor * (0.5 * imp + 0.2)

    enriched = [(idx, score_by_idx[idx], _combined(idx)) for idx in score_by_idx]
    enriched.sort(key=lambda x: x[2], reverse=True)

    out: list[dict] = []
    dropped_low_relevance = 0
    for idx, raw_logit, combined in enriched[:top_k]:
        if 0 <= idx < len(rows):
            if combined < MIN_COMBINED:
                dropped_low_relevance += 1
                continue
            row = dict(rows[idx])
            row["_rerank_score"] = round(float(raw_logit), 4)
            row["_combined_score"] = round(float(combined), 4)
            out.append(row)

    logger.info(
        "rerank applied: input=%d → top-%d (dropped=%d), "
        "top_combined=%.3f, top_logit=%.3f",
        len(rows),
        len(out),
        dropped_low_relevance,
        out[0].get("_combined_score", 0.0) if out else 0.0,
        out[0].get("_rerank_score", 0.0) if out else 0.0,
    )
    return out
