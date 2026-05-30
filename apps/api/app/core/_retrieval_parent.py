"""retrieval parent-document expansion — top-K chunk → article'ın tüm chunks'ları (P5 B3, v3).

app/core/retrieval.py'den ÇIKARILAN (behavior-preserving pure move). #661/#912:
primary chunk match → parent article'ın sibling chunks'ları context'e eklenir
(answer extraction kalitesi). `_load_parent_doc_setting` runtime config (default ON);
`_expand_parent_documents` sibling-chunk fetch + merge. Mantık değişmedi → recall sabit.
"""

from __future__ import annotations

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession


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
