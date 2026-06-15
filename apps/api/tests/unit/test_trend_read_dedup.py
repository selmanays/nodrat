"""PR-2c (#1505) — scoring dedup + snapshot-read sözleşmesi (DB'siz).

admin_trends compute_* artık aggregation'dan import edilir (tek doğruluk kaynağı).
"""

from __future__ import annotations


def test_scoring_functions_deduped():
    """admin_trends.compute_* IS aggregation.compute_* (aynı obje → dedup)."""
    from app.api import admin_trends
    from app.modules.trends import aggregation

    assert admin_trends.compute_momentum is aggregation.compute_momentum
    assert admin_trends.compute_novelty is aggregation.compute_novelty
    assert admin_trends.compute_source_diversity is aggregation.compute_source_diversity
    assert admin_trends.compute_trend_state is aggregation.compute_trend_state


def test_faz1_imports_still_work():
    """Faz1 testleri admin_trends'ten import ediyor — re-import kırılmadı."""
    from app.api.admin_trends import (  # noqa: F401
        compute_momentum,
        compute_novelty,
        compute_source_diversity,
        compute_trend_state,
        resolve_window,
    )

    assert compute_momentum(10, 5) == 1.0
    assert resolve_window("6h", "24h") == "6h"


def test_response_source_default_entity():
    from app.api.admin_trends import TrendListResponse

    resp = TrendListResponse(
        enabled=True,
        window="24h",
        sort="score",
        limit=50,
        offset=0,
        total=0,
        data=[],
        generated_at="2026-06-15T00:00:00+00:00",
    )
    assert resp.source == "entity"  # #1520: entity tek okuma yolu
