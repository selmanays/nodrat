"""Wikipedia + Wikidata HTTP provider — Layer 2 knowledge fallback (#811 Faz 2 2E).

Plan: /Users/selmanay/.claude/plans/nerdi-in-ekilde-faz-2-unified-nebula.md
Wiki: wiki/entities/wikipedia-provider.md (oluşturulacak)

Bu **ModelProvider DEĞİL** — knowledge provider (ayrı kategori). Chat'in
Layer 1 (haber arşivi) yetersiz kaldığı durumlarda, kullanıcı CTA onayı
ile (2B'de wire) tetiklenir.

Mimari:
  Layer 1 — Realtime News  (mevcut, chunks-first retrieval)
  Layer 2 — General Knowledge  (BU MODUL)
  Layer 3 — Conversation Memory  (mevcut, Faz 1)

API endpointleri:
  Wikipedia REST     : https://{lang}.wikipedia.org/api/rest_v1
  Wikipedia Action   : https://{lang}.wikipedia.org/w/api.php (opensearch)
  Wikidata SPARQL    : https://query.wikidata.org/sparql

Cost: $0 (no API key). Rate limit Wikipedia 200 req/sn — Nodrat trafiği
için >100x tampon. Redis 24h cache her halükarda dış yük düşürür.

Lisans: CC BY-SA 4.0 — 25 kelime quote cap zaten FSEK kuralımız (Türkiye
Telif Hakları). license alanı response'a dahil edilir, frontend chip
gösterir.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_TIMEOUT = httpx.Timeout(8.0, connect=3.0)
USER_AGENT = "Nodrat/1.0 (https://nodrat.com; contact@nodrat.com)"
CACHE_KEY_VERSION = "v1"
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_LANG_PRIORITY = ["tr", "en"]
DEFAULT_MAX_RESULTS = 3

# Wikidata properties — most-asked factual
WIKIDATA_FACTUAL_PROPS = {
    "P569": "birth_date",       # doğum tarihi
    "P570": "death_date",       # ölüm tarihi
    "P1082": "population",      # nüfus
    "P571": "founded_date",     # kuruluş tarihi
    "P36": "capital",           # başkent
    "P39": "position",          # pozisyon (CEO, başkan)
    "P17": "country",           # ülke
    "P102": "party",            # siyasi parti
}


# =============================================================================
# Data classes
# =============================================================================


@dataclass
class WikiArticle:
    """Wikipedia opensearch + summary sonucu — chat'te source pill olur."""

    title: str
    summary: str            # extract (max ~1200 char)
    url: str
    page_id: int
    lang: str = "tr"
    license: str = "CC BY-SA 4.0"
    description: str | None = None  # short description (Wikidata-derived)


@dataclass
class WikidataFact:
    """Wikidata SPARQL Q-ID factual property."""

    qid: str                    # Q-ID (Q42 vb.)
    label: str                  # entity adı
    properties: dict[str, Any] = field(default_factory=dict)
    """Property code → value (örn. {'P569': '1946-06-14'})"""


# =============================================================================
# Redis cache (planner_cache pattern mirror)
# =============================================================================


_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        s = get_settings()
        _redis_client = aioredis.from_url(s.redis_url, decode_responses=True)
    return _redis_client


def _cache_key(query: str, lang: str, kind: str = "search") -> str:
    """SHA1 + tarih granülasyonu. `kind` = search | summary | wikidata."""
    when = datetime.now(UTC).strftime("%Y%m%d")
    raw = f"{query.strip().lower()}|{lang}|{kind}|{when}"
    digest = hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"wiki:{CACHE_KEY_VERSION}:{kind}:{lang}:{digest}"


async def _cache_get(key: str) -> Any | None:
    try:
        raw = await _get_redis().get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception as exc:  # pragma: no cover
        logger.warning("wikipedia cache get failed: %s", exc)
        return None


async def _cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        await _get_redis().setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False))
    except Exception as exc:  # pragma: no cover
        logger.warning("wikipedia cache set failed: %s", exc)


# =============================================================================
# Provider
# =============================================================================


class WikipediaProvider:
    """Wikipedia REST + Wikidata SPARQL HTTP client.

    Stateless — her metod çağrısında httpx.AsyncClient yeni context manager
    açar (connection pool kısa ömürlü, dış API rate limit'i etkilenmez).

    Test edilebilirlik: `transport` parametresiyle httpx.MockTransport
    enjekte edilebilir (production None → gerçek HTTP).
    """

    def __init__(
        self,
        *,
        cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        lang_priority: list[str] | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self.lang_priority = lang_priority or DEFAULT_LANG_PRIORITY
        self.timeout = timeout
        self._transport = transport

    def _make_client(self) -> httpx.AsyncClient:
        """Test-injectable HTTP client factory."""
        return httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": USER_AGENT},
            transport=self._transport,
        )

    # ---- Wikipedia search ------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        lang: str | None = None,
        top_k: int = DEFAULT_MAX_RESULTS,
    ) -> list[WikiArticle]:
        """Wikipedia opensearch + summary fetch.

        Akış:
          1. Cache hit kontrol
          2. opensearch API → top title'lar
          3. Her title için /api/rest_v1/page/summary
          4. Lang fallback (tr→en) eğer tr boş veya yetersiz

        Returns:
            list[WikiArticle] — boş liste = bulunamadı.
        """
        query = query.strip()
        if not query:
            return []

        langs = [lang] if lang else self.lang_priority

        for lg in langs:
            cache_key = _cache_key(query, lg, "search")
            cached = await _cache_get(cache_key)
            if cached:
                logger.debug("wikipedia search HIT lang=%s query='%s'", lg, query[:50])
                return [_article_from_dict(d) for d in cached][:top_k]

            articles = await self._search_lang(query, lg, top_k)
            if articles:
                await _cache_set(
                    cache_key,
                    [_article_to_dict(a) for a in articles],
                    self.cache_ttl_seconds,
                )
                logger.info(
                    "wikipedia search MISS lang=%s query='%s' → %d results",
                    lg, query[:50], len(articles),
                )
                return articles

        return []

    async def _search_lang(
        self, query: str, lang: str, top_k: int,
    ) -> list[WikiArticle]:
        """Wikipedia search API + summary fetch (single lang)."""
        base = f"https://{lang}.wikipedia.org"

        async with self._make_client() as client:
            # #824 fix: opensearch (prefix/autocomplete) RELEVANCE'i zayıf —
            # "Donald Trump" araması "Donald Trump karşıtı protestolar" gibi
            # alt-konuları ana entity sayfasından önce döndürüyordu
            # (production'da gözlemlendi). list=search Wikipedia'nın gerçek
            # full-text arama motoru, relevance-ranked döner.
            try:
                resp = await client.get(
                    f"{base}/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "srlimit": top_k,
                        "srnamespace": 0,
                        "srsort": "relevance",
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("wikipedia search failed lang=%s: %s", lang, exc)
                return []

            # query+list=search format:
            #   {"query": {"search": [{"title": "...", "snippet": "..."}, ...]}}
            search_hits = (
                data.get("query", {}).get("search", [])
                if isinstance(data, dict)
                else []
            )
            if not search_hits:
                return []
            titles = [h.get("title", "") for h in search_hits if h.get("title")]

            # 2. Her title için summary fetch (paralel) — relevance sırası korunur
            summaries = await asyncio.gather(
                *[self._fetch_summary(client, base, t, lang) for t in titles],
                return_exceptions=True,
            )

            results: list[WikiArticle] = []
            for title, summary_res in zip(titles, summaries, strict=False):
                if isinstance(summary_res, Exception) or summary_res is None:
                    continue
                if not summary_res.url:
                    summary_res.url = f"{base}/wiki/{quote(title)}"
                results.append(summary_res)

            return results

    async def _fetch_summary(
        self,
        client: httpx.AsyncClient,
        base: str,
        title: str,
        lang: str,
    ) -> WikiArticle | None:
        try:
            resp = await client.get(
                f"{base}/api/rest_v1/page/summary/{quote(title)}",
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            extract = (data.get("extract") or "")[:1200]
            if not extract:
                return None
            return WikiArticle(
                title=str(data.get("title") or title),
                summary=extract,
                url=str(data.get("content_urls", {}).get("desktop", {}).get("page", "")),
                page_id=int(data.get("pageid") or 0),
                lang=lang,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "wikipedia summary failed lang=%s title='%s': %s", lang, title, exc,
            )
            return None

    # ---- Wikidata SPARQL ------------------------------------------------

    async def wikidata_factual(
        self,
        query: str,
        *,
        lang: str = "tr",
    ) -> WikidataFact | None:
        """Wikidata Q-ID + factual properties lookup.

        Akış:
          1. wbsearchentities → top Q-ID
          2. SPARQL: SELECT properties (WIKIDATA_FACTUAL_PROPS subset)
          3. Cache 24h

        Returns:
            WikidataFact | None — bulunamadı veya hata.
        """
        query = query.strip()
        if not query:
            return None

        cache_key = _cache_key(query, lang, "wikidata")
        cached = await _cache_get(cache_key)
        if cached:
            return WikidataFact(**cached)

        async with self._make_client() as client:
            # 1. Search entities
            try:
                resp = await client.get(
                    "https://www.wikidata.org/w/api.php",
                    params={
                        "action": "wbsearchentities",
                        "search": query,
                        "language": lang,
                        "limit": 1,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("wikidata search failed: %s", exc)
                return None

            results = data.get("search") or []
            if not results:
                return None
            top = results[0]
            qid = top.get("id")
            label = top.get("label") or query

            if not qid:
                return None

            # 2. SPARQL — Q-ID properties
            props_list = ", ".join(f"wdt:{p}" for p in WIKIDATA_FACTUAL_PROPS)
            sparql = f"""
            SELECT ?prop ?value WHERE {{
              VALUES ?prop {{ {props_list} }}
              wd:{qid} ?prop ?value.
            }}
            """
            try:
                resp = await client.get(
                    "https://query.wikidata.org/sparql",
                    params={"query": sparql, "format": "json"},
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/sparql-results+json",
                    },
                )
                resp.raise_for_status()
                sparql_data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("wikidata sparql failed qid=%s: %s", qid, exc)
                return None

            properties: dict[str, Any] = {}
            for binding in sparql_data.get("results", {}).get("bindings", []):
                prop_uri = binding.get("prop", {}).get("value", "")
                value = binding.get("value", {}).get("value")
                if not prop_uri or value is None:
                    continue
                # http://www.wikidata.org/prop/direct/P569 → P569
                prop_code = prop_uri.rsplit("/", 1)[-1]
                if prop_code not in WIKIDATA_FACTUAL_PROPS:
                    continue
                # İlk değeri al (multi-value property'lerde rastgele)
                if prop_code not in properties:
                    properties[prop_code] = value

            fact = WikidataFact(qid=qid, label=label, properties=properties)
            await _cache_set(
                cache_key,
                {"qid": fact.qid, "label": fact.label, "properties": fact.properties},
                self.cache_ttl_seconds,
            )
            return fact


# =============================================================================
# Helpers
# =============================================================================


def _article_to_dict(a: WikiArticle) -> dict[str, Any]:
    return {
        "title": a.title,
        "summary": a.summary,
        "url": a.url,
        "page_id": a.page_id,
        "lang": a.lang,
        "license": a.license,
        "description": a.description,
    }


def _article_from_dict(d: dict[str, Any]) -> WikiArticle:
    return WikiArticle(
        title=str(d.get("title", "")),
        summary=str(d.get("summary", "")),
        url=str(d.get("url", "")),
        page_id=int(d.get("page_id") or 0),
        lang=str(d.get("lang", "tr")),
        license=str(d.get("license", "CC BY-SA 4.0")),
        description=d.get("description"),
    )


# Default singleton — chat_stream lazy import edip kullanır
_default_provider: WikipediaProvider | None = None


async def get_wikipedia_provider() -> WikipediaProvider:
    """Singleton accessor — settings'ten config oku, lazy init."""
    global _default_provider
    if _default_provider is not None:
        return _default_provider

    # Settings (best-effort — bozuksa default)
    try:
        from app.core.db import get_session_factory
        from app.core.settings_store import settings_store

        factory = get_session_factory()
        async with factory() as db:
            ttl_hours = await settings_store.get_int(
                db, "wikipedia.cache_ttl_hours", DEFAULT_CACHE_TTL_HOURS,
            )
            lang_raw = await settings_store.get(
                db, "wikipedia.lang_priority", DEFAULT_LANG_PRIORITY,
            )
            lang_priority = (
                lang_raw
                if isinstance(lang_raw, list) and lang_raw
                else DEFAULT_LANG_PRIORITY
            )
    except Exception as exc:
        logger.warning("wikipedia provider config load failed: %s", exc)
        ttl_hours = DEFAULT_CACHE_TTL_HOURS
        lang_priority = DEFAULT_LANG_PRIORITY

    _default_provider = WikipediaProvider(
        cache_ttl_hours=ttl_hours,
        lang_priority=lang_priority,
    )
    return _default_provider
