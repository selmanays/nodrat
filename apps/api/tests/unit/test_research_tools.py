"""Unit tests for research_tools (#822 LLM tool-use Wikipedia)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.core.research_tools import (
    _CANON_MAX_RETRY,
    RESEARCH_TOOL_DEFINITIONS,
    RESEARCH_TOOLS,
    SEARCH_NEWS_TOOL,
    SEARCH_WIKIPEDIA_TOOL,
    _has_exact_title,
    _prioritize_canonical,
    _resolve_canonical,
    _since_hours_from_timeframes,
    _wiki_norm_title,
    execute_search_news,
    execute_search_wikipedia,
)
from app.providers.base import GenerationResult, Message, ToolCall

# =============================================================================
# Tool definition shape (OpenAI-compatible)
# =============================================================================


def test_tool_definition_openai_shape():
    assert SEARCH_WIKIPEDIA_TOOL["type"] == "function"
    fn = SEARCH_WIKIPEDIA_TOOL["function"]
    assert fn["name"] == "search_wikipedia"
    assert "query" in fn["parameters"]["properties"]
    assert fn["parameters"]["required"] == ["query"]


def test_tool_registry_wired():
    assert "search_wikipedia" in RESEARCH_TOOLS
    assert RESEARCH_TOOLS["search_wikipedia"] is execute_search_wikipedia
    assert SEARCH_WIKIPEDIA_TOOL in RESEARCH_TOOL_DEFINITIONS


def test_news_tool_definition_and_priority():
    # #845 — search_news BİRİNCİL: tanım listesinde search_wikipedia'dan ÖNCE
    assert SEARCH_NEWS_TOOL["function"]["name"] == "search_news"
    names = [d["function"]["name"] for d in RESEARCH_TOOL_DEFINITIONS]
    assert names == ["search_news", "search_wikipedia"]
    assert "query" in SEARCH_NEWS_TOOL["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_execute_search_news_empty_query():
    txt, sources, meta = await execute_search_news(
        {"query": "  "},
        db=None,
        now=None,
        user=None,
    )
    assert "Geçersiz" in txt
    assert sources == [] and meta == {}


@pytest.mark.asyncio
async def test_execute_search_news_contract():
    """#845 — (text, sources, meta) sözleşmesi: [n] bloklar, news cite token,
    source_type='news', meta.query_class."""

    class _Plan:
        topic_query = "Trump Çin ziyareti"
        critical_entities = ["trump"]
        query_class = "news_query"

    class _Emb:
        vectors = [[0.1, 0.2, 0.3]]

    class _Provider:
        async def create_embedding(self, _q):
            return _Emb()

    chunks = [
        {
            "article_id": "a1",
            "chunk_id": "c1",
            "article_title": "Trump Çin'i değerlendirdi",
            "chunk_text": "Trump görüşmeyi olumlu buldu.",
            "source_name": "Anadolu Ajansı",
            "article_canonical_url": "https://aa.com.tr/x",
        },
        {
            "article_id": "a2",
            "chunk_id": "c2",
            "article_title": "Boeing anlaşması",
            "chunk_text": "Çin daha fazla Boeing alacak.",
            "source_name": "Bloomberg HT",
            "url": "https://bloomberght.com/y",
        },
    ]

    with (
        patch(
            "app.prompts.query_planner.plan_query",
            AsyncMock(return_value=_Plan()),
        ),
        patch(
            "app.providers.registry.registry.route_for_tier",
            lambda **_kw: _Provider(),
        ),
        patch(
            "app.core.retrieval.hybrid_search_chunks",
            AsyncMock(return_value=chunks),
        ),
    ):
        txt, sources, meta = await execute_search_news(
            {"query": "Trump Çin son durum"},
            db=object(),
            now=None,
            user=None,
            content_top_k=5,
        )

    assert "[1]" in txt and "[2]" in txt
    assert "Anadolu Ajansı" in txt
    assert len(sources) == 2
    assert all(s["source_type"] == "news" for s in sources)
    assert sources[0]["cite"] == "[1]" and sources[1]["cite"] == "[2]"
    assert sources[0]["url"] == "https://aa.com.tr/x"
    assert meta["query_class"] == "news_query"
    assert meta["chunk_count"] == 2


@pytest.mark.asyncio
async def test_execute_search_news_includes_publication_date():
    """#audit 2026-05-15 — search_news bloğu + source yayın tarihini
    TAŞIMALI. Eksikse LLM haberin ne zaman olduğunu bilemez → eski
    haberi 'bugün' sanar (prod conv 0a097738 regresyonu). datetime
    → ISO gün; None → 'bilinmiyor'. result_text yayın-tarihi yönergesi."""
    from datetime import datetime

    class _Plan:
        topic_query = "Özgür Özel son durum"
        critical_entities = ["özgür özel"]
        query_class = "news_query"

    class _Emb:
        vectors = [[0.1, 0.2, 0.3]]

    class _Provider:
        async def create_embedding(self, _q):
            return _Emb()

    chunks = [
        {
            "article_id": "a1",
            "chunk_id": "c1",
            "article_title": "Rize mitingi",
            "chunk_text": "Özgür Özel Rize'de konuştu.",
            "source_name": "Evrensel",
            "article_canonical_url": "https://evrensel.net/x",
            "published_at": datetime(2026, 5, 9, 14, 30, tzinfo=UTC),
        },
        {
            "article_id": "a2",
            "chunk_id": "c2",
            "article_title": "Fezleke haberi",
            "chunk_text": "3 yeni fezleke gönderildi.",
            "source_name": "Evrensel",
            "url": "https://evrensel.net/y",
            "published_at": None,  # bilinmiyor → düşmemeli, etiketlenmeli
        },
    ]

    with (
        patch(
            "app.prompts.query_planner.plan_query",
            AsyncMock(return_value=_Plan()),
        ),
        patch(
            "app.providers.registry.registry.route_for_tier",
            lambda **_kw: _Provider(),
        ),
        patch(
            "app.core.retrieval.hybrid_search_chunks",
            AsyncMock(return_value=chunks),
        ),
    ):
        txt, sources, meta = await execute_search_news(
            {"query": "Özgür Özel en son ne yaptı"},
            db=object(),
            now=None,
            user=None,
            content_top_k=5,
        )

    # Blokta yayın tarihi görünür (datetime → ISO gün)
    assert "yayın tarihi: 2026-05-09" in txt
    assert "yayın tarihi: bilinmiyor" in txt  # None → düşmedi, etiketli
    # result_text LLM'e "olay zamanı = yayın tarihi (bugün değil)" der
    assert "yayın tarihi" in txt and "bugünün tarihi DEĞİL" in txt
    # source dict published_at taşır (UI + sources_used temporal)
    assert sources[0]["published_at"] == "2026-05-09"
    assert sources[1]["published_at"] is None
    assert len(sources) == 2 and meta["chunk_count"] == 2


# =============================================================================
# #912 — sunum-katmanı article-collapse (aynı haber tek [n] kartı)
# =============================================================================


def _collapse_setup(chunks):
    """plan/embed/hybrid patch helper — chunks param ile."""

    class _Plan:
        topic_query = "gündem"
        critical_entities = []
        query_class = "news_query"

    class _Emb:
        vectors = [[0.1, 0.2, 0.3]]

    class _Provider:
        async def create_embedding(self, _q):
            return _Emb()

    return (
        patch("app.prompts.query_planner.plan_query", AsyncMock(return_value=_Plan())),
        patch("app.providers.registry.registry.route_for_tier", lambda **_kw: _Provider()),
        patch("app.core.retrieval.hybrid_search_chunks", AsyncMock(return_value=chunks)),
    )


@pytest.mark.asyncio
async def test_search_news_article_collapse_single_cite():
    """#912 — #661 parent-doc aynı article'dan çok chunk verir; her
    chunk'a ayrı [n] vermek yerine article başına TEK [n] + TEK source
    kartı. LLM block'ları tüm chunk'ları görmeye devam eder (#661)."""
    chunks = [
        {
            "article_id": "A1",
            "chunk_id": "c1",
            "article_title": "Erdoğan AB",
            "chunk_text": "Birinci paragraf.",
            "source_name": "Hürriyet",
            "article_canonical_url": "https://h/1",
        },
        {
            "article_id": "A1",
            "chunk_id": "c2",
            "article_title": "Erdoğan AB",
            "chunk_text": "PARENTDOC ikinci paragraf.",
            "source_name": "Hürriyet",
            "article_canonical_url": "https://h/1",
        },
        {
            "article_id": "A2",
            "chunk_id": "c3",
            "article_title": "Galatasaray",
            "chunk_text": "Transfer haberi.",
            "source_name": "Fanatik",
            "article_canonical_url": "https://f/2",
        },
    ]
    p1, p2, p3 = _collapse_setup(chunks)
    with p1, p2, p3:
        txt, sources, meta = await execute_search_news(
            {"query": "gündem"},
            db=object(),
            now=None,
            user=None,
            content_top_k=10,
        )
    # A1'in 2 chunk'ı → tek kart, A2 → ayrı kart
    assert len(sources) == 2
    assert sources[0]["article_id"] == "A1" and sources[0]["cite"] == "[1]"
    assert sources[1]["article_id"] == "A2" and sources[1]["cite"] == "[2]"
    # 3. chunk parent-doc → ayrı [3] OLMAMALI (collapse)
    assert "[3]" not in txt
    assert "[1]" in txt and "[2]" in txt
    # #661 — A1'in 2. chunk metni LLM context'inde KALIR (zenginlik)
    assert "PARENTDOC ikinci paragraf." in txt
    # meta: chunk_count ham chunk; source_count distinct article
    assert meta["chunk_count"] == 3
    assert meta["source_count"] == 2


@pytest.mark.asyncio
async def test_search_news_collapse_respects_cite_start():
    """#912 + #851 — multi-round global cite sayacı (cite_start) korunur;
    article-collapse cite_start+1'den numaralandırır."""
    chunks = [
        {
            "article_id": "A1",
            "chunk_id": "c1",
            "article_title": "Haber X",
            "chunk_text": "x1.",
            "source_name": "S1",
            "article_canonical_url": "https://s/x",
        },
        {
            "article_id": "A1",
            "chunk_id": "c2",
            "article_title": "Haber X",
            "chunk_text": "x2.",
            "source_name": "S1",
            "article_canonical_url": "https://s/x",
        },
        {
            "article_id": "A2",
            "chunk_id": "c3",
            "article_title": "Haber Y",
            "chunk_text": "y1.",
            "source_name": "S2",
            "article_canonical_url": "https://s/y",
        },
    ]
    p1, p2, p3 = _collapse_setup(chunks)
    with p1, p2, p3:
        txt, sources, _meta = await execute_search_news(
            {"query": "gündem"},
            db=object(),
            now=None,
            user=None,
            content_top_k=10,
            cite_start=4,
        )
    assert sources[0]["cite"] == "[5]" and sources[1]["cite"] == "[6]"
    assert "[5]" in txt and "[6]" in txt
    assert "[1]" not in txt and "[7]" not in txt
    assert len(sources) == 2


@pytest.mark.asyncio
async def test_search_news_collapse_distinct_cap_keeps_parentdoc():
    """#912 — top_k DISTINCT article'a ulaşınca yeni HABER alınmaz ama
    mevcut article'ların parent-doc ek chunk'ları block'ta KALIR (#661).
    Not: top_k = max(3, min(content_top_k, 15)) — floor 3 (eski kod)."""
    chunks = [
        {
            "article_id": "A1",
            "chunk_id": "c1",
            "article_title": "T1",
            "chunk_text": "a1c1.",
            "source_name": "S",
            "article_canonical_url": "https://s/1",
        },
        {
            "article_id": "A2",
            "chunk_id": "c2",
            "article_title": "T2",
            "chunk_text": "a2c1.",
            "source_name": "S",
            "article_canonical_url": "https://s/2",
        },
        {
            "article_id": "A2",
            "chunk_id": "c3",
            "article_title": "T2",
            "chunk_text": "PARENT a2c2.",
            "source_name": "S",
            "article_canonical_url": "https://s/2",
        },
        {
            "article_id": "A3",
            "chunk_id": "c4",
            "article_title": "T3",
            "chunk_text": "a3c1.",
            "source_name": "S",
            "article_canonical_url": "https://s/3",
        },
        {
            "article_id": "A4",
            "chunk_id": "c5",
            "article_title": "T4",
            "chunk_text": "a4c1 yeni haber.",
            "source_name": "S",
            "article_canonical_url": "https://s/4",
        },
    ]
    p1, p2, p3 = _collapse_setup(chunks)
    with p1, p2, p3:
        txt, sources, meta = await execute_search_news(
            {"query": "gündem"},
            db=object(),
            now=None,
            user=None,
            content_top_k=3,  # top_k=max(3,3)=3 → 3 distinct article
        )
    assert len(sources) == 3  # A1, A2, A3 (A4 cap nedeniyle alınmaz)
    assert {s["article_id"] for s in sources} == {"A1", "A2", "A3"}
    # A2 parent-doc 2. chunk block'ta KALIR (#661)
    assert "PARENT a2c2." in txt
    # A4 (4. distinct) cap'e takıldı → metni/kartı YOK
    assert "a4c1 yeni haber." not in txt
    assert meta["source_count"] == 3


# =============================================================================
# #928 — scope-aware tazelik (Ç2 fallback recency-sort + Ç3 freshness_gap)
# =============================================================================

_NOW928 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)


def _news_setup(*, ret=None, side=None, timeframes=None):
    class _Plan:
        topic_query = "Özgür Özel son haberler"
        critical_entities = []
        query_class = "news_query"

    if timeframes is not None:
        _Plan.timeframes = timeframes

    class _Emb:
        vectors = [[0.1, 0.2, 0.3]]

    class _Provider:
        async def create_embedding(self, _q):
            return _Emb()

    hp = AsyncMock()
    if side is not None:
        hp.side_effect = side
    else:
        hp.return_value = ret
    return (
        patch("app.prompts.query_planner.plan_query", AsyncMock(return_value=_Plan())),
        patch("app.providers.registry.registry.route_for_tier", lambda **_k: _Provider()),
        patch("app.core.retrieval.hybrid_search_chunks", hp),
    )


def _tf7():
    """son 7 gün timeframe (recency_requested=True üretir)."""
    from datetime import timedelta

    return [
        SimpleNamespace(
            label="son 7 gün",
            from_iso=(_NOW928 - timedelta(days=7)).isoformat(),
            to_iso=_NOW928.isoformat(),
        )
    ]


@pytest.mark.asyncio
async def test_search_news_freshness_gap_meta_and_note():
    """#928 Ç3 — kullanıcı güncel istedi (timeframe dar) ama en yeni
    sonuç 7 gün eski → meta sinyali + result_text scope-aware DİKKAT
    notu (sahte güncellik engeli; conv 74eecc15)."""
    chunks = [
        {
            "article_id": "A1",
            "chunk_id": "c1",
            "article_title": "Özgür Özel Karabük mitingi",
            "chunk_text": "Eski miting.",
            "source_name": "Habertürk",
            "article_canonical_url": "https://h/1",
            "published_at": datetime(2026, 5, 10, tzinfo=UTC),
        }
    ]
    p1, p2, p3 = _news_setup(ret=chunks, timeframes=_tf7())
    with p1, p2, p3:
        txt, _sources, meta = await execute_search_news(
            {"query": "Özgür Özel son haberler"},
            db=object(),
            now=_NOW928,
            user=None,
            content_top_k=10,
        )
    assert meta["recency_requested"] is True
    assert meta["newest_published_at"] == "2026-05-10"
    assert meta["freshness_gap_days"] == 7
    assert "DİKKAT — TAZELİK" in txt
    assert "2026-05-10" in txt
    assert "sahte güncellik" in txt.lower() or "scope-aware" in txt.lower() or "daha yeni" in txt


@pytest.mark.asyncio
async def test_search_news_no_note_when_fresh():
    """#928 Ç3 — sonuç bugüne ait (gap 0) → DİKKAT notu YOK, meta gap=0."""
    chunks = [
        {
            "article_id": "A1",
            "chunk_id": "c1",
            "article_title": "Bugün",
            "chunk_text": "Taze.",
            "source_name": "AA",
            "article_canonical_url": "https://a/1",
            "published_at": datetime(2026, 5, 17, tzinfo=UTC),
        }
    ]
    p1, p2, p3 = _news_setup(ret=chunks, timeframes=_tf7())
    with p1, p2, p3:
        txt, _sources, meta = await execute_search_news(
            {"query": "x"},
            db=object(),
            now=_NOW928,
            user=None,
            content_top_k=10,
        )
    assert meta["freshness_gap_days"] == 0
    assert meta["recency_requested"] is True
    assert "DİKKAT — TAZELİK" not in txt


@pytest.mark.asyncio
async def test_search_news_fallback_recency_sort():
    """#928 Ç2 — dar pencere boş → 90g fallback; fallback dalı
    recency-sıralı (eski-prototipik gömülmez; conv 74eecc15 kökü).
    Ana dal RRF sırası bu test kapsamı DIŞI (yalnız fallback)."""
    fallback_chunks = [
        {
            "article_id": "OLD",
            "chunk_id": "o1",
            "article_title": "Eski Karabük",
            "chunk_text": "3 May.",
            "source_name": "S",
            "article_canonical_url": "https://s/o",
            "published_at": datetime(2026, 5, 3, tzinfo=UTC),
        },
        {
            "article_id": "NEW",
            "chunk_id": "n1",
            "article_title": "Yeni gelişme",
            "chunk_text": "15 May.",
            "source_name": "S",
            "article_canonical_url": "https://s/n",
            "published_at": datetime(2026, 5, 15, tzinfo=UTC),
        },
    ]
    # 1. çağrı (dar pencere) → [] ; 2. çağrı (90g fallback) → karışık
    p1, p2, p3 = _news_setup(side=[[], fallback_chunks], timeframes=_tf7())
    with p1, p2, p3:
        _txt, sources, meta = await execute_search_news(
            {"query": "Özgür Özel son haberler"},
            db=object(),
            now=_NOW928,
            user=None,
            content_top_k=10,
        )
    # fallback recency-sort → en YENİ (15 May) ilk kart [1]
    assert sources[0]["article_id"] == "NEW"
    assert sources[0]["published_at"] == "2026-05-15"
    assert sources[1]["article_id"] == "OLD"
    assert meta["chunk_count"] == 2


# =============================================================================
# execute_search_wikipedia
# =============================================================================


@pytest.mark.asyncio
async def test_execute_empty_query():
    result, sources = await execute_search_wikipedia({"query": "  "})
    assert "Geçersiz" in result
    assert sources == []


@pytest.mark.asyncio
async def test_execute_no_results():
    fake_provider = AsyncMock()
    fake_provider.search = AsyncMock(return_value=[])
    fake_provider.wikidata_factual = AsyncMock(return_value=None)
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake_provider),
    ):
        result, sources = await execute_search_wikipedia({"query": "xyzqwerty"})
    assert "bulunamadı" in result.lower()
    assert sources == []


@pytest.mark.asyncio
async def test_execute_success_builds_numbered_sources():
    class _Art:
        def __init__(self, title, summary, url, lang, lic):
            self.title = title
            self.summary = summary
            self.url = url
            self.lang = lang
            self.license = lic

    arts = [
        _Art(
            "Donald Trump",
            "ABD'nin 47. başkanı...",
            "https://tr.wikipedia.org/x",
            "tr",
            "CC BY-SA 4.0",
        ),
        _Art("Trump Organization", "Şirket...", "https://tr.wikipedia.org/y", "tr", "CC BY-SA 4.0"),
    ]
    fake_provider = AsyncMock()
    fake_provider.search = AsyncMock(return_value=arts)
    fake_provider.wikidata_factual = AsyncMock(return_value=None)
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake_provider),
    ):
        result, sources = await execute_search_wikipedia({"query": "Donald Trump"})

    # #851 — tek `[n]` namespace (W prefix YOK), cite_start=0 → [1][2]
    assert "[1]" in result
    assert "[2]" in result
    assert "[W1]" not in result
    assert "Donald Trump" in result
    assert len(sources) == 2
    assert all(s["source_type"] == "wikipedia" for s in sources)
    assert sources[0]["title"] == "Donald Trump"
    assert sources[0]["url"] == "https://tr.wikipedia.org/x"
    assert sources[0]["cite"] == "[1]"
    assert sources[1]["cite"] == "[2]"


@pytest.mark.asyncio
async def test_execute_wikipedia_cite_start_offset():
    """#851 — cite_start ile global benzersiz citation (multi-round çakışma yok)."""

    class _Art:
        def __init__(self, t):
            self.title, self.summary = t, "özet..."
            self.url, self.lang, self.license = "https://tr.wp/" + t, "tr", "CC BY-SA 4.0"

    fake = AsyncMock()
    fake.search = AsyncMock(return_value=[_Art("A"), _Art("B")])
    fake.wikidata_factual = AsyncMock(return_value=None)
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake),
    ):
        result, sources = await execute_search_wikipedia(
            {"query": "x"},
            cite_start=4,
        )
    assert "[5]" in result and "[6]" in result
    assert "[1]" not in result
    assert sources[0]["cite"] == "[5]" and sources[1]["cite"] == "[6]"


@pytest.mark.asyncio
async def test_execute_provider_exception_graceful():
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(side_effect=RuntimeError("network down")),
    ):
        result, sources = await execute_search_wikipedia({"query": "Trump"})
    assert "başarısız" in result.lower()
    assert sources == []


@pytest.mark.asyncio
async def test_execute_wikidata_fact_prepended():
    """#827/#851 — Wikidata fact varsa [1] Wikidata, Wikipedia [2] (tek namespace)."""

    class _Art:
        def __init__(self, title, summary, url, lang, lic):
            self.title, self.summary = title, summary
            self.url, self.lang, self.license = url, lang, lic

    class _Fact:
        qid = "Q22686"
        label = "Donald Trump"
        properties = {"P569": "1946-06-14T00:00:00Z", "P102": "Q29468"}

    arts = [_Art("Donald Trump", "ABD başkanı...", "https://tr.wp/x", "tr", "CC BY-SA 4.0")]
    fake_provider = AsyncMock()
    fake_provider.search = AsyncMock(return_value=arts)
    fake_provider.wikidata_factual = AsyncMock(return_value=_Fact())
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake_provider),
    ):
        result, sources = await execute_search_wikipedia({"query": "Trump yaşı"})

    # #851 — Wikidata [1] başta, Wikipedia [2] (tek `[n]` namespace, W YOK)
    assert "[1] Wikidata" in result
    assert "Doğum tarihi: 1946-06-14" in result
    assert "[W1]" not in result
    assert "[2]" in result
    assert sources[0]["source_name"] == "Wikidata"
    assert sources[0]["cite"] == "[1]"
    assert sources[0]["url"] == "https://www.wikidata.org/wiki/Q22686"
    assert sources[1]["title"] == "Donald Trump"
    assert sources[1]["cite"] == "[2]"


# =============================================================================
# #967 — exact-title kanonik sayfa önceliklendirme
# =============================================================================


class _WArt:
    """WikiArticle stub — _prioritize_canonical title attr okur."""

    def __init__(self, title, lang="tr"):
        self.title = title
        self.summary = f"{title} özeti..."
        self.url = "https://tr.wikipedia.org/wiki/" + title.replace(" ", "_")
        self.lang = lang
        self.license = "CC BY-SA 4.0"


def test_wiki_norm_title_turkish_casefold():
    """#939 dersi — Python lower() TR 'İ'/'I'yı bozar; normalize
    TR büyük→küçük + U+0307 strip + tire/boşluk kanonikleştirir."""
    # 'İ' → 'i' (Python lower'da 'i' + U+0307 olurdu)
    assert _wiki_norm_title("İzmir") == "izmir"
    assert _wiki_norm_title("izmir") == "izmir"
    assert _wiki_norm_title("İzmir") == _wiki_norm_title("izmir")
    # 'I' → 'ı' (TR), 'ş/ğ/ü/ö/ç' küçültme
    assert _wiki_norm_title("Işık") == "ışık"
    assert _wiki_norm_title("Galatasaray ŞĞÜÖÇ") == "galatasaray şğüöç"
    # tire varyantı (U+2013 en-dash, U+2011 nbhyphen) + boşluk sıkıştırma
    raw = "Yıldız  Geçidi–SG‑1"
    assert _wiki_norm_title(raw) == "yıldız geçidi-sg-1"
    assert _wiki_norm_title("") == ""


def test_prioritize_canonical_exact_title_promoted():
    """#967 — tam-başlık eşleşen kanonik sayfa #1 olur; alt-sayfa/
    parantezli geri itilir; tier içi orijinal relevance korunur."""
    arts = [
        _WArt("Yıldız Geçidi SG-1 karakterleri listesi"),  # side
        _WArt("Yıldız Geçidi (film)"),  # paren side
        _WArt("Yıldız Geçidi SG-1"),  # KANONİK
        _WArt("Yıldız Geçidi SG-1 (5. sezon)"),  # paren side
    ]
    out = _prioritize_canonical(arts, "Yıldız Geçidi SG-1")
    assert out[0].title == "Yıldız Geçidi SG-1"  # kanonik öne
    # kalanlar: tier-1 yok → tümü tier-2, orijinal sıra korunur (stable)
    assert [a.title for a in out[1:]] == [
        "Yıldız Geçidi SG-1 karakterleri listesi",
        "Yıldız Geçidi (film)",
        "Yıldız Geçidi SG-1 (5. sezon)",
    ]


def test_prioritize_canonical_no_exact_match_unchanged():
    """#967 geri uyum — tam eşleşme YOKSA liste hiç dokunulmaz
    (mevcut full-text relevance davranışı; kullanıcı onayı)."""
    arts = [
        _WArt("Yıldız Geçidi (film)"),
        _WArt("Yıldız Geçidi SG-1 karakterleri listesi"),
        _WArt("Yıldız Geçidi Atlantis"),
    ]
    out = _prioritize_canonical(arts, "Yıldız Geçidi SG-1")
    assert [a.title for a in out] == [a.title for a in arts]  # değişmedi


def test_prioritize_canonical_exact_with_parens_wins():
    """#967 — tam eşleşme parantezli OLSA bile tier-0 (exact heuristiği
    yener); deprioritize sadece eşleşmeyen parantezlilere uygulanır."""
    arts = [
        _WArt("Yıldız Geçidi SG-1 karakterleri listesi"),
        _WArt("Yıldız Geçidi (film)"),  # query ile TAM eşleşir
        _WArt("Yıldız Geçidi"),
    ]
    out = _prioritize_canonical(arts, "Yıldız Geçidi (film)")
    assert out[0].title == "Yıldız Geçidi (film)"


def test_prioritize_canonical_turkish_aware_match():
    """#967 + #939 — LLM küçük harf/aksanlı sorgu üretse de TR-duyarlı
    normalize ile kanonik başlığa eşleşir."""
    arts = [
        _WArt("İstanbul (anlam ayrımı)"),
        _WArt("İstanbul Üniversitesi"),
        _WArt("İstanbul"),
    ]
    out = _prioritize_canonical(arts, "istanbul")  # küçük 'i'
    assert out[0].title == "İstanbul"


def test_prioritize_canonical_short_list_noop():
    """#967 — 0/1 elemanlı liste reorder edilmez (anlamsız)."""
    assert _prioritize_canonical([], "x") == []
    one = [_WArt("Tek")]
    assert _prioritize_canonical(one, "Tek") is one


@pytest.mark.asyncio
async def test_execute_wikipedia_canonical_drives_qid_and_cite():
    """#967 + #863 — reorder `_qid` ÖNCESİ: kanonik sayfa hem
    wikidata_qid_for_title'a hem [1] bloğa temsilci olur (conv
    3f1ca529 senaryosu — asıl madde kümede ama 2. sıradaydı)."""
    arts = [
        _WArt("Yıldız Geçidi SG-1 karakterleri listesi"),
        _WArt("Yıldız Geçidi SG-1"),  # kanonik, relevance #2
    ]
    captured: dict = {}

    async def _search(q, *, lang=None, top_k=3):
        return arts

    async def _qid_for_title(title, lang):
        captured["qid_title"] = title
        return None

    async def _wikidata(q, *, lang="tr", qid=None):
        return None

    fake = AsyncMock()
    fake.search = _search
    fake.wikidata_qid_for_title = _qid_for_title
    fake.wikidata_factual = _wikidata
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake),
    ):
        result, sources = await execute_search_wikipedia({"query": "Yıldız Geçidi SG-1"})

    # #863 QID çağrısı KANONİK başlıkla yapıldı (side-page DEĞİL)
    assert captured["qid_title"] == "Yıldız Geçidi SG-1"
    # [1] bloğu + ilk source kartı = kanonik madde
    assert sources[0]["title"] == "Yıldız Geçidi SG-1"
    assert sources[0]["cite"] == "[1]"
    assert "[1] Yıldız Geçidi SG-1 (tr)" in result


# =============================================================================
# #970 — canonical-page garantisi (kademeli trimmed retry)
# =============================================================================


class _FakeProv:
    """provider.search stub — query→title-listesi mapping + çağrı sayacı."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.calls: list[str] = []

    async def search(self, q, *, lang=None, top_k=3):
        self.calls.append(q)
        return [_WArt(t) for t in self.mapping.get(q, [])]


def test_has_exact_title_turkish():
    arts = [_WArt("Yıldız Geçidi SG-1"), _WArt("200 (Yıldız Geçidi SG-1)")]
    assert _has_exact_title(arts, "yıldız geçidi sg-1") is True  # TR-norm
    assert _has_exact_title(arts, "Yıldız Geçidi SG-1 ilk bölüm") is False
    assert _has_exact_title([], "x") is False
    assert _has_exact_title(arts, "") is False


@pytest.mark.asyncio
async def test_resolve_canonical_exact_present_no_retry():
    """#970 — küme zaten tam-başlık eşleşme içeriyorsa ekstra arama
    YAPILMAZ (latency koruması; #967 yeter)."""
    prov = _FakeProv({})
    arts = [_WArt("Yıldız Geçidi SG-1"), _WArt("Yıldız Geçidi SG-1 karakterleri listesi")]
    out, eff = await _resolve_canonical(prov, "Yıldız Geçidi SG-1", arts)
    assert out is arts and eff == "Yıldız Geçidi SG-1"
    assert prov.calls == []  # ekstra çağrı YOK


@pytest.mark.asyncio
async def test_resolve_canonical_trimmed_retry_surfaces():
    """#970 — niteleyicili query; full-text canonical'ı getirmedi
    (prod conv 75711aa0 msg4/8). Sağdan kademeli kısalt → "Yıldız
    Geçidi SG-1" prefix'i canonical sayfayı yüzeye çıkarır → kümeye
    BAŞA katılır, eff_query=prefix; _prioritize_canonical [1] yapar."""
    prov = _FakeProv(
        {
            "Yıldız Geçidi SG-1": [
                "Yıldız Geçidi SG-1",
                "200 (Yıldız Geçidi SG-1)",
            ],
        }
    )
    side = [_WArt("200 (Yıldız Geçidi SG-1)"), _WArt("Yıldız Geçidi SG-1 karakterleri listesi")]
    out, eff = await _resolve_canonical(
        prov,
        "Yıldız Geçidi SG-1 ilk bölüm kanal",
        side,
    )
    # sağdan kısaltma: 5tok→4tok→3tok ("Yıldız Geçidi SG-1") HIT
    assert prov.calls == [
        "Yıldız Geçidi SG-1 ilk bölüm",
        "Yıldız Geçidi SG-1 ilk",
        "Yıldız Geçidi SG-1",
    ]
    assert eff == "Yıldız Geçidi SG-1"
    assert out[0].title == "Yıldız Geçidi SG-1"  # canonical başa
    # _prioritize_canonical(eff) ile [1] kesinleşir
    pri = _prioritize_canonical(out, eff)
    assert pri[0].title == "Yıldız Geçidi SG-1"


@pytest.mark.asyncio
async def test_resolve_canonical_not_found_backward_compat():
    """#970 geri uyum — hiçbir prefix canonical vermezse (articles,
    query) aynen döner (mevcut davranış; kullanıcı onaylı)."""
    prov = _FakeProv({})  # her arama boş → asla exact
    side = [_WArt("200 (Yıldız Geçidi SG-1)")]
    out, eff = await _resolve_canonical(
        prov,
        "Yıldız Geçidi SG-1 ilk bölüm kanal",
        side,
    )
    assert out is side and eff == "Yıldız Geçidi SG-1 ilk bölüm kanal"
    assert len(prov.calls) <= _CANON_MAX_RETRY  # bounded


@pytest.mark.asyncio
async def test_resolve_canonical_bounded_max_retry():
    """#970 — eşleşme hiç gelmese bile ekstra arama _CANON_MAX_RETRY
    ile sınırlı (latency tavanı)."""
    prov = _FakeProv({})
    long_q = "a b c d e f g h"  # çok token; mapping hep boş
    _out, _eff = await _resolve_canonical(prov, long_q, [_WArt("z")])
    assert len(prov.calls) == _CANON_MAX_RETRY  # tam tavan, fazlası YOK


@pytest.mark.asyncio
async def test_resolve_canonical_min_tokens_guard():
    """#970 — kısa query (≤2 token) trim edilince <2 kalır → retry YOK
    (aşırı-jenerik arama önlenir; İngilizce-ad #842 kapsam dışı)."""
    prov = _FakeProv({})
    _out, eff = await _resolve_canonical(prov, "Stargate SG-1", [_WArt("q")])
    assert prov.calls == [] and eff == "Stargate SG-1"


@pytest.mark.asyncio
async def test_execute_wikipedia_qualifier_query_recovers_canonical():
    """#970 entegrasyon (prod conv 75711aa0 msg4/8 senaryosu) —
    execute_search_wikipedia: niteleyicili query full-text yalnız yan
    sayfa verir; trimmed retry canonical'ı getirir → sources[0]=
    kanonik, cite [1], #863 QID kanonik başlıkla."""
    captured: dict = {}

    async def _search(q, *, lang=None, top_k=3):
        if q == "Yıldız Geçidi SG-1":
            return [_WArt("Yıldız Geçidi SG-1"), _WArt("200 (Yıldız Geçidi SG-1)")]
        # niteleyicili / ara prefix'ler → yalnız yan sayfa
        return [_WArt("200 (Yıldız Geçidi SG-1)"), _WArt("Yıldız Geçidi SG-1 karakterleri listesi")]

    async def _qid(title, lang):
        captured["qid_title"] = title
        return None

    async def _wd(q, *, lang="tr", qid=None):
        return None

    fake = AsyncMock()
    fake.search = _search
    fake.wikidata_qid_for_title = _qid
    fake.wikidata_factual = _wd
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake),
    ):
        result, sources = await execute_search_wikipedia(
            {"query": "Yıldız Geçidi SG-1 ilk bölüm kanal"}
        )

    assert captured["qid_title"] == "Yıldız Geçidi SG-1"  # #863 kanonik
    assert sources[0]["title"] == "Yıldız Geçidi SG-1"
    assert sources[0]["cite"] == "[1]"
    assert "[1] Yıldız Geçidi SG-1 (tr)" in result


# =============================================================================
# Provider ToolCall / Message dataclass shape
# =============================================================================


def test_message_tool_fields_optional():
    m = Message(role="user", content="merhaba")
    assert m.tool_calls is None
    assert m.tool_call_id is None


def test_message_with_tool_calls():
    tc = ToolCall(id="call_1", name="search_wikipedia", arguments={"query": "x"})
    m = Message(role="assistant", content="", tool_calls=[tc])
    assert m.tool_calls[0].name == "search_wikipedia"
    assert m.tool_calls[0].arguments == {"query": "x"}


def test_tool_result_message():
    m = Message(role="tool", content="sonuç", tool_call_id="call_1")
    assert m.role == "tool"
    assert m.tool_call_id == "call_1"


def test_generation_result_tool_calls_default_none():
    gr = GenerationResult(text="hi", model="deepseek")
    assert gr.tool_calls is None


@pytest.mark.asyncio
async def test_execute_wikipedia_qid_via_sitelink_then_wikidata():
    """#863 — bulletproof zincir: Wikipedia full-text (niteleyiciye
    toleranslı) → makale sayfasının wikibase_item'ı (dil-bağımsız kesin
    QID) → wikidata_factual(qid=...) (fuzzy entity araması ATLANIR).
    Niteleyici içeren query bile doğru biyografik veriyi getirir."""

    class _Art:
        def __init__(self, title):
            self.title, self.summary = title, "Kanadalı senarist..."
            self.url, self.lang, self.license = (
                "https://tr.wp/x",
                "tr",
                "CC BY-SA 4.0",
            )

    class _Fact:
        qid = "Q431432"
        label = "Robert C. Cooper"
        properties = {"P569": "1968-10-14"}

    captured: dict = {}

    async def _search(q, *, lang=None, top_k=3):
        return [_Art("Robert C. Cooper")]  # full-text niteliyiciye tolere

    async def _qid_for_title(title, lang):
        captured["title"] = title
        captured["lang"] = lang
        return "Q431432"  # sitelink → dil-bağımsız kesin QID

    async def _wikidata(q, *, lang="tr", qid=None):
        captured["wd_qid"] = qid
        return _Fact() if qid == "Q431432" else None

    fake = AsyncMock()
    fake.search = _search
    fake.wikidata_qid_for_title = _qid_for_title
    fake.wikidata_factual = _wikidata
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake),
    ):
        # LLM/condense niteliyici içeren query gönderse bile çalışmalı
        result, sources = await execute_search_wikipedia({"query": "Robert C. Cooper doğum tarihi"})

    # QID Wikipedia sayfasından (sitelink) çözüldü, Wikidata o QID ile
    assert captured["title"] == "Robert C. Cooper"
    assert captured["wd_qid"] == "Q431432"
    assert "Doğum tarihi: 1968-10-14" in result
    assert any(s["source_name"] == "Wikidata" for s in sources)


# =============================================================================
# _since_hours_from_timeframes (#906 — planner timeframe → retrieval penceresi)
# =============================================================================

# Sabit referans: now = 2026-05-16 12:00 UTC. default_h = 90 gün (prod _FULL_H).
_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
_FULL_H = 24 * 90  # 2160


def _tf(from_iso: str | None):
    """Planner TimeframeSpec stub — yalnız from_iso okunur (getattr)."""
    return SimpleNamespace(label="x", from_iso=from_iso, to_iso="")


def test_since_hours_empty_timeframes_returns_default():
    # Planner timeframe üretmediyse (örn. eski davranış / non-news) →
    # davranış DEĞİŞMEZ: 90g tavan korunur.
    assert _since_hours_from_timeframes([], _NOW, default_h=_FULL_H) == _FULL_H


def test_since_hours_now_none_returns_default():
    # now=None (test_research_tools mevcut çağrı kalıbı) → güvenli default.
    assert (
        _since_hours_from_timeframes([_tf("2026-05-16T00:00:00+00:00")], None, default_h=_FULL_H)
        == _FULL_H
    )


def test_since_hours_today_window_narrows():
    # "bugün" → from=bugün 00:00; now=12:00 → 12 saatlik dar pencere.
    # Eski semantik-benzer haberler bu filtreyle DIŞARIDA kalır (#906 özü).
    out = _since_hours_from_timeframes([_tf("2026-05-16T00:00:00+00:00")], _NOW, default_h=_FULL_H)
    assert out == 12


def test_since_hours_last_7_days():
    # B (planner prompt) örtük güncellik → "son 7 gün" üretir; 7*24=168.
    out = _since_hours_from_timeframes([_tf("2026-05-09T12:00:00+00:00")], _NOW, default_h=_FULL_H)
    assert out == 168


def test_since_hours_clamped_lower_to_min_h():
    # from 1 saat önce → ceil(1)=1 ama min_h=6 tabanı (tz/saat-sınırı güvenliği).
    out = _since_hours_from_timeframes([_tf("2026-05-16T11:00:00+00:00")], _NOW, default_h=_FULL_H)
    assert out == 6


def test_since_hours_clamped_upper_to_default():
    # from 200 gün önce → 4800h ama default_h (90g=2160) ASLA aşılmaz
    # (mevcut retrieval tavanı korunur — kalite makinesi DEĞİŞMEZ).
    out = _since_hours_from_timeframes([_tf("2025-10-28T12:00:00+00:00")], _NOW, default_h=_FULL_H)
    assert out == _FULL_H


def test_since_hours_comparison_oldest_wins():
    # Çoklu timeframe (comparison) → EN ESKİ from baz → en geniş pencere
    # (her iki aralığın haberi de retrieval'a girsin).
    out = _since_hours_from_timeframes(
        [
            _tf("2026-05-15T00:00:00+00:00"),  # ~1.5 gün
            _tf("2026-05-09T12:00:00+00:00"),  # 7 gün ← kazanır
        ],
        _NOW,
        default_h=_FULL_H,
    )
    assert out == 168


def test_since_hours_unparseable_skipped_then_default():
    # Tüm from_iso parse edilemez → güvenli default (davranış değişmez).
    out = _since_hours_from_timeframes(
        [_tf("garbage"), _tf(""), _tf(None)], _NOW, default_h=_FULL_H
    )
    assert out == _FULL_H


def test_since_hours_unparseable_mixed_uses_valid():
    # Biri bozuk biri geçerli → geçerli olan kullanılır (bozuk atlanır).
    out = _since_hours_from_timeframes(
        [_tf("garbage"), _tf("2026-05-09T12:00:00+00:00")],
        _NOW,
        default_h=_FULL_H,
    )
    assert out == 168


def test_since_hours_z_suffix_parsed():
    # ISO "Z" soneki (planner çıktısında yaygın) → +00:00 olarak çözülür.
    out = _since_hours_from_timeframes([_tf("2026-05-16T00:00:00Z")], _NOW, default_h=_FULL_H)
    assert out == 12


def test_since_hours_tz_naive_from_iso_treated_utc():
    # tz'siz from_iso → UTC kabul (planner bazen offset'siz üretir).
    out = _since_hours_from_timeframes([_tf("2026-05-16T00:00:00")], _NOW, default_h=_FULL_H)
    assert out == 12


def test_since_hours_tz_naive_now_treated_utc():
    # tz'siz now → UTC kabul; yine de hesaplanır (NameError/exception yok).
    naive_now = datetime(2026, 5, 16, 12, 0, 0)
    out = _since_hours_from_timeframes(
        [_tf("2026-05-16T00:00:00+00:00")], naive_now, default_h=_FULL_H
    )
    assert out == 12
