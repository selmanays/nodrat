"""Unit tests for Türkçe sorgu normalize + phrase threshold (#198)."""

from __future__ import annotations

from app.core.retrieval import _normalize_tr_query, _phrase_match_threshold


# ---------------------------------------------------------------------------
# _normalize_tr_query
# ---------------------------------------------------------------------------


def test_normalize_lowercases():
    assert _normalize_tr_query("CHP") == "chp"


def test_normalize_strips_apostrophe_ascii():
    assert _normalize_tr_query("CHP'li") == "chpli"


def test_normalize_strips_apostrophe_unicode():
    # U+2019 RIGHT SINGLE QUOTATION MARK (smart quote)
    assert _normalize_tr_query("CHP’li") == "chpli"


def test_normalize_no_change_when_already_normalized():
    assert _normalize_tr_query("chpli") == "chpli"


def test_normalize_collapses_whitespace():
    assert _normalize_tr_query("  CHP   li  ") == "chp li"


def test_normalize_handles_mixed_case_and_apostrophes():
    assert _normalize_tr_query("Türkiye'nin AB'ye") == "türkiyenin abye"


def test_normalize_empty():
    assert _normalize_tr_query("") == ""
    assert _normalize_tr_query(None) == ""  # type: ignore[arg-type]


def test_normalize_keeps_turkish_chars():
    # Türkçe ç/ğ/ı/ö/ş/ü korunur
    assert _normalize_tr_query("İzmir Çevre Yolu") == "i̇zmir çevre yolu"
    assert "çevre" in _normalize_tr_query("ÇEVRE")


# ---------------------------------------------------------------------------
# _phrase_match_threshold
# ---------------------------------------------------------------------------


def test_threshold_short_query():
    # 3 karakterli kısa query → 0.05
    assert _phrase_match_threshold("chp") == 0.05


def test_threshold_medium_query():
    # 6 karakter altı → 0.10
    assert _phrase_match_threshold("emekli") == 0.10


def test_threshold_long_query():
    # 7+ karakter → 0.15
    assert _phrase_match_threshold("emeklilik zammı") == 0.15
    assert _phrase_match_threshold("izmir çevre yolu") == 0.15


def test_threshold_extreme_short():
    # 1 char → 0.05 (yine en düşük)
    assert _phrase_match_threshold("a") == 0.05


def test_threshold_boundary_3_chars():
    assert _phrase_match_threshold("abc") == 0.05  # <=3


def test_threshold_boundary_4_chars():
    assert _phrase_match_threshold("abcd") == 0.10  # >3, <=6


def test_threshold_boundary_6_chars():
    assert _phrase_match_threshold("abcdef") == 0.10


def test_threshold_boundary_7_chars():
    assert _phrase_match_threshold("abcdefg") == 0.15  # >6
