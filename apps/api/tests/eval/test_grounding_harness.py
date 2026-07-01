"""Grounding harness testleri (#1805).

İki katman:

  1. CI deterministik (marker YOK, LLM YOK) — harness motorunun mantığını
     kanıtlar: cümle-fallback, oy toplama (#1076 edge-case'leri), skorlama,
     mock-judge uçtan-uca, calibration YAML bütünlüğü. CI api-eval job'unda
     ``-m "eval or not integration"`` ile seçilir (integration DEĞİL).

  2. Opt-in eval (``@pytest.mark.eval``, provider gerektirir) — gerçek LLM ile
     self-calibration gate: false_positive_control sınıfında FP oranı v1'in
     0.50'sinden düşük, reconstruction sınıfı yakalanır. İKİ katman guard
     (``NODRAT_GROUNDING_EVAL=1`` + ``DEEPSEEK_API_KEY``) → CI'da deterministik
     skip, scheduled/manuel koşumda çalışır.
"""

from __future__ import annotations

import os

import pytest

from tests.eval.framework import load_golden_set
from tests.eval.grounding_harness import (
    FABRICATED,
    INFERRED,
    MANUAL_REVIEW_CONFIDENCE,
    SUPPORTED,
    Claim,
    ClaimVerdict,
    GroundingReport,
    aggregate_votes,
    default_provider_and_model,
    format_context,
    run_grounding_report,
    run_llm_grounding_report,
    split_sentences_fallback,
)

CALIBRATION_SET = "grounding_calibration.yaml"


# ===========================================================================
# 1) Saf çekirdek — split fallback
# ===========================================================================


def test_split_sentences_fallback_splits_bullets_and_sentences():
    text = "- Merkez Bankası faizi sabit tuttu [1]. Enflasyon açıklandı [2].\n- Meclis toplandı."
    claims = split_sentences_fallback(text)
    assert len(claims) == 3
    # Atıf token'ları temizlenmeli
    assert all("[" not in c for c in claims)
    assert "Merkez Bankası faizi sabit tuttu" in claims[0]


def test_split_sentences_fallback_drops_empty_and_tiny():
    assert split_sentences_fallback("\n\n-  \n.\n") == []


def test_format_context_tolerates_schemas():
    articles = [
        {
            "title": "A",
            "source_name": "AA",
            "published_at": "2026-06-30",
            "clean_text_excerpt": "gövde-1",
        },
        {"article_title": "B", "source_slug": "bbc", "chunk_text": "gövde-2"},
    ]
    ctx = format_context(articles)
    assert "gövde-1" in ctx and "gövde-2" in ctx
    assert "AA" in ctx and "bbc" in ctx
    assert "---" in ctx  # blok ayracı


# ===========================================================================
# 2) aggregate_votes — #1076 dersinin çekirdeği
# ===========================================================================


def test_aggregate_unanimous_supported():
    label, conf = aggregate_votes([SUPPORTED, SUPPORTED, SUPPORTED])
    assert label == SUPPORTED
    assert conf == pytest.approx(1.0)


def test_aggregate_unanimous_fabricated():
    label, conf = aggregate_votes([FABRICATED, FABRICATED, FABRICATED])
    assert label == FABRICATED
    assert conf == pytest.approx(1.0)


def test_aggregate_majority_supported_keeps_confidence_at_two_thirds():
    # 2 SUPPORTED + 1 FABRICATED → SUPPORTED, conf 0.67 (needs_review sınırı üstü)
    label, conf = aggregate_votes([SUPPORTED, SUPPORTED, FABRICATED])
    assert label == SUPPORTED
    assert conf == pytest.approx(2 / 3)


def test_aggregate_three_way_tie_falls_to_inferred_not_fabricated():
    # #1076 KRİTİK: tam bölünmede FABRICATED'a ZORLAMA yok → nötr orta.
    label, conf = aggregate_votes([SUPPORTED, INFERRED, FABRICATED])
    assert label == INFERRED
    assert conf < MANUAL_REVIEW_CONFIDENCE  # düşük mutabakat → insan-review


def test_aggregate_supported_fabricated_tie_falls_to_inferred():
    # Beraberlik (1-1) → FABRICATED'a düşmez, INFERRED'a düşer.
    label, _ = aggregate_votes([SUPPORTED, FABRICATED])
    assert label == INFERRED


def test_aggregate_empty_or_invalid_votes_is_inferred_zero_conf():
    label, conf = aggregate_votes(["garbage", ""])
    assert label == INFERRED
    assert conf == 0.0


# ===========================================================================
# 3) GroundingReport skorlama + ClaimVerdict.needs_review
# ===========================================================================


def _verdict(label: str, confidence: float, idx: int = 0) -> ClaimVerdict:
    return ClaimVerdict(claim=Claim(text=f"c{idx}", index=idx), label=label, confidence=confidence)


def test_report_rates_and_faithfulness():
    report = GroundingReport(
        answer="x",
        verdicts=[
            _verdict(SUPPORTED, 1.0, 0),
            _verdict(SUPPORTED, 1.0, 1),
            _verdict(INFERRED, 1.0, 2),
            _verdict(FABRICATED, 1.0, 3),
        ],
    )
    assert report.total == 4
    assert report.grounding_rate == pytest.approx(0.5)
    assert report.inferred_rate == pytest.approx(0.25)
    assert report.hallucination_rate == pytest.approx(0.25)
    assert report.faithfulness == pytest.approx(0.75)
    assert report.manual_review is True  # FABRICATED var
    assert len(report.unsupported) == 1


def test_report_low_confidence_triggers_review_without_fabrication():
    report = GroundingReport(answer="x", verdicts=[_verdict(SUPPORTED, 0.5, 0)])
    assert report.hallucination_rate == 0.0
    assert report.manual_review is True  # düşük güven → review
    assert report.unsupported[0].label == SUPPORTED


def test_report_clean_answer_no_review():
    report = GroundingReport(
        answer="x", verdicts=[_verdict(SUPPORTED, 1.0, 0), _verdict(INFERRED, 1.0, 1)]
    )
    assert report.manual_review is False
    assert report.unsupported == []
    assert report.faithfulness == 1.0


def test_empty_report_safe_defaults():
    report = GroundingReport(answer="", verdicts=[])
    assert report.grounding_rate == 0.0
    assert report.hallucination_rate == 0.0
    assert report.faithfulness == 1.0
    assert report.manual_review is False


# ===========================================================================
# 4) run_grounding_report — mock judge ile uçtan uca (LLM'siz)
# ===========================================================================

_ARTICLES = [{"title": "t", "source_name": "AA", "clean_text_excerpt": "kaynak gövdesi"}]


def test_run_report_all_supported_is_clean():
    report = run_grounding_report(
        "İlk iddia. İkinci iddia.",
        _ARTICLES,
        splitter=split_sentences_fallback,
        judge=lambda *_: SUPPORTED,
    )
    assert report.total == 2
    assert report.hallucination_rate == 0.0
    assert report.grounding_rate == 1.0
    assert report.manual_review is False


def test_run_report_all_fabricated_flags_everything():
    report = run_grounding_report(
        "Uydurma bir. Uydurma iki.",
        _ARTICLES,
        splitter=split_sentences_fallback,
        judge=lambda *_: FABRICATED,
    )
    assert report.hallucination_rate == 1.0
    assert report.manual_review is True
    assert len(report.unsupported) == report.total


def test_run_report_uses_injected_splitter():
    calls: list[str] = []

    def splitter(answer: str) -> list[str]:
        calls.append(answer)
        return ["tek iddia"]

    report = run_grounding_report(
        "herhangi", _ARTICLES, splitter=splitter, judge=lambda *_: INFERRED
    )
    assert calls == ["herhangi"]
    assert report.total == 1
    assert report.verdicts[0].label == INFERRED


# ===========================================================================
# 5) Calibration YAML bütünlüğü (LLM'siz — CI'da koşar)
# ===========================================================================


def test_calibration_set_loads_and_has_both_classes():
    gs = load_golden_set(CALIBRATION_SET)
    assert gs.test_type == "grounding_calibration"
    classes = {c.expected.get("class") for c in gs.cases}
    assert classes == {"false_positive_control", "reconstruction"}


def test_calibration_has_all_four_v1_false_positive_classes():
    """#1076'nın 4 yanlış-pozitif sınıfı negatif-kontrol olarak mevcut."""
    gs = load_golden_set(CALIBRATION_SET)
    trap_types = {
        c.trap_type for c in gs.cases if c.expected.get("class") == "false_positive_control"
    }
    assert trap_types >= {
        "agenda_multi_source_summary",
        "aggregate_single_person",
        "topic_partial_direct",
        "single_source_direct",
    }


def test_calibration_cases_wellformed():
    gs = load_golden_set(CALIBRATION_SET)
    assert len(gs.cases) >= 6
    for c in gs.cases:
        assert isinstance(c.input, dict), f"{c.id}: input dict olmalı"
        assert c.input.get("answer"), f"{c.id}: answer eksik"
        ctx = c.input.get("context_articles")
        assert isinstance(ctx, list) and ctx, f"{c.id}: context_articles boş"
        cls = c.expected.get("class")
        if cls == "false_positive_control":
            assert c.expected.get("max_hallucination_rate") == 0.0, f"{c.id}: FP-control 0.0 bekler"
        elif cls == "reconstruction":
            assert c.expected.get("must_flag") is True, (
                f"{c.id}: reconstruction must_flag=true bekler"
            )
        else:  # pragma: no cover - defensive
            raise AssertionError(f"{c.id}: bilinmeyen class {cls!r}")


def test_calibration_logic_fp_control_no_false_positive_with_oracle():
    """Motor doğrulaması: FP-control case'lerinde judge grounded derse harness
    FABRICATED ÜRETMEZ (aggregate/skorlama mantığı FP yaratmıyor)."""
    gs = load_golden_set(CALIBRATION_SET)
    for c in gs.cases:
        if c.expected.get("class") != "false_positive_control":
            continue
        report = run_grounding_report(
            c.input["answer"],
            c.input["context_articles"],
            splitter=split_sentences_fallback,
            judge=lambda *_: SUPPORTED,
        )
        assert report.hallucination_rate <= c.expected["max_hallucination_rate"], (
            f"{c.id}: FP-control'da hallucination_rate={report.hallucination_rate}"
        )


def test_calibration_logic_reconstruction_flagged_with_oracle():
    """Motor doğrulaması: reconstruction case'inde judge FABRICATED derse harness
    bunu rapora yansıtır (must_flag)."""
    gs = load_golden_set(CALIBRATION_SET)
    for c in gs.cases:
        if c.expected.get("class") != "reconstruction":
            continue
        report = run_grounding_report(
            c.input["answer"],
            c.input["context_articles"],
            splitter=split_sentences_fallback,
            judge=lambda *_: FABRICATED,
        )
        assert report.manual_review is True, f"{c.id}: reconstruction flag'lenmeli"
        assert report.hallucination_rate > 0.0, f"{c.id}: reconstruction halu>0 bekler"


# ===========================================================================
# 6) Opt-in eval — gerçek LLM self-calibration gate
# ===========================================================================


def _require_grounding_eval() -> None:
    """İki katman guard — CI'da deterministik skip, scheduled/manuel'de çalışır."""
    if os.environ.get("NODRAT_GROUNDING_EVAL") != "1":
        pytest.skip("opt-in gerekli: NODRAT_GROUNDING_EVAL=1 (scheduled/manuel koşum)")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY yok — grounding eval provider gerektirir")


@pytest.mark.eval
async def test_calibration_gate_real_llm_beats_v1_false_positive_rate():
    """SELF-CALIBRATION GATE (#1805 kabul kriteri): gerçek LLM ile
    false_positive_control FP oranı v1'in 0.50'sinden düşük olmalı.
    """
    _require_grounding_eval()
    gs = load_golden_set(CALIBRATION_SET)
    fp_cases = [c for c in gs.cases if c.expected.get("class") == "false_positive_control"]
    assert fp_cases, "FP-control case'i yok"

    provider, model = default_provider_and_model()
    false_positives = 0
    for c in fp_cases:
        report = await run_llm_grounding_report(
            c.input["answer"], c.input["context_articles"], provider=provider, model=model
        )
        if report.hallucination_rate > c.expected["max_hallucination_rate"]:
            false_positives += 1
            print(f"FP: {c.id}\n" + "\n".join(report.summary_lines()))

    fp_rate = false_positives / len(fp_cases)
    assert fp_rate < 0.5, (
        f"FP oranı {fp_rate:.2%} v1'in 50%'sini geçemedi ({false_positives}/{len(fp_cases)})"
    )


@pytest.mark.eval
async def test_calibration_gate_real_llm_catches_reconstruction():
    """Gerçek LLM reconstruction (geriye-çıkarsama) case'lerini yakalamalı."""
    _require_grounding_eval()
    gs = load_golden_set(CALIBRATION_SET)
    recon_cases = [c for c in gs.cases if c.expected.get("class") == "reconstruction"]
    assert recon_cases, "reconstruction case'i yok"

    provider, model = default_provider_and_model()
    caught = 0
    for c in recon_cases:
        report = await run_llm_grounding_report(
            c.input["answer"], c.input["context_articles"], provider=provider, model=model
        )
        if report.manual_review and report.hallucination_rate > 0.0:
            caught += 1
        else:  # görünürlük için
            print(f"MISS: {c.id}\n" + "\n".join(report.summary_lines()))

    assert caught >= 1, f"Hiçbir reconstruction yakalanmadı (0/{len(recon_cases)})"
