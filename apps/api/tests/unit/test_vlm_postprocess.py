"""Unit tests for VLM caption post-processing (#304 fix).

Pure Python — caption + depicts uyumsuzluğu durumunda otomatik birleştirme.
"""

from __future__ import annotations

from app.core.vlm_postprocess import (
    _name_in_caption,
    enrich_caption_with_depicts,
)


# =============================================================================
# _name_in_caption
# =============================================================================


def test_name_in_caption_full_match():
    assert _name_in_caption("Aziz Yıldırım kürsüde konuştu", "Aziz Yıldırım")


def test_name_in_caption_partial_surname():
    assert _name_in_caption("Yıldırım açıklama yaptı", "Aziz Yıldırım")


def test_name_in_caption_partial_firstname():
    """Sadece ad geçerse de match (3+ char)."""
    assert _name_in_caption("Şebnem konseri verdi", "Şebnem Ferah")


def test_name_in_caption_no_match():
    assert not _name_in_caption("Bir adam konuşuyor", "Aziz Yıldırım")


def test_name_in_caption_case_insensitive():
    assert _name_in_caption("ÖZGÜR ÖZEL açıkladı", "Özgür Özel")


def test_name_in_caption_short_name_rejected():
    """3 char altı isimler match etmez (yanlış pozitif önle)."""
    assert not _name_in_caption("AB konseri", "AB CD")


# =============================================================================
# enrich_caption_with_depicts — strateji 2 (generic replacement)
# =============================================================================


def test_enrich_replaces_bir_adam():
    """'bir adam' generic referansı kişi adıyla değiştirilir."""
    result = enrich_caption_with_depicts(
        "Fenerbahçe logosu önünde konuşan bir adam", ["Aziz Yıldırım"]
    )
    assert result == "Fenerbahçe logosu önünde konuşan Aziz Yıldırım"


def test_enrich_replaces_takim_elbiseli_adam():
    result = enrich_caption_with_depicts(
        "Takım elbiseli bir adam mikrofonlara konuşuyor.", ["Özgür Özel"]
    )
    assert "Özgür Özel" in result
    assert "bir adam" not in result.lower()


def test_enrich_replaces_bir_kadin():
    result = enrich_caption_with_depicts(
        "Sahneye mikrofonla çıkan bir kadın gülümsüyor.", ["Şebnem Ferah"]
    )
    assert "Şebnem Ferah" in result
    assert "bir kadın" not in result.lower()


def test_enrich_replaces_bir_erkek_adam():
    result = enrich_caption_with_depicts(
        "Bir erkek adam kürsüde", ["Erdoğan"]
    )
    assert "Erdoğan" in result


# =============================================================================
# enrich_caption_with_depicts — strateji 3 (prefix)
# =============================================================================


def test_enrich_prepends_when_no_generic():
    """Caption'da generic referans yok ve depicts ismi yoksa prefix ekle."""
    result = enrich_caption_with_depicts(
        "Sahnede şarkı söylüyor.", ["Şebnem Ferah"]
    )
    assert result == "Şebnem Ferah, sahnede şarkı söylüyor."


def test_enrich_prefix_lowercases_first_char():
    """Prefix sonrası eski caption'ın ilk harfi küçük olur."""
    result = enrich_caption_with_depicts("Konuşma yapıyor.", ["Erdoğan"])
    assert result == "Erdoğan, konuşma yapıyor."


# =============================================================================
# Pass-through (değişiklik yok)
# =============================================================================


def test_enrich_no_change_when_name_already_in_caption():
    """İsim zaten caption'daysa olduğu gibi kal."""
    cap = "Aziz Yıldırım Fenerbahçe başkanlığına aday"
    result = enrich_caption_with_depicts(cap, ["Aziz Yıldırım"])
    assert result == cap


def test_enrich_no_change_when_depicts_empty():
    cap = "Bir adam konuşuyor"
    assert enrich_caption_with_depicts(cap, []) == cap
    assert enrich_caption_with_depicts(cap, None) == cap


def test_enrich_no_change_when_caption_empty():
    assert enrich_caption_with_depicts("", ["Erdoğan"]) == ""


def test_enrich_skips_object_depicts():
    """Lowercase depicts ('kürsü', 'mikrofon') person olarak sayılmaz."""
    cap = "Bir adam kürsüde konuşuyor"
    result = enrich_caption_with_depicts(cap, ["kürsü", "mikrofon"])
    # Kişi ismi yok, hiçbir şey değişmez
    assert result == cap


def test_enrich_picks_first_missing_name():
    """Birden fazla missing isim varsa ilki kullanılır."""
    result = enrich_caption_with_depicts(
        "İki adam konuşuyor", ["Devlet Bahçeli", "Özgür Özel"]
    )
    assert "Devlet Bahçeli" in result


def test_enrich_skips_names_already_in_caption():
    """Birden fazla depicts var, biri caption'da → diğerini ekle."""
    result = enrich_caption_with_depicts(
        "Erdoğan yan yana ile bir adam görüşüyor",
        ["Erdoğan", "Kılıçdaroğlu"],
    )
    # Erdoğan zaten var, "bir adam" → Kılıçdaroğlu olmalı
    assert "Kılıçdaroğlu" in result
    assert "bir adam" not in result.lower()
