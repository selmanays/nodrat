"""Unit tests for answer_quality refusal detection (#819 Faz 2 follow-up)."""

from __future__ import annotations

import pytest

from app.core.answer_quality import is_answer_refusal


# =============================================================================
# Refusal detected (TRUE)
# =============================================================================


@pytest.mark.parametrize(
    "answer",
    [
        # Birincil pattern — prompt'tan direkt çıkış
        "Verilen kaynaklarda bu bilgi yer almıyor.",
        "Verilen kaynaklarda Donald Trump'ın yaşına dair herhangi bir bilgi bulunmuyor [1][4][9].",
        "Verilen kaynaklarda bu konu hakkında bilgi mevcut değil.",
        # "kaynaklarda" + olumsuzluk varyantları
        "Bu konuda kaynaklarda yeterli bilgi yer almıyor.",
        "Kaynaklarda Trump'ın yaşı hakkında bilgi bulunmuyor.",
        "Maalesef kaynaklarda bu detay içermiyor.",
        # Refusal direkt ifadeleri
        "Bu konuda yeterli bilgi yok.",
        "Yeterli veri bulunmuyor.",
        "Elimde bu bilgi yok şu anda.",
        "Trump'ın yaşı hakkında bilgi yok.",
        # Mixed (cevap içinde refusal + citation)
        "Trump İran konusunda açıklama yaptı [1]. Ancak yaşına dair bilgi bulunmuyor [2].",
        # Genişletilmiş Türkçe varyantlar
        "Bu konuda kaynaklarda bilgi mevcut değildir.",
        "Verilen kaynaklarda yaş bilgisi içermiyor.",
    ],
)
def test_refusal_detected(answer: str):
    is_refusal, pattern = is_answer_refusal(answer)
    assert is_refusal is True, f"Expected refusal but missed: {answer}"
    assert pattern is not None


# =============================================================================
# Normal answer (FALSE)
# =============================================================================


@pytest.mark.parametrize(
    "answer",
    [
        # Normal haber cevabı (kaynaklı, refusal yok)
        "Trump bugün Çin ziyareti kapsamında Boeing ile 200 uçaklık anlaşma yaptı [1].",
        "Kaynaklar [1][2][3] son gelişmeleri ele alıyor.",
        # Kısa cevap
        "Trump Beyaz Saray'da açıklama yaptı [1].",
        # Çoklu kaynak sentezi
        "İlk kaynak [1] X derken, ikinci kaynak [2] Y diyor.",
        # Boş veya çok kısa
        "",
        "Tamam.",
        # "kaynaklarda" geçiyor ama olumsuzluk yok
        "Kaynaklarda Trump'ın açıklaması detaylı şekilde anlatılıyor [1].",
        # "bilgi yok" geçmiyor
        "Trump'ın yaşı bu bağlamda önemsiz [1].",
    ],
)
def test_normal_answer_no_refusal(answer: str):
    is_refusal, pattern = is_answer_refusal(answer)
    assert is_refusal is False, (
        f"False positive — pattern '{pattern}' matched on normal answer: {answer}"
    )


# =============================================================================
# Edge cases
# =============================================================================


def test_none_returns_false():
    is_refusal, pattern = is_answer_refusal(None)  # type: ignore[arg-type]
    assert is_refusal is False
    assert pattern is None


def test_empty_string_returns_false():
    is_refusal, pattern = is_answer_refusal("")
    assert is_refusal is False
    assert pattern is None


def test_whitespace_only_returns_false():
    is_refusal, pattern = is_answer_refusal("   \n\t  ")
    assert is_refusal is False


def test_case_insensitive():
    """Case farklı olsa da pattern match etmeli."""
    is_refusal_a, _ = is_answer_refusal("VERİLEN KAYNAKLARDA BİLGİ YOK.")
    is_refusal_b, _ = is_answer_refusal("Verilen Kaynaklarda Bilgi Yok.")
    is_refusal_c, _ = is_answer_refusal("verilen kaynaklarda bilgi yok.")
    assert is_refusal_a is True
    assert is_refusal_b is True
    assert is_refusal_c is True


def test_multiline_answer():
    """Cevap çok satırlı olsa da DOTALL flag ile yakalanmalı."""
    multiline = """Bu konu hakkında bilgi vermek istedim ancak

verilen kaynaklarda yeterli detay yer almıyor.

Yeni bir sorgu deneyebilirsiniz."""
    is_refusal, _ = is_answer_refusal(multiline)
    assert is_refusal is True
