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
    RELATED_TOP_K,
    _rank_related,
    format_context_block,
    l1_accept_rewrite,
    serialize_embedding,
)


def _m(role, content, sources_used=None):
    return SimpleNamespace(role=role, content=content, sources_used=sources_used)


_EMBED_DIM = 1024  # serialize_embedding 1024-dim ZORUNLU (aksi ValueError)


def _vec(a, b):
    """1024-dim vektör: ilk iki bileşen (a,b), kalan 0 → cosine kontrollü."""
    return [float(a), float(b)] + [0.0] * (_EMBED_DIM - 2)


def _qm(role, vec):
    """Message-like: _rank_related yalnız role + query_embedding okur."""
    return SimpleNamespace(
        role=role,
        query_embedding=serialize_embedding(vec) if vec is not None else None,
    )


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


# --- Redesign: _rank_related (Tier0/REACH çekirdeği, S5 Gate-5 saf test) ---

_Q = _vec(1.0, 0.0)  # sorgu yönü
_HI = _vec(1.0, 0.0)  # cos 1.00
_MID = _vec(0.8, 0.6)  # cos 0.80
_MID2 = _vec(0.72, 0.694)  # cos ~0.72
_LO = _vec(0.5, 0.866)  # cos 0.50  (< 0.65 eşik)


def test_rank_related_threshold_and_score_order():
    """Yalnız cosine ≥ eşik user mesajları; skora göre AZALAN sıra."""
    hi = _qm("user", _HI)
    lo = _qm("user", _LO)
    mid = _qm("user", _MID)
    picked = _rank_related([lo, hi, mid], _Q, 0.65)
    assert picked == [hi, mid]  # lo elendi (0.50<0.65), sıra skor-desc


def test_rank_related_caps_at_top_k():
    """RELATED_TOP_K tavanı — pencere dökümü değil, en iyi K araştırma."""
    assert RELATED_TOP_K == 2
    hi = _qm("user", _HI)
    mid = _qm("user", _MID)
    mid2 = _qm("user", _MID2)
    picked = _rank_related([mid2, mid, hi], _Q, 0.65)
    assert picked == [hi, mid]  # 3 ilişkili → top-2; mid2(0.72) düştü


def test_rank_related_ignores_assistant_and_none_embedding():
    """Assistant rolü + embedding'i olmayan user → aday değil."""
    asst = _qm("assistant", _HI)  # yüksek skor ama assistant → yok
    noemb = _qm("user", None)  # embedding yok → yok
    mid = _qm("user", _MID)
    picked = _rank_related([asst, noemb, mid], _Q, 0.65)
    assert picked == [mid]


def test_rank_related_empty_when_none_pass():
    lo = _qm("user", _LO)
    assert _rank_related([lo], _Q, 0.65) == []
