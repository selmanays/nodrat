"""#961 — research_followup parse_followups: tolerant ama gürültü-dayanıklı
(JSON DEĞİL; #819/#840 dersi)."""

from __future__ import annotations

from app.prompts.research_followup import (
    SYSTEM_PROMPT,
    parse_followups,
    render_user_payload,
)


def test_prefixed_priority_drops_plain_noise():
    # Önekli ≥2 var → öneksiz açıklama/gürültü ("Buyrun:", "çok kısa")
    # ELENİR; dup soru tekleşir; ≤5.
    t = (
        "Buyrun, işte sorular:\n"
        "- 19 Mayıs neden tatil?\n"
        "1. 2026 resmi tatilleri neler?\n"
        "* Kurban Bayramı ne zaman?\n"
        "• Hafta sonu birleşen tatiller hangileri var?\n"
        "- 19 Mayıs neden tatil?\n"
        "çok kısa\n"
        "- Dini bayramların 2026 tarihleri ne?"
    )
    r = parse_followups(t, limit=5)
    assert len(r) == 5
    assert r[0] == "19 Mayıs neden tatil?"
    assert "çok kısa" not in r
    assert "Buyrun, işte sorular:" not in r
    assert len({x.lower() for x in r}) == 5  # dedup


def test_plain_fallback_requires_question_like():
    # Hiç önekli yok → yalnız soru-benzeri öneksiz satırlar (soru
    # işareti / soru kelimesi); düz gürültü elenir.
    t = (
        "Sistem hazır.\n"
        "2026 resmi tatilleri neler?\n"
        "Bu bir açıklama cümlesidir yeterince uzun ama soru değil\n"
        "Kurban Bayramı ne zaman kutlanır?"
    )
    r = parse_followups(t, limit=5)
    assert "2026 resmi tatilleri neler?" in r
    assert "Kurban Bayramı ne zaman kutlanır?" in r
    assert all("açıklama cümlesidir" not in x for x in r)


def test_edge_cases():
    assert parse_followups("", limit=5) == []
    assert parse_followups("   \n  \n", limit=5) == []
    # hepsi çok kısa öneksiz → boş (min 10 char)
    assert parse_followups("ne?\nkim?\nnasıl?", limit=5) == []
    # limit'e uy
    long = "\n".join(f"- {i} numaralı soru gerçekten mi?" for i in range(9))
    assert len(parse_followups(long, limit=5)) == 5


def test_render_payload_truncates():
    p = render_user_payload("soru" * 200, "cevap " * 1000)
    assert "…" in p and len(p) < 2600
    assert "Kullanıcının sorusu:" in p and "Verilen cevap:" in p


def test_system_prompt_identity_safe():
    s = SYSTEM_PROMPT.lower()
    # asistan-jargonu / öznel ton YASAK kuralı promptta olmalı (#851/#958)
    assert "kullanıcının ağzından" in s
    assert "yasak" in s  # editoryal/asistan-jargonu yasağı
    assert "json" not in s or "json değil" in s or "yalnız 5" in s
