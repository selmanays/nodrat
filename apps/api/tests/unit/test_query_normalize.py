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


# #647 — kök sebep: smart double quote varyantları normalize edilmiyordu.
# Tüm major quote varyantları (single+double, smart, low-9, guillemets, prime)
# Python tarafında `strip_quote_variants` ile silinir.


def test_normalize_strips_double_quote_ascii():
    assert _normalize_tr_query('"Toprakaltı" sergisi') == "toprakaltı sergisi"


def test_normalize_strips_double_quote_left_smart():
    # U+201C LEFT DOUBLE QUOTATION MARK
    assert _normalize_tr_query("“Toprakaltı sergisi") == "toprakaltı sergisi"


def test_normalize_strips_double_quote_right_smart():
    # U+201D RIGHT DOUBLE QUOTATION MARK — Bianet Toprakaltı vakası
    assert _normalize_tr_query("Toprakaltı” sergisi") == "toprakaltı sergisi"


def test_normalize_strips_double_quote_pair_smart():
    # Bianet üretim verisi: "Toprakaltı" sergisi 3 Mayıs'a dek
    text = "“Toprakaltı” sergisi 3 Mayıs’a dek"
    assert _normalize_tr_query(text) == "toprakaltı sergisi 3 mayısa dek"


def test_normalize_strips_low9_quotes():
    # German-style „..." quotes
    assert _normalize_tr_query("„örnek‟ metin") == "örnek metin"


def test_normalize_strips_guillemets():
    assert _normalize_tr_query("«kelime» test") == "kelime test"


def test_normalize_strips_left_single_smart():
    # U+2018 LEFT SINGLE QUOTATION MARK
    assert _normalize_tr_query("‘Toprakaltı sergisi") == "toprakaltı sergisi"


def test_normalize_strips_backtick():
    assert _normalize_tr_query("`örnek` test") == "örnek test"


def test_normalize_strips_prime_chars():
    # U+2032 PRIME, U+2033 DOUBLE PRIME
    assert _normalize_tr_query("test ′kelime″") == "test kelime"


def test_normalize_phrase_match_after_strip():
    """Quote variants normalize edildikten sonra phrase ILIKE semantik:
    chunk_text'te '"Toprakaltı" sergisi' geçen Bianet article'ı
    sorgu 'toprakaltı sergisi' ile eşleşmeli (ardışık kelime sınırı korunur).
    """
    chunk_norm = _normalize_tr_query('"Toprakaltı" sergisi 3 Mayısa dek')
    query_norm = _normalize_tr_query("Toprakaltı sergisi")
    assert query_norm in chunk_norm  # phrase match → True (kök fix)


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


# ---------------------------------------------------------------------------
# _phrase_grams (#200)
# ---------------------------------------------------------------------------


from app.core.retrieval import _phrase_grams


def test_grams_5_word_query():
    grams = _phrase_grams("izmir çevre yolu ücretli olacak")
    assert "izmir çevre yolu" in grams  # target için kritik
    assert "izmir çevre" in grams
    assert "çevre yolu" in grams
    assert "izmir çevre yolu ücretli" in grams


def test_grams_filters_noise_only_phrases():
    grams = _phrase_grams("izmir çevre yolu mi olacak")
    # 'mi olacak' tamamen noise → filter
    assert "mi olacak" not in grams
    # 'yolu mi' — yolu noise değil → kalır
    assert any("yolu" in g for g in grams)


def test_grams_skips_too_short():
    # 'a b' (3 char) → min 5 char filter ile drop
    grams = _phrase_grams("a b c d e")
    assert all(len(g) >= 5 for g in grams)


def test_grams_short_query_returns_empty():
    # tek kelime → 2-gram yok
    assert _phrase_grams("CHP") == []
    assert _phrase_grams("emekli") == []


def test_grams_empty_input():
    assert _phrase_grams("") == []
    assert _phrase_grams("   ") == []


def test_grams_unique():
    grams = _phrase_grams("test test test başka")
    # tekrar eden 'test test' bir kez
    assert len([g for g in grams if g == "test test"]) <= 1


def test_grams_max_4_grams():
    grams = _phrase_grams("a b c d e f g h", n_min=2, n_max=4)
    # En uzun gram 4 kelime
    assert all(len(g.split()) <= 4 for g in grams)
