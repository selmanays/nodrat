"""Article cleaning + dedupe + state machine.

PRD §1.6 (cleaning) + §1.7 (dedupe)
docs/engineering/data-model.md §3.4 (articles state machine)

Akış:
  ExtractedArticle → CleanedArticle:
    1. URL canonicalize (utm_*, fbclid vb. kaldır)
    2. HTML boilerplate sil (Abone Ol, Son Dakika, Reklam, vb.)
    3. Whitespace normalize + paragraph reflow
    4. PII redaction (yorum/email/IBAN/TC pattern'leri)
    5. Dil tespiti (langdetect) — confidence düşükse 'tr' default
    6. Hash: SHA-256(clean_text), SHA-256(title_normalized)
    7. State machine: discovered → fetched → cleaned (or failed)

Boilerplate listesi sürekli genişler — admin testleriyle güncellenir.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    import langdetect

    langdetect.DetectorFactory.seed = 0  # deterministic
    _HAS_LANGDETECT = True
except ImportError:  # pragma: no cover
    _HAS_LANGDETECT = False

from app.core.extractor import ExtractedArticle
from app.core.pii import redact


logger = logging.getLogger(__name__)


# ============================================================================
# State machine constants
# ============================================================================


# articles.status valid değerleri (data-model.md §3.4)
STATUS_DISCOVERED = "discovered"
STATUS_FETCHED = "fetched"
STATUS_CLEANED = "cleaned"
STATUS_FAILED = "failed"
STATUS_ARCHIVED = "archived"

VALID_STATUSES = {
    STATUS_DISCOVERED,
    STATUS_FETCHED,
    STATUS_CLEANED,
    STATUS_FAILED,
    STATUS_ARCHIVED,
}

# Yasal geçişler — başka geçişler exception
STATE_TRANSITIONS: dict[str, set[str]] = {
    # #488 — DISCOVERED + FETCHED → ARCHIVED ekleneli: duplicate_content gibi
    # permanent_info path'leri article'ı terminal state'e taşımalı (eskiden
    # discovered'da kalıp backfill_discovered loop'una takılıyorlardı).
    STATUS_DISCOVERED: {STATUS_FETCHED, STATUS_FAILED, STATUS_ARCHIVED},
    STATUS_FETCHED: {STATUS_CLEANED, STATUS_FAILED, STATUS_ARCHIVED},
    STATUS_CLEANED: {STATUS_ARCHIVED, STATUS_FAILED},
    STATUS_FAILED: {STATUS_DISCOVERED, STATUS_ARCHIVED},  # admin retry / 72h+ archived
    STATUS_ARCHIVED: set(),  # terminal
}


class InvalidStateTransition(Exception):
    """State machine ihlali."""


def assert_transition(current: str, target: str) -> None:
    """current → target geçişi geçerli mi? Değilse exception."""
    if current not in VALID_STATUSES:
        raise InvalidStateTransition(f"unknown current state: {current}")
    if target not in VALID_STATUSES:
        raise InvalidStateTransition(f"unknown target state: {target}")
    allowed = STATE_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransition(
            f"transition {current} → {target} not allowed (allowed: {allowed})"
        )


# ============================================================================
# URL canonicalization
# ============================================================================

# UTM + tracking parametreleri (URL canonicalization sırasında kaldırılır)
TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_referrer",
        "fbclid",
        "gclid",
        "yclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "_ga",
        "ref",
        "ref_src",
        "ref_url",
        "source",
        "share",
        "share_origin",
        "spm",
    }
)


def canonicalize_url(url: str) -> str:
    """URL'yi normalize et (tracking param'ları sil + scheme/host lowercase + fragment sil).

    Örn: https://Example.COM/Path?utm_source=x&id=1#frag → https://example.com/Path?id=1
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    # default port'ları kaldır
    if (scheme == "http" and netloc.endswith(":80")) or (
        scheme == "https" and netloc.endswith(":443")
    ):
        netloc = netloc.rsplit(":", 1)[0]

    # path: trailing slash'i koru (anlamlı olabilir), sadece çift slash'leri normalize et
    path = re.sub(r"/{2,}", "/", parsed.path) or "/"

    # query: tracking param'ları çıkar, kalanları alfabetik sırala
    if parsed.query:
        kept = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k.lower() not in TRACKING_PARAMS
        ]
        kept.sort(key=lambda kv: kv[0])
        query = urlencode(kept)
    else:
        query = ""

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


# ============================================================================
# External article ID extraction (#496 — slug-change dedup)
# ============================================================================


# Generic news URL pattern'leri. Sıra önemli: daha spesifik önce.
# Pattern 1: /haber/(\d+)/ → Evrensel kalıbı, çoğu Türk haber sitesi
# Pattern 2: /(\d{6,})(?:/|\?|$) → AA, sondan ID (6+ digit, slug ile karıştırma riski düşük)
_EXTERNAL_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"/haber/(\d+)(?:/|\?|$)"),
    re.compile(r"/(\d{6,})(?:/|\?|$)"),
)


def extract_external_article_id(url: str) -> str | None:
    """Haber URL'inden kaynak sitenin haber ID'sini çıkar (slug-agnostic dedup).

    Slug değişikliği yaygın bir kalıp (Evrensel editöryel typo düzeltme); aynı
    haber farklı URL'le iki kez INSERT edilmesin diye discover dedup'ında
    kullanılır.

    Pattern'ler:
      - /haber/{id}/...   (Evrensel, çoğu Türk haber sitesi)
      - /.../{id} (6+)    (AA, suffix numeric — slug ile çakışmaz)

    None döner: pattern eşleşmedi (kaynak ID-tabanlı URL kullanmıyor).
    Bu durumda caller fallback olarak canonical_url exact match kullanır.
    """
    if not url:
        return None
    for pat in _EXTERNAL_ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


# ============================================================================
# Boilerplate detection
# ============================================================================


# Türkçe haber sitelerinde yaygın boilerplate cümleler
BOILERPLATE_PATTERNS = [
    r"abone\s*ol(un)?",
    r"haberi\s*kaydet",
    r"son\s*dakika\s*haberleri",
    r"reklam(?!\s*\w)",
    r"sponsor(lu)?\s*içerik",
    r"yorum(lar)?\s*yap",
    r"yorum(unu(zu)?)?\s*ekle",
    r"diğer\s*haberler",
    r"i?lgili\s*haberler",
    r"bu\s*haberi\s*paylaş",
    r"sosyal\s*medyada\s*paylaş",
    r"fotoğraf:\s*[^\n]{0,80}$",
    r"foto:\s*[^\n]{0,80}$",
    r"©\s*\d{4}",
    r"tüm\s*hakları\s*saklıdır",
    r"telif\s*hakk[ıi]",
    r"e[-\s]*posta\s*bültenimize\s*kaydolun",
    r"bültenimize\s*abone",
    r"whatsapp(?:'tan|'da)?\s*takip\s*et",
    r"instagram(?:'da|'dan)?\s*takip\s*et",
    r"şu\s*haberler\s*da\s*ilginizi\s*çekebilir",
    r"editör(ün)?\s*notu",
]

BOILERPLATE_RE = re.compile(
    "|".join(rf"(?:{p})" for p in BOILERPLATE_PATTERNS),
    flags=re.IGNORECASE | re.UNICODE,
)


def remove_boilerplate(text: str) -> tuple[str, float]:
    """Boilerplate satırlarını kaldır.

    Returns:
        (cleaned_text, boilerplate_ratio) — ratio kaldırılan / toplam paragraf
    """
    if not text:
        return text, 0.0
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return text, 0.0

    keep: list[str] = []
    removed = 0
    for p in paragraphs:
        # Çok kısa (< 30 char) + boilerplate match → at
        is_short = len(p) < 30
        match = BOILERPLATE_RE.search(p)
        if match and (is_short or len(p) < 80):
            removed += 1
            continue
        keep.append(p)

    cleaned = "\n\n".join(keep)
    ratio = removed / len(paragraphs)
    return cleaned, round(ratio, 3)


# ============================================================================
# Date / language helpers
# ============================================================================


def detect_language(text: str, *, default: str = "tr") -> tuple[str, float]:
    """langdetect ile dil tespit et. Türkçe için yüksek confidence beklenir.

    Returns:
        (lang_code, confidence)
    """
    if not text or len(text) < 50:
        return default, 0.0
    if not _HAS_LANGDETECT:
        return default, 0.0

    try:
        # detect_langs: top languages with probability
        langs = langdetect.detect_langs(text[:5000])
        if not langs:
            return default, 0.0
        top = langs[0]
        return str(top.lang), round(float(top.prob), 3)
    except Exception:  # pragma: no cover - external lib
        return default, 0.0


def normalize_title(title: str) -> str:
    """Title hash için normalize:
    - lowercase
    - whitespace tek boşluğa
    - başta/sonda noktalama at
    """
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = t.strip(""" .,;:!?-\"'""''""")
    return t


# ============================================================================
# Hash helpers (dedupe için)
# ============================================================================


def compute_content_hash(text: str) -> str:
    """SHA-256(normalize(text)) — dedupe key.

    Normalize:
    - whitespace tek boşluğa
    - lowercase
    """
    if not text:
        return hashlib.sha256(b"").hexdigest()
    norm = re.sub(r"\s+", " ", text.lower().strip())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def compute_title_hash(title: str) -> str:
    """SHA-256(normalize_title(title)) — başlık dedupe."""
    norm = normalize_title(title)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# ============================================================================
# CleanedArticle — extractor → DB-ready
# ============================================================================


@dataclass
class CleanedArticle:
    """articles tablosuna persist edilmeden önceki son hal."""

    canonical_url: str
    source_url: str
    title: str
    subtitle: str = ""
    author: str | None = None
    published_at: datetime | None = None
    body_html: str = ""
    clean_text: str = ""
    main_image_url: str | None = None
    """LEGACY (#300 PR-2): tek og:image. Kullanılmaz, body_images tercih."""
    body_images: list = field(default_factory=list)
    """#300 PR-2: BodyImage listesi — article body içindeki tüm img tag'leri."""
    language: str = "tr"

    content_hash: str = ""
    title_hash: str = ""

    extraction_confidence: float = 0.0
    cleaning_quality: float = 0.0
    """0..1 — boilerplate_ratio'dan ters orantılı + min length kontrolü."""

    boilerplate_ratio: float = 0.0
    language_confidence: float = 0.0

    pii_redactions: int = 0
    """Kaç adet PII pattern redact edildi."""

    status: str = STATUS_FETCHED
    """clean'den önce ne durumdayız — fetched (extractor başarılı)"""

    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def successful(self) -> bool:
        return (
            bool(self.title.strip())
            and len(self.clean_text) >= 200
            and self.cleaning_quality >= 0.4
            and self.error is None
        )


# ============================================================================
# Public API
# ============================================================================


def clean_extracted(
    extracted: ExtractedArticle,
    *,
    apply_pii_redaction: bool = True,
    boilerplate_threshold: float = 0.15,
) -> CleanedArticle:
    """ExtractedArticle → CleanedArticle.

    Args:
        extracted: Strategy-N extractor çıktısı
        apply_pii_redaction: yorum/PII pattern'leri redact et (default True)
        boilerplate_threshold: bu oranın üstünde boilerplate varsa warning

    Returns:
        CleanedArticle — caller .successful kontrolü yapmalı.
    """
    canon_source = canonicalize_url(extracted.url)

    cleaned = CleanedArticle(
        canonical_url=canon_source,
        source_url=extracted.url,
        title=extracted.title.strip() if extracted.title else "",
        subtitle=extracted.subtitle.strip() if extracted.subtitle else "",
        author=extracted.author,
        published_at=extracted.published_at,
        body_html=extracted.body_html,
        main_image_url=extracted.main_image_url,
        body_images=list(extracted.body_images),
        language=extracted.language or "tr",
        extraction_confidence=extracted.extraction_confidence,
        status=STATUS_FETCHED,
    )

    # Body clean_text yoksa veya çok kısaysa fail
    if not extracted.clean_text or len(extracted.clean_text) < 100:
        cleaned.clean_text = extracted.clean_text or ""
        cleaned.error = "clean_text too short"
        cleaned.cleaning_quality = 0.0
        return cleaned

    # 1) Boilerplate kaldır
    text_no_boiler, ratio = remove_boilerplate(extracted.clean_text)
    cleaned.boilerplate_ratio = ratio
    if ratio > boilerplate_threshold:
        cleaned.warnings.append(f"high boilerplate ratio: {ratio}")

    # 2) PII redaction
    if apply_pii_redaction:
        result = redact(text_no_boiler)
        cleaned.pii_redactions = result.total_redactions
        cleaned.clean_text = result.text
        if cleaned.subtitle:
            cleaned.subtitle = redact(cleaned.subtitle).text
    else:
        cleaned.clean_text = text_no_boiler

    # 3) Whitespace normalize
    cleaned.clean_text = re.sub(r"\n{3,}", "\n\n", cleaned.clean_text)
    cleaned.clean_text = re.sub(r"[ \t]+", " ", cleaned.clean_text).strip()

    # 4) Dil tespiti
    lang, lang_conf = detect_language(cleaned.clean_text, default="tr")
    cleaned.language = lang
    cleaned.language_confidence = lang_conf

    # 5) Hash
    cleaned.content_hash = compute_content_hash(cleaned.clean_text)
    cleaned.title_hash = compute_title_hash(cleaned.title)

    # 6) Cleaning quality
    quality = 1.0 - min(ratio * 2, 0.5)  # boilerplate ratio'dan
    if len(cleaned.clean_text) >= 500:
        quality += 0.1
    if cleaned.published_at:
        quality += 0.05
    if lang_conf >= 0.95:
        quality += 0.05
    cleaned.cleaning_quality = round(min(quality, 1.0), 3)

    return cleaned


# ============================================================================
# DB integration helpers (Faz 1 article worker tarafında kullanılacak)
# ============================================================================


def is_duplicate_signature(
    *,
    existing_canonical_urls: set[str],
    existing_content_hashes_for_source: set[str],
    canonical_url: str,
    content_hash: str,
) -> str | None:
    """Dedupe sinyali — caller DB query'lerini yapar, bu fonksiyon karar verir.

    Returns:
        None: yeni article
        'canonical_url': aynı URL daha önce alınmış (cross-source bile olabilir)
        'content_hash': aynı kaynak için aynı içerik
    """
    if canonical_url in existing_canonical_urls:
        return "canonical_url"
    if content_hash in existing_content_hashes_for_source:
        return "content_hash"
    return None
