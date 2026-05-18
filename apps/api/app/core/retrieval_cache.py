"""Retrieval result Redis cache (#784).

Plan: hybrid_search_chunks sonucunu Redis'te kısa TTL ile sakla. Aynı sorgu
aynı gün tekrar gelirse retrieve pipeline (sparse + dense + summary + ner +
keyword + critical_entity + parent_doc) **TAMAMEN ATLA** — sub-saniye yanıt.

Cache key (sha1):
    rqc:v1:{sha1(norm_query + tf_from + tf_to + since_hours + top_k + sorted(critical_entities))}

Value: orjson-serialized list[dict] (chunks). UUID/datetime → str.

TTL: 1 saat (haberler hızlı döner, planner cache 24h'tan kısa).

Cache HIT: pipeline atlanır.
Cache MISS: pipeline çalışır + sonuç cache'lenir.

Hit/miss telemetri: logger.info ile basit.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)


_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        s = get_settings()
        _redis_client = aioredis.from_url(s.redis_url, decode_responses=True)
    return _redis_client


CACHE_TTL_SECONDS = 60 * 60  # 1h — haberler hızlı dönüyor
CACHE_KEY_VERSION = "v1"


def _cache_key(
    *,
    norm_query: str,
    top_k: int,
    candidate_pool: int,
    since_hours: int,
    timeframe_from: datetime | None,
    timeframe_to: datetime | None,
    critical_entities: list[str] | None,
) -> str:
    """Cache key — query + retrieval parametreleri ile hash.

    `critical_entities` sorted: aynı entity'ler farklı sıralarda → aynı key.
    """
    ce_sorted = sorted(critical_entities) if critical_entities else []
    tf_from_str = timeframe_from.isoformat() if timeframe_from else ""
    tf_to_str = timeframe_to.isoformat() if timeframe_to else ""
    raw = (
        f"{norm_query.strip()}|{top_k}|{candidate_pool}|{since_hours}"
        f"|{tf_from_str}|{tf_to_str}|{','.join(ce_sorted)}"
    )
    digest = hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"rqc:{CACHE_KEY_VERSION}:{digest}"


def _serialize_chunk(row: dict) -> dict:
    """dict içindeki UUID/datetime → str."""
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif hasattr(v, "hex") and hasattr(v, "version"):  # UUID
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _deserialize_chunk(row: dict) -> dict:
    """ISO datetime str'leri tekrar datetime'a çevir (published_at vb.)."""
    out = dict(row)
    for date_field in ("published_at",):
        v = out.get(date_field)
        if isinstance(v, str):
            try:
                out[date_field] = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
    return out


async def get_cached_retrieval(
    *,
    norm_query: str,
    top_k: int,
    candidate_pool: int,
    since_hours: int,
    timeframe_from: datetime | None,
    timeframe_to: datetime | None,
    critical_entities: list[str] | None,
) -> list[dict] | None:
    """Cache lookup. Hit → list[dict], miss → None.

    Hata durumunda None (miss davranışı) — pipeline normal çalışır.
    """
    try:
        key = _cache_key(
            norm_query=norm_query,
            top_k=top_k,
            candidate_pool=candidate_pool,
            since_hours=since_hours,
            timeframe_from=timeframe_from,
            timeframe_to=timeframe_to,
            critical_entities=critical_entities,
        )
        r = _get_redis()
        raw = await r.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("retrieval_cache bad JSON, evicting key=%s", key[:30])
            await r.delete(key)
            return None
        if not isinstance(data, list):
            return None
        return [_deserialize_chunk(r) for r in data]
    except Exception as exc:
        logger.warning("retrieval_cache get failed: %s", exc)
        return None


async def set_cached_retrieval(
    *,
    norm_query: str,
    top_k: int,
    candidate_pool: int,
    since_hours: int,
    timeframe_from: datetime | None,
    timeframe_to: datetime | None,
    critical_entities: list[str] | None,
    results: list[dict],
) -> None:
    """Cache write — TTL 1h. Hata fail-silent."""
    if not results:
        return
    try:
        key = _cache_key(
            norm_query=norm_query,
            top_k=top_k,
            candidate_pool=candidate_pool,
            since_hours=since_hours,
            timeframe_from=timeframe_from,
            timeframe_to=timeframe_to,
            critical_entities=critical_entities,
        )
        r = _get_redis()
        serialized = [_serialize_chunk(row) for row in results]
        # Filter out unpicklable types — keep core fields
        safe_payload = json.dumps(serialized, ensure_ascii=False, default=str)
        await r.set(key, safe_payload, ex=CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.warning("retrieval_cache set failed: %s", exc)
