"""SettingsStore unit tests (#264, MVP-1.2)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.settings_store import (
    SettingsStore,
    SettingValue,
)

# ---------------------------------------------------------------------------
# L1 cache
# ---------------------------------------------------------------------------


def test_l1_set_get_round_trip():
    store = SettingsStore()
    store._l1_set("rerank.enabled", True)
    entry = store._l1_get("rerank.enabled")
    assert entry is not None
    assert entry.value is True


def test_l1_expiry_evicts_entry():
    store = SettingsStore()
    store._l1["x"] = SettingValue(value=42, expires_at=time.monotonic() - 1)
    assert store._l1_get("x") is None
    assert "x" not in store._l1


def test_l1_invalidate_removes_key():
    store = SettingsStore()
    store._l1_set("a", 1)
    store._l1_set("b", 2)
    store._l1_invalidate("a")
    assert store._l1_get("a") is None
    assert store._l1_get("b") is not None


def test_l1_invalidate_all_clears():
    store = SettingsStore()
    store._l1_set("a", 1)
    store._l1_set("b", 2)
    store._l1_invalidate_all()
    assert len(store._l1) == 0


# ---------------------------------------------------------------------------
# get with DB fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_default_when_db_miss():
    store = SettingsStore()
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=lambda: None))
    val = await store.get(db, "missing.key", default=0.42)
    assert val == 0.42


@pytest.mark.asyncio
async def test_get_uses_l1_cache_on_second_call():
    store = SettingsStore()
    db = MagicMock()
    # First call hits DB
    db.execute = AsyncMock(return_value=MagicMock(first=lambda: ("hit",)))
    val1 = await store.get(db, "key1", default=None)
    assert val1 == "hit"

    # Second call should hit L1, not DB
    db.execute.reset_mock()
    val2 = await store.get(db, "key1", default=None)
    assert val2 == "hit"
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_returns_default_on_db_exception():
    store = SettingsStore()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db down"))
    val = await store.get(db, "k", default="fallback")
    assert val == "fallback"


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_float_coerces_string():
    store = SettingsStore()
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=lambda: ("0.25",)))
    val = await store.get_float(db, "k", default=0.15)
    assert val == 0.25


@pytest.mark.asyncio
async def test_get_int_coerces():
    store = SettingsStore()
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=lambda: (5,)))
    val = await store.get_int(db, "k", default=3)
    assert val == 5


@pytest.mark.asyncio
async def test_get_bool_coerces_string_truthy():
    store = SettingsStore()
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=lambda: ("true",)))
    val = await store.get_bool(db, "k", default=False)
    assert val is True


@pytest.mark.asyncio
async def test_get_bool_coerces_native_bool():
    store = SettingsStore()
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=lambda: (False,)))
    val = await store.get_bool(db, "k", default=True)
    assert val is False


@pytest.mark.asyncio
async def test_get_int_returns_default_on_invalid_value():
    store = SettingsStore()
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=lambda: ("not_a_number",)))
    val = await store.get_int(db, "k", default=99)
    assert val == 99


# ---------------------------------------------------------------------------
# set + reset publish to pub/sub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_invalidates_l1_and_publishes():
    store = SettingsStore()
    store._l1_set("k", "old_value")

    redis_mock = MagicMock()
    redis_mock.publish = AsyncMock()
    store._redis = redis_mock

    db = MagicMock()
    db.execute = AsyncMock()

    await store.set(db, key="k", value="new_value", type_="string", group_name="rag")

    # L1 invalidated
    assert store._l1_get("k") is None
    # Redis publish called
    redis_mock.publish.assert_awaited_once_with("settings:invalidate", "k")


@pytest.mark.asyncio
async def test_reset_invalidates_and_publishes():
    store = SettingsStore()
    store._l1_set("k", "value")

    redis_mock = MagicMock()
    redis_mock.publish = AsyncMock()
    store._redis = redis_mock

    db = MagicMock()
    db.execute = AsyncMock()

    await store.reset(db, "k")

    assert store._l1_get("k") is None
    redis_mock.publish.assert_awaited_once_with("settings:invalidate", "k")
