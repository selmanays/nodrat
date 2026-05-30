"""Async heavy-mock helper characterization tests for `_tracked_chat_generate`
(T6 P6 PR-A2b).

`_tracked_chat_generate` is a heavy-mock async helper that calls:
  1. `provider.generate_text(**gen_kwargs)` — LLM call (AsyncMock)
  2. `track_provider_call(...)` — `@asynccontextmanager` yielding `CallTracker`
  3. `get_session_factory()` — sync factory; `factory()` async cm yielding session
  4. `record_research_cache_telemetry(...)` — best-effort async telemetry

This PR characterizes the helper's **current orchestration behavior** without
touching `_tracked_chat_generate` source. Four external symbols are patched
via `unittest.mock.patch` (lazy imports inside the helper):
  - `app.shared.observability.cost_tracker.track_provider_call`
  - `app.core.db.get_session_factory`
  - `app.modules.generations.services.research_cache_telemetry.record_research_cache_telemetry`

`provider` itself is built fresh per test via `AsyncMock()` with explicit
`.name` attribute.

Refs:
- PR #1157 — async heavy-mock characterization PR-A2a (`_generate_followups`)
- PR #1155 — async helper PR-A1 (light mock pattern)
- PR #1150 — pure helper PR-A
- Master plan §6 (God-file Strategy)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# `app.api.app_research_stream` → `app.modules.accounts.deps` → `app.core.security` import
# zinciri `pyotp` (Docker-only) gerektiriyor. Local pre-flight'ta pyotp yoksa
# testler SKIP; CI/Docker'da modül yüklüyse çalışır (PR #1150 pattern).
pytest.importorskip("pyotp")

from app.api.app_research_stream import _tracked_chat_generate

# ============================================================================
# Helper — provider / response / track factory builders
# ============================================================================


def _make_response(
    *,
    text="ok",
    input_tokens=10,
    output_tokens=20,
    cached_input_tokens=3,
    model="test-model",
    cost_usd=0.0042,
):
    """Build a ProviderResponse-like MagicMock with attribute access."""
    response = MagicMock()
    response.text = text
    response.input_tokens = input_tokens
    response.output_tokens = output_tokens
    response.cached_input_tokens = cached_input_tokens
    response.model = model
    response.cost_usd = cost_usd
    return response


def _make_provider(*, name="test-provider", response=None, raise_exc=None):
    """AsyncMock provider with name + generate_text."""
    provider = AsyncMock()
    provider.name = name
    if raise_exc is not None:
        provider.generate_text = AsyncMock(side_effect=raise_exc)
    else:
        provider.generate_text = AsyncMock(return_value=response or _make_response())
    return provider


def _make_provider_no_name(*, response=None):
    """Provider WITHOUT `.name` attribute → getattr fallback path.

    `AsyncMock` auto-creates attrs; bunu kapatmak için explicit `spec=` ile dar
    yüzey bağlıyoruz. Sadece `generate_text` callable kalır; `name` getattr ile
    erişilemez → `getattr(provider, "name", "unknown")` fallback'a düşer.
    """
    provider = AsyncMock(spec=["generate_text"])
    provider.generate_text = AsyncMock(return_value=response or _make_response())
    return provider


def _make_session_factory_patch(commit_raises=None):
    """Mock get_session_factory → factory() → async cm yielding session.

    Patches `app.core.db.get_session_factory` since the helper does
    `from app.core.db import get_session_factory` inside its body.
    Returns (patch_object, session_mock) so tests can assert commit().
    """
    session_mock = MagicMock()
    if commit_raises is not None:
        session_mock.commit = AsyncMock(side_effect=commit_raises)
    else:
        session_mock.commit = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield session_mock

    factory_callable = MagicMock(return_value=_session_cm())

    def _factory_call():
        # Each invocation must return a fresh async cm (mock state reuse safe).
        return _session_cm()

    factory_callable.side_effect = lambda: _session_cm()
    factory_fn = MagicMock(return_value=factory_callable)

    return (
        patch("app.core.db.get_session_factory", factory_fn),
        session_mock,
        factory_fn,
    )


def _make_track_patch():
    """Mock track_provider_call → async cm yielding CallTracker-like mock.

    Patches `app.shared.observability.cost_tracker.track_provider_call` (lazy import inside
    helper). Returns (patch_object, tracker_mock, track_call_mock) so tests
    assert kwargs + record().
    """
    tracker_mock = MagicMock()
    tracker_mock.record = MagicMock()

    @asynccontextmanager
    async def _track_cm(**kwargs):
        yield tracker_mock

    track_call_mock = MagicMock(side_effect=_track_cm)
    return (
        patch("app.shared.observability.cost_tracker.track_provider_call", track_call_mock),
        tracker_mock,
        track_call_mock,
    )


def _make_telemetry_patch(side_effect=None):
    """Mock record_research_cache_telemetry (best-effort async)."""
    if side_effect is not None:
        tel = AsyncMock(side_effect=side_effect)
    else:
        tel = AsyncMock(return_value=None)
    return (
        patch(
            "app.modules.generations.services.research_cache_telemetry.record_research_cache_telemetry",
            tel,
        ),
        tel,
    )


# ============================================================================
# _tracked_chat_generate — heavy-mock characterization
# ============================================================================


@pytest.mark.asyncio
async def test_tracked_chat_generate_default_success_returns_response():
    """Default path: provider OK + track + factory + telemetry all OK → returns res."""
    response = _make_response()
    provider = _make_provider(response=response)
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}

    session_patch, session_mock, _factory_fn = _make_session_factory_patch()
    track_patch, _tracker_mock, _track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        res = await _tracked_chat_generate(
            provider,
            user_id="u-1",
            totals=totals,
            messages=[{"role": "user", "content": "x"}],
        )

    assert res is response
    # commit yine çalıştı (finally)
    assert session_mock.commit.await_count == 1


@pytest.mark.asyncio
async def test_tracked_chat_generate_provider_name_fallback_to_unknown():
    """provider.name yok → `getattr(provider, "name", "unknown")` fallback."""
    response = _make_response()
    provider = _make_provider_no_name(response=response)
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}

    session_patch, _session_mock, _ = _make_session_factory_patch()
    track_patch, _tracker_mock, track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        await _tracked_chat_generate(provider, user_id="u-1", totals=totals)

    # track_provider_call kwargs.provider == "unknown"
    track_mock.assert_called_once()
    kwargs = track_mock.call_args.kwargs
    assert kwargs.get("provider") == "unknown"


@pytest.mark.asyncio
async def test_tracked_chat_generate_track_provider_call_kwargs_locked():
    """track_provider_call kwargs: db=<session>, provider, operation="chat", user_id."""
    response = _make_response()
    provider = _make_provider(name="deepseek", response=response)
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}

    session_patch, _session_mock, _ = _make_session_factory_patch()
    track_patch, _tracker_mock, track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        await _tracked_chat_generate(provider, user_id="user-xyz", totals=totals)

    kwargs = track_mock.call_args.kwargs
    assert kwargs.get("provider") == "deepseek"
    assert kwargs.get("operation") == "chat"
    assert kwargs.get("user_id") == "user-xyz"
    # db = factory()'den gelen session (mocked); kimlik karşılaştırması
    # mock async cm üzerinden olduğundan, kwarg'ın varlığını ve sessionr
    # nesnesinin commit'inin çağrıldığını lock'luyoruz.
    assert "db" in kwargs


@pytest.mark.asyncio
async def test_tracked_chat_generate_tracker_record_uses_response_attrs():
    """_tr.record(*, input_tokens, output_tokens, cached_tokens, model, cost_usd) res attrs."""
    response = _make_response(
        input_tokens=42,
        output_tokens=99,
        cached_input_tokens=7,
        model="model-x",
        cost_usd=0.12345,
    )
    provider = _make_provider(response=response)
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}

    session_patch, _session_mock, _ = _make_session_factory_patch()
    track_patch, tracker_mock, _track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        await _tracked_chat_generate(provider, user_id="u-1", totals=totals)

    tracker_mock.record.assert_called_once()
    rkwargs = tracker_mock.record.call_args.kwargs
    assert rkwargs == {
        "input_tokens": 42,
        "output_tokens": 99,
        "cached_tokens": 7,
        "model": "model-x",
        "cost_usd": 0.12345,
    }


@pytest.mark.asyncio
async def test_tracked_chat_generate_totals_dict_accumulates_in_place():
    """totals dict mutate edilir (in-place); 2 ardışık çağrıda toplanır."""
    provider = _make_provider(
        response=_make_response(
            input_tokens=10,
            output_tokens=20,
            cached_input_tokens=3,
            cost_usd=0.001,
            model="m1",
        )
    )
    totals = {
        "input_tokens": 100,
        "output_tokens": 200,
        "cached_tokens": 30,
        "cost_usd": 0.5,
    }

    session_patch, _session_mock, _ = _make_session_factory_patch()
    track_patch, _tracker_mock, _track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        await _tracked_chat_generate(provider, user_id="u-1", totals=totals)

    assert totals["input_tokens"] == 110
    assert totals["output_tokens"] == 220
    assert totals["cached_tokens"] == 33
    assert abs(totals["cost_usd"] - 0.501) < 1e-9
    assert totals["model"] == "m1"
    assert totals["provider"] == "test-provider"
    assert totals["calls"] == 1


@pytest.mark.asyncio
async def test_tracked_chat_generate_cost_usd_none_skipped():
    """res.cost_usd=None → totals["cost_usd"] güncellenmez (None guard)."""
    provider = _make_provider(response=_make_response(cost_usd=None))
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 7.0}

    session_patch, _session_mock, _ = _make_session_factory_patch()
    track_patch, _tracker_mock, _track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        await _tracked_chat_generate(provider, user_id="u-1", totals=totals)

    # 7.0 değişmedi — None guard
    assert totals["cost_usd"] == 7.0


@pytest.mark.asyncio
async def test_tracked_chat_generate_model_none_preserves_previous_via_or():
    """res.model=None → `res.model or totals.get("model")` short-circuit; previous korunur."""
    provider = _make_provider(response=_make_response(model=None))
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cost_usd": 0.0,
        "model": "previous-model",
    }

    session_patch, _session_mock, _ = _make_session_factory_patch()
    track_patch, _tracker_mock, _track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        await _tracked_chat_generate(provider, user_id="u-1", totals=totals)

    # model None → "previous-model" korunur (or short-circuit)
    assert totals["model"] == "previous-model"


@pytest.mark.asyncio
async def test_tracked_chat_generate_provider_exception_propagates_commit_still_runs():
    """provider.generate_text raises → exception PROPAGATES; totals mutate edilmez; finally yine commit."""
    provider = _make_provider(raise_exc=RuntimeError("LLM 503"))
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}

    session_patch, session_mock, _ = _make_session_factory_patch()
    track_patch, _tracker_mock, _track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        with pytest.raises(RuntimeError, match="LLM 503"):
            await _tracked_chat_generate(provider, user_id="u-1", totals=totals)

    # Helper YUTMAZ; ama finally commit yine çalıştı
    assert session_mock.commit.await_count == 1
    # totals dokunulmamış (provider call raise → record yapılmadı → totals update yok)
    assert totals == {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}


@pytest.mark.asyncio
async def test_tracked_chat_generate_research_cache_telemetry_kwargs_locked():
    """record_research_cache_telemetry kwargs: provider/model/call_type/conv_id/user_id/messages/tools/res/call_seq/success=True."""
    response = _make_response(model="m-x")
    provider = _make_provider(name="prov-y", response=response)
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cost_usd": 0.0,
        "calls": 4,
    }

    session_patch, _session_mock, _ = _make_session_factory_patch()
    track_patch, _tracker_mock, _track_mock = _make_track_patch()
    tel_patch, tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        await _tracked_chat_generate(
            provider,
            user_id="user-1",
            totals=totals,
            conv_id="conv-77",
            call_type="condense",
            messages=[{"role": "user", "content": "x"}],
            tools=[{"name": "search_news"}],
        )

    tel_mock.assert_awaited_once()
    kwargs = tel_mock.call_args.kwargs
    assert kwargs.get("provider") == "prov-y"
    assert kwargs.get("model") == "m-x"
    assert kwargs.get("call_type") == "condense"
    assert kwargs.get("conv_id") == "conv-77"
    assert kwargs.get("user_id") == "user-1"
    assert kwargs.get("messages") == [{"role": "user", "content": "x"}]
    assert kwargs.get("tools") == [{"name": "search_news"}]
    assert kwargs.get("res") is response
    # call_seq = totals.get("calls") AFTER increment → 4 + 1 = 5
    assert kwargs.get("call_seq") == 5
    assert kwargs.get("success") is True


@pytest.mark.asyncio
async def test_tracked_chat_generate_telemetry_exception_swallowed():
    """record_research_cache_telemetry raises → outer flow break ETMEZ; res yine döner."""
    response = _make_response()
    provider = _make_provider(response=response)
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}

    session_patch, session_mock, _ = _make_session_factory_patch()
    track_patch, _tracker_mock, _track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch(side_effect=RuntimeError("telemetry down"))

    with session_patch, track_patch, tel_patch:
        res = await _tracked_chat_generate(provider, user_id="u-1", totals=totals)

    # Outer flow intact
    assert res is response
    assert session_mock.commit.await_count == 1


@pytest.mark.asyncio
async def test_tracked_chat_generate_commit_exception_swallowed():
    """finally db.commit() raises → outer flow break ETMEZ; res yine döner."""
    response = _make_response()
    provider = _make_provider(response=response)
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}

    session_patch, _session_mock, _ = _make_session_factory_patch(
        commit_raises=RuntimeError("commit failed")
    )
    track_patch, _tracker_mock, _track_mock = _make_track_patch()
    tel_patch, _tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        res = await _tracked_chat_generate(provider, user_id="u-1", totals=totals)

    assert res is response


@pytest.mark.asyncio
async def test_tracked_chat_generate_call_type_default_unknown_propagates():
    """call_type=None default → telemetry'ye `"unknown"` geçer (`call_type or "unknown"`)."""
    response = _make_response()
    provider = _make_provider(response=response)
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}

    session_patch, _session_mock, _ = _make_session_factory_patch()
    track_patch, _tracker_mock, _track_mock = _make_track_patch()
    tel_patch, tel_mock = _make_telemetry_patch()

    with session_patch, track_patch, tel_patch:
        await _tracked_chat_generate(
            provider,
            user_id="u-1",
            totals=totals,
            # call_type omitted → default None → "unknown" fallback
        )

    kwargs = tel_mock.call_args.kwargs
    assert kwargs.get("call_type") == "unknown"
    assert kwargs.get("conv_id") is None
