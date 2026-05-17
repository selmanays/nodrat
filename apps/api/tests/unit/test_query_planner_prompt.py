"""Query Planner prompt v1.0 tests (#24)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.prompts.query_planner import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    VALID_INTENTS,
    VALID_MODES,
    VALID_OUTPUT_TYPES,
    VALID_TONES,
    QueryPlan,
    QueryPlanError,
    TimeframeSpec,
    _apply_news_recency_default,
    _canonical_token,
    _entity_canonical,
    _norm_words_tr,
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
        # #171/#175 — keywords planner şemasının zorunlu parçası (bkz.
        # query_planner.py "3-5 anahtar kelime"). Eksikse parse_response
        # topic_query'den türetir + `planner_keywords_empty_fallback_topic_query`
        # uyarısı verir (kasıtlı bozulma sinyali — feature). GEÇERLİ bir
        # LLM yanıtı keywords içerir → uyarısız; test bunu doğrular.
        "keywords": ["yapay zeka regülasyonları", "yapay zeka", "regülasyon"],
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


# ---------------------------------------------------------------------------
# #906 — _apply_news_recency_default (deterministik news_query timeframe kontratı)
# ---------------------------------------------------------------------------
#
# Prompt talimatı (B) LLM'de olasılıksal + #785 PR-G short-query bypass LLM'i
# HİÇ çağırmaz (timeframes=[] hardcoded) + #270 PR-B DB prompt override
# prompt'u değiştirebilir. Kontrat bu yüzden deterministik kodda garanti.

_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)


def _plan(query_class: str, timeframes: list[TimeframeSpec]) -> QueryPlan:
    return QueryPlan(
        intent="current_content_generation",
        topic_query="günün son gelişmelerini söyle",
        mode="current",
        timeframes=timeframes,
        output_type="x_post",
        tone=None,
        constraints=[],
        needs_sources=True,
        minimum_evidence_per_period=1,
        query_class=query_class,  # type: ignore[arg-type]
    )


def test_recency_default_news_query_empty_injects_7d():
    # Kök bug: bypass/LLM news_query'de timeframe üretmedi → boş kalırsa
    # retrieval 90g'lik havuzdan eski haber çekiyordu. Kontrat: son 7 gün.
    p = _apply_news_recency_default(_plan("news_query", []), _NOW)
    assert len(p.timeframes) == 1
    tf = p.timeframes[0]
    assert "#906" in tf.label
    assert datetime.fromisoformat(tf.from_iso) == _NOW - timedelta(days=7)
    assert datetime.fromisoformat(tf.to_iso) == _NOW


def test_recency_default_news_query_nonempty_unchanged():
    # LLM açık aralık ürettiyse (örn. "son 1 yıl") ASLA override etme.
    explicit = [TimeframeSpec(label="son 1 yıl",
                              from_iso="2025-05-16T00:00:00+00:00",
                              to_iso="2026-05-16T00:00:00+00:00")]
    p = _apply_news_recency_default(_plan("news_query", list(explicit)), _NOW)
    assert p.timeframes == explicit  # değişmedi


def test_recency_default_general_knowledge_unchanged():
    # general_knowledge haber penceresi almamalı (C2 brand contamination).
    p = _apply_news_recency_default(_plan("general_knowledge", []), _NOW)
    assert p.timeframes == []


def test_recency_default_meta_query_unchanged():
    # meta_query retrieval yapmaz; timeframe enjekte edilmez.
    p = _apply_news_recency_default(_plan("meta_query", []), _NOW)
    assert p.timeframes == []


def test_recency_default_mixed_unchanged():
    # Yalnız news_query; "mixed" dahil diğer sınıflar etkilenmez.
    p = _apply_news_recency_default(_plan("mixed", []), _NOW)
    assert p.timeframes == []


def test_recency_default_current_time_none_uses_now_utc():
    # current_time=None → now(UTC); yine de enjekte (tz-aware, ~7 gün).
    p = _apply_news_recency_default(_plan("news_query", []), None)
    assert len(p.timeframes) == 1
    frm = datetime.fromisoformat(p.timeframes[0].from_iso)
    to = datetime.fromisoformat(p.timeframes[0].to_iso)
    assert frm.tzinfo is not None and to.tzinfo is not None
    span_days = (to - frm).total_seconds() / 86400.0
    assert abs(span_days - 7.0) < 0.01


def test_recency_default_tz_naive_current_time_treated_utc():
    # tz'siz current_time → UTC kabul; from/to tz-aware ISO döner.
    naive = datetime(2026, 5, 16, 12, 0, 0)  # tzinfo yok
    p = _apply_news_recency_default(_plan("news_query", []), naive)
    tf = p.timeframes[0]
    assert datetime.fromisoformat(tf.to_iso).tzinfo is not None
    assert datetime.fromisoformat(tf.from_iso).tzinfo is not None


# ---------------------------------------------------------------------------
# #942 — critical_entities kod-backstop (Türkçe kelime-kesme yakalama)
# ---------------------------------------------------------------------------


def _resp_with_ce(ce: list[str]) -> str:
    d = json.loads(VALID_RESPONSE)
    d["critical_entities"] = ce
    return json.dumps(d, ensure_ascii=False)


def test_norm_words_tr_apostrophe_splits():
    # apostrof/noktalama ayırıcı: 'imamoğlu'nun' → {imamoğlu, nun}
    w = _norm_words_tr("İmamoğlu'nun davası???")
    assert "imamoğlu" in w and "nun" in w and "davası" in w


def test_canonical_token_stem_and_wordcut():
    qw = _norm_words_tr("Özgür özelle ilgili son gelişmeler neler???")
    # 'özelle' ham sorguda TAM + '-le' eki → KÖK 'özel' (#947)
    assert _canonical_token("özelle", qw) == "özel"
    # 'özel' qw'de tam yok ama 'özelle'nin kök+eki → token zaten kök
    assert _canonical_token("özel", qw) == "özel"
    # 'öz' ~ 'özgür'/'özelle' → 'gür'/'elle' ek değil → kelime-kesme
    assert _canonical_token("öz", qw) is None
    # tam kelime, ek yok → kendisi
    assert _canonical_token("özgür", qw) == "özgür"
    # <3 char + qw'de yok → None
    assert _canonical_token("oz", qw) is None


def test_entity_canonical_compound_stems():
    qw = _norm_words_tr("Özgür özelle ilgili son gelişmeler neler???")
    # #947 ASIL senaryo: LLM ekli 'özgür özelle' → kök 'özgür özel'
    assert _entity_canonical("özgür özelle", qw) == "özgür özel"
    assert _entity_canonical("özgür özel", qw) == "özgür özel"
    # kompound'da bir token kelime-kesme → tüm entity None
    assert _entity_canonical("özgür öz", qw) is None


def test_canonical_short_exact_match_kept():
    # #944 regresyon guard: kısa/sayısal/eksiz tam-kelime AYNEN korunur
    # ('15' sayı, 'temmuz'/'abd' ek yok — kökleşmez, niche_009 güvende).
    qw = _norm_words_tr("15 Temmuz mağdurları ile röportaj")
    assert _canonical_token("15", qw) == "15"
    assert _canonical_token("temmuz", qw) == "temmuz"
    assert _entity_canonical("15 temmuz", qw) == "15 temmuz"
    # 'boğazı' AYNEN korunur: '-zı' DAR stem-ek seti'nde YOK (tek-harf
    # ünlü/belirsiz soyulmaz → 'rusya'/'gazze'/'boğazı' bozulmaz —
    # over-stem felaketi önlendi). 'abd' ek yok.
    qw2 = _norm_words_tr("ABD Hürmüz Boğazı krizi")
    assert _canonical_token("abd", qw2) == "abd"
    assert _canonical_token("rusya", _norm_words_tr("Rusya saldırısı")) == "rusya"
    assert _entity_canonical("hürmüz boğazı", qw2) == "hürmüz boğazı"


def test_backstop_drops_word_cut_entity():
    # Planner 'özgür öz' üretti (prod conv 72fc9b64) — backstop düşürür
    res = parse_response(
        _resp_with_ce(["özgür öz"]),
        user_request="Özgür özelle ilgili son haberler nedir???",
    )
    assert isinstance(res, QueryPlan)
    assert "özgür öz" not in res.critical_entities
    assert any(
        w.startswith("critical_entity_dropped_not_grounded")
        for w in res.warnings
    )


def test_backstop_stems_suffix_entity():
    # #947 ASIL: LLM ekli 'özgür özelle' (prod conv 06a034cf 4/3) →
    # backstop KÖKLEŞTİRİR → critical_entities=['özgür özel']
    res = parse_response(
        _resp_with_ce(["özgür özelle"]),
        user_request="Özgür özelle ilgili son gelişmeler neler",
    )
    assert isinstance(res, QueryPlan)
    assert res.critical_entities == ["özgür özel"]
    assert any(
        w.startswith("critical_entity_stemmed:özgür özelle->özgür özel")
        for w in res.warnings
    )


def test_backstop_keeps_root_entity():
    res = parse_response(
        _resp_with_ce(["özgür özel"]),
        user_request="Özgür özelle ilgili son haberler nedir",
    )
    assert isinstance(res, QueryPlan)
    assert "özgür özel" in res.critical_entities


def test_backstop_skipped_without_user_request():
    # Geriye-uyumlu: user_request=None → backstop atlanır (eski davranış)
    res = parse_response(_resp_with_ce(["özgür öz"]))
    assert isinstance(res, QueryPlan)
    assert "özgür öz" in res.critical_entities
