"""Citation validator + repair (#180).

LLM çıktısındaki kaynak referanslarını doğrular ve normalize eder.

Akış:
    1. repair_bad_citation_formats(text) — farklı yazım stillerini "[#N]" formatına çek
    2. validate_citations(text, sources, embedding_fn) — her cümleyi source chunk'larla
       embedding cosine eşleştir; cosine < threshold ise "unsupported claim" flag'le
    3. cited_only_sources(text, sources) — text'te referansı olan source'ları döndür

RAGFlow `dialog_service.insert_citations` + `repair_bad_citation_formats` esinlenmesi.

PRD §3.4 halüsinasyon koruması, Risk Register R-LLM-01.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex repair patterns
# ---------------------------------------------------------------------------

# Hedef tek format: [#N]
# Tolere ettiğimiz girdi formatları:
#   [ID:N], [ID: N], (ID: N), (ID:N)
#   [ref:N], [ref N], [ref: N]
#   [kaynak:N], [kaynak N], (kaynak N)
#   [N], (N) — sadece sayı (başında kelime YOKSA)
_REPAIR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\[\s*ID\s*[:\.\-]?\s*(\d+)\s*\]", re.IGNORECASE), r"[#\1]"),
    (re.compile(r"\(\s*ID\s*[:\.\-]?\s*(\d+)\s*\)", re.IGNORECASE), r"[#\1]"),
    (re.compile(r"\[\s*ref\s*[:\.\-]?\s*(\d+)\s*\]", re.IGNORECASE), r"[#\1]"),
    (re.compile(r"\(\s*ref\s*[:\.\-]?\s*(\d+)\s*\)", re.IGNORECASE), r"[#\1]"),
    (re.compile(r"\[\s*kaynak\s*[:\.\-]?\s*(\d+)\s*\]", re.IGNORECASE), r"[#\1]"),
    (re.compile(r"\(\s*kaynak\s*[:\.\-]?\s*(\d+)\s*\)", re.IGNORECASE), r"[#\1]"),
    (re.compile(r"\[\s*source\s*[:\.\-]?\s*(\d+)\s*\]", re.IGNORECASE), r"[#\1]"),
]

# Hedef format match (sayma için)
_TARGET_PATTERN = re.compile(r"\[#(\d+)\]")


def repair_bad_citation_formats(text: str) -> tuple[str, int]:
    """Citation farklı stillerini "[#N]" tek formatına normalize eder.

    Returns:
        (cleaned_text, replacements_count)
    """
    if not text:
        return text, 0

    cleaned = text
    total = 0
    for pattern, repl in _REPAIR_PATTERNS:
        cleaned, n = pattern.subn(repl, cleaned)
        total += n
    return cleaned, total


def extract_citation_ids(text: str) -> list[int]:
    """Text'teki "[#N]" referanslarından integer ID listesi döndür (sıralı, unique)."""
    if not text:
        return []
    seen: set[int] = set()
    out: list[int] = []
    for m in _TARGET_PATTERN.finditer(text):
        val = int(m.group(1))
        if val not in seen:
            seen.add(val)
            out.append(val)
    return out


# ---------------------------------------------------------------------------
# Sentence split (basit Türkçe)
# ---------------------------------------------------------------------------

# Cümle ayırma — Türkçe için . ! ? ile böl, kısaltma listesini koru
_SENTENCE_END = re.compile(r"(?<=[\.\!\?])\s+(?=[A-ZÇĞİÖŞÜ])")
_ABBREVIATIONS = {"vb", "vs", "Dr", "Prof", "TC", "ABD", "AB", "TBMM"}


def split_sentences(text: str) -> list[str]:
    """Türkçe cümle split — kısaltma awareness ile."""
    if not text:
        return []
    text = text.strip()
    candidates = _SENTENCE_END.split(text)
    sentences: list[str] = []
    buffer = ""
    for c in candidates:
        c = c.strip()
        if not c:
            continue
        # Kısaltma sonrası ise birleştir
        if buffer:
            buffer = buffer + " " + c
        else:
            buffer = c

        # Son kelimeyi kontrol et (kısaltma mı?)
        last_word = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", buffer.split()[-1])
        if last_word and last_word[-1] in _ABBREVIATIONS:
            continue  # devam et, sonraki ile birleşecek
        sentences.append(buffer)
        buffer = ""

    if buffer:
        sentences.append(buffer)

    return sentences


# ---------------------------------------------------------------------------
# Cosine helpers
# ---------------------------------------------------------------------------


def cosine_sim(a: list[float], b: list[float]) -> float:
    """1024-dim vector cosine similarity."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class SourceFragment:
    """Citation karşılığı kanıt parçası."""

    id: int  # citation ID (1, 2, 3 ...)
    title: str
    summary: str = ""

    @property
    def evidence_text(self) -> str:
        return f"{self.title}\n\n{self.summary}".strip()


@dataclass
class ClaimResult:
    """Tek cümle / claim için doğrulama sonucu."""

    sentence: str
    cited_ids: list[int] = field(default_factory=list)
    best_source_id: int | None = None
    best_score: float = 0.0
    supported: bool = False  # cosine >= threshold AND cited_ids non-empty


@dataclass
class CitationReport:
    """validate_citations sonucu."""

    cleaned_text: str
    repair_count: int
    claims: list[ClaimResult] = field(default_factory=list)
    unsupported_count: int = 0
    cited_source_ids: list[int] = field(default_factory=list)


async def validate_citations(
    text: str,
    *,
    sources: list[SourceFragment],
    embed_fn: Callable[[list[str]], Awaitable[list[list[float]] | None]],
    cosine_threshold: float = 0.55,
    min_sentence_words: int = 4,
) -> CitationReport:
    """Cümle-bazlı kanıt eşleme.

    Args:
        text: LLM çıktısı (post.text veya summary)
        sources: Kullanılabilir source fragment listesi (id ile, 1-tabanlı)
        embed_fn: text list → 1024-dim vector list (None on failure)
        cosine_threshold: Bu eşik altı cosine "unsupported"

    Returns:
        CitationReport — repair_count, claims, unsupported_count, cited_source_ids
    """
    cleaned, repair_count = repair_bad_citation_formats(text)
    cited_global = extract_citation_ids(cleaned)

    sentences = split_sentences(cleaned)
    sentences = [s for s in sentences if len(s.split()) >= min_sentence_words]

    claims: list[ClaimResult] = []
    if not sentences or not sources:
        return CitationReport(
            cleaned_text=cleaned,
            repair_count=repair_count,
            claims=[],
            unsupported_count=0,
            cited_source_ids=cited_global,
        )

    # Embed all sentences + sources
    src_texts = [s.evidence_text for s in sources]
    inputs = sentences + src_texts
    vectors = await embed_fn(inputs)

    # Embed başarısız ise: format-only validation (cited_ids dolu mu?)
    if vectors is None or len(vectors) != len(inputs):
        logger.warning("citation embed_fn unavailable, using format-only validation")
        for sent in sentences:
            ids_in_sent = extract_citation_ids(sent)
            claims.append(
                ClaimResult(
                    sentence=sent,
                    cited_ids=ids_in_sent,
                    supported=bool(ids_in_sent),
                )
            )
        return CitationReport(
            cleaned_text=cleaned,
            repair_count=repair_count,
            claims=claims,
            unsupported_count=sum(1 for c in claims if not c.supported),
            cited_source_ids=cited_global,
        )

    sent_vecs = vectors[: len(sentences)]
    src_vecs = vectors[len(sentences):]

    for sent, sent_vec in zip(sentences, sent_vecs):
        ids_in_sent = extract_citation_ids(sent)
        best_score = 0.0
        best_idx = -1
        for i, sv in enumerate(src_vecs):
            score = cosine_sim(sent_vec, sv)
            if score > best_score:
                best_score = score
                best_idx = i
        best_source_id = sources[best_idx].id if best_idx >= 0 else None
        supported = best_score >= cosine_threshold
        claims.append(
            ClaimResult(
                sentence=sent,
                cited_ids=ids_in_sent,
                best_source_id=best_source_id,
                best_score=round(best_score, 4),
                supported=supported,
            )
        )

    unsupported = sum(1 for c in claims if not c.supported)
    return CitationReport(
        cleaned_text=cleaned,
        repair_count=repair_count,
        claims=claims,
        unsupported_count=unsupported,
        cited_source_ids=cited_global,
    )


async def validate_citations_batch(
    texts: list[str],
    *,
    sources: list[SourceFragment],
    embed_fn: Callable[[list[str]], Awaitable[list[list[float]] | None]],
    cosine_threshold: float = 0.55,
    min_sentence_words: int = 4,
) -> list[CitationReport]:
    """#394 MVP-2.1 — Çoklu metin için tek-batch citation validation.

    `validate_citations` her çağrıda kendi embed_fn round-trip'ini yapıyordu;
    N post için N embedding API call gerekiyordu. Bu fonksiyon TÜM post'ları
    ve TÜM source fragment'ları tek bir embed_fn batch'inde gönderir, sonra
    sonuçları post-bazlı raporlara böler.

    Args:
        texts: LLM çıktıları (her post.text + opsiyonel summary)
        sources: Kullanılabilir source fragment listesi (1-tabanlı id)
        embed_fn: text list → 1024-dim vector list (None on failure)
        cosine_threshold: Bu eşik altı cosine "unsupported"
        min_sentence_words: Min cümle kelime sayısı (kısa cümleler atlanır)

    Returns:
        list[CitationReport] — texts ile aynı uzunlukta, sırayla.

    Boş `texts` veya `sources` durumunda her metin için boş rapor döner.
    Embed fail durumunda format-only validation fallback'i (mevcut davranış).
    """
    if not texts:
        return []

    # 1) Her metni hazırla: repair + sentence split + cited_ids
    prepared: list[dict] = []
    all_sentences: list[str] = []
    sentence_owner: list[int] = []  # index → text index
    for ti, text in enumerate(texts):
        cleaned, repair_count = repair_bad_citation_formats(text or "")
        cited_global = extract_citation_ids(cleaned)
        sentences = split_sentences(cleaned)
        sentences = [s for s in sentences if len(s.split()) >= min_sentence_words]
        prepared.append(
            {
                "cleaned": cleaned,
                "repair_count": repair_count,
                "cited_global": cited_global,
                "sentences": sentences,
            }
        )
        for sent in sentences:
            all_sentences.append(sent)
            sentence_owner.append(ti)

    # 2) Erken çıkış: hiç cümle yok veya kaynak yok
    if not all_sentences or not sources:
        return [
            CitationReport(
                cleaned_text=p["cleaned"],
                repair_count=p["repair_count"],
                claims=[],
                unsupported_count=0,
                cited_source_ids=p["cited_global"],
            )
            for p in prepared
        ]

    # 3) Tek mega-batch embed: tüm cümleler + tüm source fragment'ları
    src_texts = [s.evidence_text for s in sources]
    inputs = all_sentences + src_texts
    vectors = await embed_fn(inputs)

    # 4) Embed başarısız → format-only validation per text
    if vectors is None or len(vectors) != len(inputs):
        logger.warning(
            "citation embed_fn unavailable (batch=%d), format-only validation",
            len(inputs),
        )
        reports: list[CitationReport] = []
        for p in prepared:
            claims: list[ClaimResult] = []
            for sent in p["sentences"]:
                ids_in_sent = extract_citation_ids(sent)
                claims.append(
                    ClaimResult(
                        sentence=sent,
                        cited_ids=ids_in_sent,
                        supported=bool(ids_in_sent),
                    )
                )
            reports.append(
                CitationReport(
                    cleaned_text=p["cleaned"],
                    repair_count=p["repair_count"],
                    claims=claims,
                    unsupported_count=sum(1 for c in claims if not c.supported),
                    cited_source_ids=p["cited_global"],
                )
            )
        return reports

    # 5) Sentence vectors + source vectors ayrımı
    sent_vecs = vectors[: len(all_sentences)]
    src_vecs = vectors[len(all_sentences):]

    # 6) Her metin için claim build
    reports: list[CitationReport] = []
    sent_cursor = 0
    for ti, p in enumerate(prepared):
        n_sentences = len(p["sentences"])
        my_sent_vecs = sent_vecs[sent_cursor : sent_cursor + n_sentences]
        sent_cursor += n_sentences

        claims: list[ClaimResult] = []
        for sent, sent_vec in zip(p["sentences"], my_sent_vecs):
            ids_in_sent = extract_citation_ids(sent)
            best_score = 0.0
            best_idx = -1
            for i, sv in enumerate(src_vecs):
                score = cosine_sim(sent_vec, sv)
                if score > best_score:
                    best_score = score
                    best_idx = i
            best_source_id = sources[best_idx].id if best_idx >= 0 else None
            supported = best_score >= cosine_threshold
            claims.append(
                ClaimResult(
                    sentence=sent,
                    cited_ids=ids_in_sent,
                    best_source_id=best_source_id,
                    best_score=round(best_score, 4),
                    supported=supported,
                )
            )

        reports.append(
            CitationReport(
                cleaned_text=p["cleaned"],
                repair_count=p["repair_count"],
                claims=claims,
                unsupported_count=sum(1 for c in claims if not c.supported),
                cited_source_ids=p["cited_global"],
            )
        )

    return reports


def cited_only_sources(
    text: str, sources: list[SourceFragment]
) -> list[SourceFragment]:
    """Text içinde "[#N]" referansı olan source'ları döndürür (gereksiz olanlar elenir)."""
    used_ids = set(extract_citation_ids(text))
    if not used_ids:
        return list(sources)  # citation yok ise eski davranış
    return [s for s in sources if s.id in used_ids]
