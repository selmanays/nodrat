"""Tests for app.core.streaming_json (issue #527).

StreamingPostExtractor incremental olarak posts[] objelerini parse edip emit
ediyor mu? Edge case'ler:
- Tek chunk ile tüm response
- Karakter karakter chunking
- String içinde `}` (cited claim örneği)
- Escape edilmiş tırnak (\")
- Posts array kapanması (])
- Bozuk obje (skip)
"""

from __future__ import annotations

import json

from app.core.streaming_json import StreamingPostExtractor


SAMPLE_RESPONSE = {
    "posts": [
        {
            "text": "İlk post: Türkiye gündeminde önemli gelişmeler [#1]",
            "angle": "haber-özet",
            "char_count": 50,
            "related_agenda_card_ids": ["card-1"],
        },
        {
            "text": 'İkinci post: alıntı içerir "tırnak" örneği [#2]',
            "angle": "alıntı-örnek",
            "char_count": 47,
            "related_agenda_card_ids": ["card-2"],
        },
        {
            "text": "Üçüncü post: } süslü parantez içerir [#3]",
            "angle": "edge-case",
            "char_count": 42,
            "related_agenda_card_ids": ["card-3"],
        },
    ],
    "summary": "Üç paylaşım üretildi",
    "sources": [],
    "warnings": [],
}


def _full_json() -> str:
    return json.dumps(SAMPLE_RESPONSE, ensure_ascii=False)


def test_single_chunk_emits_all_posts():
    extractor = StreamingPostExtractor()
    full = _full_json()
    new_posts = extractor.feed(full)
    assert len(new_posts) == 3
    assert new_posts[0][0] == 0
    assert new_posts[0][1]["text"].startswith("İlk post")
    assert new_posts[1][0] == 1
    assert new_posts[2][0] == 2
    # 4. post yok
    assert extractor.posts_array_closed


def test_char_by_char_emits_progressively():
    extractor = StreamingPostExtractor()
    full = _full_json()
    emitted_indices: list[int] = []
    for ch in full:
        new_posts = extractor.feed(ch)
        for idx, _ in new_posts:
            emitted_indices.append(idx)
    assert emitted_indices == [0, 1, 2]
    assert extractor.posts_array_closed


def test_two_chunk_split_mid_post():
    """Buffer split tam ortada — `}` gelmeden önce parse etme."""
    extractor = StreamingPostExtractor()
    full = _full_json()
    half = len(full) // 2
    chunk1 = full[:half]
    chunk2 = full[half:]
    emitted = []
    for ev in extractor.feed(chunk1):
        emitted.append(ev[0])
    for ev in extractor.feed(chunk2):
        emitted.append(ev[0])
    assert emitted == [0, 1, 2]


def test_escaped_quote_in_text():
    response = {
        "posts": [
            {
                "text": 'Post with \\"escaped quotes\\" inside',
                "angle": "test",
                "char_count": 30,
                "related_agenda_card_ids": [],
            }
        ]
    }
    raw = json.dumps(response, ensure_ascii=False)
    extractor = StreamingPostExtractor()
    out = extractor.feed(raw)
    assert len(out) == 1
    # JSON parse decoded the escapes
    assert "escaped quotes" in out[0][1]["text"]


def test_brace_inside_string_not_counted():
    """String içinde `}` saymamalı — parser early-close yapmamalı."""
    response = {
        "posts": [
            {
                "text": "Bracket test: {nested}",
                "angle": "edge",
                "char_count": 22,
                "related_agenda_card_ids": [],
            }
        ]
    }
    raw = json.dumps(response, ensure_ascii=False)
    extractor = StreamingPostExtractor()
    out = extractor.feed(raw)
    assert len(out) == 1
    assert out[0][1]["text"] == "Bracket test: {nested}"


def test_empty_posts_array():
    raw = '{"posts": [], "summary": "boş"}'
    extractor = StreamingPostExtractor()
    out = extractor.feed(raw)
    assert out == []
    assert extractor.posts_array_closed


def test_no_posts_field_yet():
    """Stream başında daha `posts` keyword'ü gelmemiş — emit yok."""
    extractor = StreamingPostExtractor()
    out = extractor.feed('{"warnings": [], "sou')
    assert out == []


def test_partial_first_post_no_emit():
    """İlk post yarım — emit yok."""
    extractor = StreamingPostExtractor()
    out = extractor.feed('{"posts": [{"text": "yarım kalmış')
    assert out == []
    # Devamı gelince emit olur
    out2 = extractor.feed(
        ' post", "angle": "x", "char_count": 13, "related_agenda_card_ids": []}'
    )
    assert len(out2) == 1
    assert out2[0][1]["text"] == "yarım kalmış post"


def test_malformed_object_skipped():
    """Bozuk JSON objesi — skip edilmeli, sonraki valid olan emit olmalı."""
    # First object missing closing brace? Actually if missing, find_matching_brace
    # returns -1 and parser waits — so we test: invalid JSON syntax içeride.
    # JSON yapısal olarak `}` ile kapanan ama içerik bozuk → json.loads fail.
    raw = (
        '{"posts": ['
        '{"text": "ok1", "angle": "a", "char_count": 3, "related_agenda_card_ids": []},'
        '{"text" "missing colon", "angle": "x"},'
        '{"text": "ok2", "angle": "b", "char_count": 3, "related_agenda_card_ids": []}'
        "]}"
    )
    extractor = StreamingPostExtractor()
    out = extractor.feed(raw)
    # First and third valid, middle skipped
    texts = [o[1]["text"] for o in out]
    assert "ok1" in texts
    assert "ok2" in texts
    # No phantom emission
    assert len(out) == 2


def test_posts_array_close_stops_scan():
    raw = _full_json()
    extra = ' "summary": "extra"}'
    extractor = StreamingPostExtractor()
    extractor.feed(raw)
    # Posts kapandıktan sonra ekstra feed daha fazla emit vermez
    extra_out = extractor.feed(extra)
    assert extra_out == []
