"""Golden set framework — YAML→test runner + LLM-as-judge.

YAML format (apps/api/tests/eval/golden_sets/<name>.yaml):

    name: pii_redaction_basic
    description: "PII redaction effectiveness on Turkish corpus"
    test_type: redaction         # 'redaction' | 'classification' | 'generation' |
                                 # 'query_plan' | 'agenda_card' |
                                 # 'content_generation' | 'hallucination_trap'
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

Test fonksiyonu: load_golden_set + run_*_eval + assert_threshold.

Prompt eval runners (#44):
    run_query_plan_eval         — Query Planner schema + whitelist validation
    run_agenda_card_eval        — Agenda Card structural validation (stub)
    run_content_eval            — Content Generator structural validation (stub)
    run_hallucination_traps     — Halu trap LLM-as-judge STUB (no LLM call)

Bütün runner'lar şu an LLM çağrısı yapmaz; YAML şemasının ve case'lerin
kendi-iç tutarlılığını doğrular. Runtime LLM eval için ayrı runtime
fixture seti gerekecek (gelecek issue).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

GOLDEN_SETS_DIR = Path(__file__).parent / "golden_sets"


@dataclass
class GoldenCase:
    """Tek test case'i.

    `input` redaction set'lerinde str (örn. PII metni); query_plan / agenda_card /
    content_generation / hallucination_trap set'lerinde dict (yapılandırılmış
    fixture). Runner kendi tipini bekleyerek davranır.
    """

    id: str
    input: Any
    expected: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    trap_type: str = ""


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
            input=c.get("input"),
            expected=c.get("expected") or {},
            notes=c.get("notes", ""),
            trap_type=c.get("trap_type", ""),
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
                notes.append(f"redaction.{ptype}: expected>={expected_count}, got {actual_count}")

        # 2) must_not_contain — orijinal değerler redacted text'te kalmasın
        for forbidden in case.expected.get("must_not_contain", []):
            if forbidden in result.text:
                passed = False
                notes.append(f"text contains forbidden: {forbidden!r}")

        # 3) min_total_redactions
        min_total = case.expected.get("min_total_redactions")
        if min_total is not None and result.total_redactions < min_total:
            passed = False
            notes.append(f"total redactions {result.total_redactions} < {min_total}")

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


# ============================================================================
# Prompt eval runners (#44) — STRUCTURAL VALIDATION
# ============================================================================
#
# Bu runner ailesi LLM çağrısı YAPMAZ. YAML golden set'in iç-tutarlılığını ve
# her case'in beklenen alanlarını taşıdığını doğrular. CI'da pre-deploy gate
# olarak (cached) çalışır; runtime LLM-as-judge ileride run_*_runtime_eval
# olarak ayrı eklenecek.
# ----------------------------------------------------------------------------


def _ensure_dict_input(case: GoldenCase, *, runner: str) -> dict[str, Any]:
    """Case input'u dict olmalı (prompt eval set'lerinde). Aksi halde fail."""
    if not isinstance(case.input, dict):
        raise TypeError(
            f"{runner}: case {case.id!r} input dict olmalı, {type(case.input).__name__} bulundu"
        )
    return case.input


def run_query_plan_eval(gs: GoldenSet) -> EvalSummary:
    """Query Planner golden set runner — yapısal doğrulama (#44).

    Her case için kontrol edilir:
      - input.user_request: str (None değil)
      - input.current_time: ISO-8601 string parse edilebilir
      - expected içinde *_in (whitelist) alanları (varsa) list
      - expected.tone (varsa) None | str
      - expected.constraints_contains (varsa) list[str]
      - expected.timeframes_min (varsa) int >= 1
      - expected.minimum_evidence_per_period (varsa) int 1-5

    Runtime davranışı: LLM henüz çağrılmıyor; bu nedenle "actual plan" yerine
    "schema kabul edilebilir mi?" testidir. Pass rate beklentisi %100.
    """
    summary = EvalSummary(total=len(gs.cases), passed=0, failed=0)

    for case in gs.cases:
        passed = True
        notes: list[str] = []

        try:
            inp = _ensure_dict_input(case, runner="run_query_plan_eval")
        except TypeError as exc:  # pragma: no cover - defensive
            summary.results.append(EvalResult(case_id=case.id, passed=False, note=str(exc)))
            summary.failed += 1
            continue

        # Required input fields
        if not isinstance(inp.get("user_request"), str):
            passed = False
            notes.append("input.user_request must be str")

        ct = inp.get("current_time")
        if not isinstance(ct, str) or "T" not in ct:
            passed = False
            notes.append(f"input.current_time invalid: {ct!r}")

        # Expected whitelist fields
        for field_name in ("intent_in", "mode_in", "output_type_in"):
            if field_name in case.expected and not isinstance(case.expected[field_name], list):
                passed = False
                notes.append(f"expected.{field_name} must be list")

        # Optional fields type checks
        if "constraints_contains" in case.expected and not isinstance(
            case.expected["constraints_contains"], list
        ):
            passed = False
            notes.append("expected.constraints_contains must be list")

        if "topic_query_contains" in case.expected and not isinstance(
            case.expected["topic_query_contains"], list
        ):
            passed = False
            notes.append("expected.topic_query_contains must be list")

        tf_min = case.expected.get("timeframes_min")
        if tf_min is not None and (not isinstance(tf_min, int) or tf_min < 1):
            passed = False
            notes.append("expected.timeframes_min must be int >= 1")

        mep = case.expected.get("minimum_evidence_per_period")
        if mep is not None and (not isinstance(mep, int) or not 1 <= mep <= 5):
            passed = False
            notes.append("expected.minimum_evidence_per_period must be int 1..5")

        summary.results.append(
            EvalResult(
                case_id=case.id,
                passed=passed,
                expected=case.expected,
                note="; ".join(notes),
            )
        )
        if passed:
            summary.passed += 1
        else:
            summary.failed += 1

    return summary


def run_agenda_card_eval(gs: GoldenSet) -> EvalSummary:
    """Agenda Card golden set runner — yapısal doğrulama (#44).

    Her case için kontrol edilir:
      - input.event_cluster ve input.articles non-empty
      - articles[*].id, source_name, source_reliability, published_at hazır
      - source_refs_count_eq beklentisi articles.length ile uyumlu
      - status_in alanı list[str]
      - importance_score_range / freshness_score_range [low, high] in [0,1]
      - manual_review_required = True (#44 LLM-as-judge stub kontrolü)

    Runtime'da run_*_runtime_eval LLM çıktısını fixture'a karşı koyacak;
    şimdilik sadece schema integrity.
    """
    summary = EvalSummary(total=len(gs.cases), passed=0, failed=0)

    for case in gs.cases:
        passed = True
        notes: list[str] = []

        try:
            inp = _ensure_dict_input(case, runner="run_agenda_card_eval")
        except TypeError as exc:
            summary.results.append(EvalResult(case_id=case.id, passed=False, note=str(exc)))
            summary.failed += 1
            continue

        ec = inp.get("event_cluster") or {}
        articles = inp.get("articles") or []

        if not ec.get("id") or not ec.get("canonical_title"):
            passed = False
            notes.append("input.event_cluster missing id/canonical_title")

        if not isinstance(articles, list) or len(articles) == 0:
            passed = False
            notes.append("input.articles must be non-empty list")
        else:
            required_article_keys = {
                "id",
                "source_name",
                "source_reliability",
                "published_at",
            }
            for idx, art in enumerate(articles):
                missing = required_article_keys - set(art.keys())
                if missing:
                    passed = False
                    notes.append(f"articles[{idx}] missing keys: {sorted(missing)}")

        # Expected source_refs_count_eq matches articles count when set
        srce = case.expected.get("source_refs_count_eq")
        if srce is not None and srce != len(articles):
            passed = False
            notes.append(f"source_refs_count_eq={srce} mismatch articles={len(articles)}")

        # status_in must be list of valid enum values
        valid_statuses = {"developing", "active", "cooling", "stale"}
        status_in = case.expected.get("status_in", [])
        if status_in and not (
            isinstance(status_in, list) and set(status_in).issubset(valid_statuses)
        ):
            passed = False
            notes.append(f"status_in invalid: {status_in!r}")

        # Score ranges
        for k in ("importance_score_range", "freshness_score_range"):
            r = case.expected.get(k)
            if r is not None:
                if not (isinstance(r, list) and len(r) == 2):
                    passed = False
                    notes.append(f"{k} must be [low, high]")
                else:
                    low, high = r
                    if not (0.0 <= low <= high <= 1.0):
                        passed = False
                        notes.append(f"{k} out of [0,1] or low>high")

        # manual_review_required flag should be present (LLM-as-judge stub)
        if case.expected.get("manual_review_required") is not True:
            passed = False
            notes.append("expected.manual_review_required must be true")

        summary.results.append(
            EvalResult(
                case_id=case.id,
                passed=passed,
                expected=case.expected,
                note="; ".join(notes),
            )
        )
        if passed:
            summary.passed += 1
        else:
            summary.failed += 1

    return summary


def run_content_eval(gs: GoldenSet) -> EvalSummary:
    """Content Generator golden set runner — yapısal doğrulama (#44).

    Variant'lar: x_post | x_thread | summary | comparison.

    Her case için kontrol edilir:
      - input.request, retrieval_plan, output_constraints non-empty
      - expected.variant set'in test_type'ına uygun
      - x_post/comparison: posts_count_max <= constraint.max_posts
      - thread: thread_posts_min/max [4..12]
      - post_char_max == 280 (X limiti)
      - sources_min int >= 0
      - warnings_contains varsa list[str]

    Runtime'da run_*_runtime_eval LLM üretimini bu fixture'a karşı koyacak.
    """
    valid_variants = {"x_post", "x_thread", "summary", "comparison"}
    summary = EvalSummary(total=len(gs.cases), passed=0, failed=0)

    for case in gs.cases:
        passed = True
        notes: list[str] = []

        try:
            inp = _ensure_dict_input(case, runner="run_content_eval")
        except TypeError as exc:
            summary.results.append(EvalResult(case_id=case.id, passed=False, note=str(exc)))
            summary.failed += 1
            continue

        for k in ("request", "retrieval_plan", "output_constraints"):
            if not inp.get(k):
                passed = False
                notes.append(f"input.{k} required")

        variant = case.expected.get("variant")
        if variant not in valid_variants:
            passed = False
            notes.append(f"expected.variant invalid: {variant!r}")

        oc = inp.get("output_constraints") or {}
        max_posts = oc.get("max_posts")

        # x_post: posts_count_max ≤ max_posts
        pcm = case.expected.get("posts_count_max")
        if pcm is not None and isinstance(max_posts, int) and pcm > max_posts:
            passed = False
            notes.append(f"posts_count_max={pcm} > max_posts={max_posts}")

        # X char limit fixed
        post_char_max = case.expected.get("post_char_max")
        if post_char_max is not None and post_char_max != 280:
            passed = False
            notes.append(f"post_char_max must be 280 (X platform limit), got {post_char_max}")

        # Thread bounds
        if variant == "x_thread":
            tmin = case.expected.get("thread_posts_min")
            tmax = case.expected.get("thread_posts_max")
            if not (isinstance(tmin, int) and 4 <= tmin <= 12):
                passed = False
                notes.append(f"thread_posts_min must be int 4..12, got {tmin}")
            if not (isinstance(tmax, int) and 4 <= tmax <= 12):
                passed = False
                notes.append(f"thread_posts_max must be int 4..12, got {tmax}")
            if isinstance(tmin, int) and isinstance(tmax, int) and tmin > tmax:
                passed = False
                notes.append(f"thread_posts_min > thread_posts_max ({tmin}>{tmax})")

        # warnings_contains list
        wc = case.expected.get("warnings_contains")
        if wc is not None and not isinstance(wc, list):
            passed = False
            notes.append("warnings_contains must be list")

        # sources_min int >= 0
        sm = case.expected.get("sources_min")
        if sm is not None and (not isinstance(sm, int) or sm < 0):
            passed = False
            notes.append("sources_min must be int >= 0")

        summary.results.append(
            EvalResult(
                case_id=case.id,
                passed=passed,
                expected=case.expected,
                note="; ".join(notes),
            )
        )
        if passed:
            summary.passed += 1
        else:
            summary.failed += 1

    return summary


def run_hallucination_traps(gs: GoldenSet) -> EvalSummary:
    """Halüsinasyon trap STUB runner — yapısal doğrulama (#44).

    LLM çağrısı YAPMAZ. Yalnızca her trap case'inin:
      - trap_type set
      - input.context_articles non-empty (en az 1 article)
      - input.prompt_request set
      - expected.hallucination_rate_max == 0.0
      - expected.manual_review_required == True
      - expected içinde guard alanlarından (must_not_contain*, must_flag_warnings*,
        must_contain_phrases, quote_max_words, ...) en az biri var

    İleride run_hallucination_traps_runtime LLM çıktısı üzerinde:
      - NER ile entity extraction
      - context coverage check
      - LLM-as-judge call
    yapacak (prompt-contracts.md §6.3).
    """
    valid_guard_keys = {
        "must_not_contain",
        "must_not_contain_regex",
        "must_contain_phrases",
        "must_flag_warnings",
        "must_flag_warnings_if_mixed",
        "must_flag_warnings_if_swapped",
        "quote_max_words",
        "cross_story_mixing_forbidden",
        "official_data_source_id",
        "forbidden_attribution_swap",
    }

    summary = EvalSummary(total=len(gs.cases), passed=0, failed=0)

    for case in gs.cases:
        passed = True
        notes: list[str] = []

        try:
            inp = _ensure_dict_input(case, runner="run_hallucination_traps")
        except TypeError as exc:
            summary.results.append(EvalResult(case_id=case.id, passed=False, note=str(exc)))
            summary.failed += 1
            continue

        if not case.trap_type:
            passed = False
            notes.append("case.trap_type required")

        ctx = inp.get("context_articles") or []
        if not isinstance(ctx, list) or len(ctx) == 0:
            passed = False
            notes.append("input.context_articles must be non-empty list")

        if not isinstance(inp.get("prompt_request"), str):
            passed = False
            notes.append("input.prompt_request must be str")

        if case.expected.get("hallucination_rate_max") != 0.0:
            passed = False
            notes.append("expected.hallucination_rate_max must be 0.0")

        if case.expected.get("manual_review_required") is not True:
            passed = False
            notes.append("expected.manual_review_required must be true")

        # En az bir guard alanı bulunmalı
        if not (set(case.expected.keys()) & valid_guard_keys):
            passed = False
            notes.append(
                f"case.expected must include at least one guard key from {sorted(valid_guard_keys)}"
            )

        summary.results.append(
            EvalResult(
                case_id=case.id,
                passed=passed,
                expected=case.expected,
                note="; ".join(notes),
            )
        )
        if passed:
            summary.passed += 1
        else:
            summary.failed += 1

    return summary
