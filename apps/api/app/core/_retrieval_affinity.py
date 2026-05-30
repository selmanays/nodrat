"""retrieval L2 affinity boost — user-personalization post-processing (P5 B5, v3).

app/core/retrieval.py'den ÇIKARILAN (behavior-preserving pure move). flag+user gate'li
ADDITIVE boost: kullanıcının L2 affinity profiline göre chunk skorlarını ek-puanlar
(retrieval sırasını user-personalize eder). Mantık değişmedi → recall/ranking sabit.

PUBLIC: research_tools + test_l2_affinity `from app.core.retrieval import apply_l2_affinity_boost`
ile erişir → retrieval.py re-export eder (# noqa: F401).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core._retrieval_phrase import normalize_tr_query


async def apply_l2_affinity_boost(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    chunks: list[dict],
) -> list[dict]:
    """Kullanıcının yüksek-affinity araştırma kümelerine ait entity'lerle
    eşleşen sonuçlara ADDITIVE `_rrf_score` boost (#1019 Faz 5).

    Retrieval CORE ve Redis cache'inden SONRA, research-path'inde (kullanıcı
    bağlamı mevcut) çağrılır → base RRF cache user-agnostik kalır
    (S11: cache cross-user sızması YOK).

    İnvaryant:
      - flag kapalı | user_id None | affinity boş | eşleşme yok → chunks
        DEĞİŞMEDEN döner (byte-identical, #854).
      - ASLA down-rank (S6): yalnız eşleşen article chunk'ına +boost;
        diğer satırlar DOKUNULMAZ (negatif düzeltme YOK).
      - User-scoped (S11): yalnız message_clusters.user_id=:uid.
      - Deprecated küme hariç (S12): research_clusters.deprecated_at IS NULL.
      - Cevap prompt'u / citation / halü / freshness ETKİLENMEZ — yalnız
        retrieved chunk listesinin sırası (recall sinyali).
    """
    if user_id is None or not chunks:
        return chunks

    from app.shared.runtime_config.settings_store import settings_store

    if not await settings_store.get_bool(db, "research.l2_affinity_enabled", False):
        return chunks
    boost = await settings_store.get_float(db, "research.l2_affinity_boost", 0.05)
    if boost <= 0:
        return chunks

    # 1) Affinity küme adları — user-scoped (S11), deprecated hariç (S12)
    name_rows = (
        (
            await db.execute(
                sa_text(
                    """
                    SELECT rc.canonical_name AS name
                    FROM message_clusters mc
                    JOIN research_clusters rc ON rc.id = mc.cluster_id
                    WHERE mc.user_id = :uid
                      AND rc.deprecated_at IS NULL
                    GROUP BY rc.canonical_name
                    ORDER BY SUM(mc.mention_count) DESC
                    LIMIT 25
                    """
                ),
                {"uid": str(user_id)},
            )
        )
        .scalars()
        .all()
    )
    # Türkçe-güvenli Python normalize (C-locale SQL LOWER tuzağından kaç — #939)
    affinity = {normalize_tr_query(n) for n in name_rows if n}
    affinity.discard("")
    if not affinity:
        return chunks

    aids = {str(c["article_id"]) for c in chunks if c.get("article_id")}
    if not aids:
        return chunks

    # 2) Aday article entity'leri (haber-korpusu çapası S11); Python-tarafı
    #    normalize ile kesiştir (collation-güvenli)
    ent_rows = (
        await db.execute(
            sa_text(
                """
                SELECT article_id::text AS aid, entity_normalized AS ent
                FROM entities
                WHERE article_id::text = ANY(:aids)
                """
            ),
            {"aids": list(aids)},
        )
    ).all()
    matched_aids = {aid for aid, ent in ent_rows if ent and normalize_tr_query(ent) in affinity}
    if not matched_aids:
        return chunks

    # 3) ADDITIVE boost (S6: yalnız +, asla -); eşleşmeyen satır DOKUNULMAZ
    for c in chunks:
        if str(c.get("article_id")) in matched_aids:
            c["_rrf_score"] = float(c.get("_rrf_score", 0.0) or 0.0) + boost

    # Stable re-sort (Python sorted kararlı → eşit skor göreli sıra korunur)
    return sorted(chunks, key=lambda c: float(c.get("_rrf_score", 0.0) or 0.0), reverse=True)
