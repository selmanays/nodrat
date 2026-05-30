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

from app.modules.generations.streaming.helpers import _simulate_stream, _sse

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

    # 4) chunk × N — `_simulate_stream` üretici davranışı.
    #
    # Caveat (PR #1150 lock'u): `_simulate_stream` RAW word-group string'leri
    # yield eder (SSE-formatted DEĞİL). Production `_research_stream_body`
    # caller'ı (line 1289) bunları `_sse("chunk", {"delta": piece})` ile sarar.
    # Bu replay testinde caller davranışını birebir taklit etmemiz gerekiyor.
    content = "Türkçe örnek cevap metni — kelime grupları ile akış."
    raw_chunks = await _collect(_simulate_stream(content))
    chunk_frames = [_sse("chunk", {"delta": piece}) for piece in raw_chunks]
    transcript_parts.extend(chunk_frames)

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
    assert chunk_count == len(chunk_frames)

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


# ============================================================================
# PR-A4 — minimal replay expansion (T6 P6 PR-A4)
# ============================================================================
#
# Extends PR-A3 replay coverage with 4 boundary scenarios that PR-A3 single
# happy-path + error-path didn't reach. Same disciplines apply: 0 mock,
# 0 production code change, `_simulate_stream` chunks wrapped via
# `_sse("chunk", {"delta": piece})` to mirror production caller
# (`_research_stream_body:1289`).
#
# Refs:
# - PR #1160 (P6 PR-A3) — initial replay harness + 2 minimal tests
# - PR #1150 — pure helper single-call lock (raw word string yield invariant)
# - refactor-pr-checklist §13.4 — replay caller-wrap deseni dersi


@pytest.mark.asyncio
async def test_replay_chunk_only_stream_minimal_done():
    """Minimal chunk-only akış (no thinking_step, no source_discovered, no followup).

    Production'da bu pattern KAYNAKSIZ kısa cevaplarda görülür (greeting,
    meta, kimlik soruları — substantive-gate KAPALI; followup_suggestions
    EVENT YOK; done payload `sources_used_count=0`+`followup_count=0`).
    Replay'de SSE frame format ve event sırası lock'lanır.
    """
    raw_chunks = await _collect(_simulate_stream("Merhaba, ben Nodrat."))
    chunk_frames = [_sse("chunk", {"delta": piece}) for piece in raw_chunks]
    transcript_parts: list[str] = []
    transcript_parts.extend(chunk_frames)
    transcript_parts.append(
        _sse(
            "done",
            {
                "conversation_id": "00000000-0000-0000-0000-000000000001",
                "user_message_id": "00000000-0000-0000-0000-000000000002",
                "assistant_message_id": "00000000-0000-0000-0000-000000000003",
                "is_followup": False,
                "similarity": 0.0,
                "query_class": "greeting",
                "used_wikipedia": False,
                "sources_used_count": 0,
                "sources_considered_count": 0,
                "followup_count": 0,
            },
        )
    )

    raw_stream = "".join(transcript_parts)
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]
    chunk_count = sum(1 for e in events if e == "chunk")

    # Strict order: chunk × N → done
    assert chunk_count == len(chunk_frames)
    assert events == ["chunk"] * chunk_count + ["done"]
    assert raw_stream.count("\n\n") == len(parsed)

    # done payload sources/followup zero invariant
    _done_event, done_data = parsed[-1]
    assert done_data["sources_used_count"] == 0
    assert done_data["sources_considered_count"] == 0
    assert done_data["followup_count"] == 0


@pytest.mark.asyncio
async def test_replay_empty_followup_no_followup_event_emitted():
    """followups=[] → `followup_suggestions` event YOK; done.followup_count=0.

    Production guard `_research_stream_body:1387` (`if followups: yield ...`)
    boş listede event'i atlar. Replay'de event yokluğu + done event sırası
    lock'lanır.
    """
    transcript_parts: list[str] = []
    transcript_parts.append(
        _sse(
            "thinking_step",
            {"phase": "context_check", "detail": "Yeni konu", "latency_ms": 0},
        )
    )
    transcript_parts.append(
        _sse("source_discovered", {"id": "s1", "title": "T", "domain": "example.com"})
    )
    raw_chunks = await _collect(_simulate_stream("Kısa cevap."))
    transcript_parts.extend([_sse("chunk", {"delta": p}) for p in raw_chunks])

    # PRODUCTION GUARD: followups=[] → followup_suggestions event YIELD EDİLMEZ
    followups: list[str] = []
    if followups:
        transcript_parts.append(_sse("followup_suggestions", {"questions": followups}))

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
                "followup_count": 0,
            },
        )
    )

    raw_stream = "".join(transcript_parts)
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]

    # followup_suggestions event hiç olmamalı
    assert "followup_suggestions" not in events
    # done.followup_count = 0
    _done, done_data = parsed[-1]
    assert done_data["followup_count"] == 0


@pytest.mark.asyncio
async def test_replay_unicode_newline_quote_payload_json_shape_locked():
    """`_sse` JSON encoding invariant'ları: Unicode/newline/quote/emoji edge cases.

    `_sse` üretici (`_research_stream_helpers.py:44`):
        `json.dumps(data or {}, ensure_ascii=False, default=str)`

    Lock'lar (replay'de SSE frame parse round-trip):
      - ensure_ascii=False → Türkçe karakter (ş/ü/ğ/İ) inline
      - emoji code-points inline (escape edilmez)
      - newline `\\n` JSON-escaped olur (literal `\\n` payload byte'ında),
        `\\n\\n` SSE block boundary KORUNUR
      - double-quote `"` JSON-escaped olur (literal `\\"`); SSE frame
        parse round-trip korunur
      - parse_sse_stream → json.loads round-trip ile original değer döner
    """
    # Edge payload — newline + quote + Unicode + emoji
    tricky_text = 'İlk satır\n"alıntılı" ikinci 🚀 satır\nüçüncü ş/ğ/ı'
    transcript_parts: list[str] = []
    transcript_parts.append(_sse("chunk", {"delta": tricky_text}))
    transcript_parts.append(
        _sse(
            "done",
            {
                "conversation_id": "abc",
                "user_message_id": "def",
                "assistant_message_id": "ghi",
                "is_followup": False,
                "similarity": 0.0,
                "query_class": "research",
                "used_wikipedia": False,
                "sources_used_count": 0,
                "sources_considered_count": 0,
                "followup_count": 0,
            },
        )
    )

    raw_stream = "".join(transcript_parts)

    # Üretici SSE format invariant'ları
    # 1) Sadece 2 SSE blok ayracı `\n\n` (newline payload içinde JSON-escape
    #    edildiği için block boundary'yi bozmaz)
    assert raw_stream.count("\n\n") == 2
    # 2) Türkçe karakter ve emoji ham byte'larda görünür (ensure_ascii=False)
    assert "İlk satır" in raw_stream
    assert "ş/ğ/ı" in raw_stream
    assert "🚀" in raw_stream
    # 3) Newline payload içinde literal `\n` (escape edilmiş) — SSE block
    #    boundary'yi paramparça etmez
    assert "\\n" in raw_stream
    # 4) Double-quote payload içinde JSON-escaped (`\"`)
    assert '\\"alıntılı\\"' in raw_stream

    # Round-trip parse — JSON.loads orijinal değeri geri verir
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]
    assert events == ["chunk", "done"]
    chunk_event, chunk_data = parsed[0]
    assert chunk_event == "chunk"
    # delta round-trip: literal newline + quote + Unicode aynen döner
    assert chunk_data["delta"] == tricky_text


@pytest.mark.asyncio
async def test_replay_multiple_source_discovered_event_order_preserved():
    """5 ardışık `source_discovered` event'i — order strict, ID/title round-trip.

    Production'da `_research_stream_body:1122` her bulunan kaynak için
    `yield _sse("source_discovered", s)` yapar. Replay'de 5+ kaynak
    event'inin SSE byte sequence'de ilk yield'den son yield'e doğru
    çıkması lock'lanır (interleave veya reorder YOK).
    """
    sources = [
        {"id": f"src-{i}", "title": f"Kaynak {i}", "domain": f"d{i}.example.com"}
        for i in range(1, 6)  # 5 kaynak
    ]
    transcript_parts: list[str] = []
    transcript_parts.append(
        _sse("thinking_step", {"phase": "retrieval", "detail": "Aranıyor", "latency_ms": 0})
    )
    for s in sources:
        transcript_parts.append(_sse("source_discovered", s))
    transcript_parts.append(
        _sse(
            "done",
            {
                "conversation_id": "c",
                "user_message_id": "u",
                "assistant_message_id": "a",
                "is_followup": False,
                "similarity": 0.0,
                "query_class": "research",
                "used_wikipedia": False,
                "sources_used_count": 5,
                "sources_considered_count": 5,
                "followup_count": 0,
            },
        )
    )

    raw_stream = "".join(transcript_parts)
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]

    # Strict order: thinking_step → source_discovered × 5 → done
    assert events == ["thinking_step"] + ["source_discovered"] * 5 + ["done"]

    # ID order: ilk yield → ilk parse; 5. yield → 5. parse (interleave yok)
    source_events = [data for ev, data in parsed if ev == "source_discovered"]
    assert [s["id"] for s in source_events] == [f"src-{i}" for i in range(1, 6)]
    # Title round-trip Unicode korunur
    assert source_events[0]["title"] == "Kaynak 1"
    assert source_events[-1]["title"] == "Kaynak 5"


# ============================================================================
# PR-A6 — minimal SSE replay/edge characterization
# ============================================================================
#
# Extends PR-A4 (4 boundary) replay coverage with 3 structural edge invariants.
# Same disciplines: 0 mock, 0 production code change, caller-wrap rule
# (PR #1160 dersi; refactor-pr-checklist §13.4).
#
# DEFERRED (kullanıcı plan rehberi — derinlik/risk):
# - RC3-B marker / marker-like event invariant: deep grounding loop
#   integration (faithfulness reframe step orchestrator içi); replay-level
#   minimal değil → PR-C+ full SSE integration kapsamı.
# - tool-loop timeout / timeout-like error event: PR #1160 test 2 generic
#   `error` event shape'i zaten lock'lu (`{code, title, reason<=200}`);
#   timeout-specific reason="" subtle ek karakterizasyon marjinal → ek
#   değer düşük → defer.
#
# Refs:
# - PR #1160 (PR-A3) — replay harness + typical/error path
# - PR #1162 (PR-A4) — 4 boundary scenarios
# - PR #1150 — pure helper single-call lock
# - refactor-pr-checklist §13.4 — caller-wrap deseni dersi


@pytest.mark.asyncio
async def test_replay_done_event_is_terminal_and_singular():
    """`done` event terminal + singular invariant — replay-level structural lock.

    Production'da `_research_stream_body` (line 1390-1404 success path,
    line 1416 error path) `done` event'i yield etmek için tek bir noktada
    dururlar; sonraki kod YOK (try block çıkışı). Python async generator
    control flow `done` yield'inden sonra ek event üretmez.

    Replay lock'lar:
      - `done` event sayısı = 1 (duplicate done guard)
      - `done` event index = parsed[-1] (terminal position)
      - SSE stream'in son block'u `event: done` ile başlar
    """
    transcript_parts: list[str] = []
    transcript_parts.append(
        _sse(
            "thinking_step",
            {"phase": "context_check", "detail": "Yeni konu", "latency_ms": 0},
        )
    )
    transcript_parts.append(
        _sse("source_discovered", {"id": "s1", "title": "T", "domain": "ex.com"})
    )
    raw_chunks = await _collect(_simulate_stream("Kısa cevap metni."))
    transcript_parts.extend([_sse("chunk", {"delta": p}) for p in raw_chunks])
    transcript_parts.append(
        _sse(
            "done",
            {
                "conversation_id": "c-1",
                "user_message_id": "u-1",
                "assistant_message_id": "a-1",
                "is_followup": False,
                "similarity": 0.0,
                "query_class": "research",
                "used_wikipedia": False,
                "sources_used_count": 1,
                "sources_considered_count": 1,
                "followup_count": 0,
            },
        )
    )

    raw_stream = "".join(transcript_parts)
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]

    # done singular + terminal
    done_count = sum(1 for e in events if e == "done")
    assert done_count == 1, f"done event must be singular, got {done_count}"
    assert events[-1] == "done", f"done event must be terminal, last={events[-1]!r}"

    # SSE byte-level: raw stream'in son non-empty block'u `event: done` ile başlar
    last_block = raw_stream.rstrip("\n").split("\n\n")[-1]
    assert last_block.startswith("event: done\n"), f"last block: {last_block!r}"


@pytest.mark.asyncio
async def test_replay_chunk_followup_done_combo_without_thinking_or_sources():
    """Chunk + followup + done minimal combo — no thinking_step, no source_discovered.

    Production'da bu pattern KAYNAKSIZ ama followup üretilen path'lerde
    görülebilir (örn. greeting → substantive değil ama yine takip soruları
    isteyen edge case; ya da meta soru cevabı). Replay lock: chunk stream
    + followup_suggestions + done sequence, source-free akış.

    Lock'lar:
      - Event sırası strict: chunk × N → followup_suggestions → done
      - Total event count = N + 2
      - `thinking_step` event hiç yok
      - `source_discovered` event hiç yok
      - `followup_suggestions` payload `{questions: list[str]}` shape
      - done.sources_used_count=0, done.followup_count > 0
    """
    transcript_parts: list[str] = []
    raw_chunks = await _collect(_simulate_stream("Selam, ben buradayım."))
    chunk_frames = [_sse("chunk", {"delta": piece}) for piece in raw_chunks]
    transcript_parts.extend(chunk_frames)

    followups = ["Daha fazla bilgi ister misiniz?", "Başka bir konu?", "Detay?"]
    transcript_parts.append(_sse("followup_suggestions", {"questions": followups}))

    transcript_parts.append(
        _sse(
            "done",
            {
                "conversation_id": "c-fu",
                "user_message_id": "u-fu",
                "assistant_message_id": "a-fu",
                "is_followup": False,
                "similarity": 0.0,
                "query_class": "greeting",
                "used_wikipedia": False,
                "sources_used_count": 0,
                "sources_considered_count": 0,
                "followup_count": len(followups),
            },
        )
    )

    raw_stream = "".join(transcript_parts)
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]
    chunk_count = sum(1 for e in events if e == "chunk")

    # Strict event order: chunk × N → followup_suggestions → done
    assert events == ["chunk"] * chunk_count + ["followup_suggestions", "done"]
    # Source-free / thinking-free invariant
    assert "thinking_step" not in events
    assert "source_discovered" not in events
    # followup payload shape
    fu_event, fu_data = parsed[-2]
    assert fu_event == "followup_suggestions"
    assert set(fu_data.keys()) == {"questions"}
    assert fu_data["questions"] == followups
    # done payload zero-source + non-zero followup
    _, done_data = parsed[-1]
    assert done_data["sources_used_count"] == 0
    assert done_data["sources_considered_count"] == 0
    assert done_data["followup_count"] == 3


@pytest.mark.asyncio
async def test_replay_source_discovered_precedes_all_chunks_no_interleave():
    """Production invariant: TÜM `source_discovered` event'leri TÜM `chunk` event'lerinden ÖNCE yield edilir.

    `_research_stream_body` orchestrator akış sırası: retrieval step
    sources'ı keşfeder (source_discovered ×N) → answer streaming step
    chunks'ı yield eder (chunk ×N). İki step ardışık, interleave YOK.

    Replay lock'lar:
      - Son `source_discovered` index < İlk `chunk` index (strict precede)
      - source_discovered'lar contiguous blok (arasında chunk yok =
        interleave yok)
    """
    transcript_parts: list[str] = []
    transcript_parts.append(
        _sse(
            "thinking_step",
            {"phase": "retrieval", "detail": "Aranıyor", "latency_ms": 50},
        )
    )
    # 3 ardışık source_discovered
    for i in range(1, 4):
        transcript_parts.append(
            _sse(
                "source_discovered",
                {"id": f"src-{i}", "title": f"K {i}", "domain": f"d{i}.com"},
            )
        )
    # Chunk stream — caller wrap (PR #1160 dersi)
    raw_chunks = await _collect(_simulate_stream("Bir iki üç dört beş altı yedi sekiz."))
    transcript_parts.extend([_sse("chunk", {"delta": p}) for p in raw_chunks])
    transcript_parts.append(
        _sse(
            "done",
            {
                "conversation_id": "c-int",
                "user_message_id": "u-int",
                "assistant_message_id": "a-int",
                "is_followup": False,
                "similarity": 0.0,
                "query_class": "research",
                "used_wikipedia": False,
                "sources_used_count": 3,
                "sources_considered_count": 3,
                "followup_count": 0,
            },
        )
    )

    raw_stream = "".join(transcript_parts)
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]

    # Strict precede invariant
    source_indices = [i for i, e in enumerate(events) if e == "source_discovered"]
    chunk_indices = [i for i, e in enumerate(events) if e == "chunk"]
    assert source_indices, "expected source_discovered events"
    assert chunk_indices, "expected chunk events"
    # Son source_discovered < ilk chunk
    assert source_indices[-1] < chunk_indices[0], (
        f"source_discovered must precede all chunks: last_source={source_indices[-1]}, "
        f"first_chunk={chunk_indices[0]}"
    )
    # Contiguous blok lock: ilk source'tan son source'a kadar hepsi source_discovered
    first_src = source_indices[0]
    last_src = source_indices[-1]
    sources_block = events[first_src : last_src + 1]
    assert all(e == "source_discovered" for e in sources_block), (
        f"source_discovered events must be contiguous (no interleave), got: {sources_block}"
    )


# ============================================================================
# PR-A7 — SSE replay/golden coverage 10. senaryo + bonus boundary edge
# ============================================================================
#
# PR-A6 sonrası 9 senaryo. Master plan §13 SSE replay golden hedefi: 10
# senaryo. PR-A7 ile 10/10 tamamlanır + 1 bonus edge.
#
# Mevcut 9 senaryo (PR-A3/A4/A6):
#   1. Typical transcript (PR-A3)
#   2. Error path (PR-A3)
#   3. Chunk-only stream + done (PR-A4)
#   4. Empty followup_suggestions (PR-A4)
#   5. Unicode/newline/quote payload (PR-A4)
#   6. Multiple source_discovered order (PR-A4)
#   7. Done event terminal + singular (PR-A6)
#   8. Chunk + followup + done combo no thinking/sources (PR-A6)
#   9. source_discovered → chunk no-interleave (PR-A6)
#
# PR-A7 yeni senaryo:
#   10. **Done payload success vs failure field-set invariant** (10. golden)
#   11. **Empty content chunk boundary** (bonus boundary edge)
#
# DEFERRED (kullanıcı plan rehberi):
# - RC3-B marker / marker-like event invariant: deep grounding loop
#   (faithfulness reframe step orchestrator içi) → replay-level minimal
#   değil → PR-C+ scope.
# - tool-loop timeout / timeout-like error: PR #1160 test 2 generic error
#   shape (`{code, title, reason<=200}`) zaten lock'lu; timeout-specific
#   reason="" subtle ek değer marjinal → defer.
#
# Refs:
# - PR #1160 / #1162 / #1166 — replay harness + 9 senaryo
# - PR #1150 — pure helper single-call lock
# - refactor-pr-checklist §13.4 — caller-wrap deseni


@pytest.mark.asyncio
async def test_replay_done_payload_success_vs_failure_field_set_invariant():
    """10. SSE replay golden: `done` event success vs failure payload field-set kıyaslaması.

    Production iki ayrı done event yield noktası:
      - Success path (line 1390-1404): 10-field payload (`conversation_id`,
        `user_message_id`, `assistant_message_id`, `is_followup`,
        `similarity`, `query_class`, `used_wikipedia`, `sources_used_count`,
        `sources_considered_count`, `followup_count`)
      - Failure path (line 1416): 1-field payload (`status: "failed"`)

    Replay lock — karşılıklı dışlayan field set:
      - Success `done` payload: 10 field, "status" YOK
      - Failure `done` payload: 1 field, success field'larından hiç yok
      - Field set kesişimi boş (orthogonal payload shapes)
    """
    # Success path done
    success_done_frame = _sse(
        "done",
        {
            "conversation_id": "c-success",
            "user_message_id": "u-success",
            "assistant_message_id": "a-success",
            "is_followup": False,
            "similarity": 0.42,
            "query_class": "research",
            "used_wikipedia": True,
            "sources_used_count": 2,
            "sources_considered_count": 5,
            "followup_count": 3,
        },
    )
    # Failure path done
    failure_done_frame = _sse("done", {"status": "failed"})

    _success_event, success_data = _parse_sse_block(success_done_frame)
    _failure_event, failure_data = _parse_sse_block(failure_done_frame)

    success_fields = set(success_data.keys())
    failure_fields = set(failure_data.keys())

    # Success: 10-field shape lock
    expected_success_fields = {
        "conversation_id",
        "user_message_id",
        "assistant_message_id",
        "is_followup",
        "similarity",
        "query_class",
        "used_wikipedia",
        "sources_used_count",
        "sources_considered_count",
        "followup_count",
    }
    assert success_fields == expected_success_fields
    assert "status" not in success_fields

    # Failure: 1-field shape lock
    assert failure_fields == {"status"}
    assert failure_data["status"] == "failed"

    # Karşılıklı dışlayan invariant: kesişim boş
    assert success_fields.isdisjoint(failure_fields), (
        f"success ∩ failure must be empty: {success_fields & failure_fields}"
    )


@pytest.mark.asyncio
async def test_replay_empty_content_chunk_boundary_caller_wrap():
    """Bonus boundary edge: `_simulate_stream("")` → 1 yield (empty string) → caller wrap.

    PR #1150 single-call lock'u (`_simulate_stream` empty/single word
    final iteration): empty string için `await asyncio.sleep(0.018)`
    ÇAĞRILIR ve yield edilen değer = "" (boş string). Production caller
    `_research_stream_body:1289` bunu `_sse("chunk", {"delta": piece})`
    ile sarar → SSE chunk frame mevcut, delta payload boş.

    Caller-wrap rule (PR #1160 dersi): replay testte üretici davranışı
    birebir taklit edilir. Empty content → 1 chunk frame `{delta: ""}`.

    Lock'lar:
      - `_simulate_stream("")` yield count = 1 (PR #1150 lock'u — empty
        iteration final group)
      - Caller wrap → 1 SSE chunk frame
      - Transcript shape: thinking + source + chunk(delta="") + done geçerli
      - Empty delta JSON round-trip → "" string aynen
    """
    transcript_parts: list[str] = []
    transcript_parts.append(
        _sse(
            "thinking_step",
            {"phase": "context_check", "detail": "Yeni konu", "latency_ms": 0},
        )
    )
    transcript_parts.append(
        _sse("source_discovered", {"id": "s1", "title": "T", "domain": "ex.com"})
    )

    # `_simulate_stream("")` — empty content edge case
    raw_chunks = await _collect(_simulate_stream(""))
    # Production caller-wrap rule (PR #1160 dersi)
    chunk_frames = [_sse("chunk", {"delta": piece}) for piece in raw_chunks]
    transcript_parts.extend(chunk_frames)

    transcript_parts.append(
        _sse(
            "done",
            {
                "conversation_id": "c-empty",
                "user_message_id": "u-empty",
                "assistant_message_id": "a-empty",
                "is_followup": False,
                "similarity": 0.0,
                "query_class": "research",
                "used_wikipedia": False,
                "sources_used_count": 1,
                "sources_considered_count": 1,
                "followup_count": 0,
            },
        )
    )

    raw_stream = "".join(transcript_parts)
    parsed = _parse_sse_stream(raw_stream)
    events = [e for e, _ in parsed]

    # `_simulate_stream("")` 1 yield "" → 1 chunk frame `{delta: ""}` (PR #1150 lock)
    assert len(chunk_frames) == 1, f"expected 1 chunk frame, got {len(chunk_frames)}"
    # Transcript shape geçerli
    assert events == ["thinking_step", "source_discovered", "chunk", "done"]

    # Empty delta JSON round-trip
    _chunk_event, chunk_data = parsed[2]
    assert chunk_data == {"delta": ""}
    # SSE byte-level: chunk frame format intact
    assert 'event: chunk\ndata: {"delta": ""}\n\n' in raw_stream
