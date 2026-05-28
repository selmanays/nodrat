"""Module: billing.services

Billing domain service layer. Plan/Subscription tabanlı iş mantığı.

Public surface (lazy import — paket-init eager değil):
    plan_features — resolve_user_plan_features (tier → plan feature resolution)

T7-1 (2026-05-28): `core/plan_features.py` → buraya taşındı (billing domain
owns Plan + Subscription).
"""

__all__: list[str] = []
