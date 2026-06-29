"""Unit — #1785 Faz 5.2a research_runner non-streaming çekirdeği.

Tool-loop akışı + cited-only (#1754) süzme + zorla-final dalı. Yapı-taşları
(execute_search_news / _tracked_chat_generate / registry / prompts_store) KAYNAK
modülde monkeypatch'lenir (lazy import → çağrı-anında resolve, tracked_chat.py deseni).
DB gerekmez — saf orkestrasyon birimi.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.modules.generations import research_runner as rr

NOW = datetime(2026, 6, 27, tzinfo=UTC)


def _tc(query: str = "asgari ücret", cid: str = "c1"):
    return SimpleNamespace(id=cid, name="search_news", arguments={"query": query})


def _decisions(seq: list):
    """Stateful fake _tracked_chat_generate — sırayla canned karar döndürür."""
    it = iter(seq)

    async def _fake(provider, *, user_id, totals, messages, call_type=None, **kw):
        totals["calls"] = totals.get("calls", 0) + 1
        return next(it)

    return _fake


def _search(sources: list, text: str = "[1] haber metni"):
    async def _fake(
        arguments, *, db, now, user, query_vec_hint=None, content_top_k=5, cite_start=0
    ):
        return text, list(sources), {"query_class": "news_query"}

    return _fake


def _patch_common(monkeypatch):
    # Runner'ın kullandığı singleton OBJE'leri doğrudan patch'le (string-path
    # monkeypatch instance↔submodule ad çakışmasında patlar — prompts_store).
    from app.providers.registry import registry
    from app.shared.runtime_config.prompts_store import prompts_store
    from app.shared.runtime_config.settings_store import settings_store

    monkeypatch.setattr(registry, "route_for_tier", lambda **k: SimpleNamespace(name="fake"))

    async def _ps_get(db, key, default):
        return default

    monkeypatch.setattr(prompts_store, "get", _ps_get)

    # faithfulness guard flag → default (prod default True; canlı-yol paritesi)
    async def _ss_get_bool(db, key, default=False):
        return default

    monkeypatch.setattr(settings_store, "get_bool", _ss_get_bool)


# ≥120 char + rekonstrüksiyon imleci ("anlaşıldığı kadarıyla") + [1] atıf →
# faithfulness reframe gate'in 4 koşulunu (guard+sources+substantive+marker) tetikler.
_RECON_TEXT = (
    "Cumhurbaşkanı'nın açıklamasına gelen tepkiden anlaşıldığı kadarıyla asgari "
    "ücret zammı konusunda taraflar arasında bir mutabakat sağlanmış görünüyor ve "
    "önümüzdeki hafta masaya dönülmesi bekleniyor [1]."
)


@pytest.fixture
def user():
    return SimpleNamespace(id="u1", tier="free")


async def test_ok_cited(monkeypatch, user):
    """tur1 retrieval → tur2 [1] atıflı cevap → status ok, sources_used yalnız atıflı."""
    _patch_common(monkeypatch)
    s1 = {"title": "A", "article_id": "a1"}
    s2 = {"title": "B", "article_id": "a2"}
    monkeypatch.setattr("app.core.research_tools.execute_search_news", _search([s1, s2]))
    monkeypatch.setattr(
        "app.modules.generations.llm.tracked_chat._tracked_chat_generate",
        _decisions(
            [
                SimpleNamespace(tool_calls=[_tc()], text=""),
                SimpleNamespace(tool_calls=None, text="Asgari ücret zammı açıklandı [1]."),
            ]
        ),
    )
    res = await rr.run_cluster_research(
        object(), user=user, query="asgari ücret neden gündemde", now=NOW
    )
    assert res.status == "ok"
    assert res.sources_used == [s1]  # yalnız [1] cite edildi → s2 dışarıda
    assert len(res.all_sources) == 2
    assert res.usage["calls"] == 2


async def test_skipped_no_citation(monkeypatch, user):
    """Kaynak VAR ama cevapta [n] yok → cited-only (#1754) → skipped_no_sources."""
    _patch_common(monkeypatch)
    monkeypatch.setattr("app.core.research_tools.execute_search_news", _search([{"title": "A"}]))
    monkeypatch.setattr(
        "app.modules.generations.llm.tracked_chat._tracked_chat_generate",
        _decisions(
            [
                SimpleNamespace(tool_calls=[_tc()], text=""),
                SimpleNamespace(tool_calls=None, text="Bu konuda net bir bilgi yok."),
            ]
        ),
    )
    res = await rr.run_cluster_research(object(), user=user, query="x", now=NOW)
    assert res.status == "skipped_no_sources"
    assert res.sources_used == []


async def test_skipped_when_no_sources(monkeypatch, user):
    """Retrieval 0 kaynak → skipped_no_sources (artefakt çağıranda üretilmez)."""
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        "app.core.research_tools.execute_search_news", _search([], text="kaynak yok")
    )
    monkeypatch.setattr(
        "app.modules.generations.llm.tracked_chat._tracked_chat_generate",
        _decisions(
            [
                SimpleNamespace(tool_calls=[_tc()], text=""),
                SimpleNamespace(tool_calls=None, text="Kaynak bulunamadı."),
            ]
        ),
    )
    res = await rr.run_cluster_research(object(), user=user, query="x", now=NOW)
    assert res.status == "skipped_no_sources"
    assert res.all_sources == []


async def test_faithfulness_reframe_drops_reconstruction(monkeypatch, user):
    """Geriye-çıkarsama (rekonstrüksiyon) imleci sızmış cevap → faithfulness reframe
    (canlı SSE paritesi) → [n] kalmaz → cited boşalır → skipped_no_sources (#denetim2)."""
    _patch_common(monkeypatch)  # guard default True
    s1 = {"title": "A", "article_id": "a1"}
    monkeypatch.setattr("app.core.research_tools.execute_search_news", _search([s1]))
    monkeypatch.setattr(
        "app.modules.generations.llm.tracked_chat._tracked_chat_generate",
        _decisions(
            [
                SimpleNamespace(tool_calls=[_tc()], text=""),
                SimpleNamespace(
                    tool_calls=None, text=_RECON_TEXT
                ),  # [1] atıflı AMA rekonstrüksiyon
            ]
        ),
    )
    res = await rr.run_cluster_research(object(), user=user, query="x", now=NOW)
    assert res.status == "skipped_no_sources"  # reframe → artefakt-yok paritesi
    assert res.sources_used == []
    assert "Çıkarımsal ya da" in res.content  # reframe metni uygulandı


async def test_faithfulness_guard_off_passes_reconstruction(monkeypatch, user):
    """Guard flag OFF → reframe uygulanmaz; rekonstrüksiyon [1] atfı olduğu gibi geçer
    (flag-kontrollü davranış; canlı yolla aynı anahtar)."""
    _patch_common(monkeypatch)
    from app.shared.runtime_config.settings_store import settings_store

    async def _off(db, key, default=False):
        return False

    monkeypatch.setattr(settings_store, "get_bool", _off)
    s1 = {"title": "A", "article_id": "a1"}
    monkeypatch.setattr("app.core.research_tools.execute_search_news", _search([s1]))
    monkeypatch.setattr(
        "app.modules.generations.llm.tracked_chat._tracked_chat_generate",
        _decisions(
            [
                SimpleNamespace(tool_calls=[_tc()], text=""),
                SimpleNamespace(tool_calls=None, text=_RECON_TEXT),
            ]
        ),
    )
    res = await rr.run_cluster_research(object(), user=user, query="x", now=NOW)
    assert res.status == "ok"  # guard kapalı → [1] atfı korunur
    assert res.sources_used == [s1]


async def test_forced_final_when_rounds_exhausted(monkeypatch, user):
    """Her tur tool çağırıp cevap vermezse max_rounds dolar → toolsuz zorla-final."""
    _patch_common(monkeypatch)
    s1 = {"title": "A", "article_id": "a1"}
    monkeypatch.setattr("app.core.research_tools.execute_search_news", _search([s1]))
    monkeypatch.setattr(
        "app.modules.generations.llm.tracked_chat._tracked_chat_generate",
        _decisions(
            [
                SimpleNamespace(tool_calls=[_tc()], text=""),  # tur1
                SimpleNamespace(tool_calls=[_tc()], text=""),  # tur2 (max dolar)
                SimpleNamespace(tool_calls=None, text="Özet [1]."),  # zorla-final
            ]
        ),
    )
    res = await rr.run_cluster_research(object(), user=user, query="x", now=NOW, max_rounds=2)
    assert res.status == "ok"
    assert res.sources_used == [s1]
    assert res.usage["calls"] == 3  # 2 tur + 1 forced-final
