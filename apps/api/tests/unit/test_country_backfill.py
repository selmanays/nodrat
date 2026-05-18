"""Unit tests for country backfill helpers (#228)."""

from __future__ import annotations

from app.workers.tasks.agenda import _parse_country_response


def test_parse_country_basic_iso2():
    assert _parse_country_response("TR") == "TR"
    assert _parse_country_response("US") == "US"


def test_parse_country_lowercase_normalize():
    assert _parse_country_response("tr") == "TR"


def test_parse_country_with_quotes():
    assert _parse_country_response('"TR"') == "TR"
    assert _parse_country_response("'US'") == "US"


def test_parse_country_with_extra_text():
    # LLM bazen 'Country: TR' diyebilir
    assert _parse_country_response("Country: TR") == "TR"
    assert _parse_country_response("TR olarak sınıflandırılır") == "TR"


def test_parse_country_null():
    assert _parse_country_response("null") is None
    assert _parse_country_response("NULL") is None


def test_parse_country_empty():
    assert _parse_country_response("") is None
    assert _parse_country_response("   ") is None


def test_parse_country_invalid_code_returns_none():
    # Tanımlı whitelist dışı kod → None (XX, ZZ vb.)
    assert _parse_country_response("XX") is None
    assert _parse_country_response("ZZ") is None


def test_parse_country_3_letter_returns_none():
    # ISO3 kod (TUR/USA) yanlışlıkla geçirilirse → None
    assert _parse_country_response("TUR") is None


def test_parse_country_supported_codes():
    # Beklenen tanımlı kodlar
    for code in [
        "TR",
        "US",
        "DE",
        "FR",
        "GB",
        "IL",
        "PS",
        "LB",
        "RU",
        "UA",
        "SY",
        "IR",
        "GR",
        "CY",
        "AT",
        "CU",
        "JP",
        "CN",
        "IN",
        "EG",
        "SA",
        "AE",
    ]:
        assert _parse_country_response(code) == code, f"{code} reddedildi"
