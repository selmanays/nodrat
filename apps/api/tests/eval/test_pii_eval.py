"""PII redaction golden set eval (#43 seed, #45 ile genişler).

Bu test \"eval\" marker'lı değil — golden set küçük + provider çağrısı yok,
unit hızında çalışır. #45'te LLM-as-judge eklenince eval marker'ı eklenir.
"""

from __future__ import annotations

import pytest

from tests.eval.framework import (
    GOLDEN_SETS_DIR,
    assert_threshold,
    load_golden_set,
    run_redaction_eval,
)


def test_golden_set_files_exist():
    """En azından seed dosyası var."""
    assert (GOLDEN_SETS_DIR / "pii_redaction_seed.yaml").exists()


def test_load_golden_set_basic():
    gs = load_golden_set("pii_redaction_seed.yaml")
    assert gs.name == "pii_redaction_seed"
    assert gs.test_type == "redaction"
    assert len(gs.cases) >= 8


def test_pii_redaction_seed_meets_threshold():
    """Seed set %85+ pass rate. #45 ile %99 hedefi gelecek."""
    gs = load_golden_set("pii_redaction_seed.yaml")
    summary = run_redaction_eval(gs)

    assert summary.total >= 8
    # Detaylı failure raporu için custom assert
    assert_threshold(summary, min_pass_rate=0.85)


def test_assert_threshold_fails_below_min():
    """assert_threshold gerçekten fail eder mi?"""
    from tests.eval.framework import EvalResult, EvalSummary

    bad_summary = EvalSummary(
        total=10,
        passed=5,
        failed=5,
        results=[EvalResult(case_id=f"tc_{i}", passed=False) for i in range(5)],
    )
    with pytest.raises(AssertionError, match="Pass rate"):
        assert_threshold(bad_summary, min_pass_rate=0.99)


def test_assert_threshold_passes():
    from tests.eval.framework import EvalResult, EvalSummary

    good = EvalSummary(
        total=10,
        passed=10,
        failed=0,
        results=[EvalResult(case_id=f"tc_{i}", passed=True) for i in range(10)],
    )
    # No raise
    assert_threshold(good, min_pass_rate=0.99)


def test_eval_summary_pass_rate():
    from tests.eval.framework import EvalSummary

    s = EvalSummary(total=100, passed=87, failed=13)
    assert s.pass_rate == 0.87


def test_eval_summary_zero_total():
    from tests.eval.framework import EvalSummary

    s = EvalSummary(total=0, passed=0, failed=0)
    assert s.pass_rate == 0.0
