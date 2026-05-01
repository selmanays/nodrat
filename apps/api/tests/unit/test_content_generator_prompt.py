"""Content Generator (X post) prompt v1.0 tests (#25)."""

from __future__ import annotations

import json

from app.prompts.content_generator import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_X_POST,
    X_POST_MAX_CHARS,
    ContentGenError,
    GeneratedXContent,
    format_system_prompt,
    parse_x_post_response,
    render_user_payload,
)


# ---------------------------------------------------------------------------
# Static
# ---------------------------------------------------------------------------


def test_prompt_version_set():
    assert PROMPT_VERSION


def test_x_post_char_limit_280():
    assert X_POST_MAX_CHARS == 280


def test_system_prompt_critical_rules():
    """Halüsinasyon + FSEK + content rules."""
    assert "UYDURMA" in SYSTEM_PROMPT_X_POST
    assert "FSEK" in SYSTEM_PROMPT_X_POST
    assert "JSON" in SYSTEM_PROMPT_X_POST
    assert "insufficient_data" in SYSTEM_PROMPT_X_POST
    assert "280 karakteri" in SYSTEM_PROMPT_X_POST


def test_format_system_prompt_max_posts():
    p = format_system_prompt(max_posts=3)
    assert "3 adet X" in p
    p5 = format_system_prompt(max_posts=5)
    assert "5 adet X" in p5


# ---------------------------------------------------------------------------
# render_user_payload
# ---------------------------------------------------------------------------


def test_render_payload_basic():
    s = render_user_payload(
        request="Bu hafta yapay zeka tartışmaları",
        retrieval_plan={"intent": "current_content_generation", "mode": "current"},
        agenda_cards=[
            {
                "id": "card-1",
                "title": "AI regülasyon",
                "summary": "Avrupa Birliği AI Act",
                "key_points": ["Risk kategorileri", "Şeffaflık"],
                "content_angles": ["Kapsam", "Cezalar"],
                "source_refs": [{"source": "BBC"}],
                "status": "active",
            }
        ],
    )
    p = json.loads(s)
    assert p["request"] == "Bu hafta yapay zeka tartışmaları"
    assert len(p["agenda_cards"]) == 1
    assert p["agenda_cards"][0]["title"] == "AI regülasyon"


def test_render_payload_truncates_supplementary_chunks():
    long_text = "x" * 5000
    s = render_user_payload(
        request="t",
        retrieval_plan={},
        agenda_cards=[],
        supplementary_chunks=[
            {"article_id": "1", "chunk_text": long_text, "source_name": "s"}
        ],
        max_excerpt_chars=500,
    )
    p = json.loads(s)
    assert len(p["supplementary_chunks"][0]["chunk_text"]) <= 510


def test_render_payload_caps_lists():
    """Cost guard."""
    cards = [
        {"id": str(i), "title": f"t{i}", "summary": "s"} for i in range(20)
    ]
    chunks = [
        {"article_id": str(i), "chunk_text": "t", "source_name": "s"}
        for i in range(30)
    ]
    s = render_user_payload(
        request="x",
        retrieval_plan={},
        agenda_cards=cards,
        supplementary_chunks=chunks,
    )
    p = json.loads(s)
    assert len(p["agenda_cards"]) == 10
    assert len(p["supplementary_chunks"]) == 10


# ---------------------------------------------------------------------------
# parse_x_post_response
# ---------------------------------------------------------------------------


VALID_RESPONSE = json.dumps(
    {
        "posts": [
            {
                "text": "AB AI Act 2026'da yürürlüğe giriyor. Yüksek riskli sistemler için şeffaflık zorunluluğu geliyor.",
                "angle": "regülasyon kapsamı",
                "char_count": 105,
                "related_agenda_card_ids": ["card-1"],
            },
            {
                "text": "AI Act ihlal cezası küresel cironun %7'sine kadar çıkabilir. GDPR'dan ağır.",
                "angle": "cezalar",
                "char_count": 78,
                "related_agenda_card_ids": ["card-1"],
            },
        ],
        "summary": "AB AI Act giriş",
        "sources": [
            {"title": "AI Act onaylandı", "source": "BBC", "url": "https://bbc.com/x"}
        ],
        "warnings": [],
    },
    ensure_ascii=False,
)


def test_parse_valid_response():
    result = parse_x_post_response(VALID_RESPONSE)
    assert isinstance(result, GeneratedXContent)
    assert len(result.posts) == 2
    assert all(p.char_count <= X_POST_MAX_CHARS for p in result.posts)
    assert result.posts[0].angle == "regülasyon kapsamı"
    assert len(result.sources) == 1


def test_parse_truncates_long_post():
    long_text = "x" * 350
    bad = json.dumps(
        {
            "posts": [
                {
                    "text": long_text,
                    "angle": "long",
                    "related_agenda_card_ids": ["card-1"],
                }
            ],
        }
    )
    result = parse_x_post_response(bad)
    assert isinstance(result, GeneratedXContent)
    assert result.posts[0].char_count == 280
    assert any("truncated" in w for w in result.warnings)


def test_parse_warns_empty_related_cards():
    bad = json.dumps(
        {
            "posts": [
                {
                    "text": "Test paylaşım",
                    "angle": "test",
                    "related_agenda_card_ids": [],
                }
            ]
        }
    )
    result = parse_x_post_response(bad)
    assert isinstance(result, GeneratedXContent)
    assert any("empty related" in w for w in result.warnings)


def test_parse_invalid_json():
    result = parse_x_post_response("not json")
    assert isinstance(result, ContentGenError)
    assert result.error == "json_parse_error"


def test_parse_empty_posts():
    bad = json.dumps({"posts": []})
    result = parse_x_post_response(bad)
    assert isinstance(result, ContentGenError)
    assert result.error == "empty_posts"


def test_parse_insufficient_data_signal():
    bad = json.dumps(
        {
            "posts": [],
            "warnings": ["insufficient_data"],
            "sources": [],
        }
    )
    result = parse_x_post_response(bad)
    assert isinstance(result, ContentGenError)
    assert result.error == "insufficient_data"


def test_parse_handles_markdown_fence():
    fenced = f"```json\n{VALID_RESPONSE}\n```"
    result = parse_x_post_response(fenced)
    assert isinstance(result, GeneratedXContent)
    assert len(result.posts) == 2


def test_parse_caps_posts_at_10():
    many = json.dumps(
        {
            "posts": [
                {
                    "text": f"Post #{i}",
                    "angle": "x",
                    "related_agenda_card_ids": ["card-1"],
                }
                for i in range(20)
            ]
        }
    )
    result = parse_x_post_response(many)
    assert isinstance(result, GeneratedXContent)
    assert len(result.posts) == 10
