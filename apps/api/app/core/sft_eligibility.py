"""SFT eligibility — generic util (#800 S1A-C).

Mevcut `_recompute_sft_eligibility` (apps/api/app/api/app_generate.py) logic'i
buraya taşındı. Hem Generation hem Message tablosu için kullanılır.

wiki/concepts/sft-data-pipeline.md — kanonik kural seti.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

SFT_REVIEW_BUFFER_DAYS = 7
SFT_EDIT_DISTANCE_THRESHOLD = Decimal("0.05")
SFT_ELIGIBLE_ACTIONS: frozenset[str] = frozenset({"copied", "posted"})
SFT_USER_ACTION_VALUES: frozenset[str] = frozenset(
    {"copied", "posted", "edited", "regenerated", "kept", "deleted"}
)


class _SftRecord(Protocol):
    """Generation veya Message — ortak alanlar."""

    status: str | None  # Message için None — assistant rolüne göre filtrelenir
    user_action: str | None
    edit_distance: Decimal | None
    halu_flagged_at: datetime | None
    created_at: datetime


class _UserConsent(Protocol):
    model_improvement_consent_at: datetime | None
    model_improvement_consent_revoked_at: datetime | None


def recompute_sft_eligibility(
    record: _SftRecord,
    user: _UserConsent,
    *,
    require_completed_status: bool = True,
) -> tuple[bool, str | None]:
    """SFT eligibility — 7 koşul.

    Returns: (eligible, excluded_reason)
        eligible=True ise excluded_reason=None.
        excluded_reason ∈ {
            'wrong_status', 'no_consent', 'consent_revoked',
            'wrong_action', 'edit_too_large', 'halu_flagged',
            'review_buffer'
        }

    Args:
        record: Generation veya Message (assistant) — Protocol uyumlu.
        user: User — consent kayıtları
        require_completed_status: Generation için True (status='completed' zorunlu).
            Message için False (role='assistant' önceden kontrol edilir).
    """
    if require_completed_status and record.status != "completed":
        return (False, "wrong_status")
    if user.model_improvement_consent_at is None:
        return (False, "no_consent")
    if user.model_improvement_consent_revoked_at is not None:
        return (False, "consent_revoked")
    if record.user_action not in SFT_ELIGIBLE_ACTIONS:
        return (False, "wrong_action")
    if record.edit_distance is not None and record.edit_distance >= SFT_EDIT_DISTANCE_THRESHOLD:
        return (False, "edit_too_large")
    if record.halu_flagged_at is not None:
        return (False, "halu_flagged")

    review_cutoff = datetime.now(UTC) - timedelta(days=SFT_REVIEW_BUFFER_DAYS)
    if record.created_at >= review_cutoff:
        return (False, "review_buffer")

    return (True, None)


__all__ = [
    "SFT_EDIT_DISTANCE_THRESHOLD",
    "SFT_ELIGIBLE_ACTIONS",
    "SFT_REVIEW_BUFFER_DAYS",
    "SFT_USER_ACTION_VALUES",
    "recompute_sft_eligibility",
]
