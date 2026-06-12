"""#1483 search-arg observability — ``_search_telemetry_entry`` saf helper testleri.

Kontrat: sabit key-set + ``redact()``+200-char truncate (query/topic) +
PII-free payload + error-bayrağı (timeout/exception ↔ 0-sonuç ayrımı) +
log-surface'e yazmama.

Flag-OFF byte-identical kanıtı: ``research.search_arg_telemetry_enabled``
default False (SETTING_REGISTRY) → orchestrator ``_round_searches``'i hiç
doldurmaz → ``tool_result`` ``_log_step`` kwargs'sız çağrılır → mevcut
SSE-replay/orchestrator suite'i değişmeden geçer (#619 PR-3 / PR-F kanıt
kalıbı; full-orchestrator mock "first-yield-only" disiplinince burada
tekrarlanmaz).
"""

from __future__ import annotations

from unittest.mock import patch

from app.api.app_research_stream import _search_telemetry_entry

_EXPECTED_KEYS = {
    "tool",
    "round",
    "query",
    "topic",
    "query_class",
    "chunk_count",
    "source_count",
    "error",
}

_NEWS_META = {
    "query_class": "news_query",
    "topic": "asgari ücret zammı",
    "chunk_count": 7,
    "source_count": 4,
    "recency_requested": True,
    "newest_published_at": "2026-06-11",
    "freshness_gap_days": 0,
}


def test_entry_keyset_exact() -> None:
    entry = _search_telemetry_entry(
        "search_news",
        {"query": "asgari ücret son durum"},
        _NEWS_META,
        round_no=1,
        source_count=4,
    )
    assert set(entry.keys()) == _EXPECTED_KEYS


def test_news_fields_mapped() -> None:
    entry = _search_telemetry_entry(
        "search_news",
        {"query": "asgari ücret son durum"},
        _NEWS_META,
        round_no=2,
        source_count=4,
    )
    assert entry["tool"] == "search_news"
    assert entry["round"] == 2
    assert entry["query"] == "asgari ücret son durum"
    assert entry["topic"] == "asgari ücret zammı"
    assert entry["query_class"] == "news_query"
    assert entry["chunk_count"] == 7
    assert entry["source_count"] == 4
    assert entry["error"] is False


def test_query_and_topic_redacted() -> None:
    entry = _search_telemetry_entry(
        "search_news",
        {"query": "ahmet@example.com hakkında haber, tel 0532 123 45 67"},
        {"topic": "ahmet@example.com haberleri"},
        round_no=1,
        source_count=0,
    )
    assert "ahmet@example.com" not in entry["query"]
    assert "[email_redacted]" in entry["query"]
    assert "[phone_redacted]" in entry["query"]
    assert "ahmet@example.com" not in entry["topic"]
    assert "[email_redacted]" in entry["topic"]


def test_truncation_200() -> None:
    long_query = "deprem " * 60  # 420 char
    entry = _search_telemetry_entry(
        "search_news",
        {"query": long_query},
        {},
        round_no=1,
        source_count=0,
    )
    assert len(entry["query"]) <= 200


def test_wikipedia_empty_meta_nulls() -> None:
    # _dispatch wikipedia dalı meta={} döndürür → topic/query_class/chunk_count None.
    entry = _search_telemetry_entry(
        "search_wikipedia",
        {"query": "Mustafa Kemal Atatürk"},
        {},
        round_no=1,
        source_count=2,
    )
    assert entry["tool"] == "search_wikipedia"
    assert entry["query"] == "Mustafa Kemal Atatürk"
    assert entry["topic"] is None
    assert entry["query_class"] is None
    assert entry["chunk_count"] is None
    assert entry["source_count"] == 2


def test_error_flag_true_on_timeout_path() -> None:
    # Orchestrator timeout/exception dalı: tc_meta={}, tc_sources=[], error=True.
    entry = _search_telemetry_entry(
        "search_news",
        {"query": "elektrik kesintisi"},
        {},
        round_no=1,
        source_count=0,
        error=True,
    )
    assert entry["error"] is True
    assert entry["source_count"] == 0


def test_zero_result_is_not_error() -> None:
    # Başarılı ama 0-sonuç arama: error=False + source_count=0 (ayrım kontratı).
    entry = _search_telemetry_entry(
        "search_news",
        {"query": "çok niş bir konu"},
        {"query_class": "news_topic", "topic": "niş konu", "chunk_count": 0},
        round_no=1,
        source_count=0,
    )
    assert entry["error"] is False
    assert entry["source_count"] == 0


def test_missing_or_non_string_query_is_none() -> None:
    assert (
        _search_telemetry_entry("search_news", {}, {}, round_no=1, source_count=0)["query"] is None
    )
    assert (
        _search_telemetry_entry("search_news", None, None, round_no=1, source_count=0)["query"]
        is None
    )
    assert (
        _search_telemetry_entry("search_news", {"query": 42}, {}, round_no=1, source_count=0)[
            "query"
        ]
        is None
    )


def test_payload_is_pii_free() -> None:
    # user_id/email anahtarları YOK; redaksiyon sonrası '@' kalmaz.
    entry = _search_telemetry_entry(
        "search_news",
        {"query": "mehmet.demir@firma.com.tr TC 12345678950 IBAN TR330006100519786457841326"},
        _NEWS_META,
        round_no=1,
        source_count=1,
    )
    assert "user_id" not in entry and "email" not in entry
    assert "@" not in entry["query"]
    assert "TR3300" not in entry["query"]


def test_helper_does_not_log() -> None:
    # #1483 hard-stop: arg metni log-surface'e YAZILMAZ.
    with patch("app.api.app_research_stream.logger") as mock_logger:
        _search_telemetry_entry(
            "search_news",
            {"query": "gizli-sayılabilecek kullanıcı sorgusu"},
            _NEWS_META,
            round_no=1,
            source_count=1,
        )
    mock_logger.info.assert_not_called()
    mock_logger.warning.assert_not_called()
    mock_logger.error.assert_not_called()


def test_registry_entry_default_off() -> None:
    from app.modules.settings_admin.routes import SETTING_REGISTRY

    entry = SETTING_REGISTRY["research.search_arg_telemetry_enabled"]
    assert entry["default"] is False
    assert entry["type"] == "bool"
    assert entry["group"] == "research"
    assert entry["requires_restart"] is False
