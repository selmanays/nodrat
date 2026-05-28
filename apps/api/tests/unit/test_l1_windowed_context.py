"""#1014 (Pivot Faz 2b) — L1 saf yardımcı testleri.

L1 zaman-pencereli bağlam YALNIZ condense'i besler; asıl cevap prompt'una
girmez. Flag default kapalı → byte-eş. Burada saf/DB'siz parçalar test
edilir: format_context_block (condense `history` format parity — refactor
regresyon kalkanı) + l1_accept_rewrite (Gate 4 rewrite-drift). DB'li
select_windowed_context entegrasyon/CI'da.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.modules.generations.services.conversation_context import (
    format_context_block,
    is_standalone_query,
    l1_accept_rewrite,
)


def _m(role, content, sources_used=None):
    return SimpleNamespace(role=role, content=content, sources_used=sources_used)


def test_format_parity_user_assistant_source_line_gated():
    """#1058 Fix-C: kaynak-adı satırı condense bağlamına SIZMAZ
    (varsayılan `include_sources=False`). Önceki cevabın kaynak
    adlarının condense'e girmesi L1-devam halüsinasyonunun
    (conv 865e36e3 — uydurma '[Forbes Türkiye]') tohumuydu.

    Legacy birebir format yalnız `include_sources=True` ile
    erişilebilir (opt-in; mevcut çağrı yok)."""
    rows = [
        _m("user", "Özgür Özel son gelişmeler"),
        _m(
            "assistant",
            "Açıklama yaptı [1].",
            sources_used=[
                {"title": "Özel Ankara'da", "source_name": "X Gazetesi"},
                {"title": "", "source_name": "Y Ajansı"},
                "bozuk-kaynak-dict-degil",
            ],
        ),
        _m("user", "Ankara'da ne yapacakmış?"),
    ]

    # Varsayılan: kaynak-adı satırı YOK (kirlilik-koruması).
    out_default = format_context_block(rows)
    assert out_default == (
        "- Kullanıcı: Özgür Özel son gelişmeler\n"
        "- Asistan: Açıklama yaptı [1].\n"
        "- Kullanıcı: Ankara'da ne yapacakmış?"
    )
    assert "kaynakları" not in out_default

    # Opt-in: legacy birebir format korunur (geriye-dönük çağrı için).
    out_with = format_context_block(rows, include_sources=True)
    assert out_with == (
        "- Kullanıcı: Özgür Özel son gelişmeler\n"
        "- Asistan: Açıklama yaptı [1].\n"
        "  (Bu cevabın kaynakları: X Gazetesi — Özel Ankara'da; Y Ajansı)\n"
        "- Kullanıcı: Ankara'da ne yapacakmış?"
    )


def test_format_snippet_truncation_and_no_sources():
    rows = [_m("user", "x" * 600), _m("assistant", "kısa cevap", None)]
    out = format_context_block(rows)
    assert "- Kullanıcı: " + ("x" * 500) in out
    assert "x" * 501 not in out
    assert "kaynakları" not in out  # sources_used yok → kaynak satırı yok


def test_format_empty():
    assert format_context_block([]) == ""


def test_gate4_accept_when_token_overlap():
    # condense ham sorguyla ortak içerik-token paylaşıyor → KABUL
    assert (
        l1_accept_rewrite(
            "Ankara'da ne yapacakmış?",
            "Özgür Özel Ankara ziyaretinde ne yapacak?",
        )
        is True
    )


def test_gate4_reject_on_total_drift():
    # condense tamamen alakasız konu üretti (ortak ≥3-harf token yok) → RED
    assert (
        l1_accept_rewrite(
            "Merkez Bankası faiz kararı",
            "Galatasaray transfer haberleri",
        )
        is False
    )


def test_gate4_conservative_on_weak_signal():
    # kısa/sinyal yetersiz → muhafazakâr KABUL (mevcut davranışı bozma)
    assert l1_accept_rewrite("", "her neyse") is True
    assert l1_accept_rewrite("ab", "cd") is True


# --- S5 Gate-1: is_standalone_query (cosine-siz çekirdek, saf test) ---


def test_standalone_proven_failure_case_is_nonstandalone():
    """KANITLI kök-neden case'i: belirsiz takip → standalone DEĞİL
    (Tier-0 çapası devreye girmeli)."""
    assert is_standalone_query("nerde yaptı bu açıklamayı") is False


def test_standalone_proper_noun_apostrophe_is_standalone():
    """Kesme-ekli özel ad (Trump'ın) → kendine yeterli → L1 YOK."""
    assert is_standalone_query("Trump'ın son açıklaması nedir?") is True


def test_standalone_referential_pronoun_is_nonstandalone():
    assert is_standalone_query("bu ne zaman oldu") is False
    assert is_standalone_query("peki onu da araştır") is False


def test_standalone_capitalized_proper_noun_is_standalone():
    # baş-harf-dışı büyük harf (özel ad)
    assert is_standalone_query("Özgür Özel ne dedi") is True


def test_standalone_numcode_is_standalone():
    assert is_standalone_query("5651 sayılı kanun nedir") is True


def test_standalone_short_elliptical_is_nonstandalone():
    # çok kısa + özel ad yok → elips (antecedent şart)
    assert is_standalone_query("peki ya") is False
    assert is_standalone_query("detaylandır") is False


def test_standalone_contentful_multiword_no_pronoun_is_standalone():
    # 4+ kelime, referans imleci yok, kendi konusu var
    assert is_standalone_query("enflasyon son durum ne oldu") is True


def test_standalone_empty_is_standalone_skips_l1():
    assert is_standalone_query("") is True
    assert is_standalone_query("   ") is True


# --- #1064: özel-ad, eşzamanlı dangling-referent'i İPTAL ETMEZ ---


def test_standalone_proper_noun_with_dangling_referent_is_nonstandalone():
    """PROD-TEŞHİS kök case (conv quirky-gates Q3): özel ad VAR ama
    'bu iddia' çözülmemiş → standalone DEĞİL (eskiden özel-ad kısa-devre
    yapıp L1'i atlıyordu → 'hangi iddia?' bağlam kaybı)."""
    assert is_standalone_query("Özgür Özel bu iddiayı ne zaman ve nerede dile getirdi?") is False
    # kesme-ekli özel ad + dangling referent → yine False
    assert is_standalone_query("Trump'ın bu açıklamasını nerede yaptı") is False


def test_standalone_deictic_temporal_not_dangling():
    """Yanlış-pozitif koruması: bare bu/şu/o + zamansal deiktik isim
    ('bu hafta', 'bu yıl') → dangling DEĞİL → standalone."""
    assert is_standalone_query("Trump bu hafta ne yaptı") is True
    assert is_standalone_query("bu yıl enflasyon ne oldu") is True


def test_standalone_abstract_referent_still_dangling_with_proper_noun():
    """Soyut referent ('bu konuda') zamansal deiktik DEĞİL → özel ad
    olsa bile dangling → standalone DEĞİL."""
    assert is_standalone_query("Özgür Özel bu konuda ne dedi") is False
    assert is_standalone_query("Trump bu olayı nasıl değerlendirdi") is False
