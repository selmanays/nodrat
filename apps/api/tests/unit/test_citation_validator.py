"""Unit tests for citation validator (#180)."""

from __future__ import annotations

import pytest

from app.core.citation import (
    SourceFragment,
    cited_only_sources,
    cosine_sim,
    extract_citation_ids,
    repair_bad_citation_formats,
    split_sentences,
    validate_citations,
)


# ---------------------------------------------------------------------------
# repair_bad_citation_formats
# ---------------------------------------------------------------------------


def test_repair_id_format():
    cleaned, n = repair_bad_citation_formats("Şuraya bakın [ID:12] ve [ID: 3]")
    assert cleaned == "Şuraya bakın [#12] ve [#3]"
    assert n == 2


def test_repair_paren_id():
    cleaned, n = repair_bad_citation_formats("Habertürk haberi (ID:5)")
    assert cleaned == "Habertürk haberi [#5]"
    assert n == 1


def test_repair_kaynak_format():
    cleaned, n = repair_bad_citation_formats("(kaynak: 7) ve [kaynak 9]")
    assert "[#7]" in cleaned
    assert "[#9]" in cleaned
    assert n == 2


def test_repair_ref_format():
    cleaned, n = repair_bad_citation_formats("[ref:2] yazısı veya (ref 4)")
    assert cleaned == "[#2] yazısı veya [#4]"
    assert n == 2


def test_repair_source_english():
    cleaned, n = repair_bad_citation_formats("[source:1] başvurun")
    assert cleaned == "[#1] başvurun"
    assert n == 1


def test_repair_already_correct_unchanged():
    cleaned, n = repair_bad_citation_formats("[#1] ve [#2]")
    assert cleaned == "[#1] ve [#2]"
    assert n == 0


def test_repair_empty():
    cleaned, n = repair_bad_citation_formats("")
    assert cleaned == ""
    assert n == 0


# ---------------------------------------------------------------------------
# extract_citation_ids
# ---------------------------------------------------------------------------


def test_extract_unique_sorted():
    assert extract_citation_ids("[#1] [#3] [#1] [#2]") == [1, 3, 2]


def test_extract_empty():
    assert extract_citation_ids("citation yok") == []
    assert extract_citation_ids("") == []


# ---------------------------------------------------------------------------
# split_sentences (Türkçe)
# ---------------------------------------------------------------------------


def test_split_basic():
    s = "Bu birinci cümle. İkinci cümle de var. Son cümle!"
    sentences = split_sentences(s)
    assert len(sentences) == 3


def test_split_question_exclaim():
    s = "Ne dediniz? Evet doğru! Tamam o zaman."
    assert len(split_sentences(s)) == 3


def test_split_handles_abbreviation_dr():
    s = "Dr. Ali geldi. Yeni bir hasta var."
    sentences = split_sentences(s)
    # "Dr." kısaltması cümle ayırıcı sayılmamalı
    assert len(sentences) == 2
    assert sentences[0].startswith("Dr.")


def test_split_empty():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


# ---------------------------------------------------------------------------
# cosine_sim
# ---------------------------------------------------------------------------


def test_cosine_identical():
    a = [1.0, 0.0, 0.0]
    assert cosine_sim(a, a) == 1.0


def test_cosine_orthogonal():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert cosine_sim(a, b) == 0.0


def test_cosine_zero_vector():
    assert cosine_sim([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_dim_mismatch():
    assert cosine_sim([1.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# cited_only_sources
# ---------------------------------------------------------------------------


def test_cited_only_filters_unused():
    sources = [
        SourceFragment(id=1, title="A"),
        SourceFragment(id=2, title="B"),
        SourceFragment(id=3, title="C"),
    ]
    text = "[#1] ve [#3]"
    out = cited_only_sources(text, sources)
    assert {s.id for s in out} == {1, 3}


def test_cited_only_no_citations_returns_all():
    sources = [SourceFragment(id=1, title="A"), SourceFragment(id=2, title="B")]
    text = "citation yok"
    out = cited_only_sources(text, sources)
    assert len(out) == 2


# ---------------------------------------------------------------------------
# validate_citations — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_format_only_when_embed_unavailable():
    """embed_fn None döndürürse format-only fallback davranışı."""
    sources = [SourceFragment(id=1, title="Emekli zammı")]

    async def fake_embed(_inputs):
        return None

    text = "Emekli zammı yüzde 10 oldu [#1]. Memur zammı belirsiz."
    report = await validate_citations(
        text, sources=sources, embed_fn=fake_embed, cosine_threshold=0.5
    )
    assert report.repair_count == 0
    assert len(report.claims) == 2
    # İlk cümle citation içeriyor → supported (format-only)
    assert report.claims[0].supported is True
    # İkinci cümle citation YOK → unsupported
    assert report.claims[1].supported is False
    assert report.unsupported_count == 1


@pytest.mark.asyncio
async def test_validate_with_strong_cosine():
    """cosine yüksek ise supported."""
    sources = [SourceFragment(id=1, title="Emekli zammı yüzde 10")]

    async def fake_embed(inputs):
        # 2 sentence + 1 source = 3 vector
        # cosine 1.0 olsun (identical)
        return [[1.0, 0.0, 0.0]] * len(inputs)

    text = "Emekli zammı [#1] olarak açıklandı. Detay yok."
    report = await validate_citations(
        text, sources=sources, embed_fn=fake_embed, cosine_threshold=0.5
    )
    # Tüm cümleler %100 cosine (fake) → supported
    assert all(c.supported for c in report.claims)


@pytest.mark.asyncio
async def test_validate_repair_then_validate():
    """Repair + validate akışı."""
    sources = [SourceFragment(id=2, title="X")]

    async def fake_embed(_inputs):
        return None  # format-only fallback

    text = "Habere göre [ID:2] kararlaştırıldı."
    report = await validate_citations(
        text, sources=sources, embed_fn=fake_embed
    )
    assert report.repair_count == 1
    assert "[#2]" in report.cleaned_text
    assert 2 in report.cited_source_ids
