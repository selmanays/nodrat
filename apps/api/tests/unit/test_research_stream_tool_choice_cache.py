"""Regression: DeepSeek tool_choice cache-prefix invariant (research orchestrator).

#1006 / [[feedback_deepseek_toolchoice_cache]]: kontrollü deney (app_research_stream.py
~838-861) KANITLADI — `tool_choice="none"` DeepSeek'in tools şemasını prompt'a HİÇ
koymamasına yol açar (none ≡ tools-yok: input 8066 vs auto 8345); auto↔none switch
cached=0 → cache-prefix çöker. Bu yüzden agentic tool-loop'taki TÜM round'lar
`tool_choice="auto"` (veya first-round force `"required"`) kullanmalı; `"none"`
YALNIZ forced-final retry istisnasında (cache kaybı yalnız orada kabul, doğruluk > cache).

Bu test, agentic-loop'un `tool_choice` durumunun (next_tool_choice) yanlışlıkla "none"a
kaymasını (P6 orchestrator split dahil herhangi bir değişiklikte cache-break) engeller.

NOT: `app_research_stream` import edilince `pyotp` (Docker-only) gerekiyor → kaynak DOSYA
metni taranır (import yok; test_research_telemetry_wired paterni). P6 orchestrator split
sonrası tool-loop başka modüle taşınırsa _SRC path repoint edilir (4. gizli-caller sınıfı).
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2] / "app" / "api" / "app_research_stream.py").read_text(
    encoding="utf-8"
)


def test_agentic_loop_tool_choice_never_none():
    """Agentic tool-loop state (`next_tool_choice`) yalnız 'auto'/'required' olabilir.

    'none' agentic loop'a sızarsa her round prefix'i değişir → DeepSeek prompt-cache
    çöker (tools şeması in/out). Cache invariant'ın çekirdek guard'ı."""
    assignments = re.findall(r'next_tool_choice\s*=\s*"(\w+)"', _SRC)
    assert assignments, "next_tool_choice ataması yok — orchestrator yapısı değişti mi?"
    bad = set(assignments) - {"auto", "required"}
    assert not bad, (
        f"agentic-loop tool_choice 'none'/beklenmeyen değer → cache break: {assignments}"
    )


def test_forced_final_none_is_documented_exception():
    """forced-final retry `tool_choice="none"` kullanır — tek istisna (doğruluk > cache),
    cache-rationale yorumuyla belgeli."""
    assert 'tool_choice="none"' in _SRC, "forced-final 'none' istisnası kayboldu"
    assert "cache" in _SRC, "tool_choice cache-rationale belgesi (yorum) kayboldu"


def test_tool_choice_values_are_known_set():
    """Tüm literal `tool_choice="X"` değerleri {auto, none, required} kümesinden.

    Yeni/beklenmeyen değer = bilinçli denetim gerektirir (cache + DeepSeek davranışı)."""
    vals = set(re.findall(r'tool_choice\s*=\s*"(\w+)"', _SRC))
    assert vals, "tool_choice literal yok — yapı değişti mi?"
    assert vals <= {"auto", "none", "required"}, f"beklenmeyen tool_choice değeri: {vals}"
