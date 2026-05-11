"""Unit tests for rerank wrapper (#181, #251, #647)."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

import pytest

from app.core.rerank import (
    _build_passage,
    _entity_match_bonus,
    _extract_entity_candidates,
    rerank_rows,
)
from app.providers.base import RerankResult


def _patches(
    *,
    reranker_enabled: bool = True,
    min_combined: float = 0.0,
    min_query_words: int = 1,
    fake_provider=None,
):
    """Helper: tüm mock patch'leri tek context'te aç.

    Returns: ExitStack — caller `with _patches(...) as stack:` ile kullanır.
    """
    stack = ExitStack()
    gs = stack.enter_context(patch("app.core.rerank.get_settings"))
    gsf = stack.enter_context(patch("app.core.db.get_session_factory"))
    gs.return_value.reranker_enabled = reranker_enabled
    gs.return_value.rerank_min_combined_score = min_combined
    gs.return_value.rerank_min_query_words = min_query_words
    gsf.side_effect = RuntimeError("test: no db")
    if fake_provider is not None:
        route = stack.enter_context(
            patch("app.providers.registry.registry.route_for_tier")
        )
        route.return_value = fake_provider
    return stack


# ---------------------------------------------------------------------------
# _build_passage
# ---------------------------------------------------------------------------


def test_build_passage_title_summary():
    row = {"title": "Emekli zammı", "summary": "Yüzde 10 oldu"}
    assert _build_passage(row) == "Emekli zammı\n\nYüzde 10 oldu"


def test_build_passage_chunk_fallback():
    row = {"article_title": "X", "chunk_text": "Y içeriği"}
    assert _build_passage(row) == "X\n\nY içeriği"


def test_build_passage_only_title():
    row = {"title": "Sadece başlık"}
    assert _build_passage(row) == "Sadece başlık"


def test_build_passage_truncates():
    row = {"title": "x" * 500, "summary": "y" * 800}
    out = _build_passage(row)
    assert len(out) <= 800 + 2


# ---------------------------------------------------------------------------
# Entity-aware boost (#647 sistemik fix #3) — genel kural, vakaya özel kod yok
# ---------------------------------------------------------------------------


def test_entity_extract_basic():
    ents = _extract_entity_candidates("Toprakaltı sergisi ne zamandı")
    # min_len=5: "ne" filtrelenir, "sergisi" >=5 → kalır
    assert "toprakaltı" in ents
    assert "sergisi" in ents
    assert "ne" not in ents


def test_entity_extract_filters_stopwords():
    ents = _extract_entity_candidates("haberler hakkında bilgiler sun")
    # Tüm token'lar stop kelime listesinde → boş
    assert ents == []


def test_entity_extract_keeps_technical_tokens():
    ents = _extract_entity_candidates("F-16 21 ülke kim kazandı")
    assert "f-16" in ents
    assert "kazandı" in ents


def test_entity_extract_handles_quotes():
    # Smart-quote'lar normalize edilir (#647 root fix), entity yine çıkar
    ents = _extract_entity_candidates('"Toprakaltı" sergisi')
    assert "toprakaltı" in ents


def test_entity_extract_dedupes():
    ents = _extract_entity_candidates("Bayraktar Bayraktar bayraktar")
    assert ents.count("bayraktar") == 1


# ---------------------------------------------------------------------------
# #696 (C13) — Apostrof varyant testleri (#691 Faz 6.1 NER fix doğrulama)
# ---------------------------------------------------------------------------


def test_entity_extract_ascii_apostrophe_splits_possessive():
    """ASCII ' → SPACE çevrilir, possessive ek ayrı token olur."""
    ents = _extract_entity_candidates("Fatih Tutak'ın son işleri", min_len=3)
    assert "fatih" in ents
    assert "tutak" in ents  # 'ın suffix'i ayrıldı, root entity yakalandı
    # "ın" (2 char) < min_len → filtrelenir
    assert "tutakın" not in ents, "Apostrof SPACE'e çevrilmeli"


def test_entity_extract_smart_right_quote():
    """Smart right single quote (')."""
    ents = _extract_entity_candidates("İmamoğlu'nun davası", min_len=3)
    assert "imamoğlu" in ents


def test_entity_extract_smart_left_quote():
    """Smart left single quote (')."""
    ents = _extract_entity_candidates("Erdoğan'a göre", min_len=3)
    assert "erdoğan" in ents


def test_entity_extract_modifier_letter_apostrophe():
    """Modifier letter apostrophe (ʼ — bazı Unicode kaynaklar)."""
    ents = _extract_entity_candidates("Bayraktarʼın IHA'sı", min_len=3)
    assert "bayraktar" in ents


def test_entity_extract_backtick():
    """Backtick ` (bazı text editor copy-paste'inde gelir)."""
    ents = _extract_entity_candidates("AKP`nin kararı", min_len=3)
    assert "akp" in ents or len([e for e in ents if "akp" in e]) > 0


def test_entity_extract_handles_double_quotes_variants():
    """Smart double quote varyantları (" " „)."""
    ents = _extract_entity_candidates('Bianet "Toprakaltı" sergisi açıldı', min_len=3)
    assert "toprakaltı" in ents


def test_entity_extract_low9_quote():
    """Low-9 single quote ‚ (bazı kaynaklar)."""
    ents = _extract_entity_candidates("CHP‚nin politikası", min_len=3)
    # ‚ → SPACE çevrilince "CHP" + "nin" olur, CHP rare entity
    assert "chp" in ents or len([e for e in ents if "chp" == e[:3]]) > 0


# ---------------------------------------------------------------------------
# #699 — Türkçe "İ" Unicode lower() bug (combining char) fix
# ---------------------------------------------------------------------------


def test_entity_extract_turkish_capital_i_imamoglu():
    """İmamoğlu → imamoğlu olmalı (Python lower() combining char üretmesin)."""
    ents = _extract_entity_candidates("İmamoğlu'nun davası", min_len=3)
    assert "imamoğlu" in ents, f"İmamoğlu kayıp: {ents}"
    # combining char ile bölünmüş "mamoğlu" OLMAMALI
    assert "mamoğlu" not in ents


def test_entity_extract_turkish_capital_i_ibb():
    """İBB → ibb (Türkçe kurum kısaltması)."""
    ents = _extract_entity_candidates("İBB başkanı kim", min_len=3)
    assert "ibb" in ents


def test_entity_extract_turkish_capital_i_iski():
    """İSKİ → iski (çoklu İ aynı kelimede)."""
    ents = _extract_entity_candidates("İSKİ su kesintisi", min_len=3)
    assert "iski" in ents


def test_entity_extract_ascii_capital_i_unaffected():
    """ASCII büyük 'I' normal lower() ile 'i' olmalı (Türkçe değil)."""
    ents = _extract_entity_candidates("IBAN sorgulama", min_len=3)
    # Normal ASCII I → i; "iban" çıkmalı
    assert "iban" in ents


def test_entity_extract_quote_stripping_stopwords_combo():
    """Apostrof handling + stopword filter beraber çalışmalı."""
    # niche_002 senaryosu: "Karşıyaka Bursaspor maçı kaç kaç bitti"
    # maçı/kaç/bitti stopword (#696 C13 sonrası)
    ents = _extract_entity_candidates(
        "Karşıyaka Bursaspor maçı kaç kaç bitti", min_len=3
    )
    assert "karşıyaka" in ents
    assert "bursaspor" in ents
    # stopword'ler filtrelenir
    assert "maçı" not in ents, "'maçı' stopword olmalı (#696)"
    assert "kaç" not in ents, "'kaç' stopword olmalı (#696)"
    assert "bitti" not in ents, "'bitti' stopword olmalı (#696)"


def test_entity_match_bonus_full_match():
    row = {"title": "Toprakaltı Sergisi açıldı", "summary": ""}
    bonus = _entity_match_bonus(["toprakaltı", "sergisi"], row)
    # 2 entity match × 0.025 = 0.05
    assert bonus == pytest.approx(0.05, abs=1e-3)


def test_entity_match_bonus_no_match():
    row = {"title": "Slovenya tüneli sanat", "summary": ""}
    bonus = _entity_match_bonus(["toprakaltı", "bayraktar"], row)
    assert bonus == 0.0


def test_entity_match_bonus_partial_match():
    row = {"title": "Bayraktar TB3 İHA testi", "summary": "Yeni özellikler"}
    bonus = _entity_match_bonus(["bayraktar", "iha", "özellikler"], row)
    # 3 match × 0.025 = 0.075 ≤ max 0.10
    assert bonus == pytest.approx(0.075, abs=1e-3)


def test_entity_match_bonus_capped_at_max():
    row = {"title": "a b c d e f", "summary": "g h i j k l"}
    ents = ["a", "bbcd", "ccde", "ddef", "eefg", "ffgh"]
    # Tüm 5 char altı → entity adayı listesinde olmamalı normalde
    # ama edge case: çok match → max 0.10 cap
    row2 = {"title": "Aaaaaa Bbbbbb Cccccc Dddddd Eeeeee Ffffff", "summary": ""}
    ents2 = ["aaaaaa", "bbbbbb", "cccccc", "dddddd", "eeeeee", "ffffff"]
    bonus = _entity_match_bonus(ents2, row2)
    assert bonus == 0.10  # cap


def test_entity_match_bonus_finds_in_summary():
    row = {"title": "Genel başlık", "summary": "İçerik içinde Toprakaltı geçer"}
    bonus = _entity_match_bonus(["toprakaltı"], row)
    assert bonus == pytest.approx(0.025, abs=1e-3)


def test_entity_match_bonus_works_with_smart_quotes_in_source():
    # Source title smart quote ile yazılmış (Bianet pattern)
    row = {"title": "“Toprakaltı” sergisi açıldı", "summary": ""}
    bonus = _entity_match_bonus(["toprakaltı"], row)
    # strip_quote_variants source title'a da uygulanır → "toprakaltı" match
    assert bonus == pytest.approx(0.025, abs=1e-3)


# ---------------------------------------------------------------------------
# rerank_rows behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_disabled_passthrough():
    rows = [{"id": str(i), "title": f"t{i}"} for i in range(5)]
    with _patches(reranker_enabled=False):
        out = await rerank_rows(query="x", rows=rows, top_k=3)
    assert len(out) == 3
    assert out[0]["id"] == "0"


@pytest.mark.asyncio
async def test_rerank_empty_rows():
    out = await rerank_rows(query="test", rows=[], top_k=5)
    assert out == []


@pytest.mark.asyncio
async def test_rerank_empty_query():
    rows = [{"id": "1", "title": "x"}]
    out = await rerank_rows(query="", rows=rows, top_k=5)
    assert len(out) == 1


@pytest.mark.asyncio
async def test_rerank_no_provider_returns_original():
    rows = [{"id": str(i), "title": f"t{i}"} for i in range(3)]
    with _patches() as stack:
        route = stack.enter_context(
            patch("app.providers.registry.registry.route_for_tier")
        )
        route.side_effect = RuntimeError("no rerank provider")
        out = await rerank_rows(query="q", rows=rows, top_k=2)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_rerank_reorders_by_score():
    """Reranker top score'u en üste taşımalı."""
    rows = [
        {"id": "a", "title": "low relevance"},
        {"id": "b", "title": "high relevance"},
        {"id": "c", "title": "medium"},
    ]

    class _FakeProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            return [
                RerankResult(index=1, score=2.5),
                RerankResult(index=2, score=1.0),
                RerankResult(index=0, score=0.1),
            ]

    with _patches(fake_provider=_FakeProvider()):
        out = await rerank_rows(query="relevance", rows=rows, top_k=3)

    assert out[0]["id"] == "b"
    assert out[0]["_rerank_score"] == 2.5
    assert out[1]["id"] == "c"
    assert out[2]["id"] == "a"


@pytest.mark.asyncio
async def test_rerank_negative_logit_linear_penalty():
    """#251/#259 — logit ≤ 0: linear penalty × importance.

    logit=-16 imp=0.85 → factor=0.2, combined=0.2*0.625=0.125 (alakasız but
    high-imp Adana sel orneginin)
    logit=-10 imp=0.60 → factor=0.5, combined=0.5*0.50=0.250 (orta-alaka
    high-imp Otomotiv ihracat orneginin)
    logit=2.5 imp=0.40 → 0.65*sig(2.5) + 0.35*0.40 ≈ 0.731
    """
    rows = [
        {"id": "adana_sel", "title": "alakasız", "importance_score": 0.85},
        {"id": "otomotiv", "title": "orta-alakalı", "importance_score": 0.60},
        {"id": "alaka_var", "title": "alakalı", "importance_score": 0.40},
    ]

    class _FakeProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            return [
                RerankResult(index=0, score=-16.0),  # adana sel
                RerankResult(index=1, score=-10.0),  # otomotiv
                RerankResult(index=2, score=2.5),    # alakalı
            ]

    with _patches(min_combined=-1.0, fake_provider=_FakeProvider()):
        out = await rerank_rows(query="alakalı sorgu", rows=rows, top_k=5)

    assert len(out) == 3
    assert out[0]["id"] == "alaka_var", "pozitif logit + high score üstte"
    assert out[1]["id"] == "otomotiv", "logit=-10 (factor=0.5) ortada"
    assert out[2]["id"] == "adana_sel", "logit=-16 (factor=0.2) altta"
    # Linear penalty kontrolü
    assert 0.10 < out[1]["_combined_score"] < 0.30, (
        f"otomotiv combined sapma: {out[1]['_combined_score']}"
    )
    assert out[2]["_combined_score"] < 0.15, (
        f"adana_sel combined sapma: {out[2]['_combined_score']}"
    )


@pytest.mark.asyncio
async def test_rerank_drops_below_min_combined():
    """#251 — combined_score < min_combined kartlar drop edilir.

    logit=-18 imp=0.20 → factor=0.1, combined=0.03 (alakasız + low-imp DROP)
    logit=3.0 imp=0.80 → 0.65*sig(3) + 0.35*0.8 ≈ 0.898 KEEP
    """
    rows = [
        {"id": "iyi", "title": "x", "importance_score": 0.80},
        {"id": "cok_kotu", "title": "y", "importance_score": 0.20},
    ]

    class _FakeProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            return [
                RerankResult(index=0, score=3.0),
                RerankResult(index=1, score=-18.0),
            ]

    with _patches(min_combined=0.20, fake_provider=_FakeProvider()):
        out = await rerank_rows(query="q", rows=rows, top_k=5)

    assert len(out) == 1, "min_combined altındaki kart drop edilmeli"
    assert out[0]["id"] == "iyi"


@pytest.mark.asyncio
async def test_rerank_drops_all_below_threshold_returns_empty():
    """#251 — tüm kartlar threshold altındaysa boş liste; caller insufficient_data."""
    rows = [
        {"id": "1", "title": "a", "importance_score": 0.20},
        {"id": "2", "title": "b", "importance_score": 0.20},
    ]

    class _FakeProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            return [
                RerankResult(index=0, score=-19.0),  # factor=0.05
                RerankResult(index=1, score=-18.0),  # factor=0.10
            ]

    with _patches(min_combined=0.20, fake_provider=_FakeProvider()):
        out = await rerank_rows(query="q", rows=rows, top_k=5)

    assert out == []


@pytest.mark.asyncio
async def test_rerank_short_query_bypasses():
    """#253 — Tek-term query (<min_query_words) için rerank bypass,
    RRF sırası korunur. NIM cross-encoder kısa query'lerde başarısız."""
    rows = [
        {"id": "a", "title": "CHP'li Yavuzyılmaz açıklaması"},
        {"id": "b", "title": "CHP'li Gürer tarım eleştirisi"},
        {"id": "c", "title": "Adana sel haberi"},
    ]

    class _FakeProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            # Eğer rerank çağrılırsa hepsini negatif yap → drop
            return [
                RerankResult(index=0, score=-15.0),
                RerankResult(index=1, score=-14.0),
                RerankResult(index=2, score=-12.0),
            ]

    # min_query_words=3 → "CHP" (1 kelime) bypass
    with _patches(min_query_words=3, fake_provider=_FakeProvider()):
        out = await rerank_rows(query="CHP", rows=rows, top_k=5)

    # Bypass: RRF sırası korunur (3 kart, hiç drop yok)
    assert len(out) == 3
    assert [r["id"] for r in out] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_rerank_long_query_applies():
    """#253 — Uzun query'de rerank çalışır (3+ kelime).

    logit=3.0 imp=0.5 → 0.794 (üstte)
    logit=-18 imp=0.20 → factor=0.1 × 0.30 = 0.030 (drop)
    """
    rows = [
        {"id": "alaka", "title": "AKP-CHP gerilimi", "importance_score": 0.5},
        {"id": "uzak", "title": "hava durumu", "importance_score": 0.20},
    ]

    class _FakeProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            return [
                RerankResult(index=0, score=3.0),
                RerankResult(index=1, score=-18.0),
            ]

    with _patches(
        min_combined=0.20,
        min_query_words=3,
        fake_provider=_FakeProvider(),
    ):
        out = await rerank_rows(
            query="AKP CHP siyaset gerilimi",
            rows=rows,
            top_k=5,
        )

    # 3+ kelime → rerank uygulandı, alakasız drop edildi
    assert len(out) == 1
    assert out[0]["id"] == "alaka"


@pytest.mark.asyncio
async def test_rerank_provider_error_fallback():
    rows = [{"id": "1", "title": "x"}, {"id": "2", "title": "y"}]

    class _BrokenProvider:
        name = "nim_rerank"
        _default_model = "nim_rerank"

        async def rerank(self, query, documents, top_k):
            raise RuntimeError("provider down")

    with _patches(fake_provider=_BrokenProvider()):
        out = await rerank_rows(query="q", rows=rows, top_k=2)
    assert out[0]["id"] == "1"
