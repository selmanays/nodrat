"""Unit — #1767 canonical-reconcile beat task çekirdeği (`_reconcile_plan_and_apply`).

dry-run-önce + flag-gate + auto-apply cap orkestrasyonu. `reconcile_canonical_anchors`
mock'lanır (DB yok) → saf karar mantığı doğrulanır:
  flag OFF        → dry_run (yalnız gözlem, apply ÇAĞRILMAZ)
  flag ON + iş    → applied (dry-run + apply, 2 çağrı)
  flag ON + cap   → skipped_cap (merge>cap → apply ÇAĞRILMAZ, manuel)
  flag ON + iş-yok→ noop
  flag ON + yalnız backfill → applied (backfill cap'siz, additive)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

# task modülü celery_app + app zincirini çeker — local'de eksikse SKIP, CI PASS.
pytest.importorskip("celery")
import app.modules.generations.tasks.cluster_assigner as ca


def _plan(*, drift=0, merge=0, backfill=0):
    return {
        "dry_run": True,
        "drift_groups": drift,
        "merge_count": merge,
        "backfill_count": backfill,
    }


@pytest.mark.asyncio
async def test_flag_off_dry_run_only(monkeypatch):
    rec = AsyncMock(return_value=_plan(drift=2, merge=2))
    monkeypatch.setattr(ca, "reconcile_canonical_anchors", rec)

    out = await ca._reconcile_plan_and_apply(AsyncMock(), apply_enabled=False)

    assert out["status"] == "dry_run"
    rec.assert_awaited_once()  # yalnız dry-run, mutasyon YOK
    assert rec.await_args.kwargs["dry_run"] is True


@pytest.mark.asyncio
async def test_flag_on_applies_within_cap(monkeypatch):
    rec = AsyncMock(
        side_effect=[_plan(drift=3, merge=3, backfill=1), {"merge_count": 3, "backfill_count": 1}]
    )
    monkeypatch.setattr(ca, "reconcile_canonical_anchors", rec)

    out = await ca._reconcile_plan_and_apply(AsyncMock(), apply_enabled=True)

    assert out["status"] == "applied"
    assert rec.await_count == 2  # dry-run + apply
    assert rec.await_args_list[1].kwargs["dry_run"] is False


@pytest.mark.asyncio
async def test_flag_on_cap_exceeded_skips(monkeypatch):
    rec = AsyncMock(return_value=_plan(drift=99, merge=50))
    monkeypatch.setattr(ca, "reconcile_canonical_anchors", rec)

    out = await ca._reconcile_plan_and_apply(AsyncMock(), apply_enabled=True, max_auto_merge=20)

    assert out["status"] == "skipped_cap"
    rec.assert_awaited_once()  # apply ÇAĞRILMAZ (runaway-merge koruması)


@pytest.mark.asyncio
async def test_flag_on_no_work_noop(monkeypatch):
    rec = AsyncMock(return_value=_plan(drift=0, merge=0, backfill=0))
    monkeypatch.setattr(ca, "reconcile_canonical_anchors", rec)

    out = await ca._reconcile_plan_and_apply(AsyncMock(), apply_enabled=True)

    assert out["status"] == "noop"
    rec.assert_awaited_once()


@pytest.mark.asyncio
async def test_flag_on_backfill_only_applies(monkeypatch):
    # merge=0 ama backfill>0 → apply (backfill additive/risksiz, cap uygulanmaz)
    rec = AsyncMock(
        side_effect=[_plan(merge=0, backfill=5), {"merge_count": 0, "backfill_count": 5}]
    )
    monkeypatch.setattr(ca, "reconcile_canonical_anchors", rec)

    out = await ca._reconcile_plan_and_apply(AsyncMock(), apply_enabled=True)

    assert out["status"] == "applied"
    assert rec.await_count == 2
