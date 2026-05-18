"""Binary quantization helpers for embeddings (#221 MVP-1.5 PR-6).

Strateji: pgvector'ün native `binary_quantize()` fonksiyonu kullanılır
(DB tarafında işlem, network round-trip yok). Hamming distance
operatörü `<~>`. NDCG@10 düşüşü ≤ %3 (pgvector docs).

Settings flag: vector_quantization.enabled (default False).
True iken `hybrid_search_chunks` hot-path bit kolonunu kullanır
(sonraki PR'da entegre).

Bu modül scaffold — fonksiyon imzaları stabil, search routing
ayrı PR'da etkinleştirilir.
"""

from __future__ import annotations

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession


def vector_to_pg_literal(vector: list[float]) -> str:
    """Float listesi → pgvector literal `[v1,v2,...]` (7 hane precision)."""
    if not vector:
        return "[]"
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"


async def quantize_chunk_batch(
    db: AsyncSession,
    *,
    batch: int = 500,
) -> dict:
    """NULL embedding_binary olan chunk'lar için pgvector binary_quantize.

    - SADECE `embedding IS NOT NULL AND embedding_binary IS NULL` seçer
    - Tek SQL ile batch update (Python tarafında vector serialize yok)
    - Idempotent: aynı task tekrar çağrılabilir, aynı satıra dokunmaz

    Returns: {"updated": N, "remaining": M}
    """
    result = await db.execute(
        sa_text(
            """
            UPDATE article_chunks
            SET embedding_binary = binary_quantize(embedding)
            WHERE id IN (
                SELECT id FROM article_chunks
                WHERE embedding IS NOT NULL
                  AND embedding_binary IS NULL
                LIMIT :batch
            )
            """
        ),
        {"batch": batch},
    )
    updated = result.rowcount or 0

    remaining = (
        await db.execute(
            sa_text(
                """
                SELECT COUNT(*) FROM article_chunks
                WHERE embedding IS NOT NULL
                  AND embedding_binary IS NULL
                """
            )
        )
    ).scalar_one()

    await db.commit()
    return {"updated": int(updated), "remaining": int(remaining)}


async def search_chunks_binary(
    db: AsyncSession,
    *,
    query_vector: list[float],
    top_k: int = 50,
    since_hours: int | None = None,
) -> list[dict]:
    """Hamming distance ile binary HNSW araması.

    Search routing'de opt-in olarak kullanılır
    (settings vector_quantization.enabled).

    Returns: list[dict] — id + chunk_text + binary_distance + published_at
    """
    qvec_lit = vector_to_pg_literal(query_vector)
    where_clauses = ["embedding_binary IS NOT NULL"]
    params: dict = {"top_k": top_k, "qvec": qvec_lit}

    if since_hours is not None:
        where_clauses.append("published_at >= NOW() - (:hours || ' hours')::interval")
        params["hours"] = since_hours

    where_sql = " AND ".join(where_clauses)
    sql = sa_text(
        f"""
        SELECT id::text AS id,
               article_id::text AS article_id,
               source_id::text AS source_id,
               chunk_text,
               published_at,
               (embedding_binary <~> binary_quantize((:qvec)::vector))::float
                   AS binary_distance
        FROM article_chunks
        WHERE {where_sql}
        ORDER BY embedding_binary <~> binary_quantize((:qvec)::vector)
        LIMIT :top_k
        """  # noqa: S608
    )
    rows = (await db.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]
