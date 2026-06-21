"""Unit — query_clarification parse (#1701).

LLM çıktısının satır-bazlı tolerant parse'ı (JSON DEĞİL — küçük model
güvenilmezliği #819/#840). LLM call'un kendisi entegrasyon/manuel; burada saf
parse mantığı (message + suggestions çıkarımı, dedupe, limit, fallback).
"""

from __future__ import annotations

from app.prompts.query_clarification import parse_clarification


def test_parse_normal():
    r = parse_clarification(
        "MESAJ: Bu konuda dayanak kaynak bulamadım. Voleybolu kastediyor olabilirsiniz.\n"
        "- A Milli Kadın Voleybol Takımı'nın son maç sonucu ne?\n"
        "- Filenin Sultanları Almanya maçını kazandı mı?"
    )
    assert r is not None
    assert r["message"].startswith("Bu konuda dayanak")
    assert len(r["suggestions"]) == 2
    assert "A Milli" in r["suggestions"][0]


def test_parse_dedupe_and_limit():
    r = parse_clarification("Kaynak yok.\n- x\n- x\n- y\n- z\n- w")
    assert r is not None
    assert r["message"] == "Kaynak yok."
    # dedupe (x bir kez) + limit 3
    assert r["suggestions"] == ["x", "y", "z"]


def test_parse_message_label_optional():
    # MESAJ: etiketi yoksa ilk düz satır mesaj olur
    r = parse_clarification("Sanırım şunu sordunuz:\n- öneri 1")
    assert r is not None
    assert r["message"] == "Sanırım şunu sordunuz:"
    assert r["suggestions"] == ["öneri 1"]


def test_parse_bullet_variants():
    r = parse_clarification("MESAJ: m\n* a\n• b\n- c")
    assert r is not None
    assert r["suggestions"] == ["a", "b", "c"]


def test_parse_empty_or_blank_returns_none():
    assert parse_clarification("") is None
    assert parse_clarification("   \n  ") is None


def test_parse_only_suggestions_no_message_returns_none():
    # Mesaj yoksa (yalnız bülten) → None (caller degrade eder)
    assert parse_clarification("- yalnız öneri") is None
