"""#1015 (Pivot Faz 3) — research_clustering saf yardımcı testleri.

Çekirdek kümeleme kararları (kanonik key dedup, nadir-entity çapa,
n-gram aday) deterministik ve DB'siz doğrulanır. (Haber-OLAY
clustering'den AYRI namespace.)
"""

from __future__ import annotations

import pytest
from app.core.research_clustering import (
    canonical_cluster_key,
    query_grams,
    select_anchor,
    select_canonical_anchor,
    tr_ascii_kebab,
)


def test_tr_ascii_kebab():
    assert tr_ascii_kebab("Özgür Özel") == "ozgur-ozel"


# #1590/#1594 — canonical-farkında çapa: GATE + PROMINENCE (trends-hizalı)
# tuple: (norm, type, df, sources, has_canonical, display)
def test_select_canonical_anchor_prefers_canonical_over_generic():
    # canonical "Donald Trump" daha yüksek-df non-canonical "türkiye"yi yener (canonical-prefer)
    cands = [
        ("donald trump", "person", 318, 15, True, "Donald Trump"),
        ("türkiye", "place", 5000, 30, False, None),
    ]
    assert select_canonical_anchor(cands) == ("donald trump", "person", "Donald Trump")


def test_select_canonical_anchor_type_filter_excludes_number_money():
    cands = [
        ("bir", "number", 9, 5, False, None),
        ("asgari ücret", "money", 9, 5, False, None),
        ("chp", "org", 130, 18, True, "Cumhuriyet Halk Partisi"),
    ]
    assert select_canonical_anchor(cands) == ("chp", "org", "Cumhuriyet Halk Partisi")


def test_select_canonical_anchor_prominence_full_beats_fragment():
    # #1594 — en YÜKSEK df kazanır (rarest DEĞİL): "Hürmüz Boğazı"(109) > "hürmüz"(6)
    cands = [
        ("hürmüz", "place", 6, 5, False, None),
        ("hürmüz boğazı", "place", 109, 19, False, None),
    ]
    assert select_canonical_anchor(cands)[0] == "hürmüz boğazı"


def test_select_canonical_anchor_specificity_beats_generic_high_df():
    # #1697 — çok-kelimeli ÖZNE, tek-kelimeli jenerik yüksek-DF'yi YENER.
    # Gerçek: "filenin sultanları almanya maçını kazandı mı" → place:almanya
    # (df=732, çevresel ülke) DEĞİL, org:filenin sultanları (df=39, asıl özne).
    cands = [
        ("almanya", "place", 732, 35, False, "Almanya"),
        ("filenin sultanları", "org", 39, 12, False, "Filenin Sultanları"),
    ]
    assert select_canonical_anchor(cands) == (
        "filenin sultanları",
        "org",
        "Filenin Sultanları",
    )
    # Özgüllük EŞİT (ikisi de tek-kelime) → prominence (df) belirler (geriye-uyumlu).
    cands2 = [
        ("özel", "person", 80, 10, False, "Özel"),
        ("erdoğan", "person", 500, 30, False, "Erdoğan"),
    ]
    assert select_canonical_anchor(cands2)[0] == "erdoğan"


def test_select_canonical_anchor_gate_excludes_low_evidence():
    # #1594 GATE: df<2 veya kaynak<2 → elenir (nadir/tek-kaynak gürültü)
    cands = [
        ("zaman", "person", 1, 1, False, None),  # df1 → gate fail
        ("var", "org", 5, 1, False, None),  # 1 kaynak → gate fail
        ("özgür özel", "person", 50, 8, False, None),  # geçer
    ]
    assert select_canonical_anchor(cands)[0] == "özgür özel"
    # hepsi gate-altı → None
    assert select_canonical_anchor([("var", "org", 5, 1, False, None)]) is None


def test_select_canonical_anchor_excludes_ner_noise():
    # #1598 — common-word mis-NER gate'i GEÇSE bile çapa olamaz (trend ile aynı taban).
    # "var" df5/4kaynak → gate geçer ama noise → elenir; gerçek entity kazanır.
    cands = [
        ("var", "org", 5, 4, False, None),  # gate geçer ama NER-gürültü → ele
        ("özgür özel", "person", 50, 8, False, None),
    ]
    assert select_canonical_anchor(cands)[0] == "özgür özel"
    # yalnız gürültü → None (eski davranış: tek-kaynakla zaten eleniyordu; şimdi çok-kaynakla da)
    assert select_canonical_anchor([("var", "org", 5, 4, False, None)]) is None
    assert select_canonical_anchor([("bugün", "place", 9, 9, False, None)]) is None


def test_select_canonical_anchor_empty_and_all_filtered():
    assert select_canonical_anchor([]) is None
    assert select_canonical_anchor([("12", "number", 9, 9, False, None)]) is None  # tip
    assert select_canonical_anchor([("x", "person", 1, 9, False, None)]) is None  # df gate
    assert tr_ascii_kebab("İBB Davası") == "ibb-davasi"
    assert tr_ascii_kebab("  CHP  ") == "chp"
    assert tr_ascii_kebab("Çağrı/Şükrü, Ğöz!") == "cagri-sukru-goz"
    assert tr_ascii_kebab("") == ""


def test_canonical_cluster_key_deterministic_dedup():
    # Aynı (type, ad) HER ZAMAN aynı key → tek kanonik global düğüm
    k1 = canonical_cluster_key("person", "Özgür Özel")
    k2 = canonical_cluster_key("person", "özgür   özel")
    assert k1 == k2 == "person:ozgur-ozel"
    # type-prefix doğal ayrım (çakışma)
    assert canonical_cluster_key("organization", "CHP") == "organization:chp"
    assert canonical_cluster_key("person", "CHP") != canonical_cluster_key("organization", "CHP")


def test_canonical_cluster_key_empty_raises():
    with pytest.raises(ValueError):
        canonical_cluster_key("person", "   ")


def test_select_anchor_rarest_wins():
    # En NADİR (en düşük df) entity çapa olur
    cands = [
        ("CHP", "organization", 5000),
        ("Özgür Özel", "person", 120),
        ("İBB Davası", "topic", 40),
    ]
    assert select_anchor(cands) == ("İBB Davası", "topic", 40)


def test_select_anchor_tiebreak_and_empty():
    # df eşit → entity_normalized ile deterministik
    cands = [("B Olay", "topic", 10), ("A Olay", "topic", 10)]
    assert select_anchor(cands)[0] == "A Olay"
    assert select_anchor([]) is None
    assert select_anchor([("", "person", 1)]) is None


def test_query_grams_unigram_to_trigram_dedup():
    g = query_grams("Özgür Özel Ankara")
    assert "özgür" in g and "özgür özel" in g and "özgür özel ankara" in g
    # dedup + cap çalışır
    assert len(g) == len(set(g))
    assert query_grams("") == []
    assert len(query_grams("a " * 200, cap=20)) <= 20
