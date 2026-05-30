"""Regression: research hattı provider-call telemetri (#audit 2026-05-15).

Denetimde research'in HİÇ ölçülmediği bulundu: `app_research_stream.py` istek
başına 3+ LLM çağrısı (condense / agentic tur / forced-final) yapıyordu
ama hiçbiri `track_provider_call`'a sarılmamıştı; `record_usage` repo
genelinde hiç çağrılmıyordu → token/maliyet/latency + billing/quota
audit research için kördü. Bu test enstrümantasyonun sökülmesini engeller.

NOT: app_research_stream import edilince `pyotp` (Docker-only) gerekiyor →
kaynak DOSYA metni taranır (import yok).
"""

from __future__ import annotations

from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2] / "app" / "api" / "app_research_stream.py").read_text(
    encoding="utf-8"
)
# P6.2c (v2): _tracked_chat_generate → modules/generations/llm/tracked_chat.py.
# Helper def + internals (operation="chat", track_provider_call) o dosyada; çağrı
# yerleri (await _tracked_chat_generate) + record_usage app_research_stream'de kalır.
_TC_SRC = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "modules"
    / "generations"
    / "llm"
    / "tracked_chat.py"
).read_text(encoding="utf-8")


def test_tracked_generate_helper_exists():
    assert "async def _tracked_chat_generate(" in _TC_SRC
    assert 'operation="chat"' in _TC_SRC
    assert "track_provider_call(" in _TC_SRC


def test_chat_llm_calls_go_through_tracked_helper():
    """Agentic tur + forced-final doğrudan chat_provider.generate_text
    ÇAĞIRMAMALI — hepsi _tracked_chat_generate üzerinden (telemetri)."""
    assert "chat_provider.generate_text(" not in _SRC, (
        "ham chat_provider.generate_text → telemetri atlanır; _tracked_chat_generate kullan"
    )
    # iki çağrı yeri de helper'a bağlı
    assert _SRC.count("await _tracked_chat_generate(") >= 2


def test_record_usage_called_for_chat():
    """usage_events billing/quota audit ledger research için yazılmalı."""
    assert "from app.modules.billing.services.quota import record_usage" in _SRC
    assert "await record_usage(" in _SRC
    assert 'event_type="generation"' in _SRC
