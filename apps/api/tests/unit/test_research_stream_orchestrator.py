"""Minimal orchestration characterization tests for `_research_stream_body`
(T6 P6 PR-A5).

`_research_stream_body` is the SSE orchestrator (line 563, ~853 LoC) that
chains: thinking_step events → condense → planner → search/retrieve →
provider streaming → followups → done. Full integration testing requires
15+ mocks (auth + DB queries + settings_store + prompts_store + registry +
research_tools + providers + persist). PR-A5 scope: **first yield only** —
since the body emits its FIRST event BEFORE any external dep is called.

The first yielded event is always `thinking_step` with `phase=context_check`,
emitted at lines 596-605. Before this point: lazy imports (production
modules — load successfully), inline `_log_step` closure definition,
`_sse` call (PR #1150 already locked). NO external dep is touched until
line 619 (`await _recent_conversation_context(db, ...)`), which executes
AFTER the first yield is consumed.

Test strategy: call `_research_stream_body(**kwargs)`, get the async
generator, consume ONE event via `await anext(gen)`, then close the
generator. Mocks needed: 1 AsyncMock (db) + 2 MagicMock (user, payload)
+ 5 primitive args = 3 mocks total.

Refs:
- PR #1150 — `_sse` single-call lock (regression safety-net)
- PR #1160 / #1162 — replay/event-sequence characterization
- PR #1155 / #1157 / #1159 — async helper char (light + heavy mock)
- Master plan §6 (God-file Strategy)
- `app.api.app_research_stream._research_stream_body` (line 563) —
  source-of-truth; NOT touched in PR-A5
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

# `app.api.app_research_stream` import chain pulls `pyotp` (Docker-only).
# Local pre-flight SKIP, CI/Docker PASS (PR #1150 pattern).
pytest.importorskip("pyotp")

from app.api.app_research_stream import _research_stream_body

# ============================================================================
# Test-only helpers
# ============================================================================


def _parse_sse_block(block: str) -> tuple[str, dict]:
    """Tek bir `event: X\\ndata: <json>\\n\\n` blok'u parse eder.

    PR-A3 (PR #1160) replay testlerinde tanımlı pattern; orchestrator
    yield'i de aynı format'ı kullanır (PR #1150 + PR #1153 lock'lu).
    """
    lines = block.rstrip("\n").split("\n")
    assert len(lines) == 2, f"expected 2 lines per SSE block, got {len(lines)}: {block!r}"
    assert lines[0].startswith("event: ")
    assert lines[1].startswith("data: ")
    event = lines[0][len("event: ") :]
    data = json.loads(lines[1][len("data: ") :])
    return event, data


def _make_orchestrator_kwargs(
    *,
    is_related: bool = False,
    similarity: float = 0.0,
    prev_sources: list[dict] | None = None,
):
    """Build minimum-viable `_research_stream_body` kwargs.

    First yield (line 596-605) needs nothing more than `is_related`,
    `prev_sources`, `similarity`. `db`/`user`/`payload`/UUIDs/`now` must
    exist as args but are NOT consulted until line 619+ — async generator
    paused at first yield never reaches that point.
    """
    db = AsyncMock()
    user = MagicMock()
    user.id = "user-123"
    user.tier = "pro"
    payload = MagicMock()
    payload.content = "Test sorgu"
    return {
        "db": db,
        "user": user,
        "conv_id": UUID("11111111-1111-1111-1111-111111111111"),
        "user_msg_id": UUID("22222222-2222-2222-2222-222222222222"),
        "payload": payload,
        "query_vec": None,
        "is_related": is_related,
        "similarity": similarity,
        "prev_sources": prev_sources,
        "now": datetime(2026, 5, 21, 11, 0, 0),
    }


# ============================================================================
# PR-A5 — minimal orchestration characterization (first yield only)
# ============================================================================


@pytest.mark.asyncio
async def test_orchestrator_first_yield_is_thinking_step_context_check_default_path():
    """Default path (no context): first yield is `thinking_step{phase=context_check}`.

    `is_related=False` OR `prev_sources=None/[]` → else branch (line 604-605):
        yield _log_step("context_check", "Yeni konu — sıfırdan kaynak araması")

    Lock'lar:
      - Orchestrator'un İLK event'i her zaman `thinking_step` (error/done
        değil, sadece thinking_step ile başlar)
      - phase = "context_check" sabit
      - detail = "Yeni konu — sıfırdan kaynak araması" exact match
      - latency_ms = 0 (ilk step default)
      - SSE format `event: thinking_step\\ndata: {...}\\n\\n`
      - İlk yield öncesi HİÇBİR external dep (DB/provider/registry/prompts_store)
        çağrılmaz — db.execute / db.scalar / vb. `assert_not_called` ile lock'lu
    """
    kwargs = _make_orchestrator_kwargs(is_related=False, prev_sources=None)
    db_mock = kwargs["db"]

    gen = _research_stream_body(**kwargs)
    try:
        first_frame = await anext(gen)
    finally:
        await gen.aclose()

    # SSE frame parse
    event, data = _parse_sse_block(first_frame)
    assert event == "thinking_step"
    assert data == {
        "phase": "context_check",
        "detail": "Yeni konu — sıfırdan kaynak araması",
        "latency_ms": 0,
    }

    # İlk yield öncesi DB çağrı YAPILMADI — orchestrator ilk event tamamen
    # input-bound (is_related/prev_sources/similarity ile dallanır)
    db_mock.execute.assert_not_called()
    db_mock.scalar.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_first_yield_related_branch_includes_similarity_and_source_count():
    """Related branch: `is_related=True` + `prev_sources=[...]` → context_check detail
    pattern `"Önceki sorularla ilişkili (similarity=X.XX) — N kaynak değerlendiriliyor"`.

    Üretici (line 598-603):
        yield _log_step(
            "context_check",
            f"Önceki sorularla ilişkili (similarity={similarity:.2f}) — "
            f"{len(prev_sources)} kaynak değerlendiriliyor",
        )

    Lock'lar:
      - Branch koşulu: `is_related AND prev_sources` (truthy)
      - `similarity={value:.2f}` format spec — 2 decimal places sabit
      - `len(prev_sources)` integer count inline
      - detail substring lock: "Önceki sorularla ilişkili", "similarity=",
        "kaynak değerlendiriliyor"
      - phase + latency_ms aynen (default path ile özdeş)
    """
    prev = [{"id": "src-1", "title": "A"}, {"id": "src-2", "title": "B"}]
    kwargs = _make_orchestrator_kwargs(
        is_related=True,
        similarity=0.876,
        prev_sources=prev,
    )

    gen = _research_stream_body(**kwargs)
    try:
        first_frame = await anext(gen)
    finally:
        await gen.aclose()

    event, data = _parse_sse_block(first_frame)
    assert event == "thinking_step"
    assert data["phase"] == "context_check"
    assert data["latency_ms"] == 0

    # Detail substring + format lock
    detail = data["detail"]
    assert detail.startswith("Önceki sorularla ilişkili (similarity=")
    # `:.2f` → "0.88" (round-half-even); upstream format spec lock
    assert "similarity=0.88" in detail
    # `len(prev_sources)` inline → 2
    assert "2 kaynak değerlendiriliyor" in detail
