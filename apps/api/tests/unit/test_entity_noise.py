"""#1598 — NER gürültü filtresi (common-word mis-NER) deterministik testleri.

Saf/DB'siz. is_noise_entity hem NER ingest hem küme çapasını besler → trend ve
küme aynı temiz entity tabanını paylaşır.
"""

from __future__ import annotations

import pytest
from app.core.entity_noise import NER_NOISE_STOPWORDS, _fold, is_noise_entity


@pytest.mark.parametrize(
    "word",
    ["var", "yok", "bugün", "dün", "zaman", "şey", "açıklama", "haber", "olmuş", "sonuç"],
)
def test_is_noise_entity_catches_function_words(word: str):
    assert is_noise_entity(word) is True


@pytest.mark.parametrize("word", ["VAR", "Bugün", "BUGÜN", " var ", "Zaman"])
def test_is_noise_entity_case_and_fold_robust(word: str):
    # _fold: lower + TR→ASCII + combining-mark strip → büyük/küçük + aksan dayanıklı
    assert is_noise_entity(word) is True


@pytest.mark.parametrize(
    "word",
    [
        "donald trump",
        "cumhuriyet halk partisi",
        "hürmüz boğazı",
        "küba",  # legit yer — yanlış-eleme veri kaybı olurdu
        "borsa",  # belirsiz → KASITLA listede yok
        "elektrik",
        "özgür özel",
        "merkez bankası",
    ],
)
def test_is_noise_entity_keeps_real_entities(word: str):
    assert is_noise_entity(word) is False


def test_is_noise_entity_empty_and_none():
    assert is_noise_entity("") is False
    assert is_noise_entity(None) is False


def test_fold_turkish_combining_dot():
    # "BİLGİ".lower() → combining-dot'lu "i̇"; fold ASCII "bilgi" üretmeli
    assert _fold("BİLGİ") == "bilgi"
    assert _fold("bilgi") in NER_NOISE_STOPWORDS
