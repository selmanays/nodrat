"""Unit — #1737 cluster-resolve çekim-bağışık fallback yardımcısı (`_query_overlap`).

Saf fonksiyon (DB'siz): cited-makale entity'sinin, sorgu token'larıyla ÖRTÜŞÜP
örtüşmediği. YALNIZ Türkçe-ek yönü (entity-token, query-token'ın PREFIX'i) →
geniş parti/kurum elenir, sorgunun öznesi kalır. Ters yön kasıtlı dışarıda.
"""

from __future__ import annotations

from app.modules.generations.cluster_resolver import _query_overlap

# "12. yargı paketinde neler var" → query_grams single-token (≥4) çıktısı
_QTOKS = {"yargı", "paketinde", "neler"}


def test_overlap_keeps_query_subject_via_turkish_suffix():
    # entity stem query token'ın prefix'i: "yargı"=="yargı", "paketi"⊂"paketinde"
    assert _query_overlap("12. yargı paketi", _QTOKS) is True
    assert _query_overlap("yargı paketi", _QTOKS) is True


def test_overlap_drops_broad_canonical_entities():
    # cited makalelerde bol bulunan geniş parti/kurum — hiçbiri sorgu öznesi DEĞİL
    for broad in (
        "adalet ve kalkınma partisi",
        "anayasa mahkemesi",
        "türkiye büyük millet meclisi",
        "cumhuriyet halk partisi",
        "recep tayyip erdoğan",
        "donald trump",
    ):
        assert _query_overlap(broad, _QTOKS) is False, broad


def test_overlap_rejects_reverse_direction_false_neighbor():
    # "yargıtay" sorgu token'ı DEĞİL — ters yön (query⊂entity) açık olsa içeri girer
    # ve has_canonical sıralamada önde olduğundan özneyi bastırırdı → tek-yön şart.
    assert _query_overlap("yargıtay", _QTOKS) is False


def test_overlap_ignores_short_tokens_and_empty():
    assert _query_overlap(None, _QTOKS) is False
    assert _query_overlap("", _QTOKS) is False
    # 3-char entity-token gürültüsü prefix sayılmaz (eşik ≥4)
    assert _query_overlap("abd", {"abdullah"}) is False
    # tek-yön: entity "neler raporu" → "neler" query token'ının prefix'i
    assert _query_overlap("neler raporu", _QTOKS) is True
