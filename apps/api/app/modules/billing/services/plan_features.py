"""Plan features resolver — tier-aware fallback (#522).

User.tier authoritative kabul edilir; Subscription kaydı varsa o plan kullanılır,
yoksa User.tier → Plan.code mapping ile Plan tablosundan features çekilir.
Plan tablosunda da yoksa hard-coded free defaults döner (test/seedless ortam).

Çağrı yerleri:
    apps/api/app/api/style_profiles.py — Pro paywall + slot quota
    apps/api/app/api/app_generate.py — _resolve_style_profile

Migration `20260509_0400` plans tablosunu seed eder; bu helper migration sonrası
her durumda anlamlı bir features dict döndürür.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Plan, Subscription
from app.models.user import User

# User.tier → Plan.code mapping. Plan seed (20260509_0400) ile uyumlu.
# agency_seat (invited) seat sahibi olduğu için en düşük agency variant'ın
# features'ını alır — eğer parent sub bilinirse o tercih edilebilir, ama
# agency multi-seat resolve şu an scope dışı (#450 frontend tamam, server-side
# sub linking için ayrı pass).
_TIER_TO_PLAN_CODE: dict[str, str] = {
    "free": "free",
    "starter": "starter",
    "pro": "pro",
    "agency_seat": "agency_3",
}


# Hard-coded fallback (test/CI ortamlarında plans seed yoksa).
_FREE_DEFAULTS: dict[str, Any] = {
    "allowed_models": ["deepseek_v4_flash"],
    "comparison_mode": False,
    "style_profiles": False,
    "style_profiles_slots": 0,
    "visual_features": False,
    "analysis_output": False,
    "concurrent_gen": 1,
    "rate_per_hour": 5,
    "support_sla_hours": 0,
}


async def resolve_user_plan_features(db: AsyncSession, user: User) -> tuple[dict[str, Any], str]:
    """Kullanıcının efektif plan features + plan_code'unu döndürür.

    Çözümleme sırası:
      1. Active subscription (trialing/active) → o plan
      2. User.tier → _TIER_TO_PLAN_CODE → Plan tablosu
      3. _FREE_DEFAULTS hard-coded

    Returns: (features_dict, plan_code)
    """
    # 1) Active subscription
    sub_plan = (
        await db.execute(
            select(Plan)
            .join(Subscription, Subscription.plan_id == Plan.id)
            .where(
                Subscription.user_id == user.id,
                Subscription.status.in_(["trialing", "active"]),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if sub_plan is not None:
        return (sub_plan.features or {}, sub_plan.code)

    # 2) User.tier → Plan.code fallback
    fallback_code = _TIER_TO_PLAN_CODE.get(user.tier or "free", "free")
    plan = (await db.execute(select(Plan).where(Plan.code == fallback_code))).scalar_one_or_none()
    if plan is not None:
        return (plan.features or {}, plan.code)

    # 3) Hard-coded free defaults
    return (dict(_FREE_DEFAULTS), "free")
