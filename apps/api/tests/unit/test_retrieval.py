"""Vector retrieval scoring + serialization tests (#22).

DB integration testleri testcontainers ile gelecek.
Burada saf fonksiyonları (freshness_decay, compute_final_score, vector serialize)
ve mod weight tablolarını test ederiz.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.retrieval import (
    CURRENT_MODE_FALLBACKS_HOURS,
    WEIGHTS_CURRENT,
    WEIGHTS_DEFAULT,
    _vector_to_pg_literal,
    compute_final_score,
    freshness_decay,
)

# ---------------------------------------------------------------------------
# freshness_decay
# ---------------------------------------------------------------------------


def test_freshness_now_is_one():
    assert freshness_decay(datetime.now(UTC)) > 0.99


def test_freshness_one_half_life_is_half():
    """24h sonra 0.5 (default half-life=24h)."""
    past = datetime.now(UTC) - timedelta(hours=24)
    assert abs(freshness_decay(past) - 0.5) < 0.05


def test_freshness_two_half_lives_is_quarter():
    past = datetime.now(UTC) - timedelta(hours=48)
    assert abs(freshness_decay(past) - 0.25) < 0.03


def test_freshness_far_past_near_zero():
    past = datetime.now(UTC) - timedelta(days=365)
    assert freshness_decay(past) < 0.01


def test_freshness_naive_datetime_handled():
    """tzinfo=None → UTC kabul edilir."""
    naive = datetime.utcnow().replace(tzinfo=None)
    score = freshness_decay(naive)
    # Naive UTC + 0..1 second offset → score yaklaşık 1
    assert 0.99 <= score <= 1.0


def test_freshness_none_returns_half():
    assert freshness_decay(None) == 0.5


def test_freshness_custom_half_life():
    """48h half-life ile 48h önce 0.5."""
    past = datetime.now(UTC) - timedelta(hours=48)
    assert abs(freshness_decay(past, half_life_hours=48) - 0.5) < 0.05


# ---------------------------------------------------------------------------
# compute_final_score
# ---------------------------------------------------------------------------


def test_score_default_weights_sum_to_one():
    assert abs(sum(WEIGHTS_DEFAULT.values()) - 1.0) < 1e-6


def test_score_current_weights_sum_to_one():
    assert abs(sum(WEIGHTS_CURRENT.values()) - 1.0) < 1e-6


def test_score_all_max_returns_one():
    s = compute_final_score(
        semantic=1.0,
        freshness=1.0,
        importance=1.0,
        reliability=1.0,
        weights=WEIGHTS_DEFAULT,
    )
    assert abs(s - 1.0) < 1e-6


def test_score_all_zero_returns_zero():
    s = compute_final_score(
        semantic=0.0,
        freshness=0.0,
        importance=0.0,
        reliability=0.0,
        weights=WEIGHTS_DEFAULT,
    )
    assert s == 0.0


def test_score_semantic_dominates_default():
    """Default weights'te semantic en ağır faktör."""
    s_only_sem = compute_final_score(
        semantic=1.0, freshness=0, importance=0, reliability=0, weights=WEIGHTS_DEFAULT
    )
    s_only_fresh = compute_final_score(
        semantic=0, freshness=1.0, importance=0, reliability=0, weights=WEIGHTS_DEFAULT
    )
    assert s_only_sem > s_only_fresh
    assert s_only_sem == WEIGHTS_DEFAULT["semantic"]


def test_score_current_freshness_higher_weight_than_default():
    """Current modda freshness ağırlığı default'tan yüksektir."""
    assert WEIGHTS_CURRENT["freshness"] > WEIGHTS_DEFAULT["freshness"]
    assert WEIGHTS_CURRENT["semantic"] < WEIGHTS_DEFAULT["semantic"]


# ---------------------------------------------------------------------------
# _vector_to_pg_literal
# ---------------------------------------------------------------------------


def test_pg_literal_basic():
    result = _vector_to_pg_literal([0.1, 0.2, -0.3])
    assert result == "[0.1000000,0.2000000,-0.3000000]"


def test_pg_literal_empty():
    assert _vector_to_pg_literal([]) == "[]"


def test_pg_literal_high_precision():
    result = _vector_to_pg_literal([1 / 3])
    # 7 hane precision
    assert "0.3333333" in result


# ---------------------------------------------------------------------------
# Mode constants
# ---------------------------------------------------------------------------


def test_current_fallback_levels():
    """24h → 48h → 72h sıralı."""
    assert CURRENT_MODE_FALLBACKS_HOURS == (24, 48, 72)


# ---------------------------------------------------------------------------
# Hydration SELECT (#334) — country + level field fetch zorunlu
# ---------------------------------------------------------------------------


def test_hydration_select_includes_country_and_level():
    """
    #334 — hybrid_search_agenda_cards full SELECT'inde country + level
    olmalı. UI country chip + level (daily/weekly) badge için zorunlu.

    Test: source kodda SELECT statement'ı string olarak ara.
    """
    import inspect

    from app.core import retrieval as retrieval_module

    source = inspect.getsource(retrieval_module.hybrid_search_agenda_cards)
    # Asıl SELECT (full hydration) — agenda_cards alias 'ac'
    assert "ac.country" in source, (
        "agenda_cards SELECT'te ac.country eksik (#334)"
    )
    assert "ac.level" in source, (
        "agenda_cards SELECT'te ac.level eksik (#334)"
    )


# ---------------------------------------------------------------------------
# #691 — NER entity scoring overhaul (IDF + multi-entity AND)
# ---------------------------------------------------------------------------


from app.core.retrieval import (
    NER_DF_THRESHOLD,
    _resolve_ner_target_aids,
)


def test_ner_resolve_empty_returns_no_match():
    """Hiç entity match yoksa boost yok."""
    target, mode = _resolve_ner_target_aids({}, {})
    assert target == set()
    assert mode == "no_match"


def test_ner_resolve_two_rare_entities_intersect_returns_multi_and():
    """
    niche_002 senaryosu — "Karşıyaka" + "Bursaspor" rare DEĞİL ama AND ile dar.
    Bu durumda multi_and_common bekleniyor. Eğer her ikisi de rare olsaydı
    multi_and çıkardı.
    """
    aids = {
        "karşıyaka": {"a1", "a2", "ddae4672"},  # df=3 (rare)
        "bursaspor": {"a3", "ddae4672"},  # df=2 (rare)
    }
    df = {"karşıyaka": 3, "bursaspor": 2}
    target, mode = _resolve_ner_target_aids(aids, df)
    assert target == {"ddae4672"}, f"multi_and intersect bekleniyordu: {target}"
    assert mode == "multi_and"


def test_ner_resolve_two_common_intersect_dar_kume_returns_multi_and_common():
    """
    Common entity'ler ama intersect dar → multi_and_common.
    """
    aids = {
        "karşıyaka": set(f"a{i}" for i in range(50)) | {"ddae4672"},  # df=51 common
        "bursaspor": set(f"b{i}" for i in range(40)) | {"ddae4672"},  # df=41 common
    }
    # Intersect = {ddae4672} (1 article, < threshold 30)
    df = {"karşıyaka": 51, "bursaspor": 41}
    target, mode = _resolve_ner_target_aids(aids, df)
    assert "ddae4672" in target
    assert mode == "multi_and_common"


def test_ner_resolve_two_common_intersect_genis_returns_no_match():
    """
    Common entity'ler + intersect büyük (>=threshold) → no_match.
    Sinyal sulanır, boost vermek mantıksız.
    """
    # 30 ortak article (intersect=30, threshold sınırında)
    common = set(f"c{i}" for i in range(35))
    aids = {
        "karşıyaka": common | {"x1"},  # df=36
        "bursaspor": common | {"x2"},  # df=36
    }
    df = {"karşıyaka": 36, "bursaspor": 36}
    target, mode = _resolve_ner_target_aids(aids, df)
    # Intersect 35 >= threshold 30 → no_match
    assert mode == "no_match"
    assert target == set()


def test_ner_resolve_single_rare_entity_returns_single_rare():
    """
    Tek rare entity → single_rare mode (Faz 6 eski seviye).
    Örn: "Aydınbelge ne dedi" — Aydınbelge df<30.
    """
    aids = {"aydınbelge": {"7761cd94"}}
    df = {"aydınbelge": 1}
    target, mode = _resolve_ner_target_aids(aids, df)
    assert target == {"7761cd94"}
    assert mode == "single_rare"


def test_ner_resolve_single_common_entity_returns_no_match():
    """
    Tek common entity → boost yok (sinyal güvensiz).
    Örn: query "Trump ne dedi" — Trump 200 article'de var.
    """
    aids = {"trump": set(f"t{i}" for i in range(200))}
    df = {"trump": 200}
    target, mode = _resolve_ner_target_aids(aids, df)
    assert mode == "no_match"
    assert target == set()


def test_ner_resolve_rare_intersect_empty_falls_back_to_rarest():
    """
    2 rare entity intersect boş → en nadir entity tek başına single_rare.
    """
    aids = {
        "rare_a": {"x1", "x2"},  # df=2
        "rare_b": {"y1", "y2", "y3"},  # df=3
    }
    df = {"rare_a": 2, "rare_b": 3}
    target, mode = _resolve_ner_target_aids(aids, df)
    # rare_a daha nadir → onun aids'i
    assert target == {"x1", "x2"}
    assert mode == "single_rare"


def test_ner_resolve_threshold_boundary():
    """df = threshold ise rare DEĞİL (strict <). Boundary test."""
    aids = {"e1": set(f"a{i}" for i in range(NER_DF_THRESHOLD))}  # df=30
    df = {"e1": NER_DF_THRESHOLD}
    target, mode = _resolve_ner_target_aids(aids, df)
    # df=threshold → rare değil → no_match (tek entity ve common)
    assert mode == "no_match"


def test_ner_resolve_three_rare_intersect():
    """3 rare entity → multi_and (en güçlü)."""
    aids = {
        "e1": {"a1", "a2", "target"},
        "e2": {"b1", "target", "b2"},
        "e3": {"target", "c1"},
    }
    df = {"e1": 3, "e2": 3, "e3": 2}
    target, mode = _resolve_ner_target_aids(aids, df)
    assert target == {"target"}
    assert mode == "multi_and"
