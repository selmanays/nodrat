"""Golden set framework — YAML→test runner + LLM-as-judge.

YAML format (apps/api/tests/eval/golden_sets/<name>.yaml):

    name: pii_redaction_basic
    description: "PII redaction effectiveness on Turkish corpus"
    test_type: redaction         # 'redaction' | 'classification' | 'generation'
    cases:
      - id: tc_001
        input: "Ali Veli'nin TC kimlik no 12345678901."
        expected:
          redactions:
            tc: 1
          must_not_contain: ["12345678901"]
      - id: tc_002
        input: "..."
        expected: ...

Test fonksiyonu: load_golden_set + run_redaction_eval + assert_threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


GOLDEN_SETS_DIR = Path(__file__).parent / "golden_sets"


@dataclass
class GoldenCase:
    """Tek test case'i."""

    id: str
    input: str
    expected: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class GoldenSet:
    """YAML'den yüklenmiş golden set."""

    name: str
    description: str = ""
    test_type: str = "redaction"
    cases: list[GoldenCase] = field(default_factory=list)


@dataclass
class EvalResult:
    """Tek case sonucu."""

    case_id: str
    passed: bool
    actual: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass
class EvalSummary:
    """Tüm set için özet."""

    total: int
    passed: int
    failed: int
    results: list[EvalResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def load_golden_set(file_name: str) -> GoldenSet:
    """golden_sets/<file_name> YAML'den GoldenSet yükle.

    Raises FileNotFoundError if file missing, yaml.YAMLError on parse error.
    """
    path = GOLDEN_SETS_DIR / file_name
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cases = [
        GoldenCase(
            id=c["id"],
            input=c["input"],
            expected=c.get("expected") or {},
            notes=c.get("notes", ""),
        )
        for c in raw.get("cases", [])
    ]
    return GoldenSet(
        name=raw.get("name", path.stem),
        description=raw.get("description", ""),
        test_type=raw.get("test_type", "redaction"),
        cases=cases,
    )


# ============================================================================
# Runners
# ============================================================================


def run_redaction_eval(gs: GoldenSet) -> EvalSummary:
    """PII redaction golden set runner.

    Her case için:
      - app.core.pii.redact(input) çağrılır
      - expected.redactions ile actual.counts karşılaştırılır
      - expected.must_not_contain pattern'leri redacted text'te aranmaz
    """
    from app.core.pii import redact

    summary = EvalSummary(total=len(gs.cases), passed=0, failed=0)

    for case in gs.cases:
        result = redact(case.input)
        actual = {
            "redactions": dict(result.counts),
            "redacted_text": result.text,
        }

        passed = True
        notes: list[str] = []

        # 1) Redactions dict — beklenen tip ve sayı
        expected_red = case.expected.get("redactions", {})
        for ptype, expected_count in expected_red.items():
            actual_count = result.counts.get(ptype, 0)
            if actual_count < expected_count:
                passed = False
                notes.append(
                    f"redaction.{ptype}: expected>={expected_count}, got {actual_count}"
                )

        # 2) must_not_contain — orijinal değerler redacted text'te kalmasın
        for forbidden in case.expected.get("must_not_contain", []):
            if forbidden in result.text:
                passed = False
                notes.append(f"text contains forbidden: {forbidden!r}")

        # 3) min_total_redactions
        min_total = case.expected.get("min_total_redactions")
        if min_total is not None and result.total_redactions < min_total:
            passed = False
            notes.append(
                f"total redactions {result.total_redactions} < {min_total}"
            )

        summary.results.append(
            EvalResult(
                case_id=case.id,
                passed=passed,
                actual=actual,
                expected=case.expected,
                note="; ".join(notes),
            )
        )
        if passed:
            summary.passed += 1
        else:
            summary.failed += 1

    return summary


def assert_threshold(summary: EvalSummary, *, min_pass_rate: float) -> None:
    """Eval pass rate threshold check — pytest assertion içinde kullanılır."""
    pass_rate = summary.pass_rate
    if pass_rate < min_pass_rate:
        failures = [r for r in summary.results if not r.passed]
        msg_lines = [
            f"Pass rate {pass_rate:.2%} < required {min_pass_rate:.2%}",
            f"Failed: {summary.failed}/{summary.total}",
            "",
            "Failures (first 5):",
        ]
        for r in failures[:5]:
            msg_lines.append(f"  - {r.case_id}: {r.note}")
        raise AssertionError("\n".join(msg_lines))
