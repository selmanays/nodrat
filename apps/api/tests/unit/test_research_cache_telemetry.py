"""#981 — research_cache_telemetry: classify_segments + bulletproof writer.

Kritik invariant (kullanıcı teknik doğrulama yapamaz → testle KANITLA):
record_research_cache_telemetry HİÇBİR koşulda exception fırlatmaz; DB yokken
bile sessiz döner → research akışı bu telemetri için ASLA kırılmaz.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.research_cache_telemetry import (
    _approx_tokens,
    classify_segments,
    record_research_cache_telemetry,
)


@dataclass
class _Msg:
    role: str
    content: str | None = None
    tool_calls: object | None = None


@dataclass
class _Res:
    input_tokens: int = 100
    output_tokens: int = 20
    cached_input_tokens: int = 40
    model: str = "deepseek-v4-flash"


def test_approx_tokens_empty_and_nonempty():
    assert _approx_tokens(None) == 0
    assert _approx_tokens("") == 0
    assert _approx_tokens("a" * 40) == 10  # 40 // 4
    assert _approx_tokens("x") >= 1


def test_classify_segments_coarse_buckets():
    msgs = [
        _Msg(role="system", content="S" * 400),  # 100
        _Msg(role="user", content="Q" * 40),  # 10
        _Msg(role="assistant", content="", tool_calls=[{"x": 1}]),
        _Msg(role="tool", content="R" * 80),  # 20
    ]
    seg = classify_segments(msgs, tools=[{"name": "search_news"}])
    assert seg["seg_system"] == 100
    assert seg["seg_msg1_question"] == 10
    assert seg["seg_rag_tool"] == 20
    assert seg["seg_assistant_intermediate"] >= 1  # tool_calls sayıldı
    assert seg["seg_tools_schema"] >= 1  # tools schema sayıldı
    # v1 fine-split YAPILMAZ → bu kovalar 0
    assert seg["seg_msg1_static"] == 0
    assert seg["seg_msg1_history"] == 0


def test_classify_segments_handles_garbage_without_raising():
    # None / boş / bozuk dict — patlamaz, sıfır döner
    assert classify_segments(None, None)["seg_system"] == 0
    assert classify_segments([{"role": "system", "content": "ab"}])["seg_system"] >= 0


def test_record_telemetry_never_raises_without_db():
    """En kritik test: DB/bağlam yokken bile sessiz döner (raise YOK)."""
    # get_session_factory bağlanamaz / settings yok → tamamı yutulmalı.
    result = asyncio.run(
        record_research_cache_telemetry(
            provider="deepseek",
            model="deepseek-v4-flash",
            call_type="forced_final",
            conv_id="not-a-valid-uuid",  # bilinçli bozuk
            user_id=None,
            messages=[_Msg(role="system", content="x" * 12)],
            tools=[{"name": "t"}],
            res=_Res(),
            call_seq=3,
            success=True,
        )
    )
    assert result is None  # raise etmedi, None döndü


def test_record_telemetry_swallows_totally_broken_input():
    """Mesajlar/res tamamen çöp olsa bile raise YOK."""
    result = asyncio.run(
        record_research_cache_telemetry(
            provider=None,
            model=None,
            call_type="x" * 99,  # >32 char → trim edilmeli
            conv_id=object(),  # UUID'e çevrilemez
            user_id=12345,  # int
            messages="not-a-list",  # iterable ama mesaj değil
            tools="garbage",
            res=None,
            call_seq=None,
            success=False,
        )
    )
    assert result is None
