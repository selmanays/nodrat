"""Characterization baseline — query decomposition ÖNCESİ mevcut davranış kilidi.

#619 PR-1. Bu testler query decomposition feature'ı (PR-2 saf primitive +
PR-3 flag-gated orchestration) eklenmeden ÖNCE, decomposition'ın gözlemlenebilir
şekilde DEĞİŞTİRECEĞİ tek-en-kritik davranışı — citation namespace —
karakterize eder. Flag default OFF olduğunda bu baseline'ın DEĞİŞMEMESİ
(byte-identical) PR-3 için regression-guard'dır.

Kapsam (decomposition citation-merge invariant'ı):
- Decomposition (PR-2+) bir sorguyu N alt-sorguya böler; orchestrator
  (app_research_stream.py:675/782/797) her alt-sorguyu AYRI search_news turu
  olarak çalıştırıp `cite_n`'i `cite_start` ile zincirler
  (`cite_n += len(tc_sources)`). Bu zincir #851 tek-`[n]`-namespace
  invariant'ını korur.
- Bu modül o zinciri tool-fonksiyon (`execute_search_news`) seviyesinde,
  FULL tool-loop TestClient gate KURMADAN kilitler. Full tool-loop gate
  ayrı/future-optional iştir (#1421); PR-1 kapsamı dışı.

Pattern: mevcut tests/unit/test_research_tools.py mock'larıyla birebir
(plan_query / route_for_tier / hybrid_search_chunks AsyncMock). DB-suz, saf
characterization — production davranışı DEĞİŞMEZ, yalnız assert edilir.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.core.research_tools import execute_search_news


def _search_news_patches(chunks: list[dict]):
    """plan_query / route_for_tier / hybrid_search_chunks patch üçlüsü.

    test_research_tools.py::_collapse_setup ile aynı desen — test dosyaları
    arası import yerine bağımsız helper (canned chunks ile).
    """

    class _Plan:
        topic_query = "gündem"
        critical_entities: list[str] = []
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
async def test_sequential_search_news_preserves_cite_chain_no_collision():
    """#619 PR-1 — ardışık search_news turları cite_start ile çakışmasız
    birleşik [n] namespace üretir (decomposition'ın N-alt-sorgu citation-merge
    baseline'ı).

    Alt-sorgu 1 (cite_start=0) → [1][2]; alt-sorgu 2 (cite_start=len(sources_1))
    → [3]. Birleşik namespace çakışmasız. PR-2/PR-3 bu davranışı BOZMAMALI.
    """
    sub1_chunks = [
        {
            "article_id": "A1",
            "chunk_id": "c1",
            "article_title": "Ekonomi paketi",
            "chunk_text": "Yeni ekonomi adımları açıklandı.",
            "source_name": "Anadolu Ajansı",
            "article_canonical_url": "https://aa.com.tr/eko",
        },
        {
            "article_id": "A2",
            "chunk_id": "c2",
            "article_title": "Faiz kararı",
            "chunk_text": "Merkez Bankası faizi sabit tuttu.",
            "source_name": "Bloomberg HT",
            "article_canonical_url": "https://bloomberght.com/faiz",
        },
    ]
    sub2_chunks = [
        {
            "article_id": "A3",
            "chunk_id": "c3",
            "article_title": "Döviz kuru",
            "chunk_text": "Dolar/TL yatay seyretti.",
            "source_name": "Dünya",
            "article_canonical_url": "https://dunya.com/doviz",
        },
    ]

    # Alt-sorgu 1 — döngü başı (cite_start=0)
    p1, p2, p3 = _search_news_patches(sub1_chunks)
    with p1, p2, p3:
        txt1, sources1, _meta1 = await execute_search_news(
            {"query": "Türkiye ekonomisi ve faiz son durum"},
            db=object(),
            now=None,
            user=None,
            content_top_k=10,
            cite_start=0,
        )

    # Alt-sorgu 2 — orchestrator zinciri (cite_start = önceki tur source sayısı)
    p1, p2, p3 = _search_news_patches(sub2_chunks)
    with p1, p2, p3:
        txt2, sources2, _meta2 = await execute_search_news(
            {"query": "döviz kuru gelişmeleri"},
            db=object(),
            now=None,
            user=None,
            content_top_k=10,
            cite_start=len(sources1),
        )

    # Her tur kendi offset'inden numaralandırır
    assert [s["cite"] for s in sources1] == ["[1]", "[2]"]
    assert [s["cite"] for s in sources2] == ["[3]"]
    assert "[1]" in txt1 and "[2]" in txt1
    assert "[3]" in txt2
    # 2. tur kendi cite_start'ından başlar — 1. turun token'larını üretmez
    assert "[1]" not in txt2 and "[2]" not in txt2
    # Birleşik citation namespace çakışmasız (decomposition merge invariant'ı):
    # alt-sorgu 1 → [1][2], alt-sorgu 2 → [3]
    all_cites = [s["cite"] for s in (*sources1, *sources2)]
    assert all_cites == ["[1]", "[2]", "[3]"]
    assert len(all_cites) == len(set(all_cites))


@pytest.mark.asyncio
async def test_sequential_search_news_same_article_independent_namespaces():
    """#619 PR-1 — aynı article iki alt-sorguda dönerse tool-fonksiyon
    çağrı-bağımsızdır: cross-query dedup YOK (her tur kendi cite_start
    namespace'inde aynı article'ı numaralandırır).

    Bu, decomposition merge'inin (PR-3 orchestration) cross-query dedup'ı
    ORCHESTRATOR seviyesinde çözmesi gerektiğini BELGELER — `execute_search_news`
    tek-tur sözleşmesi bunu kapsamaz. Baseline: mevcut davranış böyle.
    """
    same_article = [
        {
            "article_id": "DUP1",
            "chunk_id": "c1",
            "article_title": "Muhalefet açıklaması",
            "chunk_text": "Muhalefet bütçeye tepki gösterdi.",
            "source_name": "Cumhuriyet",
            "article_canonical_url": "https://cumhuriyet.com.tr/muhalefet",
        },
    ]

    p1, p2, p3 = _search_news_patches(same_article)
    with p1, p2, p3:
        _txt1, sources1, _m1 = await execute_search_news(
            {"query": "muhalefet tepkileri"},
            db=object(),
            now=None,
            user=None,
            content_top_k=10,
            cite_start=0,
        )

    p1, p2, p3 = _search_news_patches(same_article)
    with p1, p2, p3:
        _txt2, sources2, _m2 = await execute_search_news(
            {"query": "muhalefet bütçe oylaması"},
            db=object(),
            now=None,
            user=None,
            content_top_k=10,
            cite_start=len(sources1),
        )

    # Aynı article, iki bağımsız namespace → farklı cite (dedup tool-seviyede YOK)
    assert sources1[0]["article_id"] == "DUP1" and sources1[0]["cite"] == "[1]"
    assert sources2[0]["article_id"] == "DUP1" and sources2[0]["cite"] == "[2]"
    # Çağrılar bağımsız: cite_start offset korunur, çakışma yok
    assert sources1[0]["cite"] != sources2[0]["cite"]
