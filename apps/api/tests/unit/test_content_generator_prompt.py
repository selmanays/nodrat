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


def test_format_system_prompt_static_prefix_392():
    """#392 MVP-2.1 — system prompt artık STATIC; max_posts'tan bağımsız.

    DeepSeek implicit cache hit için prefix sabit olmalı. max_posts/tone
    user payload'undaki output_constraints'tan okunur.
    """
    p3 = format_system_prompt(max_posts=3, output_type="x_post", tone=None)
    p5 = format_system_prompt(max_posts=5, output_type="x_post", tone=None)
    p_tone = format_system_prompt(max_posts=5, output_type="x_post", tone="analitik")

    # 1) max_posts/tone değişimi prefix'i değiştirmemeli (cache hit garantisi)
    assert p3 == p5, "max_posts farkı static prompt'u değiştirmemeli (cache stability)"
    assert p5 == p_tone, "tone farkı static prompt'u değiştirmemeli (cache stability)"

    # 2) Eski dynamic placeholder'lar görünmemeli
    assert "{max_posts}" not in p5
    assert "{item_count}" not in p5
    assert "TON KURALI:" not in p5, "Dynamic tone instruction append KALDIRILDI"

    # 3) User payload reference'ı bulunmalı (LLM payload'tan oku)
    assert "output_constraints.max_posts" in p5
    assert "output_constraints.tone" in p5


def test_format_system_prompt_routes_by_output_type():
    """output_type'a göre farklı template; max_posts ignore."""
    p_xpost = format_system_prompt(output_type="x_post")
    p_summary = format_system_prompt(output_type="summary")
    p_thread = format_system_prompt(output_type="thread")
    p_headline = format_system_prompt(output_type="headline")

    # Hepsi farklı (output_type başlık satırı farklı)
    prompts = {p_xpost, p_summary, p_thread, p_headline}
    assert len(prompts) == 4, "Her output_type için farklı template"

    # Anahtar kelimeler
    assert "X (Twitter) paylaş" in p_xpost
    assert "ÖZET içeri" in p_summary or "özet" in p_summary.lower()
    assert "thread" in p_thread.lower()
    assert "HEADLINE" in p_headline or "BAŞLIK" in p_headline


def test_format_system_prompt_unknown_output_type_falls_back():
    """Bilinmeyen output_type → x_post template."""
    p_unknown = format_system_prompt(output_type="quoten")
    p_xpost = format_system_prompt(output_type="x_post")
    assert p_unknown == p_xpost


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
