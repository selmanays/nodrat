---
type: entity
title: "Wikipedia Provider — REST + Wikidata SPARQL knowledge client"
slug: "wikipedia-provider"
category: "provider"
status: "live"
created: "2026-05-15"
updated: "2026-05-15"
sources:
  - "apps/api/app/providers/wikipedia.py"
  - "GitHub Issue #811 / PR #812 → #825 (list=search) #827/#828 (Wikidata kombine)"
tags: ["provider", "knowledge", "wikipedia", "wikidata", "external-api", "faz-2"]
aliases: ["wiki-provider", "knowledge-provider"]
---

# Wikipedia Provider

> **TL;DR:** Wikipedia REST (`action=query&list=search&srsort=relevance`) + Wikidata SPARQL HTTP client. Layer 2 (kaynaklı genel bilgi) altyapısı. **NOT** a `ModelProvider` — knowledge provider kategori. CC BY-SA 4.0 + Wikidata CC0, $0 cost, 24h Redis cache.
>
> **Güncel (#825/#828):** `search()` artık `opensearch` (prefix/autocomplete, relevance zayıf) yerine `list=search&srsort=relevance` (gerçek full-text motor) kullanır. `search_wikipedia` tool'u Wikipedia prose + `wikidata_factual` structured facts'i PARALEL kombine eder ([[wikipedia-wikidata-knowledge-source]]). Chat'te **LLM tool-use ile** tetiklenir — kullanıcı CTA onayı KALDIRILDI ([[llm-tool-use-wikipedia]]).

## Nedir

Layer 2 (general knowledge) için stateless HTTP client. Faz 2 (#811/#812) ile eklendi; #825 ile search API `list=search`'e geçti, #827/#828 ile Wikidata fact kombinasyonu eklendi. Chat'te LLM `search_wikipedia` tool'unu çağırınca tetiklenir (otomatik, kullanıcı müdahalesi yok).

## API yüzeyi

`apps/api/app/providers/wikipedia.py`:

```python
class WikipediaProvider:
    def __init__(self, *, cache_ttl_hours=24, lang_priority=["tr","en"], transport=None): ...
    
    async def search(self, query: str, *, lang=None, top_k=3) -> list[WikiArticle]:
        """Wikipedia opensearch + summary fetch (paralel)."""
    
    async def wikidata_factual(self, query: str, *, lang="tr") -> WikidataFact | None:
        """Wikidata Q-ID lookup + SPARQL factual properties."""

async def get_wikipedia_provider() -> WikipediaProvider:
    """Singleton accessor — settings-aware lazy init."""
```

## Data classes

```python
@dataclass
class WikiArticle:
    title: str
    summary: str            # extract (max ~1200 char)
    url: str
    page_id: int
    lang: str = "tr"
    license: str = "CC BY-SA 4.0"
    description: str | None

@dataclass
class WikidataFact:
    qid: str                # Q-ID (Q42 vb.)
    label: str
    properties: dict        # {"P569": "1946-06-14", ...}
```

## Wikidata factual properties (8)

```python
WIKIDATA_FACTUAL_PROPS = {
    "P569": "birth_date",
    "P570": "death_date",
    "P1082": "population",
    "P571": "founded_date",
    "P36": "capital",
    "P39": "position",
    "P17": "country",
    "P102": "party",
}
```

Wikipedia search yetersizse Wikidata SPARQL lookup → properties dict.

## Redis cache pattern

```python
def _cache_key(query: str, lang: str, kind: str = "search") -> str:
    when = datetime.now(UTC).strftime("%Y%m%d")
    raw = f"{query.strip().lower()}|{lang}|{kind}|{when}"
    digest = hashlib.sha1(raw.encode()).hexdigest()
    return f"wiki:v1:{kind}:{lang}:{digest}"
```

- SHA1 + gün granülasyonu (planner_cache.py pattern mirror)
- 24h TTL (Wikipedia içeriği yavaş değişir)
- `search` + `wikidata` ayrı namespace'ler
- Case insensitive (query lower-cased)

## Settings

`apps/api/app/api/admin_settings.py`:

| Key | Default | Açıklama |
|---|---|---|
| `wikipedia.enabled` | `true` | Provider tetiklenir mi (kill switch) |
| `wikipedia.cache_ttl_hours` | `24` | Redis cache TTL |
| `wikipedia.lang_priority` | `["tr","en"]` | Dil tercih sırası |
| `wikipedia.max_results` | `3` | Search top-K |

## Lisans

- **CC BY-SA 4.0** — `WikiArticle.license` field response'a dahil
- **25-kelime quote cap** — FSEK kuralımız, prompt'a inject ediliyor
- Frontend chip badge: "Wikipedia (CC BY-SA)"
- Citation format `[W1]` (haber `[N]` ile karışmasın)

## Cost & Performance

- **Cost:** $0 (no API key)
- **Wikipedia rate limit:** 200 req/sn → Nodrat trafiği için >100x tampon
- **Latency:** Cache hit ~5ms, miss ~400-600ms (opensearch + 3 paralel summary fetch)
- **Wikidata SPARQL:** ~300-800ms

## Test edilebilirlik

```python
transport = httpx.MockTransport(handler)
provider = WikipediaProvider(transport=transport)
# httpx mocked, gerçek HTTP yok
```

13 unit test (`tests/unit/test_wikipedia_provider.py`):
- Cache key determinism + case insensitive
- WikiArticle roundtrip serialization
- Search opensearch + summary fetch
- Lang fallback (tr→en)
- Cache hit → HTTP skip verification
- Wikidata SPARQL parse + empty result

## Tetikleme noktaları

1. **2B Wikipedia CTA endpoint** (`app_chat.py:wikipedia_fallback`)
   - Stream daha önce durdu, stub message persist edildi
   - Endpoint stub'ı update eder, Wikipedia kaynaklı LLM cevabı üretir

2. **Hybrid path (2D)** — kullanıcı InsufficiencySignal banner'da Wikipedia tıklarsa, parent yeni chat mesajı submit eder → planner general_knowledge → bu provider tetiklenir

3. **Direct** — gelecekte admin panel "test Wikipedia search" buton (opsiyonel)

## İlişkiler

- Üst karar: [[wikipedia-fallback-controlled]]
- Mimari: [[tiered-knowledge-architecture]]
- Kategori: [[deepseek]] (sister provider — chat) NOT a peer (knowledge vs model)

## Kaynaklar

- `apps/api/app/providers/wikipedia.py` (~370 satır)
- `apps/api/tests/unit/test_wikipedia_provider.py` (13 test)
- GitHub Issue #811 / PR #812
- Wikipedia REST: https://en.wikipedia.org/api/rest_v1/
- Wikidata SPARQL: https://query.wikidata.org/
