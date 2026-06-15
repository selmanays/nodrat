"""Unit — ExtractedArticle.apply_title_fallback (#1529).

Sayfa başlık vermediğinde keşif (RSS/sitemap/card) başlığını fallback kullan;
text/conf gate korunur, dolu title override edilmez.
"""

from __future__ import annotations

from app.shared.extraction.extractor import MIN_TEXT_LENGTH, ExtractedArticle

_GOOD_TEXT = "x" * (MIN_TEXT_LENGTH + 50)


def _art(title: str = "", text: str = _GOOD_TEXT, conf: float = 0.5) -> ExtractedArticle:
    return ExtractedArticle(
        url="https://example.com/a", title=title, clean_text=text, extraction_confidence=conf
    )


def test_fallback_fills_empty_title_and_makes_successful() -> None:
    art = _art(title="")
    assert art.successful is False  # title boş → başarısız
    art.apply_title_fallback("Gerçek Başlık")
    assert art.title == "Gerçek Başlık"
    assert art.successful is True  # artık title var + text/conf ok


def test_fallback_does_not_override_existing_title() -> None:
    art = _art(title="Var Olan Başlık")
    art.apply_title_fallback("Yeni Başlık")
    assert art.title == "Var Olan Başlık"


def test_fallback_empty_or_blank_does_nothing() -> None:
    art = _art(title="")
    art.apply_title_fallback("")
    assert art.title == ""
    art.apply_title_fallback("   ")
    assert art.title == ""
    assert art.successful is False


def test_fallback_respects_conf_gate() -> None:
    art = _art(title="", conf=0.2)  # conf < 0.3
    art.apply_title_fallback("Başlık")
    assert art.title == "Başlık"
    assert art.successful is False  # title geldi ama conf gate düşürür


def test_fallback_respects_text_length_gate() -> None:
    art = _art(title="", text="kısa metin")  # < MIN_TEXT_LENGTH
    art.apply_title_fallback("Başlık")
    assert art.title == "Başlık"
    assert art.successful is False  # title geldi ama text çok kısa
