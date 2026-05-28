"""Module: sources.services

Sources domain service layer. Source polling tier hesabı + (gelecekte)
diğer sources iş mantığı.

Public surface (lazy import — paket-init eager değil):
    polling_tier — compute_tier (adaptive polling tier #578)

T7-3 (2026-05-28): `core/polling_tier.py` → buraya taşındı (sources domain
owns Source).
"""

__all__: list[str] = []
