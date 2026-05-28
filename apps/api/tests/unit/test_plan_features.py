"""Plan features resolver tests (#522).

Subscription yokken User.tier→plan_code fallback'in çalıştığını doğrular.
DB tarafı mock yerine in-memory SQLite + ORM ile gerçekçi test edilebilir,
ama bu birim test seviyesinde tier mapping ve fallback davranışını saf
fonksiyonel olarak doğrular.
"""

from __future__ import annotations

from app.modules.billing.services.plan_features import _FREE_DEFAULTS, _TIER_TO_PLAN_CODE


def test_tier_to_plan_code_mapping_complete() -> None:
    # User.tier seçenekleri: free | starter | pro | agency_seat (models/user.py:53)
    assert _TIER_TO_PLAN_CODE["free"] == "free"
    assert _TIER_TO_PLAN_CODE["starter"] == "starter"
    assert _TIER_TO_PLAN_CODE["pro"] == "pro"
    assert _TIER_TO_PLAN_CODE["agency_seat"] == "agency_3"


def test_free_defaults_disable_paid_features() -> None:
    # Plans seed yoksa hard-coded fallback Pro feature'ları açmamalı
    assert _FREE_DEFAULTS["style_profiles"] is False
    assert _FREE_DEFAULTS["style_profiles_slots"] == 0
    assert _FREE_DEFAULTS["visual_features"] is False
    assert _FREE_DEFAULTS["analysis_output"] is False
    assert _FREE_DEFAULTS["comparison_mode"] is False


def test_free_defaults_have_minimum_quota() -> None:
    # Free user yine de generate edebilmeli (DeepSeek allowed)
    assert "deepseek_v4_flash" in _FREE_DEFAULTS["allowed_models"]
    assert _FREE_DEFAULTS["concurrent_gen"] >= 1
    assert _FREE_DEFAULTS["rate_per_hour"] >= 1
