"""Unit — #619 PR-D1 çok-bileşenli golden-quality (10→30) doğrulama.

`retrieval_golden_multi.yaml`: 30 query, 5 sınıf dengeli, `expected_decompose`
tek-etiket. relevant UUID'ler mevcut `retrieval_golden_tr.yaml` card'larından
reuse (yeni card YOK).

BENCHMARK KOŞMAZ; recall ÖLÇMEZ (prod-UUID → local sahte-düşük). Yalnız subset
yapısı + sınıf-dağılım + UUID-reuse + heuristic-expectation sabitlenir.
"""

from __future__ import annotations

from collections import Counter

from app.prompts.query_decomposition import decompose_heuristic

from tests.eval.retrieval_benchmark import load_golden_set

_MULTI = load_golden_set("retrieval_golden_multi.yaml")
_TR = load_golden_set("retrieval_golden_tr.yaml")

VALID_CLASSES = {
    "should_split",
    "should_not_split",
    "split_but_needs_cleaning",
    "heuristic_out_of_scope",
    "llm_or_ambiguous",
}
# heuristic deterministik ≥2 böler:
_HEURISTIC_SPLITS = {"should_split", "split_but_needs_cleaning", "heuristic_out_of_scope"}
# heuristic [] (bölmez):
_HEURISTIC_EMPTY = {"should_not_split", "llm_or_ambiguous"}


def _tr_card_ids() -> set[str]:
    ids: set[str] = set()
    for q in _TR["queries"]:
        for r in q.get("relevant", []):
            ids.add(r["id"])
    return ids


# =============================================================================
# Yapı + şema
# =============================================================================


def test_multi_structure():
    queries = _MULTI["queries"]
    assert len(queries) == 30, "PR-D1 golden-quality: 30 query"
    for q in queries:
        assert q.get("id") and q.get("text")
        assert q.get("expected_decompose") in VALID_CLASSES, f"{q['id']}: geçersiz sınıf"
        assert q.get("rationale", "").strip(), f"{q['id']}: rationale eksik"
        rel = q.get("relevant", [])
        assert len(rel) >= 1, f"{q['id']}: 1+ relevant"
        for r in rel:
            assert r["id"] and float(r["relevance"]) > 0


def test_class_distribution():
    dist = Counter(q["expected_decompose"] for q in _MULTI["queries"])
    assert set(dist) == VALID_CLASSES, "5 sınıf da temsil edilmeli"
    assert dist["should_split"] == 10, f"should_split=10 hedef, {dist['should_split']}"
    # not-split ailesi (should_not_split + heuristic_out_of_scope) = 10
    assert dist["should_not_split"] + dist["heuristic_out_of_scope"] == 10
    assert 5 <= dist["llm_or_ambiguous"] <= 10
    assert dist["split_but_needs_cleaning"] >= 2


# =============================================================================
# UUID reuse (yeni card YOK)
# =============================================================================


def test_relevant_ids_reuse_existing_tr_cards():
    tr_ids = _tr_card_ids()
    for q in _MULTI["queries"]:
        for r in q["relevant"]:
            assert r["id"] in tr_ids, (
                f"{q['id']} relevant {r['id']} golden_tr'de yok — yeni card yaratılmamalı"
            )


def test_no_new_uuid_introduced():
    """golden_multi UUID kümesi golden_tr alt-kümesi (yeni-card-yok invariant)."""
    tr_ids = _tr_card_ids()
    multi_ids = {r["id"] for q in _MULTI["queries"] for r in q["relevant"]}
    assert multi_ids <= tr_ids, f"yeni UUID: {multi_ids - tr_ids}"


# =============================================================================
# Heuristic expectation (sınıf ↔ gerçek davranış)
# =============================================================================


def test_heuristic_split_classes_produce_subqueries():
    """should_split / split_but_needs_cleaning / heuristic_out_of_scope → heuristic ≥2."""
    for q in _MULTI["queries"]:
        if q["expected_decompose"] in _HEURISTIC_SPLITS:
            parts = decompose_heuristic(q["text"])
            assert len(parts) >= 2, f"{q['id']} ({q['expected_decompose']}) ≥2 → {parts}"


def test_heuristic_empty_classes_do_not_split():
    """should_not_split / llm_or_ambiguous → heuristic [] (bölmez)."""
    for q in _MULTI["queries"]:
        if q["expected_decompose"] in _HEURISTIC_EMPTY:
            assert decompose_heuristic(q["text"]) == [], (
                f"{q['id']} ({q['expected_decompose']}) heuristic bölmemeli: {q['text']!r}"
            )


def test_llm_class_not_required_to_succeed_heuristic():
    """llm_or_ambiguous: heuristic'ten zorunlu başarı beklenmez (yalnız []; LLM alanı)."""
    llm_qs = [q for q in _MULTI["queries"] if q["expected_decompose"] == "llm_or_ambiguous"]
    assert len(llm_qs) >= 5
    for q in llm_qs:
        assert decompose_heuristic(q["text"]) == []


# =============================================================================
# Golden-kalibrasyon meta (PR-C bulgusu)
# =============================================================================


def test_low_confidence_flag_present_for_popular():
    """low_confidence işaretli query'ler var (popüler-UUID recall-riski belgesi)."""
    lc = [q for q in _MULTI["queries"] if q.get("low_confidence")]
    assert len(lc) >= 3, "popüler-konu low_confidence işaretlenmeli"
    mq005 = next(q for q in _MULTI["queries"] if q["id"] == "mq_005")
    assert mq005.get("low_confidence") is True


def test_kuyruksuz_control_preserved():
    """mq_007 kuyruksuz should_split = noise-strip doğal kontrol (PR-C kanıtı)."""
    mq007 = next(q for q in _MULTI["queries"] if q["id"] == "mq_007")
    assert mq007["expected_decompose"] == "should_split"
    # kuyruksuz → noise-strip uygulanmaz → alt-sorgu ham
    assert decompose_heuristic(mq007["text"]) == [
        "15 yaş altı sosyal medya yasağı",
        "doğum izni 24 hafta yasası",
    ]
