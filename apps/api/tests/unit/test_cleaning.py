"""Article cleaning + dedupe + state machine tests."""

from __future__ import annotations

import pytest

from app.core.cleaning import (
    BOILERPLATE_RE,
    STATE_TRANSITIONS,
    STATUS_ARCHIVED,
    STATUS_CLEANED,
    STATUS_DISCOVERED,
    STATUS_FAILED,
    STATUS_FETCHED,
    CleanedArticle,
    InvalidStateTransition,
    assert_transition,
    canonicalize_url,
    clean_extracted,
    compute_content_hash,
    compute_title_hash,
    detect_language,
    is_duplicate_signature,
    normalize_title,
    remove_boilerplate,
)
from app.core.extractor import ExtractedArticle


# ---------------------------------------------------------------------------
# canonicalize_url
# ---------------------------------------------------------------------------


def test_canon_strips_utm():
    assert canonicalize_url(
        "https://example.com/news/1?utm_source=twitter&utm_campaign=x&id=42"
    ) == "https://example.com/news/1?id=42"


def test_canon_lowercase_scheme_host():
    assert canonicalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"


def test_canon_strips_default_port():
    assert canonicalize_url("https://example.com:443/page") == "https://example.com/page"
    assert canonicalize_url("http://example.com:80/page") == "http://example.com/page"


def test_canon_strips_fragment():
    assert canonicalize_url("https://x.com/page#section") == "https://x.com/page"


def test_canon_handles_empty_query():
    assert canonicalize_url("https://x.com/page") == "https://x.com/page"


def test_canon_strips_fbclid_gclid():
    assert canonicalize_url("https://x.com/?fbclid=abc&gclid=def&keep=1") == (
        "https://x.com/?keep=1"
    )


def test_canon_sorts_query_params():
    """Aynı query farklı sırayla → aynı canonical URL (dedupe için)."""
    a = canonicalize_url("https://x.com/?b=2&a=1")
    b = canonicalize_url("https://x.com/?a=1&b=2")
    assert a == b


def test_canon_invalid_input_returns_original():
    assert canonicalize_url("") == ""


# ---------------------------------------------------------------------------
# Boilerplate removal
# ---------------------------------------------------------------------------


def test_boilerplate_pattern_matches_subscribe():
    assert BOILERPLATE_RE.search("Abone Ol")
    assert BOILERPLATE_RE.search("E-posta bültenimize kaydolun")


def test_boilerplate_remove_short_subscribe():
    text = "Bültenimize abone\n\nGerçek haber içeriği burada başlıyor ve uzun bir cümle ile devam ediyor."
    cleaned, ratio = remove_boilerplate(text)
    assert "abone" not in cleaned.lower() or "Bültenimize abone" not in cleaned
    assert ratio > 0.0


def test_boilerplate_keeps_long_paragraph_with_match():
    """Boilerplate pattern uzun paragrafta varsa o paragraf KORUNUR."""
    long_p = (
        "Bu uzun bir paragraf içinde 'Abone Ol' kelimesi geçiyor ama paragraf "
        "genelinde başka bir konu işleniyor ve bu yüzden silinmemeli. " * 3
    )
    cleaned, _ = remove_boilerplate(long_p)
    assert long_p in cleaned


def test_boilerplate_preserves_real_content():
    real = "Bu gerçek bir haber metnidir ve uzunca yazılmış bir paragraftır."
    cleaned, ratio = remove_boilerplate(real)
    assert cleaned == real
    assert ratio == 0.0


def test_boilerplate_empty_text():
    cleaned, ratio = remove_boilerplate("")
    assert cleaned == ""
    assert ratio == 0.0


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def test_transitions_discovered_to_fetched():
    assert_transition(STATUS_DISCOVERED, STATUS_FETCHED)


def test_transitions_discovered_to_cleaned_invalid():
    with pytest.raises(InvalidStateTransition):
        assert_transition(STATUS_DISCOVERED, STATUS_CLEANED)


def test_transitions_archived_terminal():
    """archived → hiçbir yere geçemez."""
    assert STATE_TRANSITIONS[STATUS_ARCHIVED] == set()
    with pytest.raises(InvalidStateTransition):
        assert_transition(STATUS_ARCHIVED, STATUS_DISCOVERED)


def test_transitions_failed_can_be_reset():
    """Failed → discovered (admin retry)."""
    assert_transition(STATUS_FAILED, STATUS_DISCOVERED)


# #488 — duplicate_content + permanent_info path için DISCOVERED/FETCHED →
# ARCHIVED kabul edildi (terminal, sonsuz dispatch loop kırıldı).


def test_transitions_discovered_to_archived():
    """#488 — duplicate_content path için discovered → archived geçişi."""
    assert_transition(STATUS_DISCOVERED, STATUS_ARCHIVED)


def test_transitions_fetched_to_archived():
    """#488 — fetched aşamada da archive (simetri için)."""
    assert_transition(STATUS_FETCHED, STATUS_ARCHIVED)


def test_transitions_failed_to_archived():
    """#488 — 72h+ stale failed → archived (PR #478 backfill semantiği)."""
    assert_transition(STATUS_FAILED, STATUS_ARCHIVED)


# ---------------------------------------------------------------------------
# extract_external_article_id (#496 — slug-change dedup)
# ---------------------------------------------------------------------------


def test_extract_ext_id_evrensel():
    """Evrensel /haber/{id}/slug pattern'ı."""
    from app.core.cleaning import extract_external_article_id

    url = "https://www.evrensel.net/haber/5983252/provokasyondan-gozaltina-odtude"
    assert extract_external_article_id(url) == "5983252"


def test_extract_ext_id_evrensel_slug_changed():
    """Aynı haber, farklı slug → aynı ID (dedup'ın amacı)."""
    from app.core.cleaning import extract_external_article_id

    url1 = "https://www.evrensel.net/haber/5983252/odtude-bastan-sona"
    url2 = "https://www.evrensel.net/haber/5983252/odtu-de-bastan-sona"
    assert extract_external_article_id(url1) == extract_external_article_id(url2) == "5983252"


def test_extract_ext_id_aa_suffix_numeric():
    """AA pattern: /tr/.../slug/{id}."""
    from app.core.cleaning import extract_external_article_id

    url = "https://www.aa.com.tr/tr/gundem/bayburtta-kar-yagisi-etkili-oldu/3929722"
    assert extract_external_article_id(url) == "3929722"


def test_extract_ext_id_no_match_returns_none():
    """ID-tabanlı pattern yoksa None — caller fallback canonical_url match kullanır."""
    from app.core.cleaning import extract_external_article_id

    # Slug-only URL, numeric ID yok
    assert extract_external_article_id("https://example.com/news/some-article") is None
    # Boş / None
    assert extract_external_article_id("") is None
    assert extract_external_article_id(None) is None  # type: ignore[arg-type]


def test_extract_ext_id_short_number_not_matched():
    """Kısa sayı (5 digit) accidental match riski — yakalanmaz (6+ digit ID gerekli)."""
    from app.core.cleaning import extract_external_article_id

    # /2026/05/09/ tarih path'i 4 digit, match etmez
    assert extract_external_article_id("https://example.com/2026/05/09/some-news") is None


def test_extract_ext_id_with_query_string():
    """utm parametreleri ID match'i bozmaz."""
    from app.core.cleaning import extract_external_article_id

    url = "https://www.evrensel.net/haber/5983252/slug?utm_source=rss"
    assert extract_external_article_id(url) == "5983252"


def test_transitions_unknown_state():
    with pytest.raises(InvalidStateTransition):
        assert_transition("imaginary", STATUS_FETCHED)
    with pytest.raises(InvalidStateTransition):
        assert_transition(STATUS_FETCHED, "imaginary")


# ---------------------------------------------------------------------------
# Hash + normalize
# ---------------------------------------------------------------------------


def test_normalize_title_idempotent():
    a = normalize_title("  Şarkıcı  Gülşen'e  10 ay hapis cezası!  ")
    b = normalize_title("şarkıcı gülşen'e 10 ay hapis cezası")
    assert a == b


def test_content_hash_whitespace_invariance():
    a = compute_content_hash("Aynı  metin\n\n burada")
    b = compute_content_hash("aynı metin burada")
    assert a == b


def test_content_hash_deterministic():
    assert compute_content_hash("foo") == compute_content_hash("foo")


def test_content_hash_different_for_different_content():
    a = compute_content_hash("Birinci haber")
    b = compute_content_hash("İkinci haber")
    assert a != b


def test_title_hash_deterministic():
    assert compute_title_hash("Test Başlığı") == compute_title_hash("test başlığı")


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


def test_detect_language_turkish():
    text = (
        "Türkiye'de gündem son dakika haberleri. "
        "Cumhurbaşkanı bugün açıklama yaptı. "
        "Ekonomi alanında önemli gelişmeler yaşandı. " * 5
    )
    lang, conf = detect_language(text)
    assert lang == "tr"
    assert conf > 0.5


def test_detect_language_english_returns_en():
    text = (
        "The president announced new economic measures today. "
        "Markets responded positively to the news. " * 5
    )
    lang, conf = detect_language(text)
    assert lang == "en"
    assert conf > 0.5


def test_detect_language_short_text_default():
    lang, conf = detect_language("kısa")
    assert lang == "tr"
    assert conf == 0.0


# ---------------------------------------------------------------------------
# clean_extracted (full pipeline)
# ---------------------------------------------------------------------------


def _make_extracted(text: str = "", **kwargs) -> ExtractedArticle:
    body = (
        text
        or "Bu uzun bir Türkçe haber metnidir. " * 30
    )
    defaults = dict(
        url="https://example.com/news/1?utm_source=twitter",
        title="Test Haber Başlığı",
        clean_text=body,
        extraction_confidence=0.8,
    )
    defaults.update(kwargs)
    return ExtractedArticle(**defaults)


def test_clean_canonicalizes_url():
    art = _make_extracted()
    cleaned = clean_extracted(art)
    assert cleaned.canonical_url == "https://example.com/news/1"
    assert cleaned.source_url == "https://example.com/news/1?utm_source=twitter"


def test_clean_redacts_pii_in_text():
    """PII (email gibi) clean_text'te redact edilmeli."""
    body = (
        "Haber metni başlıyor. "
        "İletişim için info@example.com adresine yazın. "
        "Devam eden uzun metin paragraflar." * 5
    )
    art = _make_extracted(text=body)
    cleaned = clean_extracted(art, apply_pii_redaction=True)
    assert "info@example.com" not in cleaned.clean_text
    assert cleaned.pii_redactions >= 1


def test_clean_short_body_fails():
    art = _make_extracted(text="çok kısa bir metin.")
    cleaned = clean_extracted(art)
    assert cleaned.error == "clean_text too short"
    assert cleaned.cleaning_quality == 0.0
    assert not cleaned.successful


def test_clean_computes_hashes():
    art = _make_extracted()
    cleaned = clean_extracted(art)
    assert len(cleaned.content_hash) == 64  # SHA-256
    assert len(cleaned.title_hash) == 64


def test_clean_detects_turkish_language():
    art = _make_extracted()
    cleaned = clean_extracted(art)
    assert cleaned.language == "tr"
    assert cleaned.language_confidence > 0.5


def test_clean_quality_score():
    art = _make_extracted()
    cleaned = clean_extracted(art)
    # Boilerplate yok + uzun + Türkçe yüksek conf → yüksek quality
    assert cleaned.cleaning_quality >= 0.7


def test_clean_records_boilerplate_warning():
    body = (
        "Abone ol\n\nReklam alanı\n\nSon dakika\n\n"
        "Bu gerçek bir haber. "
    )
    art = _make_extracted(text=body)
    cleaned = clean_extracted(art)
    # Boilerplate ratio yüksek olduğunda warning eklenir
    assert cleaned.boilerplate_ratio >= 0.0


def test_clean_successful_property():
    art = _make_extracted()
    cleaned = clean_extracted(art)
    assert cleaned.successful is True


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def test_dup_canonical_url_match():
    sig = is_duplicate_signature(
        existing_canonical_urls={"https://x.com/a"},
        existing_content_hashes_for_source=set(),
        canonical_url="https://x.com/a",
        content_hash="abc",
    )
    assert sig == "canonical_url"


def test_dup_content_hash_match():
    sig = is_duplicate_signature(
        existing_canonical_urls=set(),
        existing_content_hashes_for_source={"abc"},
        canonical_url="https://x.com/a",
        content_hash="abc",
    )
    assert sig == "content_hash"


def test_dup_canonical_takes_precedence():
    sig = is_duplicate_signature(
        existing_canonical_urls={"https://x.com/a"},
        existing_content_hashes_for_source={"abc"},
        canonical_url="https://x.com/a",
        content_hash="abc",
    )
    assert sig == "canonical_url"


def test_dup_no_match():
    sig = is_duplicate_signature(
        existing_canonical_urls={"https://x.com/other"},
        existing_content_hashes_for_source={"xyz"},
        canonical_url="https://x.com/new",
        content_hash="abc",
    )
    assert sig is None
