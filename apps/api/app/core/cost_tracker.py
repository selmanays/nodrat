"""Re-export shim — cost_tracker → shared/observability/cost_tracker (P4.1-B, v2).

P4.1 (Modular Monolith v2, #1092): cost tracking observability primitive
`app/shared/observability/cost_tracker.py`'ye taşındı (Layer 0 — pure telemetry).
Bu shim yalnız geriye dönük uyumluluk içindir; caller'lar P4.1-C/D'de
`app.shared.observability.cost_tracker`'a flip edilir, sonra bu dosya SİLİNİR.
"""

from app.shared.observability.cost_tracker import (  # noqa: F401
    CallTracker,
    estimate_cost_usd,
    track_provider_call,
)
