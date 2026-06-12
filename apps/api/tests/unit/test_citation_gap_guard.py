"""#1484 (S-2) citation-gap guard — ``_should_force_citation_gap_retry`` testleri.

Kontrat: deterministik 5-AND gate (guard-flag ∧ all_sources ∧ not-forced-once ∧
substantive ∧ hiç-[n]-yok) + nudge sabit-metin PII-suzluğu + registry default-OFF.

Flag-OFF byte-identical kanıtı: ``research.citation_gap_guard_enabled`` default
False (SETTING_REGISTRY) → gate ilk koşulda False → orchestrator'da nudge/phase
hiç üretilmez → mevcut SSE-replay/orchestrator/C1/cited-only/faithfulness
suite'leri değişmeden geçer (#619 PR-3 / PR-F kanıt kalıbı; full-orchestrator
mock "first-yield-only" disiplinince burada tekrarlanmaz — tek-retry invariant'ı
gate'in ``forced_once=True → False`` davranışıyla kilitlenir; orchestrator
``citation_gap_forced_once=True`` set edip continue eder, C1 ``c1_forced_once``
deseninin birebir aynısı).
"""

from __future__ import annotations

from app.modules.generations.citation import (
    _CITATION_GAP_NUDGE,
    _should_force_citation_gap_retry,
)

_SUBSTANTIVE = (
    "Merkez bankası bugün politika faizini açıkladı ve piyasalarda kayda değer "
    "hareketlilik gözlendi; analistler kararın enflasyon görünümüne etkisini "
    "değerlendiriyor."
)  # >= 120 char, [n] yok
_SOURCES = [{"cite": "[1]", "title": "x"}]


def test_gate_true_when_all_conditions_met() -> None:
    assert (
        _should_force_citation_gap_retry(
            _SUBSTANTIVE, _SOURCES, citation_gap_guard=True, forced_once=False
        )
        is True
    )


def test_gate_false_when_flag_off() -> None:
    assert (
        _should_force_citation_gap_retry(
            _SUBSTANTIVE, _SOURCES, citation_gap_guard=False, forced_once=False
        )
        is False
    )


def test_gate_false_when_no_sources() -> None:
    # C1'in alanı (not all_sources) — karşılıklı dışlama.
    assert (
        _should_force_citation_gap_retry(
            _SUBSTANTIVE, [], citation_gap_guard=True, forced_once=False
        )
        is False
    )


def test_gate_false_when_non_substantive() -> None:
    assert (
        _should_force_citation_gap_retry(
            "Merhaba! Size nasıl yardımcı olabilirim?",
            _SOURCES,
            citation_gap_guard=True,
            forced_once=False,
        )
        is False
    )


def test_gate_false_when_cite_token_already_present() -> None:
    cited = _SUBSTANTIVE + " Karar metni kamuoyuyla paylaşıldı [1]."
    assert (
        _should_force_citation_gap_retry(
            cited, _SOURCES, citation_gap_guard=True, forced_once=False
        )
        is False
    )


def test_gate_false_for_range_and_w_citations() -> None:
    # _cited_numbers toleransı: [1-3] ve [W1] de citation sayılır → tetiklemez.
    for tok in ("[1-3]", "[W1]", "[1, 2]"):
        cited = _SUBSTANTIVE + f" Detaylar kaynakta {tok}."
        assert (
            _should_force_citation_gap_retry(
                cited, _SOURCES, citation_gap_guard=True, forced_once=False
            )
            is False
        ), tok


def test_gate_false_when_already_forced_once() -> None:
    # Tek-retry invariant'ı: ikinci tetikleme YOK (loop/sarkaç engeli).
    assert (
        _should_force_citation_gap_retry(
            _SUBSTANTIVE, _SOURCES, citation_gap_guard=True, forced_once=True
        )
        is False
    )


def test_nudge_is_fixed_two_branch_and_pii_free() -> None:
    # Sabit metin: iki çıkış da var; kullanıcı-verisi placeholder'ı yok.
    assert "destekliyorsa" in _CITATION_GAP_NUDGE
    assert "desteklemiyorsa" in _CITATION_GAP_NUDGE
    assert "[n]" in _CITATION_GAP_NUDGE
    assert "atfetme" in _CITATION_GAP_NUDGE  # sahte-atıf yasağı hatırlatması
    for forbidden in ("{", "}", "@", "user_id", "email"):
        assert forbidden not in _CITATION_GAP_NUDGE, forbidden


def test_registry_entry_default_off() -> None:
    from app.modules.settings_admin.routes import SETTING_REGISTRY

    entry = SETTING_REGISTRY["research.citation_gap_guard_enabled"]
    assert entry["default"] is False
    assert entry["type"] == "bool"
    assert entry["group"] == "research"
    assert entry["requires_restart"] is False
