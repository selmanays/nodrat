"""#1020 (Pivot Faz 6) — infer_parent_edges curated acceptance testleri.

Hiyerarşi ANSİKLOPEDİDEN değil kullanım deseninden: asimetrik kapsama +
df-genellik. KRİTİK acceptance: CHP→Özgür Özel/İBB doğru ebeveyn;
**Erdoğan↔Özel yanlış-ebeveyn YOK** (simetrik co-occurrence kenar üretmez).
Pure fonksiyon (DB yok) — yalnız aggregate sayım girer.
"""

from __future__ import annotations

from app.core.research_clustering import infer_parent_edges


def test_chp_parent_of_ozel_and_ibb():
    """CHP genel (yüksek occ + yüksek df); Özel/İBB çoğunlukla CHP ile
    birlikte ama CHP onlarla değil → Özel→CHP, İBB→CHP."""
    occ = {"chp": 100, "ozel": 30, "ibb": 20}
    cooc = {
        ("chp", "ozel"): 27,  # P(chp|ozel)=0.9 ; P(ozel|chp)=0.27
        ("chp", "ibb"): 18,  # P(chp|ibb)=0.9 ; P(ibb|chp)=0.18
        ("ibb", "ozel"): 4,
    }
    df = {"chp": 10, "ozel": 2, "ibb": 2}  # CHP geniş co-occur = genel
    edges = infer_parent_edges(occ, cooc, df)
    assert edges == {"ozel": "chp", "ibb": "chp"}


def test_erdogan_ozel_no_false_parent():
    """KRİTİK: Erdoğan↔Özel güçlü ama SİMETRİK birlikte-geçme →
    hiçbir yön kenar üretmez (yanlış-ebeveyn YOK)."""
    occ = {"erdogan": 80, "ozel": 70}
    cooc = {("erdogan", "ozel"): 50}  # P(e|ö)=0.71 ; P(ö|e)=0.625 (ikisi >lo)
    df = {"erdogan": 8, "ozel": 7}
    assert infer_parent_edges(occ, cooc, df) == {}


def test_below_min_support_no_edge():
    occ = {"a": 50, "b": 5}
    cooc = {("a", "b"): 2}  # < min_support=3
    df = {"a": 9, "b": 1}
    assert infer_parent_edges(occ, cooc, df) == {}


def test_full_symmetric_cooccurrence_no_edge():
    """Hep birlikte (P(a|b)=P(b|a)=1.0) → asimetri yok → kenar yok."""
    occ = {"a": 10, "b": 10}
    cooc = {("a", "b"): 10}
    df = {"a": 5, "b": 5}
    assert infer_parent_edges(occ, cooc, df) == {}


def test_df_generality_guard():
    """Kapsama asimetrik ama ebeveyn yeterince GENEL değil (df_ratio) →
    kenar yok (salt kapsama yetmez)."""
    occ = {"a": 100, "b": 20}
    cooc = {("a", "b"): 18}  # P(a|b)=0.9 ; P(b|a)=0.18 (asimetrik)
    df = {"a": 3, "b": 3}  # 3 >= 3*1.5=4.5 FALSE → reddet
    assert infer_parent_edges(occ, cooc, df) == {}


def test_no_self_edge():
    occ = {"x": 10}
    cooc = {("x", "x"): 10}
    df = {"x": 9}
    assert infer_parent_edges(occ, cooc, df) == {}


def test_strongest_parent_wins():
    """Çocuk iki genel kümeyle de eşleşirse en güçlü kapsama kazanır."""
    occ = {"p1": 100, "p2": 100, "c": 20}
    cooc = {
        ("c", "p1"): 19,  # P(p1|c)=0.95
        ("c", "p2"): 14,  # P(p2|c)=0.70
        ("p1", "p2"): 5,
    }
    df = {"p1": 12, "p2": 12, "c": 2}
    edges = infer_parent_edges(occ, cooc, df)
    assert edges["c"] == "p1"  # 0.95 > 0.70


def test_threshold_tuning_changes_outcome():
    """Eşikler parametrik — daha gevşek df_ratio ile guard'lı vaka geçer
    (geri-alınabilir/ayarlanabilir tasarım kanıtı)."""
    occ = {"a": 100, "b": 20}
    cooc = {("a", "b"): 18}
    df = {"a": 3, "b": 3}
    assert infer_parent_edges(occ, cooc, df) == {}  # default df_ratio=1.5
    loose = infer_parent_edges(occ, cooc, df, df_ratio=1.0)
    assert loose == {"b": "a"}  # df_ratio gevşeyince geçer
