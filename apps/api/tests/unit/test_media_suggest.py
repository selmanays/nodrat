"""Unit tests for media_suggest (#305 MVP-1.4 PR-5).

Pure-Python tokenization + Jaccard scoring — DB layer mock'lanır.
"""

from __future__ import annotations

from app.core.media_suggest import _jaccard, _tokenize


# =============================================================================
# Tokenizer
# =============================================================================


def test_tokenize_lowercase_strips_punct() -> None:
    tokens = _tokenize("Erdoğan, Ankara'da konuştu!")
    assert "erdoğan" in tokens
    assert "ankara" in tokens
    # 'da' stopword
    assert "da" not in tokens
    assert "konuştu" in tokens


def test_tokenize_stopwords_filtered() -> None:
    tokens = _tokenize("bu bir cumhurbaşkanı haberi ve önemli")
    # Türkçe stopword'ler düşmeli
    assert "bu" not in tokens
    assert "ve" not in tokens
    assert "bir" not in tokens
    # İçerik kelimeleri kalmalı
    assert "cumhurbaşkanı" in tokens
    assert "haberi" in tokens
    assert "önemli" in tokens


def test_tokenize_min_length_3() -> None:
    tokens = _tokenize("AB ile ilgili bilgi")
    # 'ab' (2 harf) düşer, 'ile' stopword
    assert "ab" not in tokens
    assert "ile" not in tokens
    assert "ilgili" in tokens
    assert "bilgi" in tokens


def test_tokenize_empty() -> None:
    assert _tokenize("") == set()
    assert _tokenize("ve bu bir") == set()  # tüm stopword


def test_tokenize_numbers_kept() -> None:
    tokens = _tokenize("2026 yılında 100 milyon")
    assert "2026" in tokens
    assert "100" in tokens
    assert "milyon" in tokens


# =============================================================================
# Jaccard
# =============================================================================


def test_jaccard_identical_sets() -> None:
    s = {"erdoğan", "ankara"}
    assert _jaccard(s, s) == 1.0


def test_jaccard_disjoint() -> None:
    a = {"erdoğan", "ankara"}
    b = {"meclis", "milletvekili"}
    assert _jaccard(a, b) == 0.0


def test_jaccard_partial_overlap() -> None:
    a = {"erdoğan", "ankara", "meclis"}
    b = {"erdoğan", "ankara", "konuşma"}
    # intersection: 2 (erdoğan, ankara)
    # union: 4 (erdoğan, ankara, meclis, konuşma)
    assert _jaccard(a, b) == 0.5


def test_jaccard_empty_inputs() -> None:
    assert _jaccard(set(), {"a"}) == 0.0
    assert _jaccard({"a"}, set()) == 0.0
    assert _jaccard(set(), set()) == 0.0


# =============================================================================
# Smoke (pure functions — DB integration tests'te real test'i koş)
# =============================================================================


def test_post_token_overlap_with_vlm_caption() -> None:
    """Post text 'Erdoğan ekonomi konuştu' ile vlm_caption 'Erdoğan ekonomi
    açıklaması yapıyor' yüksek skorla eşleşmeli."""
    post = _tokenize("Erdoğan ekonomi konuştu")
    img_text = _tokenize("Erdoğan ekonomi açıklaması yapıyor")
    score = _jaccard(post, img_text)
    # En az bir entity ortak (erdoğan, ekonomi)
    assert score > 0.0
    # 2 ortak / (3+4-2)=5 = 0.4
    assert 0.3 < score < 0.5


def test_post_unrelated_to_image_low_score() -> None:
    """Spor haberinin görseli ekonomi post'una benzemesin."""
    post = _tokenize("ekonomi büyüme rakamları")
    img_text = _tokenize("futbolcu maçta gol attı")
    score = _jaccard(post, img_text)
    assert score == 0.0  # hiç overlap yok
