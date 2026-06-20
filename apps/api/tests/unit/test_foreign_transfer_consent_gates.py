"""Unit — yurt-dışı LLM endpoint'leri server-side foreign-transfer consent gate'li.

#800 göçünde research LLM gate'i düşmüştü (KVKK boşluğu); 2026-06 geri yüklendi.
Route dependant ağacında `require_foreign_transfer_consent` var mı introspect eder
(TestClient/DB gerektirmez). Regresyon guard: billing checkout gate'i de korunmalı.
"""

from __future__ import annotations

from app.main import app
from app.modules.accounts.deps import require_foreign_transfer_consent


def _route(substr: str):
    for r in app.routes:
        if substr in getattr(r, "path", ""):
            return r
    raise AssertionError(f"route bulunamadı: {substr}")


def _has_dep(dependant, target, depth: int = 0) -> bool:
    """Dependant ağacında target callable'ı bir dependency olarak var mı (DFS)."""
    if depth > 8:
        return False
    for d in getattr(dependant, "dependencies", []):
        if getattr(d, "call", None) is target:
            return True
        if _has_dep(d, target, depth + 1):
            return True
    return False


def test_research_messages_has_consent_gate():
    # Birincil LLM endpoint'i (DeepSeek/Anthropic'e içerik gönderir) — KVKK m.9.
    r = _route("/conversations/{conversation_id}/messages")
    assert _has_dep(r.dependant, require_foreign_transfer_consent)


def test_quick_action_has_consent_gate():
    # Faz 3b-2 artefakt LLM revizyonu — yurt-dışı çağrı → consent zorunlu.
    r = _route("/artifacts/{artifact_id}/quick-action")
    assert _has_dep(r.dependant, require_foreign_transfer_consent)


def test_billing_checkout_still_gated():
    # Regresyon guard: mevcut gate korunuyor (değişiklik yan etkisi olmasın).
    r = _route("/checkout")
    assert _has_dep(r.dependant, require_foreign_transfer_consent)


def test_direct_edit_revise_not_consent_gated():
    # revise (canvas direkt-edit, 3b-1) LLM çağırmaz (kullanıcı içeriği) →
    # consent gate'i OLMAMALI (yalnız yurt-dışı çağrı yapan endpoint'ler gate'li).
    r = _route("/artifacts/{artifact_id}/revise")
    assert not _has_dep(r.dependant, require_foreign_transfer_consent)
