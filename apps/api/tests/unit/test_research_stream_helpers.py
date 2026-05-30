"""SSE + research stream pure-helper characterization tests (T6 P6 PR-A).

Locking the current behavior of pure helpers in
`apps/api/app/api/app_research_stream.py` BEFORE any refactor:

- `_sse(event, data)` — SSE event serialization
- `_simulate_stream(text)` — async word-group generator
- `_log_coverage_gap(reason, question)` — telemetry logging

Davranış İCAT ETMEZ — production output'unu doğrular. Hiçbir DB / async
network call yok; tüm test'ler pure or light-mock.

PR #1144 (extractor characterization) ve PR #1148 (retrieval characterization)
pattern'ini takip eder. Refactor sonrası bu testler PASS koşulu sağlamalı.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch
from uuid import UUID

import pytest

# `app.api.app_research_stream` → `app.modules.accounts.deps` → `app.core.security` import
# zinciri `pyotp` (Docker-only) gerektiriyor. Local pre-flight'ta pyotp yoksa
# testler SKIP; CI/Docker'da modül yüklüyse çalışır.
pytest.importorskip("pyotp")

from app.api.app_research_stream import (
    _log_coverage_gap,
    _simulate_stream,
    _sse,
)
from app.modules.generations.citation import (
    _has_reconstruction_marker,
    _maybe_reframe_for_faithfulness,
)

# ============================================================================
# _sse() — SSE event formatting (pure JSON + string assembly)
# ============================================================================


def test_sse_basic_format_event_and_data():
    """SSE format: 'event: NAME\\ndata: JSON\\n\\n'."""
    out = _sse("chunk", {"delta": "hello"})
    assert out == 'event: chunk\ndata: {"delta": "hello"}\n\n'


def test_sse_none_data_becomes_empty_dict():
    """data=None → '{}' JSON (not 'null')."""
    out = _sse("done")
    assert out == "event: done\ndata: {}\n\n"


def test_sse_empty_dict_data():
    """data={} aynen '{}' yazılır."""
    out = _sse("ping", {})
    assert "data: {}" in out


def test_sse_unicode_preserved_no_ascii_escape():
    """ensure_ascii=False — Türkçe karakter ham gönderilir."""
    out = _sse("thinking_step", {"detail": "İmamoğlu davası"})
    # Türkçe chars JSON'da escape edilmemeli
    assert "İmamoğlu" in out
    assert "davası" in out
    # \\u escape'i YOK
    assert "\\u0130" not in out


def test_sse_uuid_serialized_via_default_str():
    """UUID object → str (default=str)."""
    uid = UUID("12345678-1234-5678-1234-567812345678")
    out = _sse("done", {"conversation_id": uid})
    assert "12345678-1234-5678-1234-567812345678" in out
    # Parse edilebilir JSON olmalı
    data_line = out.split("data: ")[1].split("\n\n")[0]
    parsed = json.loads(data_line)
    assert parsed["conversation_id"] == str(uid)


def test_sse_nested_dict_serialized():
    """Nested dict (sources list of dict) → valid JSON."""
    sources = [
        {"id": "s1", "title": "Haber 1", "score": 0.85},
        {"id": "s2", "title": "Haber 2", "score": 0.72},
    ]
    out = _sse("source_discovered", {"sources": sources})
    data_line = out.split("data: ")[1].split("\n\n")[0]
    parsed = json.loads(data_line)
    assert len(parsed["sources"]) == 2
    assert parsed["sources"][0]["title"] == "Haber 1"
    assert parsed["sources"][1]["score"] == 0.72


def test_sse_special_chars_json_escaped():
    """Newline, quote, backslash → JSON-escape (raw görmez)."""
    out = _sse("chunk", {"delta": 'line1\nline2 "quoted" with\\backslash'})
    data_line = out.split("data: ")[1].split("\n\n")[0]
    parsed = json.loads(data_line)
    assert parsed["delta"] == 'line1\nline2 "quoted" with\\backslash'


def test_sse_trailing_double_newline():
    """SSE block sonu mutlaka '\\n\\n' (event separator)."""
    out = _sse("error", {"code": "E1"})
    assert out.endswith("\n\n")
    # Tek bir '\n\n' bloğu (gereksiz boşluk yok)
    assert out.count("\n\n") == 1


# ============================================================================
# _simulate_stream() — async word-group generator (light async, no I/O)
# ============================================================================


@pytest.mark.asyncio
async def test_simulate_stream_empty_string_yields_empty_chunk():
    """Caveat: empty string → `"".split(" ")` → `[""]` → 1 iteration, final
    group `[""]` yielded as `""` (one empty chunk).

    Caveat: final iteration `yield` sonrası `await asyncio.sleep(0.018)`
    ÇAĞRILIR (loop body son `sleep` satırını her zaman çalıştırır — yield
    point'inden sonra). Davranış aynen kilitlenir; "skip last sleep"
    optimization YOK.
    """
    with patch("app.api.app_research_stream.asyncio.sleep") as mock_sleep:
        chunks = [c async for c in _simulate_stream("")]
    # split("") → [""] → 1 yield, final group → "" + "" = ""
    assert chunks == [""]
    # Final iteration sleep ÇAĞRILIR (`await asyncio.sleep` yield sonrası)
    assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_simulate_stream_single_word_yields_one_no_sleep():
    """Tek kelime → tek group, final yield (no trailing space, no sleep)."""
    with patch("app.api.app_research_stream.asyncio.sleep") as mock_sleep:
        chunks = [c async for c in _simulate_stream("merhaba")]
    assert chunks == ["merhaba"]
    # Final iteration → sleep çağrılır ama loop'tan çıkıldığı için etkisiz
    # (Caveat: kod final group'tan sonra da sleep() çağırır — `await asyncio.sleep`)
    assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_simulate_stream_four_word_group_then_partial_final():
    """4 kelime → bir group (trailing space) → 5. partial (no trailing space)."""
    with patch("app.api.app_research_stream.asyncio.sleep"):
        chunks = [c async for c in _simulate_stream("bir iki üç dört beş")]
    # Group 1 (4 word): "bir iki üç dört " (trailing space)
    # Group 2 (final partial): "beş" (no trailing space)
    assert chunks == ["bir iki üç dört ", "beş"]


@pytest.mark.asyncio
async def test_simulate_stream_eight_words_two_full_groups_final_no_space():
    """8 kelime → 2 dolu 4'lü group (her ikisi trailing space) + final iteration empty extra group YOK."""
    with patch("app.api.app_research_stream.asyncio.sleep"):
        chunks = [c async for c in _simulate_stream("a b c d e f g h")]
    # Group 1: "a b c d " (i=3, len>=4); group 2: "e f g h" (i=7=len-1, no trailing)
    assert chunks == ["a b c d ", "e f g h"]
    # Caveat: 8. (son) word'te trailing space YOK — final iteration check
    assert chunks[-1] == "e f g h"
    assert not chunks[-1].endswith(" ")


@pytest.mark.asyncio
async def test_simulate_stream_pacing_sleep_018_per_group():
    """Her group yield sonrası `asyncio.sleep(0.018)` çağrısı."""
    with patch("app.api.app_research_stream.asyncio.sleep") as mock_sleep:
        chunks = [c async for c in _simulate_stream("bir iki üç dört beş altı")]
    # 6 kelime → group1 (4 word, i=3) + group2 (2 word, i=5=len-1) = 2 yield
    assert len(chunks) == 2
    # 2 sleep çağrısı (her yield sonrası)
    assert mock_sleep.call_count == 2
    for call in mock_sleep.call_args_list:
        # İlk pozisyonel argüman 0.018
        assert call.args[0] == 0.018


# ============================================================================
# _log_coverage_gap() — telemetry logging (#1067 RC2)
# ============================================================================


def test_log_coverage_gap_logs_warning_with_reason_and_question(caplog):
    """logger.warning('coverage_gap reason=%s q=%r', reason, q)."""
    with caplog.at_level(logging.WARNING, logger="app.api.app_research_stream"):
        _log_coverage_gap("zero_source", "İmamoğlu davası tarihçesi")

    # En az 1 WARNING kaydı
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) >= 1
    msg = warnings[0].getMessage()
    assert "coverage_gap" in msg
    assert "zero_source" in msg
    assert "İmamoğlu" in msg


def test_log_coverage_gap_question_truncated_at_160(caplog):
    """`(question or '')[:160]` — uzun question kısaltılır."""
    long_q = "x" * 500  # 500 char
    with caplog.at_level(logging.WARNING, logger="app.api.app_research_stream"):
        _log_coverage_gap("indirect:UNSUPPORTED", long_q)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) >= 1
    msg = warnings[0].getMessage()
    # 'q=' sonrası repr edilen string — 160 char limitiyle kısalır
    # repr eklediği tırnaklar dahil değil; truncated string 160 char
    truncated_count = msg.count("x")
    assert truncated_count == 160


def test_log_coverage_gap_none_question_defaults_to_empty(caplog):
    """`question=None` → `(question or '')[:160]` → ''."""
    with caplog.at_level(logging.WARNING, logger="app.api.app_research_stream"):
        _log_coverage_gap("zero_source", "")  # type: ignore[arg-type]

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) >= 1
    msg = warnings[0].getMessage()
    assert "coverage_gap" in msg
    # Empty string repr'i — q='' veya q=""
    assert "q=''" in msg or 'q=""' in msg


def test_log_coverage_gap_suppresses_exceptions(caplog):
    """`contextlib.suppress(Exception)` — logger fail olsa bile akış bozulmaz.

    Caveat: telemetri ASLA akışı bozmaz (#1067 RC2 invariant).
    """
    with patch("app.api.app_research_stream.logger.warning", side_effect=RuntimeError("boom")):
        # Exception YUTULMALI — function None döner, hata propage etmez
        result = _log_coverage_gap("zero_source", "test")
    assert result is None  # void return


def test_log_coverage_gap_reason_categories_supported(caplog):
    """`reason` kategorileri: zero_source | indirect:INDIRECT | indirect:UNSUPPORTED.

    Davranış aynen — sadece string formatlanır, kategori validate YOK.
    """
    with caplog.at_level(logging.WARNING, logger="app.api.app_research_stream"):
        _log_coverage_gap("zero_source", "q1")
        _log_coverage_gap("indirect:INDIRECT", "q2")
        _log_coverage_gap("indirect:UNSUPPORTED", "q3")
        # Unbekannt reason — yine de log'a girer (validation yok)
        _log_coverage_gap("unknown_category", "q4")

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 4
    reasons = [r.getMessage() for r in warnings]
    assert any("reason=zero_source" in m for m in reasons)
    assert any("reason=indirect:INDIRECT" in m for m in reasons)
    assert any("reason=indirect:UNSUPPORTED" in m for m in reasons)
    assert any("reason=unknown_category" in m for m in reasons)


# ============================================================================
# _has_reconstruction_marker() — RC3-B v2 helper-level characterization
# ============================================================================
#
# `_has_reconstruction_marker(text: str) -> bool` is a PURE regex matcher
# at `app_research_stream.py:138`. Used by `_research_stream_body` to detect
# "anlaşıldığı kadarıyla / tepkisinden anlaşıl…" reconstruction tells in
# final answer text — if present + grounded sources exist, the helper
# triggers a faithfulness reframe step (orchestrator-level, NOT tested here).
#
# This PR (PR-A8) locks the **regex pattern catalogue** only — 9 marker
# variants + boundary cases. Orchestrator-level marker→faithfulness_reframed
# event coupling is DEFERRED (deep `_research_stream_body` integration
# required; 15+ mock infra) — Phase 6 PR-C+ scope.
#
# DEFERRED (PR-A7 closure analizi sonucu):
# - RC3-B orchestrator marker → `faithfulness_reframed` thinking_step event
#   coupling: deep integration required → PR-C+ scope.
# - Tool-loop timeout event: production'da timeout-specific event YOK
#   (placeholder string injection + generic tool_result thinking_step) →
#   replay-level test edilemez → PR-C+ scope.
#
# Refs:
# - PR #1067 — RC3-B v2 spec (LLM-verifier → regex marker geçişi)
# - PR #1150 — pure helper single-call lock pattern (this PR's parent)
# - app.api.app_research_stream._RECONSTRUCTION_MARKER_RE (line 124)


def test_has_reconstruction_marker_anlasildigi_kadariyla_returns_true():
    """Pattern 1/9: `"anlaşıldığı kadarıyla"` → True (canonical marker)."""
    assert _has_reconstruction_marker("Anlaşıldığı kadarıyla parti bunu reddetti.") is True


def test_has_reconstruction_marker_anlasildigina_gore_returns_true():
    """Pattern 2/9: `"anlaşıldığına göre"` → True."""
    assert _has_reconstruction_marker("Anlaşıldığına göre uzlaşı sağlanamadı.") is True


def test_has_reconstruction_marker_yansidigi_kadariyla_returns_true():
    """Pattern 3/9: `"yansıdığı kadarıyla"` → True."""
    assert _has_reconstruction_marker("Yansıdığı kadarıyla muhalefet itiraz etti.") is True


def test_has_reconstruction_marker_tepkisinden_anlasil_returns_true():
    """Pattern 4/9: `"tepkisinden anlaşıl…"` (prefix matches `anlaşılan`/`anlaşılıyor`/etc) → True."""
    assert _has_reconstruction_marker("Bakanın tepkisinden anlaşılan kararı desteklemiyor.") is True
    # Inflection coverage: "tepkisinden anlaşılıyor"
    assert _has_reconstruction_marker("Liderin tepkisinden anlaşılıyor bu konuda hassas.") is True


def test_has_reconstruction_marker_tepkisine_bakilirsa_returns_true():
    """Pattern 5/9: `"tepkisine bakılırsa"` → True."""
    assert _has_reconstruction_marker("Genel başkanın tepkisine bakılırsa süreç gergin.") is True


def test_has_reconstruction_marker_tepkisinden_cikaril_returns_true():
    """Pattern 6/9: `"tepkisinden çıkaril…"` (prefix matches `çıkarılan`/`çıkarılıyor`) → True."""
    assert _has_reconstruction_marker("Tepkisinden çıkarılan sonuç anlaşmazlık olduğudur.") is True


def test_has_reconstruction_marker_oldugu_anlasiliyor_returns_true():
    """Pattern 7/9: `"olduğu anlaşılıyor"` → True."""
    assert _has_reconstruction_marker("Mutabakat olduğu anlaşılıyor.") is True


def test_has_reconstruction_marker_oldugu_saniliyor_returns_true():
    """Pattern 8/9: `"olduğu sanılıyor"` → True."""
    assert _has_reconstruction_marker("Görüşmenin yakın olduğu sanılıyor.") is True


def test_has_reconstruction_marker_muhtemelen_demis_within_40_char_gap_returns_true():
    """Pattern 9/9: `"muhtemelen [^.]{0,40}? (demiş|söylemiş|iddia etmiş|demişti)"`.

    Lock'lar: 4 fiil alternation (demiş/söylemiş/iddia etmiş/demişti),
    `[^.]{0,40}?` gap (max 40 char, no period boundary, non-greedy).
    """
    # 4 fiil varyantı
    assert _has_reconstruction_marker("Lider muhtemelen kabul etmediğini demiş.") is True
    assert _has_reconstruction_marker("Konuyu muhtemelen toplantıda söylemiş.") is True
    assert _has_reconstruction_marker("Açıklamayı muhtemelen basına iddia etmiş.") is True
    assert _has_reconstruction_marker("Daha önce muhtemelen aynı şeyi demişti.") is True


def test_has_reconstruction_marker_muhtemelen_period_in_gap_returns_false():
    """`muhtemelen … demiş` pattern: gap içinde `.` varsa eşleşme YOK (`[^.]` exclude)."""
    # Gap'te `.` var → pattern eşleşmez
    assert _has_reconstruction_marker("Muhtemelen birden bitti. Sonra demiş.") is False


def test_has_reconstruction_marker_empty_string_returns_false():
    """Empty string → erken `if not text: return False` guard."""
    assert _has_reconstruction_marker("") is False


def test_has_reconstruction_marker_negative_normal_news_returns_false():
    """Normal Türkçe haber metni (marker keywords yok) → False."""
    assert (
        _has_reconstruction_marker(
            "Cumhurbaşkanı dün açıklama yaptı; ekonomik kararlar konusunda kararlı."
        )
        is False
    )
    assert (
        _has_reconstruction_marker(
            "Toplantı saat 14:00'te başladı, üç saat sürdü ve uzlaşı sağlandı."
        )
        is False
    )


def test_has_reconstruction_marker_case_insensitive_uppercase_returns_true():
    """`re.IGNORECASE` flag — büyük/küçük harf invariant."""
    assert _has_reconstruction_marker("ANLAŞILDIĞI KADARIYLA SÜREÇ GERGİN.") is True
    assert _has_reconstruction_marker("Tepkisine BAKILIRSA durum farklı.") is True


def test_has_reconstruction_marker_unicode_turkish_chars_preserved():
    """`re.UNICODE` flag — Türkçe karakter (ş/ğ/ı/ü/ç/ö) eşleşmesi korunur."""
    # Türkçe karakter içeren marker (canonical form: "anlaşıldığı kadarıyla")
    assert _has_reconstruction_marker("anlaşıldığı kadarıyla") is True
    # Türkçe karakter içeren negatif (marker yok)
    assert _has_reconstruction_marker("ağaç çiçek üzüm ışık") is False


def test_has_reconstruction_marker_multi_pattern_single_text_returns_true():
    """Bir metinde birden fazla marker — herhangi biri True döndürür (alternation OR)."""
    multi = (
        "Anlaşıldığı kadarıyla muhalefet itiraz etti; "
        "tepkisinden anlaşılan parti bunu kabul etmiyor."
    )
    assert _has_reconstruction_marker(multi) is True


# ============================================================================
# _maybe_reframe_for_faithfulness() — RC3-B reframe-decision pure helper
# (T6 P6 PR-C+4). Orchestrator L1118-1137'den çıkarılan SAF karar:
#   _maybe_reframe_for_faithfulness(final_text, all_sources, guard) -> str|None
# 4-predicate AND gate DA truthy ise sabit reframe metnini döner, aksi None.
# Yan etki YOK (yield/`_log_coverage_gap`/atama orchestrator'da kalır → mock=0).
# Davranış İCAT ETMEZ — production gate'ini (guard ∧ all_sources ∧
# _is_substantive ∧ _has_reconstruction_marker) doğrular.
# ============================================================================

# >120 char (substantive) + reconstruction marker ("anlaşıldığı kadarıyla")
_SUBSTANTIVE_WITH_MARKER = (
    "Anlaşıldığı kadarıyla muhalefet partisi bu yasa teklifine sert biçimde "
    "itiraz etti ve görüşmeler boyunca taraflar arasında uzlaşı sağlanamadı; "
    "eldeki kaynaklar konuya yalnız dolaylı değiniyor."
)
# >120 char (substantive) ama marker YOK (doğrudan olgusal anlatım)
_SUBSTANTIVE_NO_MARKER = (
    "Hükümet sözcüsü bugün düzenlenen basın toplantısında yeni ekonomi "
    "paketinin ayrıntılarını açıkladı ve enflasyonla mücadele için alınacak "
    "tedbirleri tek tek sıraladı; takvim de paylaşıldı."
)
# Bu PR-C+4 testlerinde beklenen reframe metni — byte-for-byte lock
# (orijinal inline literal; tek karakter değişirse test 5 KIRILIR).
_EXPECTED_REFRAME = (
    "Bu soruya **doğrudan** dayanak oluşturan bir kaynak "
    "bulunamadı; eldeki kaynaklar konuya yalnız dolaylı "
    "değiniyor (ör. bir tepki/yanıt). Çıkarımsal ya da "
    "dayanaksız cevap vermiyorum — soruyu farklı biçimde "
    "ya da daha belirgin sorabilir misin?"
)


def test_maybe_reframe_guard_false_returns_none():
    """guard=False → None (admin flag kapalı; diğer 3 koşul true olsa bile)."""
    out = _maybe_reframe_for_faithfulness(
        _SUBSTANTIVE_WITH_MARKER,
        [{"id": "s1"}],
        faithfulness_guard=False,
    )
    assert out is None


def test_maybe_reframe_empty_sources_returns_none():
    """all_sources=[] (boş, falsy) → None (taranan kaynak yok)."""
    out = _maybe_reframe_for_faithfulness(
        _SUBSTANTIVE_WITH_MARKER,
        [],
        faithfulness_guard=True,
    )
    assert out is None


def test_maybe_reframe_non_substantive_returns_none():
    """final_text kısa (non-substantive, <120) → None (marker olsa bile)."""
    short_with_marker = "Anlaşıldığı kadarıyla evet."  # marker VAR ama kısa
    out = _maybe_reframe_for_faithfulness(
        short_with_marker,
        [{"id": "s1"}],
        faithfulness_guard=True,
    )
    assert out is None


def test_maybe_reframe_no_marker_returns_none():
    """final_text substantive ama reconstruction marker YOK → None."""
    out = _maybe_reframe_for_faithfulness(
        _SUBSTANTIVE_NO_MARKER,
        [{"id": "s1"}],
        faithfulness_guard=True,
    )
    assert out is None


def test_maybe_reframe_all_conditions_true_returns_exact_reframe():
    """4 koşul DA true → sabit reframe metni (byte-for-byte lock)."""
    out = _maybe_reframe_for_faithfulness(
        _SUBSTANTIVE_WITH_MARKER,
        [{"id": "s1"}, {"id": "s2"}],
        faithfulness_guard=True,
    )
    # Exact string lock — tek karakter değişirse bu assertion KIRILIR
    assert out == _EXPECTED_REFRAME


def test_maybe_reframe_1058_exclusion_no_sources_even_with_marker():
    """#1058 karşılıklı dışlama: kaynak YOKKEN marker+substantive olsa bile None.

    Bu gate `all_sources` (truthy) ister; #1058'in `not all_sources` dalı
    AYRI ele alınır (orchestrator). Yani kaynak-yok + imleç → bu reframe
    TETİKLENMEZ (çift-reframe önlenir).
    """
    out = _maybe_reframe_for_faithfulness(
        _SUBSTANTIVE_WITH_MARKER,  # substantive + marker VAR
        [],  # ama kaynak YOK
        faithfulness_guard=True,
    )
    assert out is None
