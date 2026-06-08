"""Unit — #619 PR-A decomposition TRIGGER characterization.

`decompose_heuristic` trigger davranışını CI'da KİLİTLER. Bu bir CHARACTERIZATION
suite'i: MEVCUT (kimi zaman yanlış) davranışı assert eder; HEDEF davranış golden'daki
`expected` + `divergence` alanlarıyla belgelenir (PR-B referansı). xfail/TODO YOK —
PR-B heuristic guard ekleyince `divergence==True` case'lerin `current_splits`'i 0'a
inecek ve bu suite + golden GÜNCELLENECEK (davranış değişimi diff'te explicit).

Golden: ``tests/eval/golden_sets/decompose_trigger_cases.yaml`` (relevant-id YOK,
recall ölçmez; yalnız trigger sınıflandırması). Production ``decompose_heuristic``
import edilir — benchmark proxy ile aynı primitive.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.prompts.query_decomposition import decompose_heuristic

_GOLDEN_DIR = Path(__file__).parent.parent / "eval" / "golden_sets"
_TRIGGER_YAML = _GOLDEN_DIR / "decompose_trigger_cases.yaml"
_MULTI_YAML = _GOLDEN_DIR / "retrieval_golden_multi.yaml"

VALID_CLASSES = {
    "should_split",
    "should_not_split",
    "llm_or_ambiguous",
    "split_but_needs_cleaning",
}
# "bölmeli" hedef sınıfları → current_splits >= 2 beklenir.
_SPLIT_CLASSES = {"should_split", "split_but_needs_cleaning"}


def _load_cases() -> list[dict]:
    data = yaml.safe_load(_TRIGGER_YAML.read_text(encoding="utf-8"))
    return data["cases"]


_CASES = _load_cases()


# =============================================================================
# Schema
# =============================================================================


def test_trigger_yaml_loads_and_nonempty():
    assert len(_CASES) >= 12, "trigger golden en az 12 case (4 sınıf kapsama) içermeli"
    # Her 4 sınıf temsil edilmeli.
    classes = {c["expected"] for c in _CASES}
    assert classes == VALID_CLASSES, f"eksik/fazla sınıf: {classes}"


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["query"][:38])
def test_case_schema(case):
    assert set(case) >= {"query", "expected", "current_splits", "divergence", "note"}
    assert case["expected"] in VALID_CLASSES
    assert isinstance(case["current_splits"], int) and case["current_splits"] >= 0
    assert isinstance(case["divergence"], bool)
    assert case["note"].strip()


# =============================================================================
# Characterization — MEVCUT davranış kilitli (CI-green; PR-B'de değişecek)
# =============================================================================


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["query"][:38])
def test_characterization_current_behavior(case):
    """``decompose_heuristic``'in ŞU ANKİ parça sayısı ``current_splits`` ile eşleşmeli.

    Mevcut davranışı kilitler (regression guard). PR-B davranışı değiştirince
    yalnız ``divergence==True`` case'lerin assert'i güncellenir → diff'te görünür.
    """
    out = decompose_heuristic(case["query"])
    assert len(out) == case["current_splits"], (
        f"CHARACTERIZATION DRIFT: {case['query']!r} → {out} "
        f"(golden current_splits={case['current_splits']})"
    )


# =============================================================================
# Divergence — HEDEF ile mevcut davranış farkı (PR-B'nin kapatacağı)
# =============================================================================


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["query"][:38])
def test_divergence_flag_consistent(case):
    """``divergence==True`` ⟺ hedef 'bölmemeli' AMA heuristic şu an bölüyor (>=2)."""
    target_should_not_split = case["expected"] not in _SPLIT_CLASSES
    currently_splits = case["current_splits"] >= 2
    assert case["divergence"] == (target_should_not_split and currently_splits)


def test_known_divergence_set_is_locked():
    """PR-B HEDEFİ: şu an 3 divergence (heuristic yanlış bölüyor) → guard sonrası 0.

    Bu sayı PR-B'de azalır (düzelen her divergence → current_splits 0, divergence False).
    Test o zaman güncellenir; ilerleme ölçülebilir. Üç bilinen kök-pattern:
    tek-kurum-adı (' ve '), liste-bağlacı (' ve '), tek-konu-refine (' ile ilgili ').
    """
    divergent = [c["query"] for c in _CASES if c["divergence"]]
    assert len(divergent) == 3, f"divergence seti değişti: {divergent}"
    assert any("çevre şehircilik" in q for q in divergent)  # tek kurum adı
    assert any("sosyal güvenlik ve emeklilik" in q for q in divergent)  # liste-bağlacı
    assert any("ile ilgili" in q for q in divergent)  # tek-konu refine


# =============================================================================
# Sınıf-bazlı mevcut davranış (yaml ile bağımsız çapraz-doğrulama)
# =============================================================================


def test_split_classes_currently_split():
    for c in _CASES:
        if c["expected"] in _SPLIT_CLASSES:
            assert c["current_splits"] >= 2, (
                f"{c['query']!r} bölmeli, current={c['current_splits']}"
            )


def test_llm_ambiguous_heuristic_does_not_split():
    """Marker'sız (virgül/örtük) → heuristic bölmez; LLM-fallback alanı (current 0)."""
    for c in _CASES:
        if c["expected"] == "llm_or_ambiguous":
            out = decompose_heuristic(c["query"])
            assert out == [], f"{c['query']!r} heuristic bölmemeli (LLM gerek), döndü: {out}"


def test_should_not_split_already_correct_stay_empty():
    """divergence==False olan should_not_split case'leri zaten [] (min-words guard).

    Bunlar PR-B'de DE [] kalmalı (kazara-doğru → kasıtlı-doğru).
    """
    for c in _CASES:
        if c["expected"] == "should_not_split" and not c["divergence"]:
            out = decompose_heuristic(c["query"])
            assert out == [], f"{c['query']!r} (already-correct) bölmemeli, döndü: {out}"


# =============================================================================
# retrieval_golden_multi.yaml expected_decompose label tutarlılığı
# =============================================================================


def test_retrieval_golden_multi_has_expected_decompose():
    data = yaml.safe_load(_MULTI_YAML.read_text(encoding="utf-8"))
    queries = data["queries"]
    assert len(queries) == 10
    for q in queries:
        assert "expected_decompose" in q, f"{q['id']}: expected_decompose label eksik"
        assert q["expected_decompose"] in VALID_CLASSES, (
            f"{q['id']}: geçersiz sınıf {q['expected_decompose']!r}"
        )


def test_retrieval_golden_multi_labels_match_heuristic_mode():
    """`decompose: heuristic` query'leri bölünebilir sınıfta; `decompose: llm` → llm_or_ambiguous."""
    data = yaml.safe_load(_MULTI_YAML.read_text(encoding="utf-8"))
    for q in data["queries"]:
        mode = q.get("decompose")
        exp = q["expected_decompose"]
        if mode == "llm":
            assert exp == "llm_or_ambiguous", f"{q['id']}: llm-mode ama {exp}"
        elif mode == "heuristic":
            assert exp in _SPLIT_CLASSES, f"{q['id']}: heuristic-mode ama {exp}"
