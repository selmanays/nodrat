"""#1493 — L1 Gate-4 strict drift gate (``l1_accept_rewrite`` strict modu).

Kontrat: flag/param OFF → eski Gate-4 davranışı BİREBİR (tek-token
kesişimi yeter). Strict ON → dangling-referent'siz muğlak sorguda
rewrite'ın içerik-token çoğunluğu ham sorgudan türemiyorsa RED
(cross-conversation konu taşıma engeli); dangling-referent'li gerçek
takipler gevşek kabulle AYNEN korunur. Saf/deterministik — LLM yok.

Q5 golden (S-2 canary, prod-gözlem): raw "borsa ne olur" + önceki
konuşmanın "uzay madenciliği yasası" çapası → rewrite "Türkiye 2026
uzay madenciliği yasası borsa etkisi" → strict modda REDDEDİLMELİ.
"""

from __future__ import annotations

from app.modules.generations.services.conversation_context import l1_accept_rewrite

Q5_RAW = "borsa ne olur"
Q5_DRIFTED = "Türkiye 2026 uzay madenciliği yasası borsa etkisi"


# ---- 1) Flag/param OFF → byte-identical eski davranış ----------------------


def test_off_q5_drift_still_accepted() -> None:
    # Eski Gate-4: tek ortak token ("borsa") kabul için yeterliydi.
    assert l1_accept_rewrite(Q5_RAW, Q5_DRIFTED) is True
    assert l1_accept_rewrite(Q5_RAW, Q5_DRIFTED, strict_drift_gate=False) is True


def test_off_zero_overlap_still_rejected() -> None:
    assert l1_accept_rewrite("Merkez Bankası faiz", "Galatasaray transfer haberi") is False


def test_off_short_signal_conservative_accept() -> None:
    assert l1_accept_rewrite("ab", "cd") is True


# ---- 2) Strict ON — Q5 golden: cross-topic drift REDDEDİLİR ----------------


def test_strict_q5_golden_rejected() -> None:
    assert l1_accept_rewrite(Q5_RAW, Q5_DRIFTED, strict_drift_gate=True) is False


def test_strict_cross_topic_variant_rejected() -> None:
    # raw "borsa ne olur" → tamamen başka konudan zenginleştirme → red.
    assert (
        l1_accept_rewrite(
            "borsa ne olur",
            "uzay madenciliği yasası borsa etkisi",
            strict_drift_gate=True,
        )
        is False
    )


# ---- 3) Strict ON — genuine follow-up (dangling referent) KORUNUR ----------


def test_strict_dangling_pek_bu_gelismeler_accepted() -> None:
    # Q7-sınıfı gerçek takip: "bu gelişmeler" dangling → gevşek kabul.
    assert (
        l1_accept_rewrite(
            "peki bu gelişmeler vatandaşın günlük harcamalarını nasıl etkiler",
            "Türkiye enflasyon merkez bankası faiz kararı döviz kuru "
            "gelişmelerinin vatandaşın günlük harcamalarına etkisi",
            strict_drift_gate=True,
        )
        is True
    )


def test_strict_dangling_bu_konuda_accepted() -> None:
    # "bu konuda ne oldu" → soyut referent dangling → context-rewrite kabul.
    # (Zero-overlap ön-kuralı her iki modda da geçerli kalır → gerçekçi
    # condense çıktısı ham sorgudan en az bir token taşır: "oldu".)
    assert (
        l1_accept_rewrite(
            "bu konuda ne oldu",
            "uzay madenciliği yasasında son durum ne oldu",
            strict_drift_gate=True,
        )
        is True
    )


def test_strict_dangling_ankara_followup_accepted() -> None:
    # Mevcut Gate-4 testindeki genuine-follow-up sınıfı strict modda da geçer
    # ("yapacakmış" raw'da; rewrite ortak kök "ankara" + "yapacak…" taşır).
    assert (
        l1_accept_rewrite(
            "Ankara'da bu açıklamayı ne zaman yapacakmış",
            "Özgür Özel Ankara ziyaretinde açıklamayı ne zaman yapacak",
            strict_drift_gate=True,
        )
        is True
    )


# ---- 4) Strict ON — dangling YOK ama rewrite ham sorgudan türemiş → kabul --


def test_strict_same_topic_suffix_expansion_accepted() -> None:
    # Türkçe ek toleransı (4-char kök): borsa/borsanın, olur/olur.
    assert (
        l1_accept_rewrite(
            "borsa ne olur",
            "borsanın bugün ne olur",
            strict_drift_gate=True,
        )
        is True
    )


def test_strict_identity_rewrite_accepted() -> None:
    assert (
        l1_accept_rewrite(
            "asgari ücret zammı son durum",
            "asgari ücret zammı son durum",
            strict_drift_gate=True,
        )
        is True
    )


# ---- 5) Strict ON — kısa-muğlak + ağır genişletme: davranış sabitlenir -----


def test_strict_short_ambiguous_heavy_expansion_rejected_pinned() -> None:
    # "faiz ne olur" → "merkez bankası faiz kararı ne olur": türemiş 2/5
    # (faiz, olur) < çoğunluk → strict modda RED. Bilinçli trade-off
    # (deterministik token-matematiği "ilgili genişletme"yi "cross-topic
    # taşıma"dan ayıramaz); flag-gated olmasının nedeni de bu — davranış
    # testle SABİTLENİR, gelecek iterasyon gevşetirse bilinçli diff olur.
    assert (
        l1_accept_rewrite(
            "faiz ne olur",
            "merkez bankası faiz kararı ne olur",
            strict_drift_gate=True,
        )
        is False
    )


# ---- 6) Strict ON — zero-overlap reddi aynen sürer -------------------------


def test_strict_zero_overlap_still_rejected() -> None:
    assert (
        l1_accept_rewrite(
            "Merkez Bankası faiz",
            "Galatasaray transfer haberi",
            strict_drift_gate=True,
        )
        is False
    )


def test_strict_short_signal_conservative_accept() -> None:
    # Sinyal yetersiz (≥3-harf token yok) → muhafazakâr kabul korunur.
    assert l1_accept_rewrite("ab", "cd", strict_drift_gate=True) is True


# ---- 7) Registry kontratı ---------------------------------------------------


def test_registry_entry_default_off() -> None:
    from app.modules.settings_admin.routes import SETTING_REGISTRY

    entry = SETTING_REGISTRY["research.l1_strict_drift_gate"]
    assert entry["default"] is False
    assert entry["type"] == "bool"
    assert entry["group"] == "research"
    assert entry["requires_restart"] is False
