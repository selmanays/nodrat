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
    validate_citations_batch,
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

    # validate_citations min_sentence_words=4 (default) → 4 kelimeden kısa
    # cümleler claim sayılmaz. 2. cümle ≥4 kelime olmalı ki uncited→
    # unsupported davranışı test edilebilsin (eski "Memur zammı belirsiz."
    # = 3 kelime, filtreye takılıyordu → stale fixture).
    text = "Emekli zammı yüzde 10 oldu [#1]. Memur zammı ise henüz belirsiz."
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
    report = await validate_citations(text, sources=sources, embed_fn=fake_embed)
    assert report.repair_count == 1
    assert "[#2]" in report.cleaned_text
    assert 2 in report.cited_source_ids


# ---------------------------------------------------------------------------
# validate_citations_batch — #394 MVP-2.1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_empty_texts():
    """Empty texts list — boş liste döner."""
    sources = [SourceFragment(id=1, title="X")]

    async def fake_embed(_):
        return None

    reports = await validate_citations_batch([], sources=sources, embed_fn=fake_embed)
    assert reports == []


@pytest.mark.asyncio
async def test_batch_format_only_fallback():
    """embed_fn None döndürürse her metin için format-only validation.

    Note: split_sentences + min_sentence_words=4 filter; her cümle ≥4 kelime olmalı.
    """
    sources = [SourceFragment(id=1, title="A"), SourceFragment(id=2, title="B")]

    async def fake_embed(_):
        return None

    texts = [
        "Birinci cümle citation içeriyor [#1] olarak güvenli. Ikincisi citation içermez kaynak yok.",
        "Sadece şu citation referansı [#2] güvenli kaynak içerir.",
    ]
    reports = await validate_citations_batch(
        texts, sources=sources, embed_fn=fake_embed, cosine_threshold=0.5
    )
    assert len(reports) == 2
    # İlk metin: 2 cümle, 1 unsupported (citation yok olan ikinci cümle)
    assert reports[0].unsupported_count == 1
    # İkinci metin: 1 cümle, supported (citation var)
    assert reports[1].unsupported_count == 0


@pytest.mark.asyncio
async def test_batch_equivalence_with_single():
    """Batch çağrısı, tek-tek validate_citations çağrılarıyla eşdeğer rapor üretir."""
    sources = [SourceFragment(id=1, title="Emekli zammı yüzde 10 oldu")]

    call_log: list[int] = []

    async def fake_embed(inputs):
        call_log.append(len(inputs))
        # Sabit yüksek-cosine vektör
        return [[1.0, 0.0, 0.0]] * len(inputs)

    texts = [
        "Emekli zammı [#1] olarak açıklandı.",
        "Memur zammı [#1] da yakında belli olacak.",
    ]

    # Batch
    call_log.clear()
    batch_reports = await validate_citations_batch(
        texts, sources=sources, embed_fn=fake_embed, cosine_threshold=0.5
    )
    batch_calls = len(call_log)

    # Tek tek
    call_log.clear()
    individual_reports = []
    for t in texts:
        r = await validate_citations(t, sources=sources, embed_fn=fake_embed, cosine_threshold=0.5)
        individual_reports.append(r)
    individual_calls = len(call_log)

    # Equivalence: aynı sayıda rapor, aynı supported claim sayıları, aynı cleaned text
    assert len(batch_reports) == len(individual_reports)
    for b, i in zip(batch_reports, individual_reports, strict=False):
        assert b.cleaned_text == i.cleaned_text
        assert b.repair_count == i.repair_count
        assert b.unsupported_count == i.unsupported_count
        assert len(b.claims) == len(i.claims)

    # Batch optimization: 1 embed call (batch) vs 2 (individual)
    assert batch_calls == 1
    assert individual_calls == len(texts)


@pytest.mark.asyncio
async def test_batch_repair_aggregation():
    """Her metin için repair_count ayrı raporlanır."""
    sources = [SourceFragment(id=1, title="X"), SourceFragment(id=2, title="Y")]

    async def fake_embed(_):
        return None

    texts = [
        "İlk metin [ID:1] formatı kötü.",  # 1 repair
        "İkinci metin [#2] formatı temiz.",  # 0 repair
    ]
    reports = await validate_citations_batch(texts, sources=sources, embed_fn=fake_embed)
    assert reports[0].repair_count == 1
    assert reports[1].repair_count == 0
    assert "[#1]" in reports[0].cleaned_text


# ---------------------------------------------------------------------------
# validate_citations_batch — #398 MVP-2.1 source embedding reuse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_source_embedding_reuse_skips_embed_for_sources():
    """Source.embedding pre-set ise embed_fn sadece sentence'lar için çağrılır."""
    # Sources have pre-existing embedding (1024-dim)
    pre_emb = [1.0, 0.0, 0.0] + [0.0] * 1021
    sources = [
        SourceFragment(id=1, title="Konu 1", embedding=pre_emb),
        SourceFragment(id=2, title="Konu 2", embedding=pre_emb),
    ]

    received_inputs: list[list[str]] = []

    async def tracking_embed(inputs):
        received_inputs.append(list(inputs))
        # Sentence + (varsa) ek source. Her input için identical 1024-dim vektör
        return [pre_emb for _ in inputs]

    texts = [
        "Birinci cümle citation içeriyor [#1] olarak güvenli kaynak.",
        "İkinci metnin tek cümlesi referans [#2] içerir kaynaklar var.",
    ]
    reports = await validate_citations_batch(
        texts, sources=sources, embed_fn=tracking_embed, cosine_threshold=0.5
    )

    # Embed'a giden input sayısı SADECE sentence sayısı kadar (sources zaten embedded)
    assert len(received_inputs) == 1, "Tek embed_fn çağrısı bekleniyor"
    n_sentences = sum(len(r.claims) for r in reports)
    assert len(received_inputs[0]) == n_sentences, (
        f"Source'lar zaten embedded; embed_fn'e sadece {n_sentences} cümle gitmeli, "
        f"gerçekte {len(received_inputs[0])} input gitti"
    )
    # Tüm raporlar üretilmiş (1024-dim vektörler match → high cosine → supported)
    assert len(reports) == 2


@pytest.mark.asyncio
async def test_batch_source_embedding_partial_reuse():
    """Bazı source'larda embedding var, bazılarında yok — kısmi reuse."""
    pre_emb = [1.0] + [0.0] * 1023
    sources = [
        SourceFragment(id=1, title="A", embedding=pre_emb),  # pre-existing
        SourceFragment(id=2, title="B", embedding=None),  # embed_fn'e gider
        SourceFragment(id=3, title="C", embedding=[0.5] + [0.0] * 1022),  # WRONG dim → embed_fn
    ]

    embed_calls: list[int] = []

    async def tracking_embed(inputs):
        embed_calls.append(len(inputs))
        return [[0.0] * 1024 for _ in inputs]

    texts = ["İlk cümle citation [#1] referansıyla bazı bilgiler var burada."]
    reports = await validate_citations_batch(texts, sources=sources, embed_fn=tracking_embed)

    # Beklenen: 1 sentence + 2 source (id=2 ve id=3 eksik/yanlış-dim) = 3 input
    assert embed_calls == [3], f"Beklenen [3], gerçek: {embed_calls}"
    assert len(reports) == 1


@pytest.mark.asyncio
async def test_batch_source_embedding_invalid_dim_falls_back():
    """Source.embedding boyut yanlışsa (≠1024) embed_fn fallback."""
    sources = [
        SourceFragment(id=1, title="X", embedding=[0.1, 0.2]),  # 2-dim, geçersiz
    ]
    embed_calls: list[int] = []

    async def tracking_embed(inputs):
        embed_calls.append(len(inputs))
        return [[0.0] * 1024 for _ in inputs]

    texts = ["Test cümlesi yeterince uzun citation [#1] içerir bu cümle."]
    await validate_citations_batch(texts, sources=sources, embed_fn=tracking_embed)
    # 1 sentence + 1 source (geçersiz dim → re-embed) = 2 input
    assert embed_calls == [2]


# ---------------------------------------------------------------------------
# QueryPlan.is_short_query — #396 MVP-2.1
# ---------------------------------------------------------------------------


def test_query_plan_is_short_query_flag():
    """topic_query ≤2 kelime ise is_short_query=True."""
    from app.prompts.query_planner import parse_response

    plan_short = parse_response(
        '{"intent":"current_content_generation","topic_query":"CHP","mode":"current","timeframes":[],"output_type":"x_post","tone":null,"constraints":[],"needs_sources":true,"keywords":[]}'
    )
    from app.prompts.query_planner import QueryPlan as _QP

    assert isinstance(plan_short, _QP)
    assert plan_short.is_short_query is True

    plan_short2 = parse_response(
        '{"intent":"current_content_generation","topic_query":"İmamoğlu davası","mode":"current","timeframes":[],"output_type":"x_post","tone":null,"constraints":[],"needs_sources":true,"keywords":[]}'
    )
    assert isinstance(plan_short2, _QP)
    assert plan_short2.is_short_query is True

    plan_long = parse_response(
        '{"intent":"current_content_generation","topic_query":"Türkiye ekonomisi enflasyon görünümü","mode":"current","timeframes":[],"output_type":"x_post","tone":null,"constraints":[],"needs_sources":true,"keywords":[]}'
    )
    assert isinstance(plan_long, _QP)
    assert plan_long.is_short_query is False
