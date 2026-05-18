"""Prompt eval golden set integrity (#44).

3 prompt + 1 hallucination trap golden set'inin yüklenebilir, gerekli
sayıda case içerdiği ve yapısal validasyonu geçtiği ucu çıplak doğrulamalar.

Bu testler 'eval' marker'lı DEĞİL — LLM çağrısı yok, sadece YAML şemasının
ve runner'ların kendi-iç tutarlılığını test eder. CI'da unit testlerle koşar.

Runtime LLM eval (cached responses + actual provider) ileride ayrı bir
test_prompt_runtime_eval.py altında eklenecek; o test 'eval' marker'lı
olacak ve gerçek halu/citation eşiklerini zorlayacak.
"""

from __future__ import annotations

from tests.eval.framework import (
    GOLDEN_SETS_DIR,
    GoldenCase,
    assert_threshold,
    load_golden_set,
    run_agenda_card_eval,
    run_content_eval,
    run_hallucination_traps,
    run_query_plan_eval,
)

# ============================================================================
# 1) File presence
# ============================================================================


def test_query_planner_yaml_exists():
    assert (GOLDEN_SETS_DIR / "query_planner_golden.yaml").exists()


def test_agenda_card_yaml_exists():
    assert (GOLDEN_SETS_DIR / "agenda_card_golden.yaml").exists()


def test_content_generator_yaml_exists():
    assert (GOLDEN_SETS_DIR / "content_generator_golden.yaml").exists()


def test_hallucination_traps_yaml_exists():
    assert (GOLDEN_SETS_DIR / "hallucination_traps.yaml").exists()


# ============================================================================
# 2) Set sizes — issue #44 acceptance
# ============================================================================


def test_query_planner_set_size_at_least_20():
    gs = load_golden_set("query_planner_golden.yaml")
    assert gs.test_type == "query_plan"
    assert len(gs.cases) >= 20, f"Query Planner ≥20 case bekleniyor, mevcut: {len(gs.cases)}"


def test_agenda_card_set_size_at_least_10():
    gs = load_golden_set("agenda_card_golden.yaml")
    assert gs.test_type == "agenda_card"
    assert len(gs.cases) >= 10, f"Agenda Card ≥10 case bekleniyor, mevcut: {len(gs.cases)}"


def test_content_generator_set_size_at_least_20():
    gs = load_golden_set("content_generator_golden.yaml")
    assert gs.test_type == "content_generation"
    assert len(gs.cases) >= 20, f"Content Generator ≥20 case bekleniyor, mevcut: {len(gs.cases)}"


def test_hallucination_traps_set_size_at_least_10():
    gs = load_golden_set("hallucination_traps.yaml")
    assert gs.test_type == "hallucination_trap"
    assert len(gs.cases) >= 10, f"Halu trap ≥10 case bekleniyor, mevcut: {len(gs.cases)}"


def test_total_eval_cases_at_least_60():
    """#44 acceptance: 20+10+20+10 = 60 örnek minimum."""
    qp = load_golden_set("query_planner_golden.yaml")
    ac = load_golden_set("agenda_card_golden.yaml")
    cg = load_golden_set("content_generator_golden.yaml")
    ht = load_golden_set("hallucination_traps.yaml")
    total = len(qp.cases) + len(ac.cases) + len(cg.cases) + len(ht.cases)
    assert total >= 60, f"Toplam eval case ≥60 bekleniyor (20+10+20+10), mevcut: {total}"


# ============================================================================
# 3) Schema integrity per set — runner validation
# ============================================================================


def test_query_planner_schema_validation_100_percent():
    """Query Planner YAML şeması %100 valide."""
    gs = load_golden_set("query_planner_golden.yaml")
    summary = run_query_plan_eval(gs)
    assert summary.total == len(gs.cases)
    # Schema integrity zorunlu — her case geçmeli
    assert_threshold(summary, min_pass_rate=1.0)


def test_agenda_card_schema_validation_100_percent():
    """Agenda Card YAML şeması %100 valide."""
    gs = load_golden_set("agenda_card_golden.yaml")
    summary = run_agenda_card_eval(gs)
    assert summary.total == len(gs.cases)
    assert_threshold(summary, min_pass_rate=1.0)


def test_content_generator_schema_validation_100_percent():
    """Content Generator YAML şeması %100 valide."""
    gs = load_golden_set("content_generator_golden.yaml")
    summary = run_content_eval(gs)
    assert summary.total == len(gs.cases)
    assert_threshold(summary, min_pass_rate=1.0)


def test_hallucination_traps_schema_validation_100_percent():
    """Halu trap YAML şeması %100 valide (her case guard taşıyor)."""
    gs = load_golden_set("hallucination_traps.yaml")
    summary = run_hallucination_traps(gs)
    assert summary.total == len(gs.cases)
    assert_threshold(summary, min_pass_rate=1.0)


# ============================================================================
# 4) Per-case structural smoke checks
# ============================================================================


def test_query_planner_every_case_has_user_request_and_current_time():
    gs = load_golden_set("query_planner_golden.yaml")
    for c in gs.cases:
        assert isinstance(c.input, dict), f"{c.id}: input dict olmalı"
        assert "user_request" in c.input, f"{c.id}: user_request eksik"
        assert "current_time" in c.input, f"{c.id}: current_time eksik"
        assert "T" in c.input["current_time"], f"{c.id}: current_time ISO-8601 formatında olmalı"


def test_agenda_card_every_case_has_articles():
    gs = load_golden_set("agenda_card_golden.yaml")
    for c in gs.cases:
        assert isinstance(c.input, dict), f"{c.id}: input dict olmalı"
        articles = c.input.get("articles", [])
        assert len(articles) >= 1, f"{c.id}: en az 1 article gerekli"
        # Hallucination max 0 — kaynaktan dışarı çıkma yok
        assert c.expected.get("hallucination_rate_max") == 0.0, (
            f"{c.id}: hallucination_rate_max=0.0 zorunlu"
        )


def test_content_generator_every_case_has_variant():
    gs = load_golden_set("content_generator_golden.yaml")
    valid = {"x_post", "x_thread", "summary", "comparison"}
    for c in gs.cases:
        assert c.expected.get("variant") in valid, (
            f"{c.id}: variant {c.expected.get('variant')!r} geçerli değil"
        )


def test_content_generator_thread_bounds_4_to_12():
    """Thread variant'larda post sayısı 4-12 arasında olmalı (#44 spec)."""
    gs = load_golden_set("content_generator_golden.yaml")
    threads = [c for c in gs.cases if c.expected.get("variant") == "x_thread"]
    assert len(threads) >= 1, "En az 1 thread case bekleniyor"
    for c in threads:
        tmin = c.expected.get("thread_posts_min")
        tmax = c.expected.get("thread_posts_max")
        assert 4 <= tmin <= tmax <= 12, f"{c.id}: thread_posts_min={tmin}, max={tmax} 4..12 dışı"


def test_hallucination_traps_every_case_has_trap_type_and_zero_halu():
    gs = load_golden_set("hallucination_traps.yaml")
    seen_trap_types: set[str] = set()
    for c in gs.cases:
        assert c.trap_type, f"{c.id}: trap_type alanı zorunlu"
        seen_trap_types.add(c.trap_type)
        assert c.expected.get("hallucination_rate_max") == 0.0, (
            f"{c.id}: hallucination_rate_max=0.0 zorunlu"
        )
        assert c.expected.get("manual_review_required") is True, (
            f"{c.id}: manual_review_required=true zorunlu (LLM-as-judge stub)"
        )
    # En az 8 farklı trap kategorisi (issue #44 listesi 10 — varyans bekleniyor)
    assert len(seen_trap_types) >= 8, (
        f"En az 8 farklı trap_type bekleniyor, mevcut: {len(seen_trap_types)}"
    )


# ============================================================================
# 5) Runner negative-path smoke
# ============================================================================


def test_run_query_plan_eval_rejects_str_input():
    """Yanlış set'i (str input) bu runner'a verirsek, runner her case'i fail eder."""
    from tests.eval.framework import GoldenSet

    bad = GoldenSet(
        name="bad",
        test_type="query_plan",
        cases=[GoldenCase(id="x_001", input="this is a string not a dict")],
    )
    summary = run_query_plan_eval(bad)
    assert summary.total == 1
    assert summary.failed == 1


def test_run_agenda_card_eval_rejects_empty_articles():
    from tests.eval.framework import GoldenSet

    bad = GoldenSet(
        name="bad_ac",
        test_type="agenda_card",
        cases=[
            GoldenCase(
                id="ac_x",
                input={"event_cluster": {"id": "x", "canonical_title": "t"}, "articles": []},
                expected={"manual_review_required": True},
            )
        ],
    )
    summary = run_agenda_card_eval(bad)
    assert summary.failed == 1


def test_run_content_eval_rejects_invalid_variant():
    from tests.eval.framework import GoldenSet

    bad = GoldenSet(
        name="bad_cg",
        test_type="content_generation",
        cases=[
            GoldenCase(
                id="cg_x",
                input={
                    "request": "x",
                    "retrieval_plan": {"intent": "x"},
                    "output_constraints": {"max_posts": 1},
                },
                expected={"variant": "podcast"},  # invalid
            )
        ],
    )
    summary = run_content_eval(bad)
    assert summary.failed == 1


def test_run_hallucination_traps_rejects_nonzero_halu_max():
    from tests.eval.framework import GoldenSet

    bad = GoldenSet(
        name="bad_ht",
        test_type="hallucination_trap",
        cases=[
            GoldenCase(
                id="ht_x",
                input={
                    "context_articles": [{"id": "a1"}],
                    "prompt_request": "x",
                },
                expected={
                    "hallucination_rate_max": 0.05,  # invalid (must be 0.0)
                    "manual_review_required": True,
                    "must_not_contain": ["x"],
                },
                trap_type="t",
            )
        ],
    )
    summary = run_hallucination_traps(bad)
    assert summary.failed == 1


# ============================================================================
# 6) Description / metadata sanity
# ============================================================================


def test_query_planner_description_non_empty():
    gs = load_golden_set("query_planner_golden.yaml")
    assert gs.description, "Description boş olamaz"
    assert "query planner" in gs.description.lower() or "query plan" in gs.description.lower()


def test_hallucination_traps_description_mentions_traps():
    gs = load_golden_set("hallucination_traps.yaml")
    assert gs.description, "Description boş olamaz"
    assert "trap" in gs.description.lower() or "halü" in gs.description.lower()
