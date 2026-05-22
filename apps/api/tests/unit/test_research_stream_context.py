"""`_prepare_research_context` characterization tests (T6 P6 PR-C+2).

Locking the REAL behavior of the Step 1.5 condense helper extracted into
`apps/api/app/api/_research_stream_context.py` (PR-C+2, behavior-preserving):

    _prepare_research_context(db, conv_id, user_msg_id, user, payload)
        -> ResearchContextResult(effective_query, contextualized,
                                 recent_context, rewrite_latency_ms)

The helper's WHOLE POINT is to isolate 6 orchestrator dependencies (recent
context fetch, settings_store, prompts_store, provider registry, condense,
L1 windowed context) into one mockable unit — so unit-testing it means
mocking those collaborators. Mock count here is intentional, not a smell
(the orchestrator 2nd-yield test downstream rides on this isolation, PR-C+3).

Branches locked:
- empty recent context  → condense skipped, defaults returned (no routing)
- context + rewrite     → contextualized True, effective_query swapped, latency int
- context + None        → fallback (ham sorgu korunur)
- context + whitespace  → strip() guard → fallback
- L1 OFF                → Gate-4 `l1_accept_rewrite` SHORT-CIRCUITED (not consulted)

Davranış İCAT ETMEZ — production output'unu doğrular. L1-ON windowed path
(select_windowed_context + format_context_block override) heavier mock infra
gerektirdiği için DEFER edilir; default-KAPALI yol burada lock'lanır.
"""

from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# `app.api._research_stream_context` → `app.providers.registry` vb. import
# zinciri Docker-only `pyotp` gerektirebilir. Local pre-flight'ta yoksa SKIP;
# CI/Docker'da modül yüklüyse çalışır (async-helper testleriyle aynı kapı).
pytest.importorskip("pyotp")

import app.api._research_stream_context as ctx_mod
from app.api._research_stream_context import (
    ResearchContextResult,
    _prepare_research_context,
)

# NOT `import a.b.c as X` — `app.shared.runtime_config` paketi `settings_store`
# /`prompts_store` instance'larını submodule ile AYNI adla re-export ediyor;
# `as`-binding attribute-traversal'la o instance'ı yakalar (modülü DEĞİL).
# `importlib.import_module` sys.modules'tan GERÇEK submodule'ü döndürür →
# helper'ın `from ...submodule import X` çağrısının okuduğu attribute'u hedefler.
_settings_mod = importlib.import_module("app.shared.runtime_config.settings_store")
_prompts_mod = importlib.import_module("app.shared.runtime_config.prompts_store")
_qr_mod = importlib.import_module("app.prompts.query_rewrite")


# ---------------------------------------------------------------------------
# Test doubles — gerçek collaborator'ları izole eder (helper'ın amacı bu).
# ---------------------------------------------------------------------------


def _payload(content: str = "peki kaç yıl önceydi"):
    return SimpleNamespace(content=content)


def _user(tier: str = "pro"):
    return SimpleNamespace(id=uuid.uuid4(), tier=tier)


class _FakeSettings:
    """settings_store stand-in — get_bool/get_int sabit map'ten döner."""

    def __init__(self, *, l1_on=False, uscope=True, maxm=8, cond_to=6):
        self._bools = {
            "research.l1_windowed_context_enabled": l1_on,
            "research.l1_user_scope": uscope,
        }
        self._ints = {
            "research.l1_window_max_msgs": maxm,
            "research.condense_timeout_s": cond_to,
        }

    async def get_bool(self, db, key, default):
        return self._bools.get(key, default)

    async def get_int(self, db, key, default):
        return self._ints.get(key, default)


class _FakePrompts:
    """prompts_store stand-in — get() template ya da default döner."""

    def __init__(self, tmpl=None):
        self._tmpl = tmpl

    async def get(self, db, key, default):
        return self._tmpl if self._tmpl is not None else default


def _patch_collaborators(
    monkeypatch,
    *,
    recent_context: str,
    condense_return,
    settings: _FakeSettings | None = None,
    prompts: _FakePrompts | None = None,
):
    """Lazy + module-level bağımlılıkları patch'ler, condense mock'unu döner.

    Lazy import'lar (settings_store/prompts_store/condense_followup_query)
    KAYNAK SUBMODULE üstünde patch'lenir — string-path setattr KULLANILMAZ:
    `app.shared.runtime_config` paketi `settings_store` instance'ını submodule
    ile AYNI adla re-export ediyor; pytest resolver string-path'te instance'ı
    yakalıyor (AttributeError). Helper'ın `from ...submodule import X` çağrısı
    submodule attribute'unu okuduğu için modül-objesi setattr'ı doğru hedefler.
    """
    settings = settings or _FakeSettings()
    prompts = prompts or _FakePrompts()

    recent_mock = AsyncMock(return_value=recent_context)
    monkeypatch.setattr(ctx_mod, "_recent_conversation_context", recent_mock)

    # registry.route_for_tier sync; dummy provider döner (condense mock'lu).
    fake_registry = SimpleNamespace(
        route_for_tier=MagicMock(return_value=SimpleNamespace(name="dummy"))
    )
    monkeypatch.setattr(ctx_mod, "registry", fake_registry)

    monkeypatch.setattr(_settings_mod, "settings_store", settings)
    monkeypatch.setattr(_prompts_mod, "prompts_store", prompts)

    condense_mock = AsyncMock(return_value=condense_return)
    monkeypatch.setattr(_qr_mod, "condense_followup_query", condense_mock)
    return condense_mock, fake_registry


# ===========================================================================
# 1) Empty recent context → condense SKIP, defaults returned
# ===========================================================================


@pytest.mark.asyncio
async def test_prepare_context_empty_recent_skips_condense(monkeypatch):
    """recent_context "" → `if _rw_ctx:` False → condense ÇAĞRILMAZ.

    effective_query ham kalır, contextualized False, latency 0.
    """
    condense_mock, fake_registry = _patch_collaborators(
        monkeypatch,
        recent_context="",
        condense_return="SHOULD NOT BE USED",
    )
    payload = _payload("merhaba")
    out = await _prepare_research_context(
        AsyncMock(), uuid.uuid4(), uuid.uuid4(), _user("pro"), payload
    )
    assert isinstance(out, ResearchContextResult)
    assert out.effective_query == "merhaba"
    assert out.contextualized is False
    assert out.recent_context == ""
    assert out.rewrite_latency_ms == 0
    # condense + provider routing HİÇ tetiklenmemeli (boş bağlam early-skip)
    assert condense_mock.await_count == 0
    assert fake_registry.route_for_tier.call_count == 0


# ===========================================================================
# 2) Recent context present + condense rewrites → contextualized True
# ===========================================================================


@pytest.mark.asyncio
async def test_prepare_context_rewrite_sets_contextualized(monkeypatch):
    """recent_context dolu + condense standalone döner → effective_query swap.

    contextualized True, recent_context değişmeden döner, latency int (≥0).
    """
    condense_mock, _ = _patch_collaborators(
        monkeypatch,
        recent_context="user: Stargate\nassistant: ilk bölüm 2024",
        condense_return="  Stargate ilk bölüm yayın tarihi  ",  # strip edilmeli
    )
    payload = _payload("ilk bölümün adı neydi")
    out = await _prepare_research_context(
        AsyncMock(), uuid.uuid4(), uuid.uuid4(), _user("pro"), payload
    )
    assert out.effective_query == "Stargate ilk bölüm yayın tarihi"
    assert out.contextualized is True
    assert out.recent_context == "user: Stargate\nassistant: ilk bölüm 2024"
    assert isinstance(out.rewrite_latency_ms, int)
    assert out.rewrite_latency_ms >= 0
    # condense ham mesaj + history ile çağrıldı
    assert condense_mock.await_count == 1
    args, _kwargs = condense_mock.await_args
    assert args[1] == "user: Stargate\nassistant: ilk bölüm 2024"  # history
    assert args[2] == "ilk bölümün adı neydi"  # ham mesaj


# ===========================================================================
# 3) condense None → fallback (ham sorgu korunur)
# ===========================================================================


@pytest.mark.asyncio
async def test_prepare_context_condense_none_falls_back(monkeypatch):
    """condense None döndürürse effective_query DEĞİŞMEZ, contextualized False."""
    condense_mock, _ = _patch_collaborators(
        monkeypatch,
        recent_context="user: önceki soru\nassistant: önceki cevap",
        condense_return=None,
    )
    payload = _payload("devam et")
    out = await _prepare_research_context(
        AsyncMock(), uuid.uuid4(), uuid.uuid4(), _user("agency_seat"), payload
    )
    assert out.effective_query == "devam et"  # ham korunur
    assert out.contextualized is False
    assert out.rewrite_latency_ms == 0
    assert condense_mock.await_count == 1  # çağrıldı ama None → fallback


# ===========================================================================
# 4) condense whitespace-only → strip() guard → fallback
# ===========================================================================


@pytest.mark.asyncio
async def test_prepare_context_condense_whitespace_falls_back(monkeypatch):
    """condense "   " → `rewritten.strip()` falsy → ham sorgu korunur."""
    _patch_collaborators(
        monkeypatch,
        recent_context="user: x\nassistant: y",
        condense_return="   \n  ",
    )
    payload = _payload("ham sorgu kalmalı")
    out = await _prepare_research_context(
        AsyncMock(), uuid.uuid4(), uuid.uuid4(), _user("pro"), payload
    )
    assert out.effective_query == "ham sorgu kalmalı"
    assert out.contextualized is False
    assert out.rewrite_latency_ms == 0


# ===========================================================================
# 5) L1 OFF → Gate-4 `l1_accept_rewrite` SHORT-CIRCUITED (not consulted)
# ===========================================================================


@pytest.mark.asyncio
async def test_prepare_context_l1_off_bypasses_accept_gate(monkeypatch):
    """L1 KAPALI (default) → `(not _l1_on)` True → l1_accept_rewrite ÇAĞRILMAZ.

    Gate-4 drift reddi yalnız L1 AÇIKKEN devreye girer; kapalıyken rewrite
    koşulsuz kabul edilir (davranış byte-eş, #1014 öncesi semantiği korur).
    """
    _patch_collaborators(
        monkeypatch,
        recent_context="user: a\nassistant: b",
        condense_return="standalone yeniden yazılmış sorgu",
        settings=_FakeSettings(l1_on=False),
    )
    accept_spy = MagicMock(return_value=False)  # çağrılırsa reddederdi
    monkeypatch.setattr(ctx_mod, "l1_accept_rewrite", accept_spy)

    out = await _prepare_research_context(
        AsyncMock(), uuid.uuid4(), uuid.uuid4(), _user("pro"), _payload("q")
    )
    # L1 kapalı → accept gate atlanır → rewrite kabul edilir
    assert out.effective_query == "standalone yeniden yazılmış sorgu"
    assert out.contextualized is True
    assert accept_spy.call_count == 0  # gate HİÇ danışılmadı
