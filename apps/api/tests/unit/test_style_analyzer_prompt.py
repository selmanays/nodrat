"""Style analyzer prompt v1.0 tests (#52, Faz 5).

Saf fonksiyonel testler:
  - render_user_payload (örnek metin formatı + truncation)
  - parse_response (JSON validation, type coercion, error path)
"""

from __future__ import annotations

import json

import pytest
from app.prompts.style_analyzer import (
    MAX_SAMPLE_CHARS,
    MIN_SAMPLES,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    parse_response,
    render_user_payload,
)

# ============================================================================
# render_user_payload
# ============================================================================


def test_render_payload_includes_all_samples() -> None:
    samples = [
        {"text": "Bir gündem yorumu kısa ve net.", "source_url": None},
        {"text": "İkinci örnek de aynı tonu sürdürür.", "source_url": "https://x"},
        {"text": "Üçüncü örnek bittiği gibi nokta.", "source_url": None},
    ]
    out = render_user_payload(samples)
    assert "Örnek 1" in out
    assert "Örnek 2" in out
    assert "Örnek 3" in out
    assert "Bir gündem yorumu" in out
    assert "İkinci örnek" in out
    assert out.startswith("Aşağıdaki örnek metinlerden")


def test_render_payload_truncates_long_sample() -> None:
    long_text = "A" * (MAX_SAMPLE_CHARS + 500)
    samples = [{"text": long_text, "source_url": None}]
    out = render_user_payload(samples)
    # Trailing ellipsis added
    assert "…" in out
    # Content is bounded near MAX_SAMPLE_CHARS (some leeway for prefix/suffix)
    assert len(out) < MAX_SAMPLE_CHARS + 200


def test_render_payload_skips_empty_text() -> None:
    samples = [
        {"text": "", "source_url": None},
        {"text": "   ", "source_url": None},
        {"text": "Geçerli örnek.", "source_url": None},
    ]
    out = render_user_payload(samples)
    # Only the 3rd shown — but indexing keeps original order
    assert "Geçerli örnek" in out


# ============================================================================
# parse_response
# ============================================================================


VALID_OUTPUT = {
    "style_name": "Sade politik yorum",
    "style_summary": "Kısa cümle, kanıta dayalı.",
    "sentence_length": "medium",
    "tone": ["sade", "eleştirel"],
    "rhetorical_patterns": ["Önce iddia, sonra veri"],
    "avoid": ["uzun akademik dil"],
    "sample_transforms": [{"generic": "X olur.", "styled": "X kesin oldu."}],
}


def test_parse_valid_json() -> None:
    raw = json.dumps(VALID_OUTPUT)
    parsed = parse_response(raw)
    assert parsed["style_name"] == VALID_OUTPUT["style_name"]
    assert parsed["sentence_length"] == "medium"
    assert isinstance(parsed["tone"], list)


def test_parse_strips_markdown_fence() -> None:
    raw = f"```json\n{json.dumps(VALID_OUTPUT)}\n```"
    parsed = parse_response(raw)
    assert parsed["style_name"] == VALID_OUTPUT["style_name"]


def test_parse_missing_key_raises() -> None:
    bad = dict(VALID_OUTPUT)
    bad.pop("tone")
    with pytest.raises(ValueError, match="eksik anahtar"):
        parse_response(json.dumps(bad))


def test_parse_coerces_invalid_types() -> None:
    out = dict(VALID_OUTPUT)
    out["tone"] = "yalnız string"  # list bekleniyor
    out["rhetorical_patterns"] = None
    out["sentence_length"] = "xxx"  # set'in dışında
    parsed = parse_response(json.dumps(out))
    assert parsed["tone"] == []
    assert parsed["rhetorical_patterns"] == []
    assert parsed["sentence_length"] == "medium"


def test_parse_non_dict_raises() -> None:
    with pytest.raises(ValueError):
        parse_response(json.dumps([1, 2, 3]))


def test_min_samples_constant() -> None:
    # Sözleşme: 3 örnek minimum
    assert MIN_SAMPLES == 3


def test_prompt_version_pinned() -> None:
    assert PROMPT_VERSION == "1.0.0"
    # System prompt JSON şemasını içerir
    assert "ÇIKTI SADECE JSON" in SYSTEM_PROMPT
    assert "style_name" in SYSTEM_PROMPT
