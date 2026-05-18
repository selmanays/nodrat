---
type: entity
title: "Wikipedia Provider — REST + Wikidata Action API knowledge client"
slug: "wikipedia-provider"
category: "provider"
status: "live"
created: "2026-05-15"
updated: "2026-05-18"
sources:
  - "apps/api/app/providers/wikipedia.py"
  - "apps/api/app/core/chat_tools.py (execute_search_wikipedia)"
  - "GitHub PR #812 → #825 (list=search) #827/#828 (Wikidata kombine) #851 (tek [n]) #863 (bulletproof: sitelink QID + wbgetentities, SPARQL kaldırıldı)"
tags: ["provider", "knowledge", "wikipedia", "wikidata", "external-api", "faz-2"]
aliases: ["wiki-provider", "knowledge-provider"]
---

# Wikipedia Provider

> **TL;DR:** Wikipedia REST (`action=query&list=search&srsort=relevance`
> full-text) + Wikidata **Action API** (`wbgetentities`/`wbsearchentities`
> + `pageprops` sitelink) HTTP client. **NOT** a `ModelProvider` —
> knowledge provider kategori. CC BY-SA 4.0 + Wikidata CC0, $0 cost,
> 24h Redis cache. Chat'te **LLM tool-use ile** tetiklenir (#845 —
> kullanıcı CTA onayı KALDIRILDI).
>
> **#863 bulletproof (güncel):** `execute_search_wikipedia` artık
> **SIRALI zincir** (paralel `asyncio.gather` kaldırıldı): Wikipedia
> full-text (niteleyiciye toleranslı → doğru SAYFA) → `wikidata_qid_for_title`
> (`pageprops.wikibase_item` = dil-bağımsız kesin QID) → `wikidata_factual(qid=)`
> `wbgetentities` Action API. **Wikidata SPARQL tamamen kaldırıldı**
> (prod'da flaky 400/502); fuzzy `wbsearchentities` yalnız sitelink-QID
> yoksa fallback. Mekanizma: [[wikipedia-wikidata-knowledge-source]].
>
> **#973 — TAM makale extract (lead-only DEĞİL, güncel):** `_fetch_summary`
> artık REST `/api/rest_v1/page/summary` (yalnız lead ~333-1200 char)
> KULLANMIYOR → `action=query&prop=extracts&explaintext=1&
> exsectionformat=plain&redirects=1` (tam makale düz-metin), `_WIKI_
> EXTRACT_CAP=8000` char cap (dev makale context/maliyet; paragraf
> sınırında kes + "[…]"). Sebep: #967/#970 doğru kanonik sayfayı
> SEÇSE bile gövde-içi olgu (prod conv b66bf1c2: "Türkiye'de TRT 1 /
> 14 Nisan 2007") lead'de olmadığı için GÖRÜNMÜYORDU → cevap
> "kaynakta yok" (C1-doğru ama veri yapay kırpık). `CACHE_KEY_VERSION`
> **v1→v2** (eski lead-only Redis girdileri 24h stale servis etmesin;
> #947 PROMPT_VERSION-in-key dersi). URL `{base}/wiki/{title}`
> (content_urls yok; `_search_lang` fallback'i aynısı). Lead→full
> süperset (bilgi kaybı yok). LLM tool spec & query DEĞİŞMEZ.

## Nedir

Layer 2 (general knowledge) için stateless HTTP client. Faz 2
(#811/#812) ile eklendi; #825 ile search `list=search`'e geçti,
#827/#828 ile Wikidata fact kombinasyonu, #863 ile bulletproof sıralı
zincir (SPARQL → Action API; deterministik sitelink QID). Chat'te LLM
`search_wikipedia` tool'unu çağırınca tetiklenir (otomatik, kullanıcı
müdahalesi YOK — confidence/CTA mimarisi #823/#845'te terk edildi).

## API yüzeyi

`apps/api/app/providers/wikipedia.py`:

```python
class WikipediaProvider:
    def __init__(self, *, cache_ttl_hours=24, lang_priority=["tr","en"], transport=None): ...

    async def search(self, query: str, *, lang=None, top_k=3) -> list[WikiArticle]:
        """Wikipedia full-text (action=query&list=search&srsort=relevance)
        + TAM makale extract (action=query&prop=extracts, #973 — lead
        DEĞİL). opensearch DEĞİL (#825 — relevance zayıftı)."""

    async def wikidata_qid_for_title(self, title: str, lang: str) -> str | None:
        """#863 — Wikipedia sayfa başlığı → prop=pageprops&ppprop=wikibase_item
        → DİL-BAĞIMSIZ kesin QID (fuzzy/ambiguity yok). Sıralı zincirin
        2. adımı."""

    async def wikidata_factual(self, query: str, *, lang="tr", qid=None) -> WikidataFact | None:
        """#863 — wbgetentities Action API (action=wbgetentities&ids={qid}
        &props=claims|labels). SPARQL KALDIRILDI (flaky). qid verilirse
        fuzzy wbsearchentities ATLANIR; yoksa fallback."""

async def get_wikipedia_provider() -> WikipediaProvider:
    """Singleton accessor — settings-aware lazy init."""
```

`execute_search_wikipedia` (chat_tools.py) sıralı zinciri kurar:
`search` → `wikidata_qid_for_title(articles[0].title, lang)` →
`wikidata_factual(query, lang="tr", qid=_qid)`. Wikidata fact varsa
cevapta **[1]** (tek `[n]` namespace, #851 — `[W]` prefix YOK),
Wikipedia prose sonra; `cite_start` multi-round çakışmayı önler.

## Data classes

```python
@dataclass
class WikiArticle:
    title: str
    summary: str            # #973: TAM makale düz-metin (cap 8000), lead DEĞİL
    url: str
    page_id: int
    lang: str = "tr"
    license: str = "CC BY-SA 4.0"
    description: str | None

@dataclass
class WikidataFact:
    qid: str                # Q-ID (Q22686 vb.)
    label: str
    properties: dict        # {"P569": "1946-06-14", ...} (+ lstrip)
```

## Wikidata factual properties

```python
WIKIDATA_FACTUAL_PROPS = {
    "P569": "birth_date",  "P570": "death_date",
    "P1082": "population",  "P571": "founded_date",
    "P36": "capital",       "P39": "position",
    "P17": "country",       "P102": "party",
}
```

`wbgetentities` claim'lerinden bu property'ler çıkarılır (datavalue →
time/amount/id/text; ISO tarih `+1946-...`/`...T00:00:00Z` → `1946-06-14`).
Property yoksa `None` döner. **SPARQL kullanılmaz** (#863).

## Redis cache pattern

```python
def _cache_key(query: str, lang: str, kind: str = "search") -> str:
    when = datetime.now(UTC).strftime("%Y%m%d")
    raw = f"{query.strip().lower()}|{lang}|{kind}|{when}"
    return f"wiki:v1:{kind}:{lang}:{hashlib.sha1(raw.encode()).hexdigest()}"
```

- SHA1 + gün granülasyonu (planner_cache.py pattern mirror)
- 24h TTL; `search` + `wikidata` ayrı namespace; case-insensitive

## Settings

| Key | Default | Açıklama |
|---|---|---|
| `wikipedia.enabled` | `true` | Provider/tool LLM'e sunulur mu (kill switch) |
| `wikipedia.cache_ttl_hours` | `24` | Redis cache TTL |
| `wikipedia.lang_priority` | `["tr","en"]` | Dil tercih sırası |
| `wikipedia.max_results` | `3` | Search top-K |

## Lisans

- **CC BY-SA 4.0** (Wikipedia) / **CC0 1.0** (Wikidata) — `sources_used[].license`
- **25-kelime quote cap** — FSEK kuralı, prompt'a inject
- Citation: tek `[n]` namespace (#851 — `[W]` prefix kaldırıldı;
  `source_type` news/wiki ayrımını UI taşır, token değil)

## Cost & Performance

- **Cost:** $0 (no API key)
- **Rate limit:** Wikipedia 200 req/sn → Nodrat için >100x tampon
- **Latency:** cache hit ~5ms; miss ~500-900ms (full-text + tam-makale
  extract #973 + pageprops + wbgetentities sıralı; SPARQL flakiness
  elendi). Tam extract lead'den biraz daha ağır ama cache 24h amorti

## Test edilebilirlik

```python
transport = httpx.MockTransport(handler)
provider = WikipediaProvider(transport=transport)  # gerçek HTTP yok
```

`tests/unit/test_wikipedia_provider.py` — cache key determinism,
WikiArticle roundtrip, `list=search` + summary, tr→en fallback, cache
hit HTTP-skip, `wbgetentities` parse, `wikidata_factual(qid=)` fuzzy
atlama, `wikidata_qid_for_title` sitelink (#863). **SPARQL mock'ları
kaldırıldı** (endpoint artık kullanılmıyor).

## Tetikleme noktası

**Tek yol:** agentic döngüde LLM `search_wikipedia` tool'unu çağırır
(#845 — `app_chat_stream.py` çok-turlu loop). Kullanıcı CTA / consent /
InsufficiencySignal banner / `wikipedia-fallback` endpoint **YOK**
(#823'te silindi). `query_class != 'news_query'` ise tool LLM'e sunulur
(`wikipedia.enabled` true iken); LLM kaynak yetersizse kendi karar verir.

## İlişkiler

- Knowledge source mekanizması: [[wikipedia-wikidata-knowledge-source]]
- Tool-use mimarisi: [[llm-tool-use-wikipedia]]
- Güncel orkestrasyon: [[agentic-generate-orchestration]]
- Üst mimari (SUPERSEDED bağlam): [[tiered-knowledge-architecture]]
- Terk edilen CTA: [[wikipedia-fallback-controlled]] (superseded)
- Karar/vazgeçiş zinciri: [[chat-knowledge-evolution]]

## Kaynaklar

- `apps/api/app/providers/wikipedia.py` (`search` list=search;
  `wikidata_qid_for_title` sitelink; `wikidata_factual` wbgetentities)
- `apps/api/app/core/chat_tools.py` (`execute_search_wikipedia` sıralı zincir)
- `apps/api/tests/unit/test_wikipedia_provider.py`
- GitHub PR #812 #825 #827/#828 #851 #863
- Wikipedia Action API (prop=extracts tam makale #973): https://tr.wikipedia.org/w/api.php
- Wikidata Action API: https://www.wikidata.org/w/api.php
