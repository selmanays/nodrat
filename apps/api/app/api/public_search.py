"""Public search endpoint — anonim haber arama (#261 Phase A).

docs/strategy/pricing-strategy.md §2.1b — Anonim Ziyaretçi
docs/product/prd.md — Search-as-a-Service TOFU funnel

Endpoint:
    GET  /public/search?q=...&limit=10  — Anonim semantic agenda card arama
    GET  /public/cluster/{slug}         — Tek cluster timeline (Phase B)

Rate limit: IP başına 10 req/min (Redis sliding window).
Auth: Yok — anonim. Robots.txt: /api/public/* ALLOW.
KVKK: PII redaction yok (query log only IP+timestamp, 30g retention).
"""

from __future__ import annotations

import logging
import time
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db
from app.core.deps import get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Rate limit (IP-bazlı sliding window via Redis)
# =============================================================================

PUBLIC_SEARCH_RATE = 10  # req/min/IP
PUBLIC_SEARCH_WINDOW = 60  # seconds


_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        s = get_settings()
        _redis_client = aioredis.from_url(s.redis_url, decode_responses=True)
    return _redis_client


async def _check_rate_limit(ip: str) -> tuple[bool, int]:
    """Sliding window — son 60s'de kaç istek? True = OK, False = blocked.

    Returns: (ok, remaining_count)
    """
    try:
        client = _get_redis()
        key = f"public_search:ratelimit:{ip}"
        # INCR + EXPIRE atomic'liği: pipeline ile
        async with client.pipeline(transaction=True) as pipe:
            await pipe.incr(key)
            await pipe.expire(key, PUBLIC_SEARCH_WINDOW)
            results = await pipe.execute()
        count = int(results[0])
        remaining = max(0, PUBLIC_SEARCH_RATE - count)
        return count <= PUBLIC_SEARCH_RATE, remaining
    except Exception as exc:  # pragma: no cover
        logger.warning("rate limit check failed (fail-open): %s", exc)
        return True, PUBLIC_SEARCH_RATE  # fail-open


# =============================================================================
# Schemas
# =============================================================================


class SearchResultItem(BaseModel):
    """Public search response item — minimum field'lar (FSEK 25 word kuralı)."""

    id: str
    title: str
    summary: str
    """Max 250 char özet — tam içerik gösterilmez."""
    published_at: str | None = None
    source_name: str | None = None
    source_url: str
    """Yayıncı sitesine link (CTR > %30 hedef)."""
    country: str | None = None
    relevance_score: float = 0.0


class SearchResponse(BaseModel):
    query: str
    total: int
    items: list[SearchResultItem]
    rate_limit_remaining: int


# =============================================================================
# Endpoint
# =============================================================================


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Anonim haber arama — semantic search public (#261)",
)
async def public_search(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> SearchResponse:
    """Anonim ziyaretçilerin agenda card arşivinde arama yapması.

    - IP başına 10 req/min rate limit
    - Tam içerik DEĞİL (FSEK 25 kelime kuralı): title + 250 char özet + link
    - Provider: hybrid_search_agenda_cards reuse (embedding + trigram)
    """
    ip = get_client_ip(request) or "0.0.0.0"
    ok, remaining = await _check_rate_limit(ip)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT",
                "title": "Çok fazla istek",
                "detail": f"IP başına {PUBLIC_SEARCH_RATE} req/min. Yavaşlat.",
            },
        )

    # Embedding üret (try; fallback sparse-only)
    query_vector: list[float] | None = None
    try:
        from app.providers.registry import bootstrap_default_providers, registry

        if not registry._providers:
            bootstrap_default_providers()
        emb_provider = registry.route_for_tier(operation="embedding", tier="free")
        emb_result = await emb_provider.create_embedding(texts=[q])
        if emb_result and emb_result.embeddings:
            query_vector = emb_result.embeddings[0]
    except Exception as exc:  # pragma: no cover
        logger.warning("public_search embedding failed (sparse-only): %s", exc)

    # Hybrid search reuse — sadece daily level (yayınlanmış kartlar)
    from app.core.retrieval import hybrid_search_agenda_cards

    rows = await hybrid_search_agenda_cards(
        db,
        query_text=q,
        query_vector=query_vector,
        top_k=limit,
        rerank=False,  # public search'te rerank skip (latency + cost)
        levels=("daily",),
    )

    items: list[SearchResultItem] = []
    for r in rows:
        # FSEK uyumu: max 250 char özet, tam metin YOK
        summary = (r.get("summary") or "")[:250]
        items.append(
            SearchResultItem(
                id=str(r.get("id", "")),
                title=r.get("title") or "",
                summary=summary,
                published_at=(
                    r["published_at"].isoformat()
                    if r.get("published_at")
                    else None
                ),
                source_name=r.get("source_name"),
                source_url=r.get("source_url") or "",
                country=r.get("country"),
                relevance_score=float(r.get("combined_score", 0.0)),
            )
        )

    # Telemetry — admin observability için (Phase A baseline)
    try:
        client = _get_redis()
        await client.incr(f"public_search:total:{int(time.time() // 86400)}")
    except Exception:
        pass

    return SearchResponse(
        query=q, total=len(items), items=items, rate_limit_remaining=remaining
    )
