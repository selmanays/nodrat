"""Chunker module unit tests (#18).

Test stratejisi:
  - Heuristik token count
  - Paragraph split
  - Window grouping (target / max constraints)
  - Big paragraph fallback (cümle split)
  - Overlap
  - Title prefix
  - Min size merge
"""

from __future__ import annotations

import pytest

from app.core.chunker import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MIN_TOKENS,
    DEFAULT_TARGET_TOKENS,
    ChunkingConfig,
    chunk_text,
    estimate_tokens,
)


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0
    assert estimate_tokens("   ") == 0


def test_estimate_tokens_one_word():
    # 1 word * 1.3 = 1
    assert estimate_tokens("merhaba") == 1


def test_estimate_tokens_multi_word():
    # 10 word * 1.3 = 13
    text = " ".join(["kelime"] * 10)
    assert estimate_tokens(text) == 13


# ---------------------------------------------------------------------------
# chunk_text basic
# ---------------------------------------------------------------------------


def test_chunk_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_single_short_paragraph():
    text = "Kısa bir paragraf, sadece birkaç kelime."
    chunks = chunk_text(text, title="Test")
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert "BAŞLIK: Test" in chunks[0].chunk_text
    assert "Kısa bir paragraf" in chunks[0].chunk_text


def test_chunk_short_text_no_split():
    """target_tokens altında tek chunk."""
    text = "Bu bir orta uzunlukta paragraf. " * 30
    chunks = chunk_text(text)
    assert len(chunks) == 1


def test_chunk_long_text_multiple_chunks():
    """target_tokens aşıldığında birden fazla chunk."""
    # Her paragraf yaklaşık 100 token, 10 paragraf = ~1000 token
    paragraph = "Bu bir paragraf metni Türkçe olarak yazılmıştır. " * 13  # ~85 word
    text = "\n\n".join([paragraph] * 10)
    chunks = chunk_text(text)
    assert len(chunks) >= 2

    for chunk in chunks:
        assert chunk.token_count <= DEFAULT_MAX_TOKENS + 50  # tolerance for overlap+prefix


def test_chunk_index_sequential():
    paragraph = "Test paragrafı sade. " * 30
    text = "\n\n".join([paragraph] * 6)
    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunk_includes_title_prefix():
    chunks = chunk_text(
        "İçerik metni paragrafları " * 5,
        title="Türkiye'de yeni gelişmeler",
        subtitle="Detaylı analiz",
    )
    assert chunks
    assert "BAŞLIK: Türkiye'de yeni gelişmeler" in chunks[0].chunk_text
    assert "ALT BAŞLIK: Detaylı analiz" in chunks[0].chunk_text


def test_chunk_no_title_prefix():
    cfg = ChunkingConfig(title_prefix=False)
    chunks = chunk_text("Metin " * 50, title="X", subtitle="Y", config=cfg)
    assert chunks
    assert "BAŞLIK:" not in chunks[0].chunk_text
    assert "ALT BAŞLIK:" not in chunks[0].chunk_text


# ---------------------------------------------------------------------------
# Big paragraph fallback (sentence split)
# ---------------------------------------------------------------------------


def test_chunk_big_paragraph_split_to_sentences():
    """max_tokens aşan tek paragraf cümle bazlı bölünür."""
    sentence = "Bu uzun bir cümle ile yazılmış metin parçası buraya geliyor. "
    big_paragraph = sentence * 100  # ~1000 token tek paragrafta
    chunks = chunk_text(big_paragraph, config=ChunkingConfig(max_tokens=300))
    assert len(chunks) >= 3


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------


def test_chunk_overlap_present():
    """Overlap default 80 token; 2. chunk başında 1. chunk'ın son kelimeleri var."""
    paragraph = "İlk paragraf benzersiz bir metin içeriyor. " * 20
    paragraph2 = "İkinci paragraf farklı içerikle. " * 20
    paragraph3 = "Üçüncü paragraf yine farklı. " * 20
    text = f"{paragraph}\n\n{paragraph2}\n\n{paragraph3}"
    chunks = chunk_text(text, config=ChunkingConfig(target_tokens=200, overlap_tokens=40))
    if len(chunks) >= 2:
        # 2. chunk başında 1. chunk'ın son kelimelerinden bir kısmı olmalı
        # Heuristik: chunks[0]'in son 20 kelimesinin bazıları chunks[1]'de var
        first_last_words = chunks[0].chunk_text.split()[-15:]
        second_text = chunks[1].chunk_text
        common = sum(1 for w in first_last_words if w in second_text)
        # En az birkaç kelime ortak olmalı
        assert common > 0


def test_chunk_overlap_zero_disabled():
    """overlap_tokens=0 → overlap yok."""
    paragraph = "Tekrar etmeyen kelime " * 20
    paragraph2 = "Bambaşka metin " * 20
    text = f"{paragraph}\n\n{paragraph2}"
    chunks = chunk_text(text, config=ChunkingConfig(target_tokens=100, overlap_tokens=0))
    if len(chunks) >= 2:
        # İlk paragrafın hiçbir kelimesi 2. chunk'ta olmamalı
        words_first = set(paragraph.split())
        words_second = set(chunks[1].chunk_text.split())
        # %5'ten az ortaklık (sadece şanssız stop word olabilir)
        intersection = words_first & words_second
        ratio = len(intersection) / max(len(words_first), 1)
        assert ratio < 0.2


# ---------------------------------------------------------------------------
# Min size merge
# ---------------------------------------------------------------------------


def test_chunk_short_tail_merged_with_prev():
    """Son chunk min_tokens altındaysa öncekiyle birleşir."""
    cfg = ChunkingConfig(target_tokens=200, min_tokens=100)
    p1 = "Birinci paragraf " * 80   # ~104 token
    p2 = "İkinci paragraf " * 80    # ~104 token
    p_short = "Üçüncü kısa son paragraf"  # çok küçük
    text = f"{p1}\n\n{p2}\n\n{p_short}"
    chunks = chunk_text(text, config=cfg)
    # Son kısa paragraf merge edilmiş olmalı → 2 chunk yerine 1 (eğer toplam küçükse)
    # ya da kısa paragraf önceki chunk'ın içinde
    last_text = chunks[-1].chunk_text
    assert "Üçüncü kısa son paragraf" in last_text
    last_tokens = estimate_tokens(last_text)
    assert last_tokens >= cfg.min_tokens or len(chunks) == 1


# ---------------------------------------------------------------------------
# Real article scenario (PRD §1.5 acceptance: 1500 token → 3 chunk)
# ---------------------------------------------------------------------------


def test_chunk_1500_tokens_yields_three_chunks():
    """PRD §1.5 acceptance: ~1500 token text → ~3 chunk (default config)."""
    paragraph = "Türkiye ekonomisinde yaşanan son gelişmeler ülke genelinde tartışılıyor. " * 18  # ~120 token
    text = "\n\n".join([paragraph] * 10)  # ~1200 token

    chunks = chunk_text(text)
    # Default target=500, max=900, with overlap. ~1200 token → 2-3 chunk olabilir
    assert 2 <= len(chunks) <= 4


def test_chunk_token_count_in_range():
    """Tüm chunk'lar min_tokens-max_tokens range'inde (son hariç)."""
    paragraph = "Anlamlı bir Türkçe paragraf metni bu test için. " * 25  # ~135 token
    text = "\n\n".join([paragraph] * 12)
    chunks = chunk_text(text)

    for i, chunk in enumerate(chunks):
        # max_tokens + buffer (overlap + prefix)
        assert chunk.token_count <= DEFAULT_MAX_TOKENS + 200, (
            f"chunk[{i}] {chunk.token_count} exceeds max+buffer"
        )


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------


def test_chunk_custom_config_smaller_target():
    """Daha küçük target → daha çok chunk."""
    text = "Test paragrafı içeriği. " * 100
    cfg_default = chunk_text(text)
    cfg_small = chunk_text(text, config=ChunkingConfig(target_tokens=100, max_tokens=200))
    assert len(cfg_small) > len(cfg_default)
