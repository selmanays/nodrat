"""Query Planner prompt v1.0 tests (#24)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.prompts.query_planner import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    VALID_INTENTS,
    VALID_MODES,
    VALID_OUTPUT_TYPES,
    VALID_TONES,
    QueryPlan,
    QueryPlanError,
    parse_response,
    render_user_payload,
)


# ---------------------------------------------------------------------------
# Static
# ---------------------------------------------------------------------------


def test_prompt_version_set():
    assert PROMPT_VERSION


def test_system_prompt_critical_phrases():
    """JSON-only çıktı + plan-only davranış zorunluluğu."""
    assert "JSON" in SYSTEM_PROMPT
    assert "İÇERİĞİ ÜRETME" in SYSTEM_PROMPT  # plan-only rule
    assert "Şema dışında" in SYSTEM_PROMPT
    assert "ambiguous_request" in SYSTEM_PROMPT


def test_valid_constants():
    assert "current_content_generation" in VALID_INTENTS
    assert "comparative_content_generation" in VALID_INTENTS
    assert "current" in VALID_MODES
    assert "comparison" in VALID_MODES
    assert "x_post" in VALID_OUTPUT_TYPES
    assert "tarafsız" in VALID_TONES


# ---------------------------------------------------------------------------
# render_user_payload
# ---------------------------------------------------------------------------


def test_render_payload_basic():
    s = render_user_payload(
        user_request="Bu hafta yapay zeka tartışmalarını özetle",
        current_time=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    )
    p = json.loads(s)
    assert p["user_request"].startswith("Bu hafta")
    assert p["current_time"].startswith("2026-05-01")
    assert p["user_locale"] == "tr-TR"
    assert p["user_tier"] == "free"
    assert "x_post" in p["available_output_types"]


def test_render_payload_user_tier_pro():
    s = render_user_payload(
        user_request="Test",
        user_tier="pro",
    )
    p = json.loads(s)
    assert p["user_tier"] == "pro"


# ---------------------------------------------------------------------------
# parse_response — happy path
# ---------------------------------------------------------------------------


VALID_RESPONSE = json.dumps(
    {
        "intent": "current_content_generation",
        "topic_query": "yapay zeka regülasyonları",
        "mode": "current",
        "timeframes": [
            {
                "label": "bu hafta",
                "from": "2026-04-25T00:00:00Z",
                "to": "2026-05-01T23:59:59Z",
            }
        ],
        "output_type": "x_post",
        "tone": "tarafsız",
        "constraints": ["max_5_posts"],
        "needs_sources": True,
        "minimum_evidence_per_period": 2,
    },
    ensure_ascii=False,
)


def test_parse_valid_plan():
    result = parse_response(VALID_RESPONSE)
    assert isinstance(result, QueryPlan)
    assert result.intent == "current_content_generation"
    assert result.mode == "current"
    assert result.output_type == "x_post"
    assert result.tone == "tarafsız"
    assert len(result.timeframes) == 1
    assert result.timeframes[0].label == "bu hafta"
    assert result.warnings == []


def test_parse_handles_markdown_fence():
    fenced = f"```json\n{VALID_RESPONSE}\n```"
    result = parse_response(fenced)
    assert isinstance(result, QueryPlan)


def test_parse_handles_no_lang_fence():
    fenced = f"```\n{VALID_RESPONSE}\n```"
    result = parse_response(fenced)
    assert isinstance(result, QueryPlan)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_parse_invalid_json():
    result = parse_response("not json")
    assert isinstance(result, QueryPlanError)
    assert result.error == "json_parse_error"


def test_parse_missing_topic():
    bad = json.dumps({"intent": "current_content_generation", "mode": "current"})
    result = parse_response(bad)
    assert isinstance(result, QueryPlanError)
    assert result.error == "missing_topic_query"


def test_parse_unknown_intent_defaulted():
    bad = json.dumps(
        {
            "intent": "weird_intent",
            "topic_query": "test",
            "mode": "current",
            "output_type": "x_post",
        }
    )
    result = parse_response(bad)
    assert isinstance(result, QueryPlan)
    assert result.intent == "current_content_generation"
    assert any("unknown intent" in w for w in result.warnings)


def test_parse_unknown_mode_defaulted():
    bad = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "test",
            "mode": "garbage",
            "output_type": "x_post",
        }
    )
    result = parse_response(bad)
    assert isinstance(result, QueryPlan)
    assert result.mode == "current"


def test_parse_unknown_tone_to_none():
    bad = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "test",
            "mode": "current",
            "output_type": "x_post",
            "tone": "very-rude",
        }
    )
    result = parse_response(bad)
    assert isinstance(result, QueryPlan)
    assert result.tone is None
    assert any("unknown tone" in w for w in result.warnings)


def test_parse_comparison_warns_on_few_timeframes():
    """comparison mode 2+ timeframe gerekir, 1 verirse warning."""
    bad = json.dumps(
        {
            "intent": "comparative_content_generation",
            "topic_query": "test",
            "mode": "comparison",
            "timeframes": [
                {"label": "p1", "from": "2026-01-01", "to": "2026-01-31"}
            ],
            "output_type": "x_post",
        }
    )
    result = parse_response(bad)
    assert isinstance(result, QueryPlan)
    assert any("comparison mode" in w for w in result.warnings)


def test_parse_min_evidence_clamped():
    """Out-of-range min_evidence clamped to 1..10."""
    bad = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "test",
            "mode": "current",
            "output_type": "x_post",
            "minimum_evidence_per_period": 50,
        }
    )
    result = parse_response(bad)
    assert isinstance(result, QueryPlan)
    assert result.minimum_evidence_per_period == 10


def test_parse_caps_constraints_at_10():
    """Long constraints list capped."""
    bad = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "test",
            "mode": "current",
            "output_type": "x_post",
            "constraints": [f"c{i}" for i in range(50)],
        }
    )
    result = parse_response(bad)
    assert isinstance(result, QueryPlan)
    assert len(result.constraints) == 10


def test_parse_topic_truncated_at_200():
    long_topic = "x" * 500
    bad = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": long_topic,
            "mode": "current",
            "output_type": "x_post",
        }
    )
    result = parse_response(bad)
    assert isinstance(result, QueryPlan)
    assert len(result.topic_query) == 200
    assert any("truncated" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Keywords (#175 — fallback derive from topic_query)
# ---------------------------------------------------------------------------


def test_parse_keywords_extracted_when_present():
    body = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "emekli maaşı",
            "mode": "current",
            "output_type": "x_post",
            "keywords": ["emekli", "maaş", "ssk", "bağ-kur"],
        }
    )
    result = parse_response(body)
    assert isinstance(result, QueryPlan)
    assert result.keywords == ["emekli", "maaş", "ssk", "bağ-kur"]


def test_parse_keywords_fallback_when_empty():
    body = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "en düşük emekli maaşı",
            "mode": "current",
            "output_type": "x_post",
            "keywords": [],
        }
    )
    result = parse_response(body)
    assert isinstance(result, QueryPlan)
    assert result.keywords  # non-empty
    assert "emekli" in result.keywords
    assert "maaşı" in result.keywords
    assert any("fallback" in w for w in result.warnings)


def test_parse_keywords_fallback_skips_stopwords():
    body = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "iran ile türkiye için diplomasi",
            "mode": "current",
            "output_type": "x_post",
        }
    )
    result = parse_response(body)
    assert isinstance(result, QueryPlan)
    # ile, için filtrelenir
    assert "ile" not in result.keywords
    assert "için" not in result.keywords
    assert "iran" in result.keywords


def test_parse_keywords_capped_at_5():
    body = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "test",
            "mode": "current",
            "output_type": "x_post",
            "keywords": [f"kw{i}" for i in range(20)],
        }
    )
    result = parse_response(body)
    assert isinstance(result, QueryPlan)
    assert len(result.keywords) == 5


# ---------------------------------------------------------------------------
# geographic_focus (#209)
# ---------------------------------------------------------------------------


def test_parse_geographic_focus_tr():
    body = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "türkiye gündemi",
            "mode": "current",
            "output_type": "summary",
            "geographic_focus": "TR",
        }
    )
    r = parse_response(body)
    assert isinstance(r, QueryPlan)
    assert r.geographic_focus == "TR"


def test_parse_geographic_focus_lowercase_normalized():
    body = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "test",
            "mode": "current",
            "output_type": "x_post",
            "geographic_focus": "us",
        }
    )
    r = parse_response(body)
    assert isinstance(r, QueryPlan)
    assert r.geographic_focus == "US"


def test_parse_geographic_focus_invalid_set_to_none():
    body = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "test",
            "mode": "current",
            "output_type": "x_post",
            "geographic_focus": "Türkiye",  # 2-char değil
        }
    )
    r = parse_response(body)
    assert isinstance(r, QueryPlan)
    assert r.geographic_focus is None


def test_parse_geographic_focus_null_default():
    body = json.dumps(
        {
            "intent": "current_content_generation",
            "topic_query": "test",
            "mode": "current",
            "output_type": "x_post",
        }
    )
    r = parse_response(body)
    assert isinstance(r, QueryPlan)
    assert r.geographic_focus is None
