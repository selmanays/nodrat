"""NIM VLM JSON parser tolerance tests (#480).

Production'da %0.2 oran (4/2002) "bozuk Unicode escape" yüzünden parse fail
oluyor; eski parser fallback'a düşüp raw JSON'u caption alanına döküyordu.

Multi-fallback parser:
  L1: json.loads
  L2: invalid \\u (1-3 hex) escape → literal repair
  L3: regex ile manuel field extraction
"""

from __future__ import annotations

from app.providers.nim_vlm import _manual_field_extract, _safe_json_parse


def test_parser_layer1_clean_json():
    """Sağlıklı JSON — Layer 1 ile parse."""
    text = '{"caption": "İki insan", "ocr_text": "TEST", "depicts": ["insan"]}'
    parsed = _safe_json_parse(text)
    assert parsed is not None
    assert parsed["caption"] == "İki insan"
    assert parsed["ocr_text"] == "TEST"
    assert parsed["depicts"] == ["insan"]


def test_parser_layer2_invalid_unicode_escape_3digit():
    """Production gerçek vakası — model \\u00b (3 hex) üretti, parse fail.

    L1 fail → L2 invalid escape repair → parse OK.
    """
    # Gerçek production verisinden alıntı (Turkish Airlines image)
    text = (
        '{"caption": "Turkish Airlines u\\u00bçak apronunda", '
        '"ocr_text": "TURKISH AIRLINES", '
        '"depicts": ["u\\u00bçak"]}'
    )
    parsed = _safe_json_parse(text)
    assert parsed is not None
    # \u00b literal kalır (geçersiz escape), karakter sonrası 'çak' korunur
    assert "Turkish Airlines" in parsed["caption"]
    assert "ocr_text" in parsed
    assert parsed["ocr_text"] == "TURKISH AIRLINES"


def test_parser_layer3_truncated_json_manual_extract():
    """JSON yarım (örn. token limit) → L1 ve L2 fail → L3 regex extraction."""
    # Truncated — son } yok
    text = '{"caption": "Hukuki bir belge örneği", "ocr_text": "HAVAİ FİŞEK BEYAN SUNAN..."'
    parsed = _safe_json_parse(text)
    assert parsed is not None
    assert parsed["caption"] == "Hukuki bir belge örneği"
    assert "HAVAİ FİŞEK" in parsed["ocr_text"]


def test_manual_extract_with_escaped_quotes():
    """Caption içinde escape edilmiş tırnak — regex bozulmamalı."""
    text = '{"caption": "Sahte \\"belge\\" örneği", "ocr_text": ""}'
    result = _manual_field_extract(text)
    assert result is not None
    # Escape decoded
    assert result["caption"] == 'Sahte "belge" örneği'


def test_manual_extract_returns_none_on_garbage():
    """Hiç field bulunamazsa None — fallback hattı tetiklenir."""
    assert _manual_field_extract("totally not json") is None
    assert _manual_field_extract("{}") is None  # Boş dict, field yok


def test_parser_long_ocr_text_does_not_break():
    """Uzun OCR (hukuki belge örneği) — herhangi bir katmanda parse OK."""
    long_ocr = "ACIKLAMALAR " * 200  # ~2400 char
    text = f'{{"caption": "Belge", "ocr_text": "{long_ocr.strip()}", "depicts": []}}'
    parsed = _safe_json_parse(text)
    assert parsed is not None
    assert len(parsed["ocr_text"]) > 1000
    assert parsed["caption"] == "Belge"


def test_parser_depicts_nonlist_tolerated():
    """depicts string olursa (model hatası), L1 OK ama veri kaybı —
    test edilmez burada (provider tarafı kontrol ediyor)."""
    text = '{"caption": "X", "ocr_text": "", "depicts": []}'
    parsed = _safe_json_parse(text)
    assert parsed is not None
    assert parsed["depicts"] == []
