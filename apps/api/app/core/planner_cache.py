"""Query planner Redis cache (issue #527).

Plan'ı Redis'te 24h TTL ile sakla; tekrar eden gündem sorgularında planner
LLM round-trip'i (~1.5s) yerine cache hit (~10ms).

Key formatı (CACHE_KEY_VERSION="v2" #778 — plan schema'ya
critical_entities eklendi; prompt_version #947 — planner prompt/
mantığı değişince gün-içi cache otomatik invalidate):
    qp:v2:{sha1(prompt_version + request_text + locale + tier + date_yyyymmdd)}

date_yyyymmdd ile gün granülasyonu hash'e dahil — gündem sorguları için
"bugün" semantiği gün içinde stabil, ertesi gün otomatik refresh olur.

Cache HIT olduğunda planner LLM çağrısı YAPILMAZ; serialize edilmiş plan
JSON'u parse edilip QueryPlan döner. Cost: ~10ms Redis round-trip + JSON
parse.

Cache MISS davranışı eski path ile aynı.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

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


CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h
CACHE_KEY_VERSION = "v2"  # #778 — plan schema'sına critical_entities eklendi


def _cache_key(
    *,
    request_text: str,
    locale: str,
    tier: str,
    current_time: datetime | None = None,
    prompt_version: str = "",
) -> str:
    """Cache key — gün granülasyonunda stable.

    Aynı kullanıcı veya farklı kullanıcılar gün içinde aynı request_text +
    locale + tier kombinasyonunu yazarsa hit alır.

    #947 — `prompt_version` (planner SYSTEM_PROMPT sürümü) key'e dahil:
    prompt/planner mantığı değişince (deploy) eski gün-içi cache otomatik
    miss olur; aksi halde deploy-öncesi BOZUK plan 24h TTL boyunca servis
    edilir (conv 06a034cf: `['gelişmeler','özgür']` cached → fix deploy
    edilse bile gün boyu eski sonuç). Caller (plan_query) PROMPT_VERSION
    geçirir — planner_cache query_planner'ı import etmez (circular yok).
    """
    when = current_time or datetime.now(UTC)
    date_str = when.strftime("%Y%m%d")
    raw = f"{prompt_version}|{request_text.strip()}|{locale}|{tier}|{date_str}"
    # SHA1 cache key — security context değil, collision yok hedef ihtiyaç.
    digest = hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"qp:{CACHE_KEY_VERSION}:{digest}"


async def get_cached_plan(
    *,
    request_text: str,
    locale: str,
    tier: str,
    current_time: datetime | None = None,
    prompt_version: str = "",
) -> dict | None:
    """Cache hit'te plan dict döner (parse edilmiş), miss'te None.

    Caller dict'i QueryPlan'a hidrate eder (parse_response or direct
    construct). `prompt_version` #947 — bkz `_cache_key`.
    """
    if not request_text:
        return None
    try:
        client = _get_redis()
        key = _cache_key(
            request_text=request_text,
            locale=locale,
            tier=tier,
            current_time=current_time,
            prompt_version=prompt_version,
        )
        raw = await client.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            logger.warning("planner_cache: bad JSON, evicting key=%s", key)
            await client.delete(key)
            return None
        return data
    except Exception as exc:  # pragma: no cover — Redis down değil, just miss
        logger.warning("planner_cache get failed: %s", exc)
        return None


async def set_cached_plan(
    *,
    request_text: str,
    locale: str,
    tier: str,
    plan_dict: dict,
    current_time: datetime | None = None,
    prompt_version: str = "",
) -> None:
    """Plan'ı cache'e koy. Best-effort; hata durumunda sessiz.

    plan_dict: serializable QueryPlan dict (intent, topic_query, keywords,
    requested_count, mode, timeframes (label/from_iso/to_iso), output_type,
    tone, geographic_focus, constraints, needs_sources,
    minimum_evidence_per_period, is_short_query, warnings).
    """
    if not request_text or not plan_dict:
        return
    try:
        client = _get_redis()
        key = _cache_key(
            request_text=request_text,
            locale=locale,
            tier=tier,
            current_time=current_time,
            prompt_version=prompt_version,
        )
        await client.setex(key, CACHE_TTL_SECONDS, json.dumps(plan_dict))
    except Exception as exc:  # pragma: no cover
        logger.warning("planner_cache set failed: %s", exc)
