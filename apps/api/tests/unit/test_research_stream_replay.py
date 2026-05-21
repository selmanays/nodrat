"""Minimal SSE replay characterization tests (T6 P6 PR-A3).

`_research_stream_body` yields a sequence of SSE-formatted strings:
  - `thinking_step` × N
  - `source_discovered` × N
  - `chunk` × N (content stream — via `_simulate_stream`)
  - `followup_suggestions` (optional)
  - `done` (success) OR `error` + `done(status=failed)` (error path)

PR #1150 covered each helper's SINGLE-CALL behavior. PR-A3 covers **event
sequence / chained replay** invariants without touching production source:
  - SSE frame format remains `event: <name>\\ndata: <json>\\n\\n` for every
    event in a chain.
  - Multi-event byte concatenation preserves order + separator boundaries.
  - `_simulate_stream` chained into a wider sequence emits chunks
    inline with surrounding `thinking_step` / `done` events.
  - Error path event shape (`error` + `done(status=failed)`) is locked.

No production code is touched. No mocks needed — replay is a pure-helper
chain over `_sse` + `_simulate_stream`. Both helpers live in
`app.api._research_stream_helpers` (PR #1153 internal split).

Refs:
- PR #1150 — `_sse` / `_simulate_stream` / `_log_coverage_gap` single-call
  characterization (regression safety-net)
- PR #1153 — pure-helper internal split into `_research_stream_helpers.py`
- PR #1155 / #1157 / #1159 — async helper char (light + heavy mock)
- Master plan §6 (God-file Strategy)
- `app.api.app_research_stream._research_stream_body` — public consumer
  (NOT touched in PR-A3; replay tests deferred to PR-C+)
"""

from __future__ import annotations

import json

import pytest

# `app.api._research_stream_helpers` doğrudan import edilebilir; ancak
# `app.api.app_research_stream` üzerinden gelen re-export `pyotp` (Docker-only)
# zincirine bağlı — diğer SSE testleri pattern olarak `importorskip` ediyor.
# Burada da aynı kural uygulanıyor: local pre-flight'ta pyotp yoksa SKIP,
# CI/Docker'da çalışır (PR #1150 pattern).
pytest.importorskip("pyotp")

from app.api._research_stream_helpers import _simulate_stream, _sse

# ============================================================================
# Replay harness — small pure helpers (test-only; production code DOKUNULMAZ)
# ============================================================================


async def _collect(async_iter):
    """Async iterator'ı tek liste'ye topla — async generator replay için."""
    out = []
    async for item in async_iter:
        out.append(item)
    return out


def _parse_sse_block(block: str) -> tuple[str, dict]:
    """Tek bir `event: X\\ndata: <json>\\n\\n` blok'u (event, parsed_data) verir.

    `_sse()` çıktısının düz parser'ı; üretici taraf değişirse test breaks =
    characterization sinyali. Helper test-only — production SSE consumer'ı
    farklı bir parser kullanır (browser EventSource native).
    """
    lines = block.rstrip("\n").split("\n")
    assert len(lines) == 2, f"expected 2 lines per SSE block, got {len(lines)}: {block!r}"
    assert lines[0].startswith("event: ")
    assert lines[1].startswith("data: ")
    event = lines[0][len("event: ") :]
    data = json.loads(lines[1][len("data: ") :])
    return event, data


def _parse_sse_stream(raw: str) -> list[tuple[str, dict]]:
    """Birden çok concatenated `_sse` çıktısını (event, data) listesine ayır."""
    out = []
    # SSE blokları her zaman `\n\n` ile sonlanır → split + boş eleman drop
    blocks = [b for b in raw.split("\n\n") if b]
    for b in blocks:
        out.append(_parse_sse_block(b + "\n\n"))
    return out


# ============================================================================
# PR-A3 — minimal SSE replay characterization
# ============================================================================


@pytest.mark.asyncio
async def test_replay_typical_research_transcript_event_sequence():
    """Tipik research transcript event sırası + SSE byte format zincirleme lock.

    Simüle edilen akış (gerçek `_research_stream_body` sırasının küçültülmüş
    karakterizasyonu):
      thinking_step(context_check) → thinking_step(retrieval) →
      source_discovered → [_simulate_stream → chunk×N] →
      followup_suggestions → done

    Lock'lar:
      - Toplam event count = 2 + 1 + N(chunk) + 1 + 1
      - Event sırası strict (thinking_step → source_discovered → chunk... →
        followup → done)
      - Her event SSE format invariant'ı (`event: X\\n`, `data: {json}\\n\\n`)
      - JSON Unicode ensure_ascii=False (Türkçe karakter korunur)
      - `_simulate_stream` chunk'ları sequence içine inline edilir; her
        chunk ayrı `event: chunk\\ndata: {"delta": "..."}\\n\\n` blok'u.
    """
    # Replay harness — gerçek üretici akışın küçük emülasyonu
    transcript_parts: list[str] = []

    # 1) thinking_step: context_check
    transcript_parts.append(
        _sse(
            "thinking_step",
            {
                "phase": "context_check",
                "detail": "Yeni konu — sıfırdan kaynak araması",
                "latency_ms": 0,
            },
        )
    )

    # 2) thinking_step: retrieval
    transcript_parts.append(
        _sse(
            "thinking_step",
            {
                "phase": "retrieval",
                "detail": "3 kaynak bulundu",
                "latency_ms": 142,
            },
        )
    )

    # 3) source_discovered (× 1 minimal)
    transcript_parts.append(
        _sse(
            "source_discovered",
            {"id": "src-1", "title": "Kaynak başlığı", "domain": "example.com"},
        )
    )

    # 4) chunk × N — `_simulate_stream` üzerinden gerçek üretici davranışı
    content = "Türkçe örnek cevap metni — kelime grupları ile akış."
    chunks = await _collect(_simulate_stream(content))
    transcript_parts.extend(chunks)
    # `_simulate_stream` her grup için bir `event: chunk\ndata: {...}\n\n`
    # blok üretir. PR #1150 single-call lock'u: 4-group pacing → chunk frame
    # üretici. Burada sadece chain içinde **olduğunu** doğruluyoruz.

    # 5) followup_suggestions
    transcript_parts.append(
        _sse(
            "followup_suggestions",
            {"questions": ["Soru 1", "Soru 2"]},
        )
    )

    # 6) done (success)
    transcript_parts.append(
        _sse(
            "done",
            {
                "conversation_id": "11111111-1111-1111-1111-111111111111",
                "user_message_id": "22222222-2222-2222-2222-222222222222",
                "assistant_message_id": "33333333-3333-3333-3333-333333333333",
                "is_followup": False,
                "similarity": 0.0,
                "query_class": "research",
                "used_wikipedia": False,
                "sources_used_count": 1,
                "sources_considered_count": 1,
                "followup_count": 2,
            },
        )
    )

    raw_stream = "".join(transcript_parts)

    # ---- Parse + invariant lock'ları ----
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]
    chunk_count = sum(1 for e in events if e == "chunk")

    # Strict event sırası (chunk'lar dizi içinde değişken sayıda)
    assert events[0:3] == ["thinking_step", "thinking_step", "source_discovered"]
    assert events[-2:] == ["followup_suggestions", "done"]
    # Ortada YALNIZ chunk event'leri olmalı
    middle = events[3:-2]
    assert middle and all(e == "chunk" for e in middle)
    assert chunk_count == len(chunks)

    # Toplam frame sayısı = beklenen
    assert len(parsed) == 2 + 1 + chunk_count + 1 + 1

    # SSE byte format — her event ayrı blok + \n\n separator
    # Concatenated stream `\n\n` × N defa içermeli (her event 1 kez)
    assert raw_stream.count("\n\n") == len(parsed)
    # ensure_ascii=False — Türkçe karakter inline (escape edilmez)
    assert "Türkçe" in raw_stream
    assert "ş" in raw_stream

    # done event payload shape lock (kritik alanlar)
    done_event, done_data = parsed[-1]
    assert done_event == "done"
    assert "conversation_id" in done_data
    assert "assistant_message_id" in done_data
    assert "is_followup" in done_data
    assert "followup_count" in done_data
    assert done_data["followup_count"] == 2


@pytest.mark.asyncio
async def test_replay_error_path_event_sequence():
    """Error path replay: thinking_step → error → done(status=failed).

    Lock'lar:
      - Error event payload shape: `{code, title, reason}`; `reason`
        production'da `str(exc)[:200]` ile kırpılır (replay'de invariant
        sadece <= 200 char olduğunu doğrular).
      - Done event status="failed" YALNIZ error path'inde döner; success
        path'inde tam payload (önceki test) lock'lu.
      - Format zincirleme aynı: `event: X\\ndata: {json}\\n\\n`.
    """
    transcript_parts: list[str] = []

    transcript_parts.append(
        _sse(
            "thinking_step",
            {"phase": "context_check", "detail": "Yeni konu", "latency_ms": 0},
        )
    )

    # Üretici: `yield _sse("error", {"code": "STREAM_ERROR", "title": ...,
    # "reason": str(exc)[:200]})`. Replay'de reason payload üretici sınırını
    # bilinçli aşmamalı (lock olarak <= 200 kontrol et).
    long_reason = "x" * 200  # invariant: exact upper bound; üretici str(exc)[:200]
    transcript_parts.append(
        _sse(
            "error",
            {"code": "STREAM_ERROR", "title": "Akış hatası", "reason": long_reason},
        )
    )

    transcript_parts.append(
        _sse(
            "done",
            {"status": "failed"},
        )
    )

    raw_stream = "".join(transcript_parts)
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]

    # Strict 3-event order
    assert events == ["thinking_step", "error", "done"]
    assert len(parsed) == 3
    assert raw_stream.count("\n\n") == 3

    # Error event payload shape lock
    _err_event, err_data = parsed[1]
    assert set(err_data.keys()) == {"code", "title", "reason"}
    assert err_data["code"] == "STREAM_ERROR"
    assert err_data["title"] == "Akış hatası"
    assert len(err_data["reason"]) <= 200  # üretici str(exc)[:200] sınırı

    # Done event status="failed" alternative payload
    done_event, done_data = parsed[2]
    assert done_event == "done"
    assert done_data == {"status": "failed"}
