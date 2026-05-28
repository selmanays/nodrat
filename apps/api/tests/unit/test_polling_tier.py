"""Adaptive polling tier — saf fonksiyon unit tests (#578 Faz 2).

`_classify_tier` ve `_apply_transition_rules` saf — DB gerekmez. `compute_tier`
DB query yapar (mock'lanmış); orada cold start path'i + entegre flow test
edilir. Worker integration testi testcontainers gerektirdiği için bu PR'da yok.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.modules.sources.services import polling_tier as _pt_mod
from app.modules.sources.services.polling_tier import (
    COLD_HOURS_SINCE_NEW,
    COLD_START_GRACE_HOURS,
    DWELL_TIME_MIN_MINUTES,
    HOT_ITEMS_LAST_1H,
    NORMAL_ITEMS_LAST_6H,
    TIER_COLD,
    TIER_HIBERNATE,
    TIER_HOT,
    TIER_NORMAL,
    VALID_TIERS,
    TierComputation,
    _apply_transition_rules,
    _classify_tier,
    compute_tier,
)

# ---------------------------------------------------------------------------
# _classify_tier — saf sınıflandırıcı
# ---------------------------------------------------------------------------


def test_classify_hot_threshold():
    """Son 1h ≥ HOT_ITEMS_LAST_1H → hot."""
    assert _classify_tier(items_1h=HOT_ITEMS_LAST_1H, items_6h=10, hours_since_new=0.1) == TIER_HOT
    assert _classify_tier(items_1h=10, items_6h=10, hours_since_new=0.0) == TIER_HOT


def test_classify_normal_when_below_hot_threshold():
    """1h < hot eşiği AMA 6h ≥ normal → normal."""
    assert (
        _classify_tier(items_1h=1, items_6h=NORMAL_ITEMS_LAST_6H, hours_since_new=2.0)
        == TIER_NORMAL
    )
    assert _classify_tier(items_1h=0, items_6h=5, hours_since_new=4.0) == TIER_NORMAL


def test_classify_cold_when_recent_but_no_items_in_6h():
    """6h içinde item yok ama 24h'den daha yeni → cold."""
    assert _classify_tier(items_1h=0, items_6h=0, hours_since_new=10.0) == TIER_COLD
    assert _classify_tier(items_1h=0, items_6h=0, hours_since_new=23.9) == TIER_COLD


def test_classify_hibernate_when_old_or_unknown():
    """24+ saatten eski VEYA last_item_at yok → hibernate."""
    assert (
        _classify_tier(items_1h=0, items_6h=0, hours_since_new=COLD_HOURS_SINCE_NEW)
        == TIER_HIBERNATE
    )
    assert _classify_tier(items_1h=0, items_6h=0, hours_since_new=100.0) == TIER_HIBERNATE
    assert _classify_tier(items_1h=0, items_6h=0, hours_since_new=None) == TIER_HIBERNATE


def test_classify_hot_takes_priority_over_normal():
    """Hot eşiği geçmişse hours_since_new yüksek olsa bile hot."""
    # Edge: 100 item son 1h'de + last item 50 saat önce (mantıksızca, ama priority test'i)
    assert _classify_tier(items_1h=10, items_6h=10, hours_since_new=50.0) == TIER_HOT


def test_classify_returns_only_valid_tiers():
    """Hangi input olursa olsun çıktı VALID_TIERS içinde."""
    for items_1h in (0, 1, 2, 100):
        for items_6h in (0, 1, 5):
            for hours in (None, 0.0, 5.0, 24.0, 100.0):
                result = _classify_tier(items_1h=items_1h, items_6h=items_6h, hours_since_new=hours)
                assert result in VALID_TIERS, f"invalid tier for {items_1h}/{items_6h}/{hours}"


# ---------------------------------------------------------------------------
# _apply_transition_rules — dwell-time + hibernate exit
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)


def test_no_transition_when_candidate_equals_current():
    """Tier değişmiyorsa transition yok."""
    final, transitioned, dwell = _apply_transition_rules(
        candidate=TIER_NORMAL,
        current=TIER_NORMAL,
        tier_changed_at=None,
        items_1h=0,
        now=_now(),
    )
    assert final == TIER_NORMAL
    assert transitioned is False
    assert dwell == 0.0


def test_dwell_time_blocks_transition():
    """Son tier değişiminden 15dk geçmediyse mevcut tier korunur."""
    now = _now()
    recent_change = now - timedelta(minutes=5)  # 5dk önce, 15dk minimum
    final, transitioned, dwell = _apply_transition_rules(
        candidate=TIER_HOT,
        current=TIER_NORMAL,
        tier_changed_at=recent_change,
        items_1h=10,
        now=now,
    )
    assert final == TIER_NORMAL  # değişmedi
    assert transitioned is False
    assert dwell > 0  # kaç saniye sonra değişebilir


def test_dwell_time_allows_transition_after_threshold():
    """15dk geçtiyse transition izinli."""
    now = _now()
    old_change = now - timedelta(minutes=DWELL_TIME_MIN_MINUTES + 1)
    final, transitioned, dwell = _apply_transition_rules(
        candidate=TIER_HOT,
        current=TIER_NORMAL,
        tier_changed_at=old_change,
        items_1h=10,
        now=now,
    )
    assert final == TIER_HOT
    assert transitioned is True
    assert dwell == 0.0


def test_first_transition_no_dwell_check():
    """tier_changed_at NULL ise (hiç transition olmamış) dwell guard yok."""
    final, transitioned, _ = _apply_transition_rules(
        candidate=TIER_HOT,
        current=TIER_NORMAL,
        tier_changed_at=None,
        items_1h=10,
        now=_now(),
    )
    assert final == TIER_HOT
    assert transitioned is True


def test_hibernate_exit_bypasses_dwell_time():
    """Hibernate'den çıkış: yeni item geldiyse dwell-time'a bakmadan 'normal'."""
    now = _now()
    just_changed = now - timedelta(minutes=1)  # 1dk önce hibernate'e geçti
    final, transitioned, _ = _apply_transition_rules(
        candidate=TIER_HIBERNATE,  # candidate hala hibernate (henüz 6h dolmadı)
        current=TIER_HIBERNATE,
        tier_changed_at=just_changed,
        items_1h=1,  # ama 1 yeni item geldi
        now=now,
    )
    assert final == TIER_NORMAL
    assert transitioned is True


def test_hibernate_exit_only_when_items_present():
    """Hibernate'de items_1h=0 ise hala hibernate."""
    final, transitioned, _ = _apply_transition_rules(
        candidate=TIER_HIBERNATE,
        current=TIER_HIBERNATE,
        tier_changed_at=None,
        items_1h=0,
        now=_now(),
    )
    assert final == TIER_HIBERNATE
    assert transitioned is False


# ---------------------------------------------------------------------------
# compute_tier — entegre (DB mock'lanmış)
# ---------------------------------------------------------------------------


class _FakeSource:
    """Source ORM stub'ı — sadece compute_tier'ın okuduğu alanlar."""

    def __init__(
        self,
        *,
        created_at: datetime,
        polling_tier: str = TIER_NORMAL,
        tier_changed_at: datetime | None = None,
        consecutive_unchanged: int = 0,
    ):
        self.id = uuid4()
        self.created_at = created_at
        self.polling_tier = polling_tier
        self.tier_changed_at = tier_changed_at
        self.consecutive_unchanged = consecutive_unchanged


@pytest.mark.asyncio
async def test_compute_tier_cold_start_returns_normal():
    """Yeni eklenen kaynak (24h'dan az) tier='normal' force, DB query yok."""
    now = _now()
    source = _FakeSource(
        created_at=now - timedelta(hours=COLD_START_GRACE_HOURS - 1),
    )
    db_mock = AsyncMock()  # hiç query çağrılmamalı
    result = await compute_tier(source, db_mock, now=now)

    assert isinstance(result, TierComputation)
    assert result.tier == TIER_NORMAL
    assert result.metadata["cold_start"] is True
    assert result.metadata["items_1h"] is None  # cold start = veri toplanmadı
    assert "source_age_hours" in result.metadata


@pytest.mark.asyncio
async def test_compute_tier_hot_path():
    """Yeterli eski kaynak + son 1h yoğun item → hot."""
    now = _now()
    source = _FakeSource(
        created_at=now - timedelta(days=30),  # eski
        polling_tier=TIER_NORMAL,
        tier_changed_at=now - timedelta(hours=2),  # 2 saat önce — dwell-time geçmiş
    )

    with (
        patch.object(
            _pt_mod,
            "_count_items",
            new=AsyncMock(side_effect=[5, 20]),
        ),
        patch.object(
            _pt_mod,
            "_last_item_at",
            new=AsyncMock(return_value=now - timedelta(minutes=10)),
        ),
    ):
        result = await compute_tier(source, AsyncMock(), now=now)

    assert result.tier == TIER_HOT
    assert result.metadata["items_1h"] == 5
    assert result.metadata["items_6h"] == 20
    assert result.metadata["candidate_tier"] == TIER_HOT
    assert result.transitioned is True


@pytest.mark.asyncio
async def test_compute_tier_hibernate_path():
    """Eski kaynak + 0 item + last_at >24h → hibernate."""
    now = _now()
    source = _FakeSource(
        created_at=now - timedelta(days=30),
        polling_tier=TIER_COLD,
        tier_changed_at=now - timedelta(hours=2),
    )

    with (
        patch.object(
            _pt_mod,
            "_count_items",
            new=AsyncMock(side_effect=[0, 0]),
        ),
        patch.object(
            _pt_mod,
            "_last_item_at",
            new=AsyncMock(return_value=now - timedelta(hours=48)),
        ),
    ):
        result = await compute_tier(source, AsyncMock(), now=now)

    assert result.tier == TIER_HIBERNATE
    assert result.metadata["hours_since_new"] == 48.0


@pytest.mark.asyncio
async def test_compute_tier_no_articles_returns_hibernate():
    """Hiç article yoksa (last_item_at=None) → hibernate."""
    now = _now()
    source = _FakeSource(created_at=now - timedelta(days=30))

    with (
        patch.object(
            _pt_mod,
            "_count_items",
            new=AsyncMock(side_effect=[0, 0]),
        ),
        patch.object(
            _pt_mod,
            "_last_item_at",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await compute_tier(source, AsyncMock(), now=now)

    assert result.tier == TIER_HIBERNATE
    assert result.metadata["last_item_at"] is None
    assert result.metadata["hours_since_new"] is None


@pytest.mark.asyncio
async def test_compute_tier_metadata_has_required_keys():
    """Telemetry dict tüm beklenen alanları içerir."""
    now = _now()
    source = _FakeSource(created_at=now - timedelta(days=30), consecutive_unchanged=3)

    with (
        patch.object(
            _pt_mod,
            "_count_items",
            new=AsyncMock(side_effect=[1, 3]),
        ),
        patch.object(
            _pt_mod,
            "_last_item_at",
            new=AsyncMock(return_value=now - timedelta(hours=4)),
        ),
    ):
        result = await compute_tier(source, AsyncMock(), now=now)

    required = {
        "items_1h",
        "items_6h",
        "last_item_at",
        "hours_since_new",
        "consecutive_unchanged",
        "computed_at",
        "cold_start",
        "candidate_tier",
        "dwell_remaining_sec",
    }
    assert required <= set(result.metadata.keys())
    assert result.metadata["consecutive_unchanged"] == 3
