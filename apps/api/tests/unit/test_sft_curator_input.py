"""#1013 (Faz 2a) — _build_input_payload effective_query/self-contained testi.

L1 görünmez bağlam gelince ham follow-up tek başına eğitim INPUT'u olarak
KOPUK kalır. condense sonrası standalone effective_query cevabı gerçekte
ÜRETEN sorgudur → INPUT olarak o kullanılmalı (self-contained). None ise
ham content'e düşülmeli (geriye-uyum, davranış değişmez). S8: schema/
provenance sürümü ham-input örneklerinden ayırt edilebilmeli.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.workers.tasks.sft_curator import _build_input_payload


def _msgs(*, raw: str, eff: str | None, sources=None):
    cid = uuid.uuid4()
    user = SimpleNamespace(content=raw, conversation_id=cid, id=uuid.uuid4())
    assistant = SimpleNamespace(
        effective_query=eff, sources_used=sources, id=uuid.uuid4()
    )
    return user, assistant


def test_effective_query_used_when_rewritten():
    """Follow-up ham 'Ankara'da ne yapacakmış?' → INPUT condense'li
    standalone sorgu olmalı (self-contained); rewritten=True."""
    user, assistant = _msgs(
        raw="Ankara'da ne yapacakmış?",
        eff="Özgür Özel Ankara ziyaretinde ne yapacak?",
    )
    p = _build_input_payload(user, assistant)
    assert p["messages"][0]["content"].startswith(
        "Özgür Özel Ankara ziyaretinde ne yapacak?"
    )
    assert p["effective_query_rewritten"] is True
    assert p["input_schema_version"] == "v2-effective_query"
    assert p["raw_user_content"] == "Ankara'da ne yapacakmış?"
    assert p["effective_query"] == "Özgür Özel Ankara ziyaretinde ne yapacak?"


def test_raw_fallback_when_effective_query_none():
    """effective_query None (eski örnek / rewrite yok) → ham content
    (geriye-uyum; eski davranışla birebir)."""
    user, assistant = _msgs(raw="Bugünkü gündemde ne var?", eff=None)
    p = _build_input_payload(user, assistant)
    assert p["messages"][0]["content"] == "Bugünkü gündemde ne var?"
    assert p["effective_query_rewritten"] is False
    assert p["effective_query"] is None


def test_not_rewritten_when_effective_equals_raw():
    """condense rewrite üretmedi (effective == raw) → rewritten=False."""
    user, assistant = _msgs(
        raw="Enflasyon ne durumda?", eff="Enflasyon ne durumda?"
    )
    p = _build_input_payload(user, assistant)
    assert p["effective_query_rewritten"] is False
    assert p["messages"][0]["content"] == "Enflasyon ne durumda?"


def test_sources_block_appended_to_effective_input():
    """Kaynak bloğu effective INPUT'a eklenir (mevcut davranış korunur)."""
    user, assistant = _msgs(
        raw="x",
        eff="Özgür Özel son gelişmeler",
        sources=[{"title": "Başlık", "source_name": "Kaynak"}],
    )
    p = _build_input_payload(user, assistant)
    c = p["messages"][0]["content"]
    assert c.startswith("Özgür Özel son gelişmeler")
    assert "Kaynaklar:" in c and "[1] Kaynak — Başlık" in c


def test_metadata_keys_present():
    user, assistant = _msgs(raw="r", eff="e")
    p = _build_input_payload(user, assistant)
    for k in (
        "conversation_id",
        "user_message_id",
        "assistant_message_id",
        "input_schema_version",
        "raw_user_content",
        "effective_query",
        "effective_query_rewritten",
    ):
        assert k in p
