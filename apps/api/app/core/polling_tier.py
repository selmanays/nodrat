"""Adaptive polling tier hesabı (#578 Faz 2).

Bu modül her başarılı RSS fetch sonunda çağrılır. Source'un yayın hızına göre
4 tier'dan birini hesaplar:

    hot       — son 1h ≥2 yeni item        (Faz 3'te 60sn polling)
    normal    — son 6h ≥1 item (default)   (5dk)
    cold      — 6+ saattir yeni item yok    (30dk)
    hibernate — 24+ saat hiç değişmedi      (4 saat)

Faz 2'de **shadow mode**: hesap sonucu `Source.would_be_tier` + `tier_metadata`'ya
yazılır; gerçek `polling_tier` DEĞİŞMEZ (eski crawl_interval_minutes ile akış
devam eder). Faz 3'te `app_settings.rss.tier_apply_enabled=true` olunca
polling_tier = would_be_tier transition'ı işler.

Detay: wiki/concepts/adaptive-polling-tier.md, wiki/decisions/realtime-rss-polling.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source

logger = logging.getLogger(__name__)


# Tier sabitleri — string literal'lar yerine (typo'dan korunmak için)
TIER_HOT = "hot"
TIER_NORMAL = "normal"
TIER_COLD = "cold"
TIER_HIBERNATE = "hibernate"
VALID_TIERS = frozenset({TIER_HOT, TIER_NORMAL, TIER_COLD, TIER_HIBERNATE})

# Tier eşikleri
HOT_ITEMS_LAST_1H = 2  # son 1h'de bu kadar item → hot
NORMAL_ITEMS_LAST_6H = 1  # son 6h'de bu kadar item → normal
COLD_HOURS_SINCE_NEW = 24  # bu süreden sonra hibernate'e geç
DWELL_TIME_MIN_MINUTES = 15  # tier transition arası minimum süre
COLD_START_GRACE_HOURS = 24  # kaynak açılalı bu kadar değilse default 'normal'


@dataclass(frozen=True)
class TierComputation:
    """compute_tier çıktısı — tier + telemetry."""

    tier: str
    """4 tier'dan biri."""

    metadata: dict
    """Telemetry: items_1h, items_6h, last_item_at, hours_since_new,
    consecutive_unchanged, computed_at, dwell_time_remaining_sec."""

    transitioned: bool
    """True → bu hesap önceki polling_tier'dan farklı (ve dwell-time geçmiş)."""


async def _count_items(
    db: AsyncSession,
    source_id: str,
    since: datetime,
) -> int:
    """Source'un `since`'tan sonra published_at'i olan article sayısı.

    `(source_id, published_at DESC)` indeksini kullanır
    (idx_articles_source_published).

    Notlar:
    - `published_at IS NULL` olan article'lar SAYILMAZ — RSS feed'de
      published date verilmemişse o item zaten "ne zaman yayımlandı"
      bilinmiyor; tier hesabı için belirsiz veri.
    - status filter (#904): 'cleaned'/'discovered'/'quarantine' = kaynak
      GERÇEKTEN yayınladı (quarantine = yayın var ama extraction-miss,
      tier sinyali geçerli). 'failed' (transient) / 'discarded' (gerçek
      404/duplicate/invalid) gerçek yeni yayın DEĞİL → sayılmaz.
    """
    result = await db.execute(
        sa_text(
            """
            SELECT COUNT(*)
            FROM articles
            WHERE source_id = :sid
              AND published_at IS NOT NULL
              AND published_at >= :since
              AND status IN ('cleaned', 'discovered', 'quarantine')
            """
        ),
        {"sid": str(source_id), "since": since},
    )
    return int(result.scalar() or 0)


async def _last_item_at(
    db: AsyncSession,
    source_id: str,
) -> datetime | None:
    """Source'un en son published_at (fallback: created_at)."""
    result = await db.execute(
        sa_text(
            """
            SELECT MAX(COALESCE(published_at, created_at))
            FROM articles
            WHERE source_id = :sid
              AND status IN ('cleaned', 'discovered', 'quarantine')
            """
        ),
        {"sid": str(source_id)},
    )
    return result.scalar()


def _classify_tier(
    *,
    items_1h: int,
    items_6h: int,
    hours_since_new: float | None,
) -> str:
    """Saf sınıflandırıcı — DB veya state'siz, test edilebilir."""
    if items_1h >= HOT_ITEMS_LAST_1H:
        return TIER_HOT
    if items_6h >= NORMAL_ITEMS_LAST_6H:
        return TIER_NORMAL
    if hours_since_new is None or hours_since_new >= COLD_HOURS_SINCE_NEW:
        return TIER_HIBERNATE
    return TIER_COLD


def _apply_transition_rules(
    *,
    candidate: str,
    current: str,
    tier_changed_at: datetime | None,
    items_1h: int,
    now: datetime,
) -> tuple[str, bool, float]:
    """Transition kuralları — dwell-time + hibernate exit + cold start guard.

    Returns:
        (final_tier, transitioned, dwell_remaining_sec)
        - transitioned=True → tier şu an değişiyor (caller tier_changed_at güncelle)
        - dwell_remaining_sec → kaç saniye sonra tier yeniden değişebilir
    """
    # Hibernate'den çıkış: yeni item geldiyse direkt 'normal' (dwell-time bypass)
    if current == TIER_HIBERNATE and items_1h > 0:
        return TIER_NORMAL, True, 0.0

    # Tier değişmiyorsa transition yok
    if candidate == current:
        return current, False, 0.0

    # Dwell-time guard: 15 dk geçmediyse mevcut tier'ı koru
    if tier_changed_at is not None:
        elapsed = (now - tier_changed_at).total_seconds()
        dwell_required = DWELL_TIME_MIN_MINUTES * 60
        if elapsed < dwell_required:
            return current, False, dwell_required - elapsed

    return candidate, True, 0.0


async def compute_tier(
    source: Source,
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> TierComputation:
    """Source için tier hesaplar (saf fonksiyon — sadece okuma yapar).

    Caller `would_be_tier` + `tier_metadata` (+ apply mode'da `polling_tier`
    + `tier_changed_at`) güncellemesinden sorumludur.

    Args:
        source: Source ORM (sadece id, polling_tier, tier_changed_at,
            consecutive_unchanged, created_at okunur).
        db: AsyncSession — sadece SELECT.
        now: opsiyonel (test için override).

    Returns:
        TierComputation(tier, metadata, transitioned)
    """
    if now is None:
        now = datetime.now(UTC)

    # Cold start: kaynak çok yeni → henüz tier kalibre etmek için yeterli veri yok
    source_age_hours = (now - source.created_at).total_seconds() / 3600
    if source_age_hours < COLD_START_GRACE_HOURS:
        metadata = {
            "items_1h": None,
            "items_6h": None,
            "last_item_at": None,
            "hours_since_new": None,
            "consecutive_unchanged": int(source.consecutive_unchanged or 0),
            "computed_at": now.isoformat(),
            "cold_start": True,
            "source_age_hours": round(source_age_hours, 2),
        }
        # Cold start her zaman 'normal' — transition mantığı uygulanmaz
        return TierComputation(
            tier=TIER_NORMAL,
            metadata=metadata,
            transitioned=(source.polling_tier != TIER_NORMAL),
        )

    items_1h = await _count_items(db, source.id, now - timedelta(hours=1))
    items_6h = await _count_items(db, source.id, now - timedelta(hours=6))
    last_at = await _last_item_at(db, source.id)
    hours_since_new: float | None = None
    if last_at is not None:
        # `last_at` aware mi? articles.created_at NOT NULL TIMESTAMPTZ → aware
        hours_since_new = (now - last_at).total_seconds() / 3600

    candidate = _classify_tier(
        items_1h=items_1h,
        items_6h=items_6h,
        hours_since_new=hours_since_new,
    )

    final_tier, transitioned, dwell_remaining = _apply_transition_rules(
        candidate=candidate,
        current=source.polling_tier or TIER_NORMAL,
        tier_changed_at=source.tier_changed_at,
        items_1h=items_1h,
        now=now,
    )

    metadata = {
        "items_1h": items_1h,
        "items_6h": items_6h,
        "last_item_at": last_at.isoformat() if last_at else None,
        "hours_since_new": (round(hours_since_new, 2) if hours_since_new is not None else None),
        "consecutive_unchanged": int(source.consecutive_unchanged or 0),
        "computed_at": now.isoformat(),
        "cold_start": False,
        "candidate_tier": candidate,
        "dwell_remaining_sec": round(dwell_remaining, 1),
    }

    return TierComputation(
        tier=final_tier,
        metadata=metadata,
        transitioned=transitioned,
    )
