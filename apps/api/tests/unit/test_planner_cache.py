"""Tests for app.core.planner_cache (issue #527).

Cache key determinism, gün granülasyonu, get/set roundtrip.

Redis bağlantısı için fakeredis tercih ederdim ama mevcut conftest harness'i
unit test seviyesinde Redis mock kullanmıyor (entegrasyon testleri gerçek
Redis'e bağlanır). Bu test'ler module-level _get_redis fonksiyonunu monkeypatch
edip in-memory dict üzerinden çalışır.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from app.core import planner_cache


class _MemoryRedis:
    """Minimal async Redis mock — set/get/setex/delete."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        # TTL ignored in memory mock
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest.fixture
def memory_redis(monkeypatch):
    mock = _MemoryRedis()
    monkeypatch.setattr(planner_cache, "_get_redis", lambda: mock)
    monkeypatch.setattr(planner_cache, "_redis_client", None)
    return mock


def test_cache_key_deterministic():
    when = datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC)
    k1 = planner_cache._cache_key(
        request_text="bugün gündem",
        locale="tr-TR",
        tier="free",
        current_time=when,
    )
    k2 = planner_cache._cache_key(
        request_text="bugün gündem",
        locale="tr-TR",
        tier="free",
        current_time=when,
    )
    assert k1 == k2
    # #952 — CACHE_KEY_VERSION'a bağla (v1 stale; #778 v2, gelecek-proof)
    assert k1.startswith(f"qp:{planner_cache.CACHE_KEY_VERSION}:")


def test_cache_key_changes_by_day():
    when1 = datetime(2026, 5, 9, 23, 59, 59, tzinfo=UTC)
    when2 = datetime(2026, 5, 10, 0, 0, 1, tzinfo=UTC)
    k1 = planner_cache._cache_key(
        request_text="aynı sorgu",
        locale="tr-TR",
        tier="free",
        current_time=when1,
    )
    k2 = planner_cache._cache_key(
        request_text="aynı sorgu",
        locale="tr-TR",
        tier="free",
        current_time=when2,
    )
    assert k1 != k2  # gün geçtikçe key değişmeli


def test_cache_key_locale_and_tier_separated():
    when = datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC)
    k_free = planner_cache._cache_key(
        request_text="x", locale="tr-TR", tier="free", current_time=when
    )
    k_pro = planner_cache._cache_key(
        request_text="x", locale="tr-TR", tier="pro", current_time=when
    )
    k_en = planner_cache._cache_key(
        request_text="x", locale="en-US", tier="free", current_time=when
    )
    assert len({k_free, k_pro, k_en}) == 3


@pytest.mark.asyncio
async def test_get_miss_returns_none(memory_redis):
    result = await planner_cache.get_cached_plan(
        request_text="hiç olmayan sorgu xy",
        locale="tr-TR",
        tier="free",
    )
    assert result is None


@pytest.mark.asyncio
async def test_set_then_get_roundtrip(memory_redis):
    when = datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC)
    plan_dict = {
        "intent": "current_content_generation",
        "topic_query": "ekonomi",
        "keywords": ["ekonomi", "tüfe"],
        "requested_count": 3,
        "mode": "current",
        "timeframes": [],
        "output_type": "x_post",
        "tone": None,
        "geographic_focus": None,
        "constraints": [],
        "needs_sources": True,
        "minimum_evidence_per_period": 2,
        "is_short_query": False,
        "warnings": [],
    }
    await planner_cache.set_cached_plan(
        request_text="ekonomi gündemi",
        locale="tr-TR",
        tier="free",
        plan_dict=plan_dict,
        current_time=when,
    )
    result = await planner_cache.get_cached_plan(
        request_text="ekonomi gündemi",
        locale="tr-TR",
        tier="free",
        current_time=when,
    )
    assert result is not None
    assert result["topic_query"] == "ekonomi"
    assert result["keywords"] == ["ekonomi", "tüfe"]


@pytest.mark.asyncio
async def test_corrupted_cache_evicted(memory_redis):
    when = datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC)
    key = planner_cache._cache_key(
        request_text="bozuk", locale="tr-TR", tier="free", current_time=when
    )
    # Manual write of bad JSON
    await memory_redis.setex(key, 86400, "not-a-json{")
    result = await planner_cache.get_cached_plan(
        request_text="bozuk",
        locale="tr-TR",
        tier="free",
        current_time=when,
    )
    assert result is None
    # Evicted
    assert await memory_redis.get(key) is None


@pytest.mark.asyncio
async def test_empty_request_short_circuits(memory_redis):
    """Boş request_text cache'e gitmemeli."""
    result = await planner_cache.get_cached_plan(
        request_text="",
        locale="tr-TR",
        tier="free",
    )
    assert result is None


@pytest.mark.asyncio
async def test_set_serializable(memory_redis):
    """Plan dict serialize edilirken iç içe yapı korunur."""
    when = datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC)
    plan_dict = {
        "topic_query": "test",
        "timeframes": [
            {
                "label": "bu hafta",
                "from_iso": "2026-05-02T00:00:00Z",
                "to_iso": "2026-05-09T23:59:59Z",
            }
        ],
        "keywords": ["a", "b"],
    }
    await planner_cache.set_cached_plan(
        request_text="test sorgu",
        locale="tr-TR",
        tier="free",
        plan_dict=plan_dict,
        current_time=when,
    )
    raw = await memory_redis.get(
        planner_cache._cache_key(
            request_text="test sorgu",
            locale="tr-TR",
            tier="free",
            current_time=when,
        )
    )
    assert raw is not None
    decoded = json.loads(raw)
    assert decoded["timeframes"][0]["label"] == "bu hafta"
