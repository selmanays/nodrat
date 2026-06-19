"""Quota tracking — Redis sliding window + DB usage_events ledger (#29).

docs/strategy/pricing-strategy.md §3 (tier × quota)
PRD §3.7 (usage tracking)

Tier limits (pencere tier'a göre değişir):
  free:         10 generations / AY (30g kayan pencere) — plans.free ile birebir
  trial:        10 generations / 24h (abonelik deneme statüsü)
  starter:      30 generations / 24h
  pro:          150 generations / 24h
  agency_seat:  500 generations / 24h

NOT: free tier AYLIK enforce edilir (maliyet-güvenli; sistem-testi Bulgu 10 —
plans.monthly_generation_limit['free']=10 ile birebir). Paid tier'lar 24h
pencerede (mevcut davranış korunur); plans monthly limitleriyle (starter 100 /
pro 500 / agency 2500 / AY) tam hizalama ödeyen-müşteri etkisi → ayrı karar.

İki mekanizma:
  1. Redis sliding window — fast pre-check (sub-ms)
  2. usage_events DB insert — audit + cost tracking + reconciliation

Anti-pattern: server-side check ZORUNLU. Client-side bypass yok.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.billing.models import UsageEvent

logger = logging.getLogger(__name__)


UserTier = Literal["trial", "free", "starter", "pro", "agency_seat"]


# Tier × generation limit (pricing-strategy.md §3 + plans.monthly_generation_limit).
TIER_LIMITS: dict[str, int] = {
    "trial": 10,
    "free": 10,  # eski 5/24h → 10/AY (plans.free ile birebir, maliyet-güvenli)
    "starter": 30,
    "pro": 150,
    "agency_seat": 500,
}

DEFAULT_WINDOW_SECONDS = 24 * 60 * 60  # 24h (paid tier'lar + trial)
MONTH_WINDOW_SECONDS = 30 * 24 * 60 * 60  # ~aylık (30 gün kayan pencere)

# Tier başına pencere; listede olmayan tier DEFAULT_WINDOW_SECONDS kullanır.
TIER_WINDOW_SECONDS: dict[str, int] = {
    "free": MONTH_WINDOW_SECONDS,
}

# Redis sorted-set TTL en uzun pencereyi kapsamalı; aksi halde aylık-pencere
# girişleri 24h sonra expire olur → yanlış erken sıfırlama. Okuma anında
# zremrangebyscore pencereye göre kırpar, fazladan tutmak zararsız.
_MAX_WINDOW_SECONDS = MONTH_WINDOW_SECONDS

# Geriye dönük alias (eski import yok ama güvenli).
WINDOW_SECONDS = DEFAULT_WINDOW_SECONDS


@dataclass
class QuotaStatus:
    """Kullanıcının mevcut kotası."""

    tier: str
    limit: int
    used: int
    remaining: int
    reset_at: datetime
    """Sliding window doluysa ne zaman boşalacak."""

    @property
    def exceeded(self) -> bool:
        return self.used >= self.limit


class QuotaExceeded(Exception):
    """Kotası aşan kullanıcının yeni generation talebine izin verilmez."""

    def __init__(self, status: QuotaStatus):
        self.status = status
        super().__init__(
            f"Quota exceeded for tier={status.tier}: "
            f"{status.used}/{status.limit}, resets at {status.reset_at}"
        )


# ---------------------------------------------------------------------------
# Redis sliding window
# ---------------------------------------------------------------------------


_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _quota_key(user_id: UUID) -> str:
    return f"quota:gen:{user_id}"


async def _redis_count(
    user_id: UUID, window_seconds: int = DEFAULT_WINDOW_SECONDS
) -> tuple[int, datetime | None]:
    """Sliding window count (verilen pencere) + en eski timestamp.

    Sorted set: score=timestamp, member=event_id veya str timestamp.
    window_seconds tier'a göre değişir (free=aylık, diğerleri=24h).
    """
    r = _get_redis()
    key = _quota_key(user_id)
    now_ts = datetime.now(UTC).timestamp()
    cutoff = now_ts - window_seconds

    # Pencere dışı entry'leri temizle (idempotent housekeeping)
    await r.zremrangebyscore(key, 0, cutoff)

    count = await r.zcard(key)
    if count == 0:
        return 0, None

    # En eski entry → reset_at = oldest + window
    oldest = await r.zrange(key, 0, 0, withscores=True)
    if not oldest:
        return count, None
    _member, oldest_score = oldest[0]
    reset_at = datetime.fromtimestamp(oldest_score + window_seconds, tz=UTC)
    return count, reset_at


async def _redis_record(user_id: UUID) -> None:
    """Yeni generation event → sorted set'e ekle."""
    r = _get_redis()
    key = _quota_key(user_id)
    now = datetime.now(UTC)
    await r.zadd(key, {f"{now.timestamp()}:{now.microsecond}": now.timestamp()})
    # TTL en uzun pencereyi (aylık) kapsamalı; tier-bağımsız zad sırasında tier
    # bilinmiyor → max pencere. zremrangebyscore okuma anında pencereye kırpar.
    await r.expire(key, _MAX_WINDOW_SECONDS + 60)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def _load_quota_settings(tier: str) -> tuple[int, int]:
    """#270 — runtime per-tier limit + window override.

    Default limit TIER_LIMITS, default window TIER_WINDOW_SECONDS (free=aylık,
    diğerleri 24h). Admin runtime override: quota.tier_{tier} + quota.window_seconds_{tier}.
    """
    default_limit = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    default_window = TIER_WINDOW_SECONDS.get(tier, DEFAULT_WINDOW_SECONDS)
    try:
        from app.core.db import get_session_factory
        from app.shared.runtime_config.settings_store import settings_store

        factory = get_session_factory()
        async with factory() as db:
            limit = await settings_store.get_int(db, f"quota.tier_{tier}", default_limit)
            window = await settings_store.get_int(
                db, f"quota.window_seconds_{tier}", default_window
            )
            return limit, window
    except Exception as exc:  # pragma: no cover
        logger.debug("quota settings load fallback: %s", exc)
        return default_limit, default_window


async def get_quota_status(user_id: UUID, tier: UserTier) -> QuotaStatus:
    """Mevcut kotayı döner. Eski entry'ler temizlenir."""
    limit, window_sec = await _load_quota_settings(tier)
    used, reset_at = await _redis_count(user_id, window_sec)
    remaining = max(0, limit - used)
    if reset_at is None:
        reset_at = datetime.now(UTC) + timedelta(seconds=window_sec)
    return QuotaStatus(
        tier=tier,
        limit=limit,
        used=used,
        remaining=remaining,
        reset_at=reset_at,
    )


async def enforce_quota(user_id: UUID, tier: UserTier) -> QuotaStatus:
    """Kotayı kontrol et. Aşılmışsa QuotaExceeded raise.

    Caller başarılı dispatch'ten sonra `record_usage()` çağırmalı.
    Reservation pattern'i değil — sadece check (race window minimal).
    """
    status = await get_quota_status(user_id, tier)
    if status.exceeded:
        raise QuotaExceeded(status)
    return status


async def record_usage(
    db: AsyncSession,
    *,
    user_id: UUID,
    event_type: str = "generation",
    provider: str | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    metadata: dict | None = None,
) -> None:
    """Yeni event kaydı: Redis (fast) + usage_events DB (audit).

    İkisi de best-effort — Redis fail ederse DB hâlâ kaydeder.
    """
    # Redis (sliding window)
    try:
        await _redis_record(user_id)
    except Exception as exc:  # pragma: no cover - resilience
        logger.warning("quota redis_record failed user=%s err=%s", user_id, exc)

    # DB ledger
    from decimal import Decimal

    event = UsageEvent(
        user_id=user_id,
        event_type=event_type,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal(str(cost_usd)) if cost_usd is not None else None,
        event_metadata=metadata or {},
    )
    db.add(event)


async def reconcile_redis_from_db(
    db: AsyncSession, user_id: UUID, window_seconds: int = DEFAULT_WINDOW_SECONDS
) -> int:
    """DB'den pencere içi event_count'unu Redis'e geri yansıtır.

    Redis kaybolursa (restart) DB'den replay edilir. Sliding window
    için cron/admin endpoint'i kullanır (ileride). window_seconds tier'a
    göre verilmeli (free=aylık); default 24h.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)
    result = await db.execute(
        select(func.count(UsageEvent.id))
        .where(UsageEvent.user_id == user_id)
        .where(UsageEvent.event_type == "generation")
        .where(UsageEvent.created_at >= cutoff)
    )
    db_count = int(result.scalar() or 0)

    r = _get_redis()
    key = _quota_key(user_id)
    redis_count = await r.zcard(key)

    if redis_count >= db_count:
        return redis_count

    # Backfill rough — sadece count'u eşitle (timestamp'ler exact değil)
    now_ts = datetime.now(UTC).timestamp()
    diff = db_count - redis_count
    pipe = r.pipeline()
    for i in range(diff):
        synthetic_ts = now_ts - (i * 60)  # 1 dk aralıklı sentetik
        pipe.zadd(key, {f"reconcile:{i}:{synthetic_ts}": synthetic_ts})
    await pipe.execute()
    return db_count
