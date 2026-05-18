"""#1014 (Pivot Faz 2b) — L1 saf yardımcı testleri.

L1 zaman-pencereli bağlam YALNIZ condense'i besler; asıl cevap prompt'una
girmez. Flag default kapalı → byte-eş. Burada saf/DB'siz parçalar test
edilir: format_context_block (condense `history` format parity — refactor
regresyon kalkanı) + l1_accept_rewrite (Gate 4 rewrite-drift). DB'li
select_windowed_context entegrasyon/CI'da.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.core.conversation_context import (
    format_context_block,
    l1_accept_rewrite,
)


def _m(role, content, sources_used=None):
    return SimpleNamespace(role=role, content=content, sources_used=sources_used)


def test_format_parity_user_assistant_with_sources():
    """Legacy `_recent_conversation_context` formatıyla BİREBİR
    (condense sözleşmesi değişmedi)."""
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
    out = format_context_block(rows)
    assert out == (
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
