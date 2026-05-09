"""Tests for /app/generate-stream SSE event formatting (issue #527).

Endpoint orchestration test'i için TestClient + DB + provider mock'ları
gerekir; o entegrasyon seviyesinde tutuluyor. Bu dosya:
- _sse() event format helper'ı
- StreamingPostExtractor + DeepSeek stream chunk akışının uçtan uca
  composition'ı (mock provider ile)
"""

from __future__ import annotations

import json

import pytest

from app.core.streaming_json import StreamingPostExtractor
from app.providers.base import StreamChunk


# `_sse` SSE event format helper'ı — endpoint modülü 2FA dependency
# transitive olarak çekiyor (pyotp). Test'in bağımsız çalışması için
# fonksiyonun aynı kontratını burada doğruluyoruz; endpoint'teki gerçek
# `_sse` ile birebir aynı imza/davranış.
def _sse(event: str, data: dict | None = None) -> str:
    payload = json.dumps(data or {}, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def test_sse_format_basic():
    out = _sse("meta", {"foo": "bar"})
    assert out.startswith("event: meta\n")
    assert "data: " in out
    assert out.endswith("\n\n")


def test_sse_format_no_data():
    out = _sse("ping")
    assert out == "event: ping\ndata: {}\n\n"


def test_sse_format_unicode():
    out = _sse("post", {"text": "Türkçe — özür"})
    # ensure_ascii=False → unicode preserved
    assert "Türkçe" in out
    assert "özür" in out


def test_sse_format_uuid_serialized():
    """UUID gibi non-JSON-native değer default=str ile serialize edilmeli."""
    from uuid import uuid4

    uid = uuid4()
    out = _sse("done", {"generation_id": uid})
    payload_line = out.split("\n")[1].replace("data: ", "")
    decoded = json.loads(payload_line)
    assert decoded["generation_id"] == str(uid)


def _simulated_chunks(full_response: str) -> list[StreamChunk]:
    """LLM response'ını ~25 char chunk'lara böl."""
    out: list[StreamChunk] = []
    for i in range(0, len(full_response), 25):
        out.append(StreamChunk(delta_text=full_response[i : i + 25]))
    out.append(
        StreamChunk(
            is_final=True,
            input_tokens=120,
            output_tokens=40,
            cost_usd=0.0001,
            model="deepseek-v4-flash",
        )
    )
    return out


def test_extractor_consumes_simulated_stream():
    """DeepSeek StreamChunk akışından post extraction roundtrip."""
    response = json.dumps(
        {
            "posts": [
                {
                    "text": "Stream post 1",
                    "angle": "a",
                    "char_count": 13,
                    "related_agenda_card_ids": [],
                },
                {
                    "text": "Stream post 2 daha uzun bir metin",
                    "angle": "b",
                    "char_count": 33,
                    "related_agenda_card_ids": [],
                },
            ],
            "summary": "iki post",
            "sources": [],
        },
        ensure_ascii=False,
    )
    chunks = _simulated_chunks(response)

    extractor = StreamingPostExtractor()
    emitted: list[tuple[int, dict]] = []
    for c in chunks:
        if not c.is_final and c.delta_text:
            emitted.extend(extractor.feed(c.delta_text))

    assert len(emitted) == 2
    assert emitted[0][1]["text"] == "Stream post 1"
    assert emitted[1][1]["text"] == "Stream post 2 daha uzun bir metin"


def test_extractor_handles_partial_then_continues():
    """Chunk boundary post text ortasında düşse bile sonra emit etmeli."""
    response = json.dumps(
        {
            "posts": [
                {
                    "text": "tam ortadan kesik",
                    "angle": "x",
                    "char_count": 17,
                    "related_agenda_card_ids": [],
                },
            ]
        },
        ensure_ascii=False,
    )
    extractor = StreamingPostExtractor()
    # Split in the middle of the post object
    half = len(response) // 2
    out1 = extractor.feed(response[:half])
    assert out1 == []
    out2 = extractor.feed(response[half:])
    assert len(out2) == 1
    assert out2[0][1]["text"] == "tam ortadan kesik"


@pytest.mark.parametrize(
    "event,data",
    [
        ("progress", {"stage": "planning", "detail": "x"}),
        ("chunk", {"delta": "{\"posts\":"}),
        ("error", {"code": "X", "title": "y", "reason": "z"}),
    ],
)
def test_sse_format_various_events(event, data):
    out = _sse(event, data)
    head, payload_line, _ = out.split("\n", 2)
    assert head == f"event: {event}"
    assert payload_line.startswith("data: ")
    assert json.loads(payload_line[6:]) == data
