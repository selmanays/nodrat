"""Agenda card prompt v1.0 tests (#21).

Saf fonksiyonel testler:
  - render_user_payload (input formatı)
  - parse_response (JSON validation, error path)
  - PII redaction provider tarafında (deepseek.py); buradaki test çalıştırmaz
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.prompts.agenda_card import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    AgendaCardError,
    AgendaCardOutput,
    parse_response,
    render_user_payload,
)

# ---------------------------------------------------------------------------
# Static
# ---------------------------------------------------------------------------


def test_prompt_version_semver_like():
    assert PROMPT_VERSION.count(".") == 2


def test_system_prompt_contains_critical_rules():
    """Halüsinasyon kuralları + JSON-only çıktı kontrol."""
    assert "JSON" in SYSTEM_PROMPT
    assert "UYDURMA" in SYSTEM_PROMPT  # halu rule
    assert "FSEK" in SYSTEM_PROMPT  # 25 kelime quote rule
    assert "insufficient_data" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# render_user_payload
# ---------------------------------------------------------------------------


def _make_articles(count: int = 3) -> list[dict]:
    return [
        {
            "id": f"art-{i}",
            "title": f"Article {i} başlık",
            "subtitle": f"Subtitle {i}",
            "source_name": f"Source-{i % 2}",
            "source_reliability": 0.8,
            "published_at": datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            "clean_text": f"İçerik metni {i}. " * 20,
            "canonical_url": f"https://example.com/a-{i}",
        }
        for i in range(count)
    ]


def test_render_payload_basic():
    payload_str = render_user_payload(
        event_cluster={
            "id": "cluster-1",
            "canonical_title": "Test event",
            "first_seen_at": datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
            "last_seen_at": datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            "article_count": 3,
            "source_count": 2,
        },
        articles=_make_articles(3),
    )

    payload = json.loads(payload_str)
    assert payload["event_cluster"]["canonical_title"] == "Test event"
    assert payload["event_cluster"]["article_count"] == 3
    assert len(payload["articles"]) == 3
    assert payload["articles"][0]["title"].startswith("Article 0")
    assert "current_time" in payload


def test_render_payload_truncates_long_excerpt():
    long_articles = [
        {
            "id": "art-1",
            "title": "T",
            "source_name": "S",
            "source_reliability": 0.7,
            "published_at": None,
            "clean_text": "x" * 5000,
            "canonical_url": "https://x.com/1",
        }
    ]
    payload_str = render_user_payload(
        event_cluster={"id": "c", "canonical_title": "T"},
        articles=long_articles,
        max_excerpt_chars=1000,
    )
    payload = json.loads(payload_str)
    excerpt = payload["articles"][0]["clean_text_excerpt"]
    # 1000 char + "..." (ellipsis)
    assert len(excerpt) <= 1010
    assert excerpt.endswith("...")


def test_render_payload_caps_articles_at_20():
    """Cost guard — max 20 article."""
    payload_str = render_user_payload(
        event_cluster={"id": "c", "canonical_title": "T"},
        articles=_make_articles(50),
    )
    payload = json.loads(payload_str)
    assert len(payload["articles"]) == 20


def test_render_payload_handles_naive_dates():
    """Naive datetime → no error, ISO format çıkar."""
    payload_str = render_user_payload(
        event_cluster={
            "id": "c",
            "canonical_title": "T",
            "first_seen_at": "2026-01-01T00:00:00+00:00",  # string
            "last_seen_at": datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        },
        articles=[],
    )
    payload = json.loads(payload_str)
    assert payload["event_cluster"]["first_seen_at"] == "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# parse_response — success path
# ---------------------------------------------------------------------------


VALID_RESPONSE = json.dumps(
    {
        "title": "Test gündem kartı",
        "summary": "Bu bir özet metnidir. Yeterince uzun bir paragraf, en az 50 karakter olmalı yoksa parse fails.",
        "key_points": ["Madde 1", "Madde 2", "Madde 3"],
        "content_angles": ["Açı 1", "Açı 2"],
        "timeline": [{"date": "2026-05-01", "event": "Olay"}],
        "source_refs": [
            {
                "source": "BBC",
                "title": "Haber 1",
                "url": "https://bbc.com/1",
                "published_at": "2026-05-01T10:00:00Z",
            }
        ],
        "status": "active",
        "importance_score": 0.75,
        "freshness_score": 0.9,
    },
    ensure_ascii=False,
)


def test_parse_valid_response():
    result = parse_response(VALID_RESPONSE)
    assert isinstance(result, AgendaCardOutput)
    assert result.title == "Test gündem kartı"
    assert len(result.key_points) == 3
    assert result.status == "active"
    assert 0 <= result.importance_score <= 1
    assert result.warnings == []


def test_parse_handles_markdown_fence():
    """LLM bazen ```json fence ekler — temizlenmeli."""
    fenced = f"```json\n{VALID_RESPONSE}\n```"
    result = parse_response(fenced)
    assert isinstance(result, AgendaCardOutput)
    assert result.title == "Test gündem kartı"


def test_parse_handles_markdown_fence_no_lang():
    """``` ... ``` (dil hint'siz)"""
    fenced = f"```\n{VALID_RESPONSE}\n```"
    result = parse_response(fenced)
    assert isinstance(result, AgendaCardOutput)


# ---------------------------------------------------------------------------
# parse_response — error paths
# ---------------------------------------------------------------------------


def test_parse_invalid_json():
    result = parse_response("Not JSON at all")
    assert isinstance(result, AgendaCardError)
    assert result.error == "json_parse_error"


def test_parse_insufficient_data_signal():
    """LLM 'insufficient_data' döndürürse error olarak çevrilir."""
    response = json.dumps({"error": "insufficient_data", "reason": "Sadece 1 kaynak var"})
    result = parse_response(response)
    assert isinstance(result, AgendaCardError)
    assert result.error == "insufficient_data"
    assert "kaynak" in result.reason


def test_parse_missing_title():
    bad = json.dumps({"summary": "x" * 100, "key_points": ["a", "b", "c"]})
    result = parse_response(bad)
    assert isinstance(result, AgendaCardError)
    assert result.error == "missing_title"


def test_parse_summary_too_short():
    bad = json.dumps({"title": "T", "summary": "kısa"})
    result = parse_response(bad)
    assert isinstance(result, AgendaCardError)
    assert result.error == "insufficient_summary"


def test_parse_warns_on_low_key_points():
    """3'ten az key_point → warning ama success."""
    short_response = json.dumps(
        {
            "title": "T",
            "summary": "x" * 100,
            "key_points": ["only one"],
            "status": "developing",
            "importance_score": 0.5,
            "freshness_score": 0.5,
        }
    )
    result = parse_response(short_response)
    assert isinstance(result, AgendaCardOutput)
    assert any("key_points only" in w for w in result.warnings)


def test_parse_invalid_status_defaulted():
    bad_status = json.dumps(
        {
            "title": "T",
            "summary": "x" * 100,
            "status": "garbage",
            "importance_score": 0.5,
            "freshness_score": 0.5,
        }
    )
    result = parse_response(bad_status)
    assert isinstance(result, AgendaCardOutput)
    assert result.status == "developing"
    assert any("invalid status" in w for w in result.warnings)


def test_parse_score_clamping():
    """Out-of-range scores clamped to 0..1."""
    weird = json.dumps(
        {
            "title": "T",
            "summary": "x" * 100,
            "status": "active",
            "importance_score": 5.0,  # > 1
            "freshness_score": -0.5,  # < 0
        }
    )
    result = parse_response(weird)
    assert isinstance(result, AgendaCardOutput)
    assert result.importance_score == 1.0
    assert result.freshness_score == 0.0


def test_parse_caps_lists_at_max():
    """key_points / source_refs / timeline aşırıysa kırpılır."""
    huge = json.dumps(
        {
            "title": "T",
            "summary": "x" * 100,
            "key_points": [f"point {i}" for i in range(20)],
            "source_refs": [
                {"source": f"src-{i}", "title": "t", "url": "u", "published_at": "2026-05-01"}
                for i in range(50)
            ],
            "timeline": [{"date": "2026-05-01", "event": f"e-{i}"} for i in range(50)],
            "status": "active",
            "importance_score": 0.5,
            "freshness_score": 0.5,
        }
    )
    result = parse_response(huge)
    assert isinstance(result, AgendaCardOutput)
    assert len(result.source_refs) <= 30
    assert len(result.timeline) <= 20
