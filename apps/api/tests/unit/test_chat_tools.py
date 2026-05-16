"""Unit tests for chat_tools (#822 LLM tool-use Wikipedia)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.chat_tools import (
    CHAT_TOOL_DEFINITIONS,
    CHAT_TOOLS,
    SEARCH_NEWS_TOOL,
    SEARCH_WIKIPEDIA_TOOL,
    _since_hours_from_timeframes,
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
    assert "search_wikipedia" in CHAT_TOOLS
    assert CHAT_TOOLS["search_wikipedia"] is execute_search_wikipedia
    assert SEARCH_WIKIPEDIA_TOOL in CHAT_TOOL_DEFINITIONS


def test_news_tool_definition_and_priority():
    # #845 — search_news BİRİNCİL: tanım listesinde search_wikipedia'dan ÖNCE
    assert SEARCH_NEWS_TOOL["function"]["name"] == "search_news"
    names = [d["function"]["name"] for d in CHAT_TOOL_DEFINITIONS]
    assert names == ["search_news", "search_wikipedia"]
    assert "query" in SEARCH_NEWS_TOOL["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_execute_search_news_empty_query():
    txt, sources, meta = await execute_search_news(
        {"query": "  "}, db=None, now=None, user=None,
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
            "article_id": "a1", "chunk_id": "c1",
            "article_title": "Trump Çin'i değerlendirdi",
            "chunk_text": "Trump görüşmeyi olumlu buldu.",
            "source_name": "Anadolu Ajansı",
            "article_canonical_url": "https://aa.com.tr/x",
        },
        {
            "article_id": "a2", "chunk_id": "c2",
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
            db=object(), now=None, user=None, content_top_k=5,
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
    from datetime import datetime, timezone

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
            "article_id": "a1", "chunk_id": "c1",
            "article_title": "Rize mitingi",
            "chunk_text": "Özgür Özel Rize'de konuştu.",
            "source_name": "Evrensel",
            "article_canonical_url": "https://evrensel.net/x",
            "published_at": datetime(2026, 5, 9, 14, 30, tzinfo=timezone.utc),
        },
        {
            "article_id": "a2", "chunk_id": "c2",
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
            db=object(), now=None, user=None, content_top_k=5,
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
        patch("app.prompts.query_planner.plan_query",
              AsyncMock(return_value=_Plan())),
        patch("app.providers.registry.registry.route_for_tier",
              lambda **_kw: _Provider()),
        patch("app.core.retrieval.hybrid_search_chunks",
              AsyncMock(return_value=chunks)),
    )


@pytest.mark.asyncio
async def test_search_news_article_collapse_single_cite():
    """#912 — #661 parent-doc aynı article'dan çok chunk verir; her
    chunk'a ayrı [n] vermek yerine article başına TEK [n] + TEK source
    kartı. LLM block'ları tüm chunk'ları görmeye devam eder (#661)."""
    chunks = [
        {"article_id": "A1", "chunk_id": "c1", "article_title": "Erdoğan AB",
         "chunk_text": "Birinci paragraf.", "source_name": "Hürriyet",
         "article_canonical_url": "https://h/1"},
        {"article_id": "A1", "chunk_id": "c2", "article_title": "Erdoğan AB",
         "chunk_text": "PARENTDOC ikinci paragraf.", "source_name": "Hürriyet",
         "article_canonical_url": "https://h/1"},
        {"article_id": "A2", "chunk_id": "c3", "article_title": "Galatasaray",
         "chunk_text": "Transfer haberi.", "source_name": "Fanatik",
         "article_canonical_url": "https://f/2"},
    ]
    p1, p2, p3 = _collapse_setup(chunks)
    with p1, p2, p3:
        txt, sources, meta = await execute_search_news(
            {"query": "gündem"}, db=object(), now=None, user=None,
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
        {"article_id": "A1", "chunk_id": "c1", "article_title": "Haber X",
         "chunk_text": "x1.", "source_name": "S1",
         "article_canonical_url": "https://s/x"},
        {"article_id": "A1", "chunk_id": "c2", "article_title": "Haber X",
         "chunk_text": "x2.", "source_name": "S1",
         "article_canonical_url": "https://s/x"},
        {"article_id": "A2", "chunk_id": "c3", "article_title": "Haber Y",
         "chunk_text": "y1.", "source_name": "S2",
         "article_canonical_url": "https://s/y"},
    ]
    p1, p2, p3 = _collapse_setup(chunks)
    with p1, p2, p3:
        txt, sources, meta = await execute_search_news(
            {"query": "gündem"}, db=object(), now=None, user=None,
            content_top_k=10, cite_start=4,
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
        {"article_id": "A1", "chunk_id": "c1", "article_title": "T1",
         "chunk_text": "a1c1.", "source_name": "S",
         "article_canonical_url": "https://s/1"},
        {"article_id": "A2", "chunk_id": "c2", "article_title": "T2",
         "chunk_text": "a2c1.", "source_name": "S",
         "article_canonical_url": "https://s/2"},
        {"article_id": "A2", "chunk_id": "c3", "article_title": "T2",
         "chunk_text": "PARENT a2c2.", "source_name": "S",
         "article_canonical_url": "https://s/2"},
        {"article_id": "A3", "chunk_id": "c4", "article_title": "T3",
         "chunk_text": "a3c1.", "source_name": "S",
         "article_canonical_url": "https://s/3"},
        {"article_id": "A4", "chunk_id": "c5", "article_title": "T4",
         "chunk_text": "a4c1 yeni haber.", "source_name": "S",
         "article_canonical_url": "https://s/4"},
    ]
    p1, p2, p3 = _collapse_setup(chunks)
    with p1, p2, p3:
        txt, sources, meta = await execute_search_news(
            {"query": "gündem"}, db=object(), now=None, user=None,
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
        _Art("Donald Trump", "ABD'nin 47. başkanı...", "https://tr.wikipedia.org/x", "tr", "CC BY-SA 4.0"),
        _Art("Trump Organization", "Şirket...", "https://tr.wikipedia.org/y", "tr", "CC BY-SA 4.0"),
    ]
    fake_provider = AsyncMock()
    fake_provider.search = AsyncMock(return_value=arts)
    fake_provider.wikidata_factual = AsyncMock(return_value=None)
    with patch(
        "app.providers.wikipedia.get_wikipedia_provider",
        AsyncMock(return_value=fake_provider),
    ):
        result, sources = await execute_search_wikipedia(
            {"query": "Donald Trump"}
        )

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
            {"query": "x"}, cite_start=4,
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
                "https://tr.wp/x", "tr", "CC BY-SA 4.0",
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
        result, sources = await execute_search_wikipedia(
            {"query": "Robert C. Cooper doğum tarihi"}
        )

    # QID Wikipedia sayfasından (sitelink) çözüldü, Wikidata o QID ile
    assert captured["title"] == "Robert C. Cooper"
    assert captured["wd_qid"] == "Q431432"
    assert "Doğum tarihi: 1968-10-14" in result
    assert any(s["source_name"] == "Wikidata" for s in sources)


# =============================================================================
# _since_hours_from_timeframes (#906 — planner timeframe → retrieval penceresi)
# =============================================================================

# Sabit referans: now = 2026-05-16 12:00 UTC. default_h = 90 gün (prod _FULL_H).
_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
_FULL_H = 24 * 90  # 2160


def _tf(from_iso: str | None):
    """Planner TimeframeSpec stub — yalnız from_iso okunur (getattr)."""
    return SimpleNamespace(label="x", from_iso=from_iso, to_iso="")


def test_since_hours_empty_timeframes_returns_default():
    # Planner timeframe üretmediyse (örn. eski davranış / non-news) →
    # davranış DEĞİŞMEZ: 90g tavan korunur.
    assert _since_hours_from_timeframes([], _NOW, default_h=_FULL_H) == _FULL_H


def test_since_hours_now_none_returns_default():
    # now=None (test_chat_tools mevcut çağrı kalıbı) → güvenli default.
    assert (
        _since_hours_from_timeframes([_tf("2026-05-16T00:00:00+00:00")], None,
                                     default_h=_FULL_H)
        == _FULL_H
    )


def test_since_hours_today_window_narrows():
    # "bugün" → from=bugün 00:00; now=12:00 → 12 saatlik dar pencere.
    # Eski semantik-benzer haberler bu filtreyle DIŞARIDA kalır (#906 özü).
    out = _since_hours_from_timeframes(
        [_tf("2026-05-16T00:00:00+00:00")], _NOW, default_h=_FULL_H
    )
    assert out == 12


def test_since_hours_last_7_days():
    # B (planner prompt) örtük güncellik → "son 7 gün" üretir; 7*24=168.
    out = _since_hours_from_timeframes(
        [_tf("2026-05-09T12:00:00+00:00")], _NOW, default_h=_FULL_H
    )
    assert out == 168


def test_since_hours_clamped_lower_to_min_h():
    # from 1 saat önce → ceil(1)=1 ama min_h=6 tabanı (tz/saat-sınırı güvenliği).
    out = _since_hours_from_timeframes(
        [_tf("2026-05-16T11:00:00+00:00")], _NOW, default_h=_FULL_H
    )
    assert out == 6


def test_since_hours_clamped_upper_to_default():
    # from 200 gün önce → 4800h ama default_h (90g=2160) ASLA aşılmaz
    # (mevcut retrieval tavanı korunur — kalite makinesi DEĞİŞMEZ).
    out = _since_hours_from_timeframes(
        [_tf("2025-10-28T12:00:00+00:00")], _NOW, default_h=_FULL_H
    )
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
    out = _since_hours_from_timeframes(
        [_tf("2026-05-16T00:00:00Z")], _NOW, default_h=_FULL_H
    )
    assert out == 12


def test_since_hours_tz_naive_from_iso_treated_utc():
    # tz'siz from_iso → UTC kabul (planner bazen offset'siz üretir).
    out = _since_hours_from_timeframes(
        [_tf("2026-05-16T00:00:00")], _NOW, default_h=_FULL_H
    )
    assert out == 12


def test_since_hours_tz_naive_now_treated_utc():
    # tz'siz now → UTC kabul; yine de hesaplanır (NameError/exception yok).
    naive_now = datetime(2026, 5, 16, 12, 0, 0)
    out = _since_hours_from_timeframes(
        [_tf("2026-05-16T00:00:00+00:00")], naive_now, default_h=_FULL_H
    )
    assert out == 12
