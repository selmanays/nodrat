"""Unit tests for RAPTOR-Lite hierarchical clustering (#182)."""

from __future__ import annotations

from app.workers.tasks.raptor import (
    WEEKLY_MIN_CLUSTER_SIZE,
    WEEKLY_SIM_THRESHOLD,
    _cluster_daily_cards,
    _cosine,
    _parse_summary_response,
    _parse_vector,
)


# ---------------------------------------------------------------------------
# _parse_vector
# ---------------------------------------------------------------------------


def test_parse_vector_basic():
    assert _parse_vector("[1.0, 2.0, 3.5]") == [1.0, 2.0, 3.5]


def test_parse_vector_empty():
    assert _parse_vector("") is None
    assert _parse_vector(None) is None


def test_parse_vector_malformed_returns_none():
    assert _parse_vector("[abc, def]") is None


# ---------------------------------------------------------------------------
# _cosine
# ---------------------------------------------------------------------------


def test_cosine_identical():
    a = [1.0, 0.0, 0.0]
    assert _cosine(a, a) == 1.0


def test_cosine_orthogonal():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_dim_mismatch():
    assert _cosine([1.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# _cluster_daily_cards
# ---------------------------------------------------------------------------


def test_cluster_groups_similar():
    cards = [
        {
            "id": "a",
            "title": "Emekli zammı",
            "summary": "",
            "embedding": [1.0, 0.0, 0.0],
            "importance": 0.5,
            "event_id": "e1",
            "article_count": 3,
        },
        {
            "id": "b",
            "title": "Memur zammı",
            "summary": "",
            "embedding": [1.0, 0.01, 0.0],  # similar
            "importance": 0.4,
            "event_id": "e2",
            "article_count": 2,
        },
        {
            "id": "c",
            "title": "Hava durumu",
            "summary": "",
            "embedding": [0.0, 0.0, 1.0],  # orthogonal
            "importance": 0.3,
            "event_id": "e3",
            "article_count": 1,
        },
    ]
    clusters = _cluster_daily_cards(cards)
    # a + b cluster, c yalnız (min_size 2'de filtre)
    assert len(clusters) == 1
    ids = {c["id"] for c in clusters[0]}
    assert ids == {"a", "b"}


def test_cluster_filters_singletons():
    cards = [
        {
            "id": str(i),
            "title": f"t{i}",
            "summary": "",
            "embedding": [float(i), 1.0, 0.0],  # all different
            "importance": 0.5,
            "event_id": f"e{i}",
            "article_count": 1,
        }
        for i in range(1, 4)
    ]
    clusters = _cluster_daily_cards(cards)
    # Hepsi orthogonal → singleton → filtrelenir
    assert len(clusters) == 0


def test_cluster_threshold_constants():
    assert WEEKLY_SIM_THRESHOLD == 0.75
    assert WEEKLY_MIN_CLUSTER_SIZE == 2


# ---------------------------------------------------------------------------
# _parse_summary_response
# ---------------------------------------------------------------------------


def test_parse_summary_valid():
    import json

    raw = json.dumps(
        {
            "title": "Emekli ve memur maaş zammı",
            "summary": "Bu hafta enflasyon farkı açıklandı.",
            "key_points": ["SSK Bağ-Kur", "memur enflasyon farkı"],
            "importance": 0.7,
        },
        ensure_ascii=False,
    )
    parsed = _parse_summary_response(raw)
    assert parsed is not None
    assert parsed["title"] == "Emekli ve memur maaş zammı"
    assert len(parsed["key_points"]) == 2
    assert parsed["importance"] == 0.7


def test_parse_summary_handles_markdown_fence():
    raw = '```json\n{"title": "X", "summary": "Y"}\n```'
    parsed = _parse_summary_response(raw)
    assert parsed is not None
    assert parsed["title"] == "X"


def test_parse_summary_invalid_json():
    assert _parse_summary_response("not json") is None


def test_parse_summary_missing_required():
    import json

    raw = json.dumps({"title": "X"})  # summary yok
    assert _parse_summary_response(raw) is None


def test_parse_summary_clamps_importance():
    import json

    raw = json.dumps({"title": "X", "summary": "Y", "importance": 5.0})
    parsed = _parse_summary_response(raw)
    assert parsed is not None
    assert parsed["importance"] == 1.0


# ---------------------------------------------------------------------------
# _aggregate_country (#337) — weekly card country aggregation
# ---------------------------------------------------------------------------


def test_aggregate_country_unanimous():
    from app.workers.tasks.raptor import _aggregate_country

    cluster = [
        {"country": "TR", "article_count": 5},
        {"country": "TR", "article_count": 3},
    ]
    assert _aggregate_country(cluster) == "TR"


def test_aggregate_country_majority_60_pct():
    """%60+ majority TR → TR (eşik=0.6 default)."""
    from app.workers.tasks.raptor import _aggregate_country

    cluster = [
        {"country": "TR", "article_count": 6},
        {"country": "US", "article_count": 4},
    ]
    assert _aggregate_country(cluster) == "TR"


def test_aggregate_country_no_majority_returns_none():
    """50/50 tie → None (UI'da 'global' gibi gösterilebilir)."""
    from app.workers.tasks.raptor import _aggregate_country

    cluster = [
        {"country": "TR", "article_count": 5},
        {"country": "US", "article_count": 5},
    ]
    assert _aggregate_country(cluster) is None


def test_aggregate_country_all_null_returns_none():
    from app.workers.tasks.raptor import _aggregate_country

    cluster = [
        {"country": None, "article_count": 3},
        {"country": None, "article_count": 2},
    ]
    assert _aggregate_country(cluster) is None


def test_aggregate_country_partial_null_majority():
    """3 TR + 1 None + 1 US → TR (NULL paydadan düşer)."""
    from app.workers.tasks.raptor import _aggregate_country

    cluster = [
        {"country": "TR", "article_count": 1},
        {"country": "TR", "article_count": 1},
        {"country": "TR", "article_count": 1},
        {"country": None, "article_count": 1},
        {"country": "US", "article_count": 1},
    ]
    assert _aggregate_country(cluster) == "TR"


def test_aggregate_country_empty_cluster():
    from app.workers.tasks.raptor import _aggregate_country

    assert _aggregate_country([]) is None
