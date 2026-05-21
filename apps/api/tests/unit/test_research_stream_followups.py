"""Async heavy-mock helper characterization tests for `_generate_followups`
(T6 P6 PR-A2a).

`_generate_followups` is a heavy-mock async helper that calls:
  1. `prompts_store.get(db, key, fallback)` — runtime config (with fallback)
  2. `registry.route_for_tier(operation, tier)` — provider routing
  3. `provider.generate_text(...)` — LLM call (AsyncMock)
  4. `parse_followups(text, limit)` — pure parser (called as-is)

This PR characterizes the helper's **current orchestration behavior** without
touching `_generate_followups` source. Three external functions are patched
via `unittest.mock.patch`:
  - `app.shared.runtime_config.prompts_store.prompts_store.get`
  - `app.api.app_research_stream.registry.route_for_tier`
  - `app.prompts.research_followup.parse_followups`

`provider` itself is built fresh per test via `AsyncMock()` and returned by
the routed `registry.route_for_tier`.

Refs:
- PR #1155 — async helper characterization (PR-A1, light mock pattern)
- PR #1150 — pure helper characterization (PR-A)
- Master plan §6 (God-file Strategy)
- Defer: `_tracked_chat_generate` → PR-A2b (heavier mock: ctx manager + factory)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# `app.api.app_research_stream` → `app.core.deps` → `app.core.security` import
# zinciri `pyotp` (Docker-only) gerektiriyor. Local pre-flight'ta pyotp yoksa
# testler SKIP; CI/Docker'da modül yüklüyse çalışır (PR #1150 pattern).
pytest.importorskip("pyotp")

from app.api.app_research_stream import _generate_followups

# ============================================================================
# Helper — provider/response factories
# ============================================================================


def _provider_returning(text: str, *, input_tokens=10, output_tokens=20):
    """AsyncMock provider with provider.generate_text → ProviderResponse-like."""
    provider = AsyncMock()
    response = MagicMock()
    response.text = text
    response.input_tokens = input_tokens
    response.output_tokens = output_tokens
    response.cached_input_tokens = 0
    response.model = "test-model"
    response.cost_usd = 0.0
    provider.generate_text = AsyncMock(return_value=response)
    return provider


def _provider_raising(exc: Exception):
    """AsyncMock provider whose generate_text raises `exc`."""
    provider = AsyncMock()
    provider.generate_text = AsyncMock(side_effect=exc)
    return provider


# ============================================================================
# Patch targets — used by all tests as a context-manager triplet
# ============================================================================


def _patches(
    *,
    sys_prompt: str | None = "SYSTEM_PROMPT_DEFAULT",
    sys_prompt_raises: Exception | None = None,
    provider=None,
    parse_result: list[str] | None = None,
):
    """Return 3 patches: prompts_store.get, registry.route_for_tier, parse_followups.

    Caller uses `with contextlib.ExitStack() as stack: for p in _patches(...): stack.enter_context(p)`.
    """
    # prompts_store.get is patched at the module path imported INSIDE
    # _generate_followups: `from app.shared.runtime_config.prompts_store import prompts_store`
    if sys_prompt_raises is not None:
        prompts_get_mock = AsyncMock(side_effect=sys_prompt_raises)
    else:
        prompts_get_mock = AsyncMock(return_value=sys_prompt)

    if provider is None:
        provider = _provider_returning("line1\nline2\nline3\nline4\nline5")

    if parse_result is None:
        parse_result = ["q1", "q2", "q3", "q4", "q5"]

    return [
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            prompts_get_mock,
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=provider,
        ),
        patch(
            "app.prompts.research_followup.parse_followups",
            return_value=parse_result,
        ),
    ]


# ============================================================================
# _generate_followups — heavy-mock characterization
# ============================================================================


@pytest.mark.asyncio
async def test_generate_followups_returns_parsed_list_default_path():
    """Default path: prompts_store, provider, parse all succeed → returns parsed list."""
    db = AsyncMock()
    with (
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            AsyncMock(return_value="system prompt text"),
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=_provider_returning("line1\nline2\nline3\nline4\nline5"),
        ),
        patch(
            "app.prompts.research_followup.parse_followups",
            return_value=["q1", "q2", "q3", "q4", "q5"],
        ),
    ):
        out = await _generate_followups(db, "user question", "answer text", "pro")
    assert out == ["q1", "q2", "q3", "q4", "q5"]


@pytest.mark.asyncio
async def test_generate_followups_prompts_store_failure_falls_back():
    """prompts_store.get raises → catch + use _FU_SYS fallback (no error propagation)."""
    db = AsyncMock()
    provider = _provider_returning("a\nb")
    with (
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            AsyncMock(side_effect=RuntimeError("store down")),
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=provider,
        ),
        patch(
            "app.prompts.research_followup.parse_followups",
            return_value=["a", "b"],
        ),
    ):
        out = await _generate_followups(db, "q", "a", "pro")
    # Fonksiyon try/except içeren prompts_store guard → fallback'a düşer, exception YUTULUR
    assert out == ["a", "b"]
    # Provider yine çağrılmış olmalı (fallback path)
    assert provider.generate_text.call_count == 1


@pytest.mark.asyncio
async def test_generate_followups_provider_raises_propagates():
    """Caveat: provider.generate_text raises → fonksiyon EXCEPTION'I YUTMAZ.

    Docstring der ki "Hata/timeout caller'da yutulur"; yani `_generate_followups`
    HATA yakalmaz, caller'a propage olur. Mevcut davranış lock.
    """
    db = AsyncMock()
    with (
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            AsyncMock(return_value="sys"),
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=_provider_raising(RuntimeError("LLM 503")),
        ),
        patch("app.prompts.research_followup.parse_followups", return_value=[]),
    ):
        with pytest.raises(RuntimeError, match="LLM 503"):
            await _generate_followups(db, "q", "a", "pro")


@pytest.mark.asyncio
async def test_generate_followups_empty_provider_text_yields_empty_list():
    """provider.generate_text returns text='' → parse_followups('', limit=5) → []."""
    db = AsyncMock()
    provider = _provider_returning("")
    with (
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            AsyncMock(return_value="sys"),
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=provider,
        ),
        patch(
            "app.prompts.research_followup.parse_followups",
            return_value=[],
        ) as parse_mock,
    ):
        out = await _generate_followups(db, "q", "a", "pro")
    assert out == []
    # parse_followups çağrıldı (text='' ile)
    parse_mock.assert_called_once()
    call_args = parse_mock.call_args
    # İlk pozisyonel = '' (caveat: `res.text or ""` → res.text='' → '' or '' → '')
    assert call_args[0][0] == ""


@pytest.mark.asyncio
async def test_generate_followups_none_provider_text_falls_back_to_empty():
    """Caveat: provider.text=None → 'res.text or ""' guard → '' string parse_followups'a geçer."""
    db = AsyncMock()
    provider = AsyncMock()
    response = MagicMock()
    response.text = None  # None edge case
    provider.generate_text = AsyncMock(return_value=response)
    with (
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            AsyncMock(return_value="sys"),
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=provider,
        ),
        patch(
            "app.prompts.research_followup.parse_followups",
            return_value=[],
        ) as parse_mock,
    ):
        out = await _generate_followups(db, "q", "a", "pro")
    assert out == []
    # `or ""` guard text=None → ""
    assert parse_mock.call_args[0][0] == ""


@pytest.mark.asyncio
async def test_generate_followups_tier_passed_to_route_for_tier():
    """tier parametresi `registry.route_for_tier(operation='chat', tier=<tier>)` çağrısına geçer."""
    db = AsyncMock()
    with (
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            AsyncMock(return_value="sys"),
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=_provider_returning("x"),
        ) as route_mock,
        patch(
            "app.prompts.research_followup.parse_followups",
            return_value=[],
        ),
    ):
        await _generate_followups(db, "q", "a", "basic")
    # route_for_tier(operation='chat', tier='basic') ile çağrıldı mı?
    route_mock.assert_called_once()
    kwargs = route_mock.call_args.kwargs
    assert kwargs.get("operation") == "chat"
    assert kwargs.get("tier") == "basic"


@pytest.mark.asyncio
async def test_generate_followups_provider_called_with_max_tokens_240_temp_0_5():
    """Caveat: provider.generate_text çağrısı max_tokens=240, temperature=0.5 (sabit)."""
    db = AsyncMock()
    provider = _provider_returning("y")
    with (
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            AsyncMock(return_value="sys"),
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=provider,
        ),
        patch("app.prompts.research_followup.parse_followups", return_value=[]),
    ):
        await _generate_followups(db, "q", "a", "pro")
    provider.generate_text.assert_called_once()
    kwargs = provider.generate_text.call_args.kwargs
    assert kwargs.get("max_tokens") == 240
    assert kwargs.get("temperature") == 0.5


@pytest.mark.asyncio
async def test_generate_followups_messages_have_system_and_user_roles():
    """Caveat: messages=[Message(role='system', ...), Message(role='user', ...)] iletilir."""
    db = AsyncMock()
    provider = _provider_returning("z")
    with (
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            AsyncMock(return_value="custom system prompt"),
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=provider,
        ),
        patch("app.prompts.research_followup.parse_followups", return_value=[]),
    ):
        await _generate_followups(db, "USER Q", "ANSWER A", "pro")
    msgs = provider.generate_text.call_args.kwargs.get("messages")
    assert len(msgs) == 2
    assert msgs[0].role == "system"
    assert msgs[1].role == "user"
    # System content prompts_store.get'ten gelen string olmalı
    assert msgs[0].content == "custom system prompt"


@pytest.mark.asyncio
async def test_generate_followups_parse_called_with_limit_5():
    """parse_followups(text, limit=5) çağrısı — limit sabiti lock."""
    db = AsyncMock()
    provider = _provider_returning("line1\nline2")
    with (
        patch(
            "app.shared.runtime_config.prompts_store.prompts_store.get",
            AsyncMock(return_value="sys"),
        ),
        patch(
            "app.api.app_research_stream.registry.route_for_tier",
            return_value=provider,
        ),
        patch(
            "app.prompts.research_followup.parse_followups",
            return_value=[],
        ) as parse_mock,
    ):
        await _generate_followups(db, "q", "a", "pro")
    parse_mock.assert_called_once()
    kwargs = parse_mock.call_args.kwargs
    assert kwargs.get("limit") == 5
