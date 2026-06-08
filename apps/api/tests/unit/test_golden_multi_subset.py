"""Unit — #619 PR-4B çok-bileşenli golden subset doğrulama.

`retrieval_golden_multi.yaml`: heuristic-split deterministik + şema + relevant
UUID'ler mevcut `retrieval_golden_tr.yaml` card'larından (yeni card YOK).

BENCHMARK KOŞMAZ; recall ÖLÇMEZ (prod-UUID → local sahte-düşük). Yalnız
subset'in yapısını + heuristic-tetikleme/LLM-gerektirme ayrımını sabitler.
"""

from __future__ import annotations

from app.prompts.query_decomposition import decompose_heuristic

from tests.eval.retrieval_benchmark import load_golden_set

_MULTI = load_golden_set("retrieval_golden_multi.yaml")
_TR = load_golden_set("retrieval_golden_tr.yaml")


def _tr_card_ids() -> set[str]:
    ids: set[str] = set()
    for q in _TR["queries"]:
        for r in q.get("relevant", []):
            ids.add(r["id"])
    return ids


def test_multi_structure():
    queries = _MULTI["queries"]
    assert len(queries) == 10
    for q in queries:
        assert q.get("id") and q.get("text")
        rel = q.get("relevant", [])
        assert len(rel) >= 2, f"{q['id']} çok-bileşen → 2+ relevant card beklenir"
        for r in rel:
            assert r["id"] and float(r["relevance"]) > 0
        assert q.get("decompose") in ("heuristic", "llm")


def test_relevant_ids_reuse_existing_tr_cards():
    # Relevant UUID'ler mevcut golden_tr card'larından birleştirildi (yeni card YOK)
    tr_ids = _tr_card_ids()
    for q in _MULTI["queries"]:
        for r in q["relevant"]:
            assert r["id"] in tr_ids, (
                f"{q['id']} relevant {r['id']} golden_tr'de yok — yeni card yaratılmamalı"
            )


def test_heuristic_tagged_queries_split_deterministically():
    heuristic_qs = [q for q in _MULTI["queries"] if q.get("decompose") == "heuristic"]
    assert len(heuristic_qs) >= 5
    for q in heuristic_qs:
        parts = decompose_heuristic(q["text"])
        assert len(parts) >= 2, f"{q['id']} heuristic 2+ bölünmeli: {q['text']!r} → {parts}"


def test_llm_tagged_queries_not_heuristic_splittable():
    llm_qs = [q for q in _MULTI["queries"] if q.get("decompose") == "llm"]
    assert len(llm_qs) >= 2
    for q in llm_qs:
        # Marker yok → heuristic [] (LLM-fallback gerekir; benchmark llm-mod)
        assert decompose_heuristic(q["text"]) == [], (
            f"{q['id']} heuristic tetiklememeli (LLM-gerektiren): {q['text']!r}"
        )
