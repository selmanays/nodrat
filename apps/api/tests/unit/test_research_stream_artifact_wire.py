"""Unit — Faz 4 küme-artefakt stream wire (`_resolve_and_persist_artifact`).

#11 must-fix: stream-end orkestrasyonu (artifacts.enabled gate → resolve_cluster
→ create_artifact → subscriptions.auto.enabled gate → auto_subscribe → SSE
'artifact' event dict) HİÇ test edilmiyordu. Building-block'lar izole test edilmiş
(test_artifacts_service / test_subscription_endpoints); bu test WIRE'ı — flag
gating (iki-flag-OFF no-op invariantı), event'in auto_subscribe'dan ÖNCE
kurulması (#2 hoist) ve auto_subscribe izolasyonu (#2) — building-block'lar
mock'lanarak doğrular. 15-mock'lu tam-stream entegrasyonu yerine wire helper'a
çıkarıldı (`app_research_stream._resolve_and_persist_artifact`).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

# app_research_stream import zinciri pyotp (Docker-only) çeker — local SKIP, CI PASS.
pytest.importorskip("pyotp")

import app.modules.generations.artifacts as _artifacts_mod
import app.modules.generations.cluster_resolver as _resolver_mod
import app.modules.generations.subscriptions as _subs_mod
from app.api.app_research_stream import _resolve_and_persist_artifact
from app.shared.runtime_config.settings_store import settings_store as _settings

_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
_CLUSTER_ID = UUID("33333333-3333-3333-3333-333333333333")
_ORIGIN_MSG_ID = UUID("44444444-4444-4444-4444-444444444444")
_ART_ID = UUID("55555555-5555-5555-5555-555555555555")


def _flags(**vals):
    """settings_store.get_bool yerine geçen async fake — flag dict'inden okur."""

    async def _get_bool(db, key, default=False):
        return vals.get(key, default)

    return _get_bool


def _cluster(name="Asgari Ücret"):
    c = MagicMock()
    c.id = _CLUSTER_ID
    c.canonical_name = name
    return c


def _wire_kwargs():
    return {
        "user_id": _USER_ID,
        "query": "asgari ücret ne olacak",
        "content": "Üretilen cevap [1].",
        "sources_used": [{"title": "Kaynak"}],
        "effective_query": "asgari ücret ne olacak",
        "origin_message_id": _ORIGIN_MSG_ID,
    }


@pytest.mark.asyncio
async def test_both_flags_off_is_noop(monkeypatch):
    """İki flag OFF → None, hiçbir building-block çağrılmaz (stream'i bozmama invariantı)."""
    monkeypatch.setattr(_settings, "get_bool", _flags())  # tümü default False
    resolve = AsyncMock()
    monkeypatch.setattr(_resolver_mod, "resolve_cluster_by_entity", resolve)
    persist_db = AsyncMock()

    result = await _resolve_and_persist_artifact(persist_db, **_wire_kwargs())

    assert result is None
    resolve.assert_not_awaited()
    persist_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_artifacts_on_but_no_cluster_returns_none(monkeypatch):
    """artifacts.enabled ON ama entity'siz sorgu (resolve None) → None, artefakt YAZILMAZ."""
    monkeypatch.setattr(_settings, "get_bool", _flags(**{"artifacts.enabled": True}))
    monkeypatch.setattr(_resolver_mod, "resolve_cluster_by_entity", AsyncMock(return_value=None))
    create = AsyncMock()
    monkeypatch.setattr(_artifacts_mod, "create_artifact_with_revision", create)
    persist_db = AsyncMock()

    result = await _resolve_and_persist_artifact(persist_db, **_wire_kwargs())

    assert result is None
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_zero_cited_sources_returns_none_no_resolve(monkeypatch):
    """#1754 — artifacts.enabled ON ama 0 cited kaynak (clarification / 0-source
    honest-refusal) → None; küme RESOLVE EDİLMEZ, artefakt YAZILMAZ (kaynaksız
    non-answer'a kart bağlanmaz)."""
    monkeypatch.setattr(_settings, "get_bool", _flags(**{"artifacts.enabled": True}))
    resolve = AsyncMock()
    monkeypatch.setattr(_resolver_mod, "resolve_cluster_by_entity", resolve)
    create = AsyncMock()
    monkeypatch.setattr(_artifacts_mod, "create_artifact_with_revision", create)
    persist_db = AsyncMock()

    result = await _resolve_and_persist_artifact(
        persist_db, **{**_wire_kwargs(), "sources_used": []}
    )

    assert result is None
    resolve.assert_not_awaited()  # küme çözümü bile yapılmaz (erken guard)
    create.assert_not_awaited()
    persist_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_artifact_created_without_subscription(monkeypatch):
    """artifacts ON + cluster, subscriptions OFF → event döner; auto_subscribe ÇAĞRILMAZ."""
    cluster = _cluster()
    monkeypatch.setattr(_settings, "get_bool", _flags(**{"artifacts.enabled": True}))
    monkeypatch.setattr(_resolver_mod, "resolve_cluster_by_entity", AsyncMock(return_value=cluster))
    monkeypatch.setattr(
        _artifacts_mod, "create_artifact_with_revision", AsyncMock(return_value=_ART_ID)
    )
    sub = AsyncMock()
    monkeypatch.setattr(_subs_mod, "auto_subscribe", sub)
    persist_db = AsyncMock()

    result = await _resolve_and_persist_artifact(persist_db, **_wire_kwargs())

    assert result == {
        "artifact_id": str(_ART_ID),
        "cluster_id": str(_CLUSTER_ID),
        "cluster_name": "Asgari Ücret",
    }
    sub.assert_not_awaited()
    persist_db.commit.assert_awaited()  # artefakt commit'i


@pytest.mark.asyncio
async def test_artifact_created_with_auto_subscribe(monkeypatch):
    """İki flag ON → event döner + auto_subscribe doğru (user_id, cluster_id) ile çağrılır."""
    cluster = _cluster()
    monkeypatch.setattr(
        _settings,
        "get_bool",
        _flags(**{"artifacts.enabled": True, "subscriptions.auto.enabled": True}),
    )
    monkeypatch.setattr(_resolver_mod, "resolve_cluster_by_entity", AsyncMock(return_value=cluster))
    monkeypatch.setattr(
        _artifacts_mod, "create_artifact_with_revision", AsyncMock(return_value=_ART_ID)
    )
    sub = AsyncMock(return_value=True)
    monkeypatch.setattr(_subs_mod, "auto_subscribe", sub)
    persist_db = AsyncMock()

    result = await _resolve_and_persist_artifact(persist_db, **_wire_kwargs())

    assert result["artifact_id"] == str(_ART_ID)
    sub.assert_awaited_once()
    call_args, call_kwargs = sub.await_args
    assert call_args[1] == _USER_ID
    assert call_args[2] == _CLUSTER_ID
    assert call_kwargs.get("source") == "auto_query"


@pytest.mark.asyncio
async def test_auto_subscribe_failure_preserves_artifact_event(monkeypatch):
    """#2 fix: auto_subscribe patlasa bile event YİNE döner (commit'li artefaktın
    kart bildirimi DÜŞMEZ) + abonelik rollback'i çağrılır."""
    cluster = _cluster()
    monkeypatch.setattr(
        _settings,
        "get_bool",
        _flags(**{"artifacts.enabled": True, "subscriptions.auto.enabled": True}),
    )
    monkeypatch.setattr(_resolver_mod, "resolve_cluster_by_entity", AsyncMock(return_value=cluster))
    monkeypatch.setattr(
        _artifacts_mod, "create_artifact_with_revision", AsyncMock(return_value=_ART_ID)
    )
    monkeypatch.setattr(_subs_mod, "auto_subscribe", AsyncMock(side_effect=RuntimeError("race")))
    persist_db = AsyncMock()

    result = await _resolve_and_persist_artifact(persist_db, **_wire_kwargs())

    # Event KORUNDU — abonelik hatası bildirimi düşürmedi (hoist + izolasyon).
    assert result == {
        "artifact_id": str(_ART_ID),
        "cluster_id": str(_CLUSTER_ID),
        "cluster_name": "Asgari Ücret",
    }
    persist_db.rollback.assert_awaited()  # yalnız abonelik geri alındı
