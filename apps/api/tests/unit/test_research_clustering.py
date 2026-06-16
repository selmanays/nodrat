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


# #1590 — canonical-farkında çapa (Trends yapısı)
def test_select_canonical_anchor_prefers_canonical_over_rare_noise():
    # "trump" canonical (df 318) vs "xyz-nadir" non-canonical (df 2): canonical kazanır
    # (rarest-wins olsa nadir gürültü seçilirdi)
    cands = [
        ("donald trump", "person", 318, True, "Donald Trump"),
        ("xyz nadir", "person", 2, False, None),
    ]
    assert select_canonical_anchor(cands) == ("donald trump", "person", "Donald Trump")


def test_select_canonical_anchor_type_filter_excludes_number_money():
    # number/money/misc çapa OLAMAZ
    cands = [
        ("bir", "number", 1, False, None),
        ("asgari ücret", "money", 1, False, None),
        ("chp", "org", 130, True, "Cumhuriyet Halk Partisi"),
    ]
    assert select_canonical_anchor(cands) == ("chp", "org", "Cumhuriyet Halk Partisi")


def test_select_canonical_anchor_rarest_among_canonical():
    # ikisi de canonical → en nadir (df) kazanır
    cands = [
        ("türkiye", "place", 5000, True, "Türkiye"),
        ("hürmüz boğazı", "place", 40, True, "Hürmüz Boğazı"),
    ]
    assert select_canonical_anchor(cands)[0] == "hürmüz boğazı"


def test_select_canonical_anchor_falls_back_to_raw_when_no_canonical():
    # canonical yoksa tip-filtreli rarest (özgür ham entity)
    cands = [("özgür özel", "person", 50, False, None), ("türkiye", "place", 9000, False, None)]
    assert select_canonical_anchor(cands)[0] == "özgür özel"


def test_select_canonical_anchor_empty_and_all_filtered():
    assert select_canonical_anchor([]) is None
    assert select_canonical_anchor([("12", "number", 1, False, None)]) is None
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
