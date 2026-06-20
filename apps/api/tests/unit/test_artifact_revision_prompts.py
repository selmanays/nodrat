"""Unit — Faz 3b-2 artefakt revizyon prompt render (DB'siz, saf fonksiyon).

render_user_payload her LLM intent için doğru GÖREV talimatını gömüyor mu +
_format_sources edge-case'leri (None/dict/non-dict/30+/başlıksız). Provider/DB
çağrısı YOK; yalnız prompt katmanı.
"""

from __future__ import annotations

import pytest
from app.prompts.artifact_revision import (
    LLM_QUICK_INTENTS,
    SYSTEM_PROMPT,
    render_user_payload,
)
from app.prompts.artifact_revision import _format_sources as format_sources

# Her intent → user payload'ında bulunması beklenen ayırt edici talimat parçası.
_INTENT_MARKERS = {
    "quick_shorter": "KISALT",
    "quick_longer": "GENİŞLET",
    "quick_rewrite": "FARKLI BİR AÇIDAN",
    "multi_share": "THREAD",
}


def test_llm_quick_intents_set():
    assert {
        "quick_shorter",
        "quick_rewrite",
        "quick_longer",
        "multi_share",
    } == LLM_QUICK_INTENTS


@pytest.mark.parametrize("intent", sorted(LLM_QUICK_INTENTS))
def test_render_embeds_intent_instruction(intent):
    payload = render_user_payload("Orijinal metin [1].", [{"title": "Kaynak A"}], intent)
    assert _INTENT_MARKERS[intent] in payload
    assert "MEVCUT METİN" in payload
    assert "Orijinal metin [1]." in payload  # head içeriği gömülü
    assert "[1] Kaynak A" in payload  # kaynak referansı gömülü


def test_render_unknown_intent_falls_back_to_rewrite():
    payload = render_user_payload("metin", None, "bilinmeyen_intent")
    assert _INTENT_MARKERS["quick_rewrite"] in payload  # fallback = quick_rewrite


def test_multi_share_caps_thread_length():
    payload = render_user_payload("uzun metin", None, "multi_share")
    assert "8 post" in payload  # token bütçesiyle tutarlı thread sınırı


def test_format_sources_none_fallback():
    out = format_sources(None)
    assert "kaynak listesi yok" in out
    assert format_sources([]) == out  # boş liste = None ile aynı fallback


def test_format_sources_dict_variants():
    out = format_sources(
        [
            {"title": "Başlık"},
            {"url": "https://x.example/a"},
            {"source": "ANKA"},
            {"name": "İsim"},
            {"foo": "bar"},  # bilinen alan yok → str(dict) fallback
        ]
    )
    lines = out.splitlines()
    assert lines[0] == "[1] Başlık"
    assert lines[1] == "[2] https://x.example/a"
    assert lines[2] == "[3] ANKA"
    assert lines[3] == "[4] İsim"
    assert lines[4].startswith("[5] ")  # başlıksız dict → repr, çökme yok


def test_format_sources_non_dict_elements():
    out = format_sources(["düz string kaynak", 12345])
    assert "[1] düz string kaynak" in out
    assert "[2] 12345" in out  # non-dict → str(), çökme yok


def test_format_sources_caps_at_30():
    out = format_sources([{"title": f"K{i}"} for i in range(50)])
    assert len(out.splitlines()) == 30  # aşırı liste 30'a sınırlı (prompt şişmesi)


def test_system_prompt_has_hallucination_guard():
    # Marka çekirdeği: yeni olgu eklememe + citation koruma kuralları mevcut.
    assert "halüsinasyon" in SYSTEM_PROMPT.lower()
    assert "citation" in SYSTEM_PROMPT.lower()
