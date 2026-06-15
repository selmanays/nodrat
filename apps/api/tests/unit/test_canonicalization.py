"""Entity canonicalization saf fonksiyonları (#1540, Faz 1).

DB'siz: title-strip + seed resolution + ilk-ad çakışma guard (Emine/Bilal tuzağı).
"""

from __future__ import annotations

from app.modules.entities.canonicalization import (
    SEED_GROUPS,
    build_subset_groups,
    resolve_canonical,
    strip_titles,
)

# ---------------------------------------------------------------------------
# strip_titles
# ---------------------------------------------------------------------------


def test_strip_single_title():
    assert strip_titles("cumhurbaşkanı erdoğan") == "erdoğan"


def test_strip_multiple_titles():
    assert strip_titles("akpli cumhurbaşkanı erdoğan") == "erdoğan"


def test_strip_no_title_unchanged():
    assert strip_titles("recep tayyip erdoğan") == "recep tayyip erdoğan"
    assert strip_titles("erdoğan") == "erdoğan"


def test_strip_all_titles_unchanged():
    # Tümü unvan → boşaltma (orijinali döndür)
    assert strip_titles("başkan") == "başkan"


# ---------------------------------------------------------------------------
# resolve_canonical — org akronim ↔ açık ad
# ---------------------------------------------------------------------------


def test_org_acronym_to_canonical():
    m = resolve_canonical("chp", "org")
    assert m is not None
    assert m.canonical_name == "Cumhuriyet Halk Partisi"
    assert m.entity_type == "org"
    assert m.source == "seed"


def test_org_expansion_to_canonical():
    m = resolve_canonical("cumhuriyet halk partisi", "org")
    assert m is not None and m.canonical_name == "Cumhuriyet Halk Partisi"


def test_org_merkez_bankasi():
    assert resolve_canonical("tcmb", "org").canonical_name == "Merkez Bankası"
    assert resolve_canonical("merkez bankası", "org").canonical_name == "Merkez Bankası"


# ---------------------------------------------------------------------------
# resolve_canonical — person (title-strip + seed)
# ---------------------------------------------------------------------------


def test_person_title_strip_to_canonical():
    m = resolve_canonical("cumhurbaşkanı erdoğan", "person")
    assert m is not None
    assert m.canonical_name == "Recep Tayyip Erdoğan"
    assert m.source == "title_strip"


def test_person_full_name_seed():
    m = resolve_canonical("recep tayyip erdoğan", "person")
    assert m is not None and m.canonical_name == "Recep Tayyip Erdoğan"
    assert m.source == "seed"


def test_person_surname_only_seed():
    assert resolve_canonical("erdoğan", "person").canonical_name == "Recep Tayyip Erdoğan"
    assert resolve_canonical("trump", "person").canonical_name == "Donald Trump"


# ---------------------------------------------------------------------------
# Emine/Bilal Erdoğan tuzağı — FARKLI kişi, birleşTİRİLMEZ
# ---------------------------------------------------------------------------


def test_first_name_conflict_not_merged():
    # "emine erdoğan" seed'de yok + unvan-ön-ek yok → None (Recep'e KATILMAZ)
    assert resolve_canonical("emine erdoğan", "person") is None
    assert resolve_canonical("bilal erdoğan", "person") is None


def test_unmapped_returns_none():
    assert resolve_canonical("rastgele bir kişi", "person") is None
    assert resolve_canonical("bilinmeyen kurum", "org") is None


def test_type_gating():
    # "chp" org seed'inde; place olarak sorulursa eşleşmez
    assert resolve_canonical("chp", "place") is None


def test_seed_groups_well_formed():
    for canonical_name, etype, aliases in SEED_GROUPS:
        assert canonical_name and etype in {"person", "org", "place", "event"}
        assert len(aliases) >= 1
        assert all(a == a.lower() for a in aliases)  # alias'lar normalized (lower)


# ---------------------------------------------------------------------------
# build_subset_groups (#1548) — token-altküme birleştirme (event)
# ---------------------------------------------------------------------------


def test_subset_world_cup_merge():
    # Prod senaryosu: 2026 Dünya Kupası varyantları birleşir; jenerik/2002 ayrı.
    items = [
        ("2026 fifa dünya kupası", 66),
        ("fifa 2026 dünya kupası", 10),  # aynı set, farklı sıra
        ("2026 dünya kupası", 53),
        ("fifa dünya kupası", 7),
        ("dünya kupası", 59),  # 2026 VE 2002 alt-kümesi = belirsiz
        ("2002 dünya kupası", 7),  # farklı turnuva
        ("nato zirvesi", 26),  # ilgisiz
    ]
    g = build_subset_groups(items)
    canon = "2026 fifa dünya kupası"
    for v in [
        "2026 fifa dünya kupası",
        "fifa 2026 dünya kupası",
        "2026 dünya kupası",
        "fifa dünya kupası",
    ]:
        assert g[v] == canon
    # belirsiz / farklı yıl / ilgisiz → birleşMEZ
    assert "dünya kupası" not in g
    assert "2002 dünya kupası" not in g
    assert "nato zirvesi" not in g


def test_subset_equal_set_different_order():
    g = build_subset_groups([("a b c", 5), ("c b a", 3)])
    assert g["a b c"] == g["c b a"]


def test_subset_disjoint_no_merge():
    assert build_subset_groups([("d grubu", 17), ("h grubu", 15)]) == {}


def test_subset_min_tokens_guard():
    # tek-token alt-küme genişlemez ("ankara" ⊄ kuralı uygulanmaz)
    assert build_subset_groups([("ankara", 10), ("ankara zirvesi", 5)]) == {}


def test_subset_canonical_is_highest_freq():
    g = build_subset_groups([("x y", 3), ("x y z", 9)])
    assert g["x y"] == "x y z" and g["x y z"] == "x y z"


def test_subset_empty_input():
    assert build_subset_groups([]) == {}
    assert build_subset_groups([("tek olay", 5)]) == {}
