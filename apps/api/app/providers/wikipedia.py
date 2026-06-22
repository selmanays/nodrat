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
  Wikipedia Action   : https://{lang}.wikipedia.org/w/api.php
                       (list=search #824 + prop=extracts tam makale #973
                        + prop=pageprops wikibase_item #863)
  Wikidata Action    : https://www.wikidata.org/w/api.php (wbgetentities #863)

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
# #973 — v1→v2: _fetch_summary REST-lead (~333 char) yerine tam makale
# extract'ı çeker; içerik şekli kökten değişti → eski v1 (lead-only)
# Redis girdileri 24h boyunca STALE servis etmesin diye versiyon bump
# (planner_cache #947 PROMPT_VERSION-in-key dersi: deploy anında geçerli).
CACHE_KEY_VERSION = "v2"
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_LANG_PRIORITY = ["tr", "en"]
DEFAULT_MAX_RESULTS = 3

# #973 — tam makale düz-metin cap (char). REST lead (~333) gövde-içi
# olguları (örn. "Türkiye'de TRT 1 / 14 Nisan 2007") GÖSTERMİYORDU;
# #967/#970 doğru sayfayı SEÇSE bile cevap görünmüyordu (prod conv
# b66bf1c2). Tam makale çekilir ama dev makaleler (50K+) context/
# maliyet patlatmasın diye cap'lenir; paragraf sınırında kesilir.
# Kod-sabit (admin-tunable setting ileride — #961 deseni, PR şişmesin).
_WIKI_EXTRACT_CAP = 8000

# Wikidata properties — most-asked factual
WIKIDATA_FACTUAL_PROPS = {
    "P569": "birth_date",  # doğum tarihi
    "P570": "death_date",  # ölüm tarihi
    "P1082": "population",  # nüfus
    "P571": "founded_date",  # kuruluş tarihi
    "P36": "capital",  # başkent
    "P39": "position",  # pozisyon (CEO, başkan)
    "P17": "country",  # ülke
    "P102": "party",  # siyasi parti
}


# =============================================================================
# Data classes
# =============================================================================


@dataclass
class WikiArticle:
    """Wikipedia full-text arama + TAM makale extract (#973) — source pill.

    `summary` alanı artık lead-only DEĞİL; cap'li tam makale düz-metni
    (#973). Alan adı geriye-uyum için korundu (chat_tools `a.summary`).
    """

    title: str
    summary: str  # extract (max ~1200 char)
    url: str
    page_id: int
    lang: str = "tr"
    license: str = "CC BY-SA 4.0"
    description: str | None = None  # short description (Wikidata-derived)


@dataclass
class WikidataFact:
    """Wikidata SPARQL Q-ID factual property."""

    qid: str  # Q-ID (Q42 vb.)
    label: str  # entity adı
    properties: dict[str, Any] = field(default_factory=dict)
    """Property code → value (örn. {'P569': '1946-06-14'})"""


@dataclass
class WikidataEntityMeta:
    """Wikidata entity meta — canonical etiket + alias + tip (#1710).

    `wikidata_entity_meta` çıktısı: küme/trend etiketini Wikipedia başlığına
    bağlamak için canonical başlık (trwiki sitelink) + TR alias'lar + P31 tip.
    """

    qid: str
    label_tr: str  # Wikidata labels.tr (yoksa en)
    trwiki_title: str | None  # sitelinks.trwiki.title = Wikipedia TR madde başlığı
    aliases_tr: list[str] = field(default_factory=list)  # aliases.tr yüzey biçimleri
    p31: list[str] = field(default_factory=list)  # instance-of QID'leri (tip doğrulama)


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
        """Wikipedia full-text arama + TAM makale extract fetch.

        Akış:
          1. Cache hit kontrol
          2. list=search API → relevance-ranked top title'lar (#824)
          3. Her title için tam makale düz-metni — `action=query
             prop=extracts explaintext` (#973; lead-only DEĞİL)
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
                    lg,
                    query[:50],
                    len(articles),
                )
                return articles

        return []

    async def _search_lang(
        self,
        query: str,
        lang: str,
        top_k: int,
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
            search_hits = data.get("query", {}).get("search", []) if isinstance(data, dict) else []
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
        """Makalenin TAM düz-metnini çek (#973 — lead-only DEĞİL).

        ESKİ: REST `/page/summary` yalnız lead/giriş paragrafını
        (~333-1200 char) veriyordu → gövdedeki olgular ("Türkiye'de
        ilk bölümü TRT 1 / 14 Nisan 2007" gibi) #967/#970 doğru sayfayı
        SEÇSE bile GÖRÜNMÜYORDU (prod conv b66bf1c2: kanonik [1] ama
        cevap lead'de yok → "kaynakta yok"). YENİ: `action=query
        prop=extracts explaintext` = tam makale düz-metin (lead'in
        süperseti — bilgi kaybı yok, kazanç). `_WIKI_EXTRACT_CAP` ile
        sınırlı (dev makale context/maliyet; paragraf sınırında kes).
        URL `{base}/wiki/{title}` (REST content_urls yok; _search_lang
        fallback'i de aynısını yapar). Lisans CC BY-SA + result_text'in
        "25 kelimeden uzun alıntı yapma" C1 kuralı gövdeye de geçerli.
        """
        try:
            resp = await client.get(
                f"{base}/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": 1,
                    "exsectionformat": "plain",
                    "redirects": 1,
                    "titles": title,
                    "format": "json",
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            pages = (data.get("query", {}) or {}).get("pages", {}) or {}
            page = None
            for _pid, p in pages.items():
                if str(_pid) != "-1" and (p.get("extract") or "").strip():
                    page = p
                    break
            if page is None:
                return None
            extract = (page.get("extract") or "").strip()
            if not extract:
                return None
            if len(extract) > _WIKI_EXTRACT_CAP:
                # paragraf sınırında kes (yarım cümle/kelime bırakma)
                cut = extract.rfind("\n", 0, _WIKI_EXTRACT_CAP)
                if cut < _WIKI_EXTRACT_CAP // 2:
                    cut = extract.rfind(" ", 0, _WIKI_EXTRACT_CAP)
                if cut <= 0:
                    cut = _WIKI_EXTRACT_CAP
                extract = extract[:cut].rstrip() + " […]"
            page_title = str(page.get("title") or title)
            return WikiArticle(
                title=page_title,
                summary=extract,
                url=f"{base}/wiki/{quote(page_title.replace(' ', '_'))}",
                page_id=int(page.get("pageid") or 0),
                lang=lang,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "wikipedia extract failed lang=%s title='%s': %s",
                lang,
                title,
                exc,
            )
            return None

    # ---- exact-title + redirect çözümleme (#1733) -----------------------

    async def resolve_canonical_title(
        self,
        query: str,
        *,
        lang: str | None = None,
    ) -> tuple[str, str] | None:
        """Yüzey form → gerçek Wikipedia maddesi başlığı (full-text aramadan ÖNCE).

        #1733 — full-text arama jenerik maddelere DRIFT ediyor ("Nesine 2. Lig"→"Lig").
        Wikipedia'nın KENDİ küratörlü sistemini kullan (kelime-listesi YOK, evergreen):
          (Mekanizma 1) Tam başlık + `redirects=1` → editör redirect'i takip et
            ("Spor Toto 3. Lig"→"3. Lig", "Lig B"→"2. Lig" — doğrulanmış).
          (Mekanizma 2) Tam başlık madde değilse, BAŞTAN token düşürerek gerçek-madde
            ara, İLK (en uzun) eşleşmede dur ("Nesine 2. Lig"→"2. Lig"). Suffix korunur
            (distinguishing token "2." kalır → "3. Lig"e karışmaz). **Tek-token form
            DENENMEZ** (çok-tokenlı girdinin jenerik "Lig"e inmesini engeller).
        Disambiguation sayfaları reddedilir (drift kaynağı). Bulunamazsa None →
        caller full-text aramaya düşer (gate + collapse-guard korur)."""
        query = (query or "").strip()
        if not query:
            return None
        toks = query.split()
        # tam form + her leading-drop (≥2 token KALANA dek; tek-token denenmez)
        forms = [query] + [" ".join(toks[i:]) for i in range(1, max(1, len(toks) - 1))]
        seen: set[str] = set()
        cand: list[str] = []
        for f in forms:
            fs = f.strip()
            if fs and fs.lower() not in seen:
                seen.add(fs.lower())
                cand.append(fs)

        langs = [lang] if lang else self.lang_priority
        for lg in langs:
            for c in cand:
                title = await self._resolve_title_redirect(c, lg)
                if title:
                    return (title, lg)
        return None

    async def _resolve_title_redirect(self, title: str, lang: str) -> str | None:
        """Tam başlık + redirect → gerçek madde başlığı (yoksa/disambig ise None)."""
        async with self._make_client() as client:
            try:
                resp = await client.get(
                    f"https://{lang}.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "titles": title,
                        "redirects": 1,
                        "prop": "pageprops",
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                return None
            pages = (data.get("query", {}) or {}).get("pages", {}) or {}
            for pid, page in pages.items():
                if str(pid) == "-1":  # eksik sayfa (madde yok)
                    continue
                pp = page.get("pageprops", {}) or {}
                if "disambiguation" in pp:  # anlam-ayrımı → drift kaynağı, reddet
                    continue
                t = page.get("title")
                if t:
                    return str(t)
        return None

    # ---- Wikidata (Action API — SPARQL DEĞİL, #863) ---------------------

    async def wikidata_qid_for_title(
        self,
        title: str,
        lang: str,
    ) -> str | None:
        """Wikipedia sayfa başlığı → Wikidata QID (sitelink, deterministik).

        #863 — `wbsearchentities` fuzzy + niteleyici-hassas (yanlış
        entity). Her Wikipedia makalesinin `pageprops.wikibase_item`'ı
        DİL-BAĞIMSIZ kesin QID'dir (TR sayfası da global Q'ya bağlı).
        Wikipedia full-text araması doğru SAYFAyı bulur → bu metod o
        sayfanın kesin QID'sini verir (entity ambiguity yok).
        """
        title = (title or "").strip()
        if not title:
            return None
        async with self._make_client() as client:
            try:
                resp = await client.get(
                    f"https://{lang}.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "prop": "pageprops",
                        "ppprop": "wikibase_item",
                        "titles": title,
                        "redirects": 1,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("wikibase_item lookup failed: %s", exc)
                return None
            pages = (data.get("query", {}) or {}).get("pages", {}) or {}
            for _pid, page in pages.items():
                qid = (page.get("pageprops", {}) or {}).get("wikibase_item")
                if qid:
                    return str(qid)
        return None

    async def wikidata_factual(
        self,
        query: str,
        *,
        lang: str = "tr",
        qid: str | None = None,
    ) -> WikidataFact | None:
        """Wikidata factual properties lookup (Action API — SPARQL DEĞİL).

        #863 — Eski akış SPARQL endpoint'i (query.wikidata.org) prod'da
        400/502 veriyordu (flaky) + `wbsearchentities` niteleyici-hassas
        (yanlış entity). Yeni akış:
          1. QID: caller'dan (Wikipedia sitelink — kesin) VEYA
             wbsearchentities (fallback, temiz query bekler)
          2. `wbgetentities&props=claims` — GÜVENİLİR Action API
             (wbsearchentities ile AYNI endpoint; SPARQL 400/502 yok)
          3. Cache 24h
        """
        query = (query or "").strip()
        if not query and not qid:
            return None

        cache_key = _cache_key(qid or query, lang, "wikidata")
        cached = await _cache_get(cache_key)
        if cached:
            return WikidataFact(**cached)

        async with self._make_client() as client:
            resolved_qid = qid
            label = query
            if not resolved_qid:
                # Fallback: fuzzy entity araması (temiz query gerekir;
                # caller mümkünse sitelink-QID geçmeli — #863)
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
                    results = resp.json().get("search") or []
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("wikidata search failed: %s", exc)
                    return None
                if not results:
                    return None
                resolved_qid = results[0].get("id")
                label = results[0].get("label") or query
            if not resolved_qid:
                return None

            # wbgetentities — claims (güvenilir, SPARQL flakiness yok)
            try:
                resp = await client.get(
                    "https://www.wikidata.org/w/api.php",
                    params={
                        "action": "wbgetentities",
                        "ids": resolved_qid,
                        "props": "claims|labels",
                        "languages": f"{lang}|en",
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                ent = (resp.json().get("entities", {}) or {}).get(resolved_qid, {}) or {}
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning(
                    "wikidata wbgetentities failed qid=%s: %s",
                    resolved_qid,
                    exc,
                )
                return None

            lbls = ent.get("labels", {}) or {}
            label = (
                (lbls.get(lang) or {}).get("value") or (lbls.get("en") or {}).get("value") or label
            )
            claims = ent.get("claims", {}) or {}
            properties: dict[str, Any] = {}
            for code in WIKIDATA_FACTUAL_PROPS:
                snaks = claims.get(code) or []
                if not snaks:
                    continue
                dv = ((snaks[0].get("mainsnak", {}) or {}).get("datavalue", {}) or {}).get("value")
                if dv is None:
                    continue
                if isinstance(dv, dict):
                    # time → "+1968-10-14T00:00:00Z"; quantity → amount;
                    # entity-id → Q-id (nadiren sorulan olgu)
                    val = dv.get("time") or dv.get("amount") or dv.get("id") or dv.get("text")
                else:
                    val = dv
                if val is not None:
                    properties[code] = str(val).lstrip("+")

            if not properties:
                return None
            fact = WikidataFact(
                qid=resolved_qid,
                label=label,
                properties=properties,
            )
            await _cache_set(
                cache_key,
                {
                    "qid": fact.qid,
                    "label": fact.label,
                    "properties": fact.properties,
                },
                self.cache_ttl_seconds,
            )
            return fact

    async def wikidata_entity_meta(
        self,
        qid: str,
        *,
        lang: str = "tr",
    ) -> WikidataEntityMeta | None:
        """QID → canonical etiket + TR alias'lar + trwiki başlık + P31 tip (#1710).

        Tek `wbgetentities` çağrısı (props=labels|aliases|sitelinks|claims,
        sitefilter=trwiki) ile küme/trend etiketini Wikipedia başlığına bağlamak
        için gereken her şeyi çeker. QID caller'dan KESİN gelmeli
        (`wikidata_qid_for_title` — sitelink-deterministik); çıplak-keyword
        disambiguation YOK (#997 dersi). Cache 24h.
        """
        qid = (qid or "").strip()
        if not qid:
            return None

        cache_key = _cache_key(qid, lang, "wd_meta")
        cached = await _cache_get(cache_key)
        if cached:
            return WikidataEntityMeta(**cached)

        async with self._make_client() as client:
            try:
                resp = await client.get(
                    "https://www.wikidata.org/w/api.php",
                    params={
                        "action": "wbgetentities",
                        "ids": qid,
                        "props": "labels|aliases|sitelinks|claims",
                        "languages": f"{lang}|en",
                        "sitefilter": "trwiki",
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                ent = (resp.json().get("entities", {}) or {}).get(qid, {}) or {}
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("wikidata_entity_meta failed qid=%s: %s", qid, exc)
                return None
            if not ent:
                return None

            lbls = ent.get("labels", {}) or {}
            label_tr = (lbls.get(lang) or {}).get("value") or (lbls.get("en") or {}).get("value")
            if not label_tr:
                return None

            trwiki_title = ((ent.get("sitelinks", {}) or {}).get("trwiki", {}) or {}).get("title")

            aliases_tr = [
                a.get("value")
                for a in (ent.get("aliases", {}) or {}).get(lang, []) or []
                if a.get("value")
            ]

            # P31 (instance of) — tip doğrulama
            p31: list[str] = []
            for snak in (ent.get("claims", {}) or {}).get("P31", []) or []:
                dv = ((snak.get("mainsnak", {}) or {}).get("datavalue", {}) or {}).get("value")
                if isinstance(dv, dict) and dv.get("id"):
                    p31.append(str(dv["id"]))

            meta = WikidataEntityMeta(
                qid=qid,
                label_tr=str(label_tr),
                trwiki_title=str(trwiki_title) if trwiki_title else None,
                aliases_tr=[str(a) for a in aliases_tr],
                p31=p31,
            )
            await _cache_set(
                cache_key,
                {
                    "qid": meta.qid,
                    "label_tr": meta.label_tr,
                    "trwiki_title": meta.trwiki_title,
                    "aliases_tr": meta.aliases_tr,
                    "p31": meta.p31,
                },
                self.cache_ttl_seconds,
            )
            return meta


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
        from app.shared.runtime_config.settings_store import settings_store

        factory = get_session_factory()
        async with factory() as db:
            ttl_hours = await settings_store.get_int(
                db,
                "wikipedia.cache_ttl_hours",
                DEFAULT_CACHE_TTL_HOURS,
            )
            lang_raw = await settings_store.get(
                db,
                "wikipedia.lang_priority",
                DEFAULT_LANG_PRIORITY,
            )
            lang_priority = (
                lang_raw if isinstance(lang_raw, list) and lang_raw else DEFAULT_LANG_PRIORITY
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
