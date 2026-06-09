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
    "heuristic_out_of_scope",  # #619 PR-B — tek-kurum/tek-konu ` ve `; heuristic böler (LLM alanı)
}
# "bölmeli" hedef sınıfları → current_splits >= 2 beklenir.
# heuristic_out_of_scope DAHİL DEĞİL: hedef bölünmemeli ama heuristic (yanlış) böler.
_SPLIT_CLASSES = {"should_split", "split_but_needs_cleaning"}


def _load_cases() -> list[dict]:
    data = yaml.safe_load(_TRIGGER_YAML.read_text(encoding="utf-8"))
    return data["cases"]


_CASES = _load_cases()


# =============================================================================
# Schema
# =============================================================================


def test_trigger_yaml_loads_and_nonempty():
    assert len(_CASES) >= 12, "trigger golden en az 12 case (5 sınıf kapsama) içermeli"
    # Her 5 sınıf temsil edilmeli.
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
    """``divergence==True`` ⟺ hedef ``should_not_split`` AMA heuristic bölüyor (>=2).

    ``heuristic_out_of_scope`` MUAF — tek-kurum/tek-konu ` ve ` deterministik
    çözülemez (kabul edilen kör-nokta), aktif-divergence değil.
    """
    active = case["expected"] == "should_not_split" and case["current_splits"] >= 2
    assert case["divergence"] == active


def test_no_active_divergence_after_pr_b():
    """PR-B sonrası aktif-divergence 0 (PR-A'da 3 idi).

    DIV#3 (' ile ilgili ') marker'lıktan çıkarıldı → ``should_not_split`` + [].
    DIV#1/#2 (tek-kurum/tek-konu ' ve ') ``heuristic_out_of_scope``'a taşındı —
    deterministik ayrılamaz (``≥3-kelime`` kuralı PR-2 cap/dedup/multi-topic'i
    bozardı, B kararı reddetti) → LLM-fallback alanı, kabul edilen kör-nokta.
    """
    divergent = [c["query"] for c in _CASES if c["divergence"]]
    assert divergent == [], f"beklenmeyen aktif-divergence: {divergent}"
    # DIV#1/#2 kör-nokta olarak korunur (current böler ama divergence değil).
    oos = [c for c in _CASES if c["expected"] == "heuristic_out_of_scope"]
    assert len(oos) == 2
    assert any("çevre şehircilik" in c["query"] for c in oos)
    assert any("sosyal güvenlik ve emeklilik" in c["query"] for c in oos)


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
    """#619 PR-D1: golden_multi 30 query, hepsi geçerli expected_decompose sınıfı.

    (Sınıf↔heuristic-davranış tutarlılığı test_golden_multi_subset.py'de;
    `decompose` mode alanı PR-D1'de kaldırıldı → tek-etiket expected_decompose.)
    """
    data = yaml.safe_load(_MULTI_YAML.read_text(encoding="utf-8"))
    queries = data["queries"]
    assert len(queries) == 30
    for q in queries:
        assert "expected_decompose" in q, f"{q['id']}: expected_decompose label eksik"
        assert q["expected_decompose"] in VALID_CLASSES, (
            f"{q['id']}: geçersiz sınıf {q['expected_decompose']!r}"
        )


# =============================================================================
# #619 PR-B — yeni davranış (ile-ilgili çıkar · noise-strip · heuristic_out_of_scope)
# =============================================================================


def test_ile_ilgili_no_longer_a_split_marker():
    """DIV#3 — ' ile ilgili ' tek-konu refine; PR-B'de split-marker değil → []."""
    assert decompose_heuristic("kira artışı ile ilgili yeni düzenleme kararı") == []
    assert decompose_heuristic("deprem ile ilgili son açıklama") == []


def test_mq005_split_but_cleaned():
    """mq_005 — bölme KORUNUR ama parçalar noise-strip ile temizlenir."""
    out = decompose_heuristic("altın fiyatı bugün gram ve 12 yargı paketi ne zaman çıkacak")
    assert len(out) == 2  # bölme iptal edilmedi
    joined = " ".join(out).lower()
    assert "bugün" not in joined  # zaman-noise temizlendi
    assert "ne zaman" not in joined  # soru-kuyruğu temizlendi
    assert out == ["altın fiyatı gram", "12 yargı paketi çıkacak"]


def test_should_split_subqueries_noise_stripped():
    """should_split parçaları soru-eki/kuyruğu'ndan arınır (retrieval-kalitesi)."""
    out = decompose_heuristic("kurban bayramı ne zaman ve üniversiteler tatil mi")
    assert out == ["kurban bayramı", "üniversiteler tatil"]


def test_mq007_should_split_preserved():
    """mq_007 — temiz noun-phrase'ler; PR-B değiştirmez (regression guard)."""
    out = decompose_heuristic("15 yaş altı sosyal medya yasağı ve doğum izni 24 hafta yasası")
    assert out == ["15 yaş altı sosyal medya yasağı", "doğum izni 24 hafta yasası"]


def test_pr2_legitimate_multi_topic_preserved():
    """PR-2 meşru 2-kelime-parçalı çok-konu KORUNUR (B kararı: ≥3-kelime kuralı yok)."""
    out = decompose_heuristic("Türkiye ekonomisi ve faiz kararları son durum")
    assert len(out) == 2
    assert out[0] == "Türkiye ekonomisi"
    assert "faiz kararları" in out[1]


def test_heuristic_out_of_scope_still_splits_is_llm_domain():
    """heuristic_out_of_scope (tek-kurum/tek-konu ' ve ') — heuristic BÖLER (kabul).

    Deterministik ayrılamaz → LLM-fallback alanı. PR-B'nin BİLEREK çözmediği
    kör-noktayı belgeler (aktif-divergence değil).
    """
    oos = [c for c in _CASES if c["expected"] == "heuristic_out_of_scope"]
    assert len(oos) == 2
    for c in oos:
        out = decompose_heuristic(c["query"])
        assert len(out) >= 2, f"{c['query']!r} heuristic-out beklenen >=2, döndü {out}"
        assert c["current_splits"] == len(out)
        assert not c["divergence"]


def test_strip_subquery_noise_helper():
    """_strip_subquery_noise — soru-kuyruğu/zaman atar, içerik korur."""
    from app.prompts.query_decomposition import _strip_subquery_noise

    assert _strip_subquery_noise("12 yargı paketi ne zaman çıkacak") == "12 yargı paketi çıkacak"
    assert _strip_subquery_noise("altın fiyatı bugün gram") == "altın fiyatı gram"
    assert _strip_subquery_noise("üniversiteler tatil mi") == "üniversiteler tatil"
    assert (
        _strip_subquery_noise("sosyal medya yasağı") == "sosyal medya yasağı"
    )  # noise yoksa değişmez
