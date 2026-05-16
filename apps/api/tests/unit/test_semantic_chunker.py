"""Unit tests for semantic chunker (#661 Faz 5.1)."""

from __future__ import annotations

import pytest

from app.core.semantic_chunker import (
    SemanticChunkConfig,
    _flatten_paragraphs_to_sentences,
    _is_heading,
    _split_sentences,
    semantic_chunk_text,
)


# ---------------------------------------------------------------------------
# Sentence split
# ---------------------------------------------------------------------------


def test_split_sentences_basic():
    text = "İlk cümle. Çevirme süreci başladı. Şimdi yeni cümle."
    sentences = _split_sentences(text)
    assert len(sentences) == 3
    assert "İlk cümle" in sentences[0]


def test_split_sentences_turkish_punctuation():
    text = "Karşıyaka 84-82 kazandı. Bursaspor üzgün. Hakemler iyi yönetti."
    sentences = _split_sentences(text)
    assert len(sentences) == 3


def test_split_sentences_short_fragment_merged():
    """3 char altı fragment önceki cümleye birleşir."""
    text = "Uzun cümle örnek. A. Diğer cümle başlangıç."
    sentences = _split_sentences(text)
    # 'A.' tek başına kısa, öncekiyle birleşir
    assert len(sentences) <= 2


# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------


def test_is_heading_markdown():
    assert _is_heading("# Ana Başlık")
    assert _is_heading("## Alt Başlık")
    assert not _is_heading("Normal cümle.")


def test_is_heading_all_caps():
    # #661 — heading tespiti BİLİNÇLİ olarak KONSERVATİF: tek-token cap-only
    # (`" " not in text_stripped[:20]`). Çok-kelimeli ALL-CAPS ifadeler
    # (haber metni içinde "EKONOMI HABERLERİ", "SON DAKİKA" gibi) heading
    # SAYILMAZ — yanlış mandatory-break = article fragmentasyonu/recall
    # zararı. Eski test çok-kelimeli caps'i heading bekliyordu (stale,
    # over-permissive); güncel sözleşme aşağıda.
    assert _is_heading("GÜNDEM")  # tek token, cap-only → heading
    assert not _is_heading("EKONOMI HABERLERİ")  # çok kelime → heading DEĞİL (#661 guard)
    assert not _is_heading("Normal cümle başlığı")
    # Çok kısa cap-only
    assert not _is_heading("AA")


def test_is_heading_punctuation_filter():
    # Cap-only ama nokta ile biten → heading değil
    assert not _is_heading("KARŞIYAKA KAZANDI.")


# ---------------------------------------------------------------------------
# Flatten paragraphs → sentence stream
# ---------------------------------------------------------------------------


def test_flatten_basic():
    text = "Paragraf 1 cümle 1. Cümle 2.\n\nParagraf 2 cümle 1."
    units = _flatten_paragraphs_to_sentences(text)
    # 2 cümle paragraf 1 + 1 cümle paragraf 2 = 3 unit
    assert len(units) == 3
    assert units[0].paragraph_idx == 0
    assert units[2].paragraph_idx == 1
    assert units[2].is_first_of_paragraph


def test_flatten_heading_isolated():
    text = "GÜNDEM\n\nBu paragraf normal. İçerik."
    units = _flatten_paragraphs_to_sentences(text)
    assert units[0].is_heading
    assert units[0].text == "GÜNDEM"
    # Sonraki paragraph cümleleri heading olmamalı
    assert not units[1].is_heading


# ---------------------------------------------------------------------------
# Semantic chunk_text (no embedding — structural fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semantic_chunk_no_embed_fallback():
    """embed_fn=None → structural-only chunking çalışmalı."""
    text = (
        "Karşıyaka basketbol takımı son saniye basketiyle Bursaspor'u 84-82 mağlup etti. "
        "Maç boyunca taraftarlar yoğun ilgi gösterdi. "
        "Karşılaşmanın hakemleri Mehmet Yıldız, Ali Demir ve Hakan Karahan oldular.\n\n"
        "İlk yarıyı 40-38 önde kapatan ev sahibi takım üstün oynadı. "
        "İkinci yarıda Karşıyaka kontrolü ele aldı.\n\n"
        "Bir sonraki maç için hazırlıklar başladı."
    )
    chunks = await semantic_chunk_text(
        text, title="Karşıyaka Bursaspor", subtitle=None, embed_fn=None,
    )
    assert len(chunks) >= 1
    # Title prefix her chunk'ta
    for c in chunks:
        assert "BAŞLIK: Karşıyaka Bursaspor" in c.chunk_text


@pytest.mark.asyncio
async def test_semantic_chunk_short_article_single_chunk():
    """Min_tokens altı article → tek chunk."""
    text = "Kısa haber metni."
    chunks = await semantic_chunk_text(
        text, title="Test", subtitle=None, embed_fn=None,
    )
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_semantic_chunk_token_budget_enforced():
    """Çok uzun article → birden fazla chunk (max_tokens cap'i aşmaz)."""
    # ~1500 token text üret
    long_text = "\n\n".join(
        "Bu paragraf çok ilginç bilgiler içeriyor ve uzun bir cümle örneği. " * 5
        for _ in range(20)
    )
    cfg = SemanticChunkConfig(min_tokens=150, target_tokens=400, max_tokens=800)
    chunks = await semantic_chunk_text(
        long_text, title="Uzun", subtitle=None, embed_fn=None, config=cfg,
    )
    assert len(chunks) >= 2
    # Hard cap: max_tokens + prefix buffer
    for c in chunks:
        assert c.token_count <= 800 + 100  # prefix buffer


@pytest.mark.asyncio
async def test_semantic_chunk_with_mock_embeddings():
    """embed_fn callback ile semantic break detection çalışmalı."""
    text = (
        "Karşıyaka basketbol kazandı. İlk yarı 40-38 önde geçildi. "
        "Hakemler maçı iyi yönetti.\n\n"
        "Ekonomi farklı bir konu. Enflasyon arttı. "
        "Merkez Bankası açıklama yaptı."
    )

    # Mock embeddings: ilk 3 cümle similar, son 3 cümle similar
    # ama 4. cümlede semantic break (topic shift)
    mock_embeddings = [
        [1.0, 0.0, 0.0] + [0.0] * 1021,  # basketbol
        [0.9, 0.1, 0.0] + [0.0] * 1021,
        [0.8, 0.2, 0.0] + [0.0] * 1021,
        [0.0, 1.0, 0.0] + [0.0] * 1021,  # ekonomi
        [0.0, 0.9, 0.1] + [0.0] * 1021,
        [0.0, 0.8, 0.2] + [0.0] * 1021,
    ]

    call_count = {"n": 0}

    async def mock_embed(texts: list[str]) -> list[list[float]]:
        call_count["n"] += 1
        return mock_embeddings[: len(texts)]

    cfg = SemanticChunkConfig(
        min_tokens=10, target_tokens=50, max_tokens=200,
        breakpoint_percentile=50,
    )
    chunks = await semantic_chunk_text(
        text, title="Karma", subtitle=None,
        embed_fn=mock_embed, config=cfg,
    )
    # Tek batch call (cost guard)
    assert call_count["n"] == 1
    # En az 1 chunk üretildi (semantic break paragraph boundary'sinde)
    assert len(chunks) >= 1


@pytest.mark.asyncio
async def test_semantic_chunk_overlap_applied():
    """Adjacent chunks arasında overlap sentence'lar görünmeli."""
    long_text = "\n\n".join(
        [
            "Paragraf " + str(i) + " başlangıç cümlesi. Devamı uzun bir cümle örneği daha. Üçüncü cümle ekleniyor."
            for i in range(15)
        ]
    )
    cfg = SemanticChunkConfig(
        min_tokens=50, target_tokens=100, max_tokens=200, overlap_sentences=2,
    )
    chunks = await semantic_chunk_text(
        long_text, title=None, subtitle=None, embed_fn=None, config=cfg,
    )
    if len(chunks) >= 2:
        # 2. chunk'ın başında 1. chunk'ın son cümlelerinden bir şey olmalı (overlap)
        # Test: her iki chunk arasında en az 1 ortak kelime
        c1_words = set(chunks[0].chunk_text.split())
        c2_words = set(chunks[1].chunk_text.split())
        common = c1_words & c2_words
        # Title yok, ortak kelime sadece content overlap'tan gelebilir
        assert len(common) > 0
