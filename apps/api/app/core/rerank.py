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
    if not settings.reranker_enabled:
        return rows[:top_k]

    if not rows or not query.strip():
        return rows[:top_k]

    try:
        provider = registry.route_for_tier(operation="rerank", tier="free")
    except (RuntimeError, NotImplementedError) as exc:
        logger.warning("rerank provider unavailable, skip: %s", exc)
        return rows[:top_k]

    passages = [_build_passage(r) for r in rows]
    try:
        results: list[RerankResult] = await provider.rerank(
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
    sorted_pairs = sorted(
        score_by_idx.items(), key=lambda x: x[1], reverse=True
    )

    out: list[dict] = []
    for idx, score in sorted_pairs[:top_k]:
        if 0 <= idx < len(rows):
            row = dict(rows[idx])
            row["_rerank_score"] = round(float(score), 4)
            out.append(row)

    logger.info(
        "rerank applied: input=%d → top-%d, top_score=%.3f",
        len(rows),
        len(out),
        out[0].get("_rerank_score", 0.0) if out else 0.0,
    )
    return out
