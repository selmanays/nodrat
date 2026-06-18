"""#1604 — research yardımcı LLM çağrılarının best-effort cost loglaması.

Kritik invariant: loglama (session açma / track_provider_call) başarısız olsa
BİLE yardımcı fonksiyon NORMAL sonucunu döndürür — kullanıcı-facing research
akışı loglama uğruna ASLA bozulmaz. `decompose_query_llm` desen temsilcisidir
(planner/query_rewrite/followup aynı best-effort bloğu kullanır).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from app.prompts.query_decomposition import decompose_query_llm


class _FakeResult:
    text = '["alt sorgu bir", "alt sorgu iki"]'
    input_tokens = 120
    output_tokens = 30
    cost_usd = 0.0001
    model = "deepseek-v4-flash"
    cached_input_tokens = 0


def _make_provider() -> AsyncMock:
    p = AsyncMock()
    p.name = "deepseek"
    p.generate_text = AsyncMock(return_value=_FakeResult())
    return p


async def test_decompose_returns_normally_when_logging_fails(monkeypatch):
    """Loglama (session açma) patlasa bile decompose normal sonuç döndürür."""

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("app.core.db.get_session_factory", _boom)

    out = await decompose_query_llm(_make_provider(), "test sorgu")

    # loglama hatası yutuldu; decompose yine parse edip döndü (akış sağlam)
    assert isinstance(out, list)


async def test_decompose_logs_with_decomposition_operation(monkeypatch):
    """Happy path: track_provider_call operation='decomposition' + commit ile çağrılır."""
    captured: dict = {}

    class _Tracker:
        def record(self, **kw):
            captured["recorded"] = kw

    @asynccontextmanager
    async def _fake_track(*, db, provider, operation, **_kw):
        captured["operation"] = operation
        captured["provider"] = provider
        yield _Tracker()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def commit(self):
            captured["committed"] = True

    monkeypatch.setattr("app.core.db.get_session_factory", lambda: lambda: _Session())
    monkeypatch.setattr("app.shared.observability.cost_tracker.track_provider_call", _fake_track)

    out = await decompose_query_llm(_make_provider(), "test sorgu")

    assert isinstance(out, list)
    assert captured.get("operation") == "decomposition"
    assert captured.get("provider") == "deepseek"
    assert captured.get("committed") is True
    assert captured["recorded"]["cost_usd"] == 0.0001
