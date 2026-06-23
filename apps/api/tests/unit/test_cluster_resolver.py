"""Unit — #1737 cluster-resolve çekim-bağışık fallback yardımcısı (`_query_overlap`).

Saf fonksiyon (DB'siz): cited-makale entity'sinin, sorgu token'larıyla ÖRTÜŞÜP
örtüşmediği. YALNIZ Türkçe-ek yönü (entity-token, query-token'ın PREFIX'i) →
geniş parti/kurum elenir, sorgunun öznesi kalır. Ters yön kasıtlı dışarıda.
"""

from __future__ import annotations

from app.modules.generations.cluster_resolver import _answer_mentions, _query_overlap

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


# ---------------------------------------------------------------------------
# #1751 — cevap-tarafı özne tespiti (_answer_mentions)
# ---------------------------------------------------------------------------

_ANSWER = "deniz kaya, 35 yaşında bir oyuncu, kalp krizi sonucu hayatını kaybetti.".lower()


def test_answer_mentions_subject_named_in_answer():
    # cevapta adı geçen özne (norm veya display) → True
    assert _answer_mentions("deniz kaya", "Deniz Kaya", _ANSWER) is True
    assert _answer_mentions("oyuncu", None, _ANSWER) is True  # ≥4, cevapta geçiyor


def test_answer_mentions_drops_context_not_in_answer():
    # cevapta GEÇMEYEN bağlam entity'si (df'de baskın olsa bile) → False
    assert _answer_mentions("tayland", "Tayland", _ANSWER) is False
    assert _answer_mentions("genç", "Genç", _ANSWER) is False  # sorgu kelimesi, cevapta yok


def test_answer_mentions_short_and_empty():
    assert _answer_mentions(None, None, _ANSWER) is False
    assert _answer_mentions("ab", "AB", _ANSWER) is False  # <4 char gürültü


# ---------------------------------------------------------------------------
# #1759 — alias-farkında cevap-eşleşmesi (_answer_mentions surface_forms)
# ---------------------------------------------------------------------------


def test_answer_mentions_alias_surface_form():
    # canonical adı uzun ama cevap KISALTMAYI yazıyor → ham yüzey-form'dan yakalanır
    ans = "dem parti bugün gündemde; tülay hatimoğulları açıklama yaptı.".lower()
    # norm=canonical (uzun, cevapta YOK), surface_forms=['dem parti'] (cevapta VAR)
    assert _answer_mentions(
        "halkların eşitlik ve demokrasi partisi", "Halkların Eşitlik ve Demokrasi Partisi",
        ans, ["dem parti"]
    ) is True
    # surface_form da yoksa → False (cevapta hiç geçmiyor)
    assert _answer_mentions(
        "numan kurtulmuş", "Numan Kurtulmuş", ans, ["numan kurtulmuş"]
    ) is False
