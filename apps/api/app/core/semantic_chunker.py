"""Akıllı semantik chunker (#661 Faz 5.1 — RAGFlow-tier hybrid).

Mevcut sentence-window chunker (chunker.py, #652 Faz 1) niş bilgi recall'unu
%27 → %45 sağladı ama 6 niş vaka hala başarısız:
  - Karşıyaka hakemler (hakem isimleri 1 cümle, gömülü)
  - Rodos kaç kent (sayısal niş, büyük chunk içi)
  - 15 Temmuz röportaj (meta-sorgu)
  - vs.

Faz 5.1 — semantic-aware breakpoint detection:
  1. Paragraph + heading boundary mandatory break (RAGFlow DeepDoc pattern)
  2. Paragraph içinde cümle-level BATCH embedding (1 API call/article — cost guard)
  3. Adjacent cosine similarity hesapla → percentile-based breakpoint
     (top %10 lowest similarity → konu değişimi)
  4. Token budget enforcement: 150 / 400 / 800
  5. Overlap: 2 sentence (chunk arası context flow)
  6. Title + subtitle prefix HER chunk'a (article-level context)

ChatGPT'nin önerdiği semantic chunking pattern + RAGFlow DeepDoc hierarchical
+ batch embedding (önerdiği "her cümle ayrı call" yerine).

Anti-pattern:
  - Cümle ortası bölme YOK
  - Heading mandatory break (HTML/markdown # detection)
  - Min size altı → sonraki ile birleştir (chunk fragmentation önle)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import numpy as np

from app.core.chunker import ChunkRecord, estimate_tokens, _make_prefix

logger = logging.getLogger(__name__)


# Türkçe sentence split — Türkçe noktalama + cap'li başlangıç
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÇĞİıÖŞÜ\"'“‘])")

# Paragraph split — çift satır sonu
_PARAGRAPH_SPLIT_RE = re.compile(r"\n{2,}")

# Heading detection — kısa satır, hep cap, veya markdown #
_HEADING_RE = re.compile(r"^(#{1,6}\s|[A-ZÇĞİıÖŞÜ\s]{6,80}:?$)")


@dataclass
class SemanticChunkConfig:
    """Faz 5.1 semantic chunker config — ChatGPT önerisinden adapte."""

    min_tokens: int = 150
    target_tokens: int = 400
    max_tokens: int = 800
    overlap_sentences: int = 2

    # Semantic breakpoint: top N% lowest adjacent similarity = break point
    # ChatGPT öneri "semanticBreakpointPercentile: 90" = top 10% drop
    # Bizde: percentile arg "P" = P-inci percentile altı break
    # Düşük percentile = daha az break (daha büyük chunks)
    # Yüksek percentile = daha çok break (daha küçük chunks)
    breakpoint_percentile: int = 25  # alt %25 quartile

    # Semantic break enable/disable (test/fallback için)
    use_semantic_breaks: bool = True

    # Embedding batch enable (False = fallback structural-only)
    use_batch_embedding: bool = True

    title_prefix: bool = True


@dataclass
class _SentenceUnit:
    """Tek cümle + metadata."""

    text: str
    paragraph_idx: int
    sentence_idx: int  # paragraf içi sıra
    is_heading: bool = False
    is_first_of_paragraph: bool = False
    token_count: int = 0
    embedding: list[float] | None = None


def _split_sentences(paragraph: str) -> list[str]:
    """Paragraph → cümle listesi (#652 Faz 1 → 5.1 — geliştirilmiş)."""
    if not paragraph:
        return []
    raw = _SENTENCE_SPLIT_RE.split(paragraph.strip())
    sentences: list[str] = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        if len(s) < 3 and sentences:
            sentences[-1] = sentences[-1] + " " + s
        else:
            sentences.append(s)
    return sentences


def _is_heading(text: str) -> bool:
    """Heading tespiti (mandatory break point)."""
    if not text:
        return False
    text_stripped = text.strip()
    if not text_stripped:
        return False
    # Markdown heading
    if text_stripped.startswith("#"):
        return True
    # Kısa cap-only satır (örn. "GÜNDEM" başlığı)
    if (
        5 <= len(text_stripped) <= 80
        and text_stripped == text_stripped.upper()
        and not text_stripped.endswith((".", "!", "?"))
        and " " not in text_stripped[:20]
    ):
        return True
    return False


def _flatten_paragraphs_to_sentences(text: str) -> list[_SentenceUnit]:
    """Article'ı paragraph + sentence stream olarak düzleştir."""
    units: list[_SentenceUnit] = []
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]
    for p_idx, paragraph in enumerate(paragraphs):
        is_heading_para = _is_heading(paragraph)
        if is_heading_para:
            # Heading tek başına bir unit
            units.append(
                _SentenceUnit(
                    text=paragraph,
                    paragraph_idx=p_idx,
                    sentence_idx=0,
                    is_heading=True,
                    is_first_of_paragraph=True,
                    token_count=estimate_tokens(paragraph),
                )
            )
            continue
        sentences = _split_sentences(paragraph)
        for s_idx, sent in enumerate(sentences):
            units.append(
                _SentenceUnit(
                    text=sent,
                    paragraph_idx=p_idx,
                    sentence_idx=s_idx,
                    is_heading=False,
                    is_first_of_paragraph=(s_idx == 0),
                    token_count=estimate_tokens(sent),
                )
            )
    return units


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity (vector1, vector2 1024-dim)."""
    if not a or not b:
        return 0.0
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def _compute_breakpoints(
    units: list[_SentenceUnit], *, percentile: int
) -> set[int]:
    """Adjacent sentence cosine similarity → percentile-based breakpoints.

    Returns: set of indices `i` where break SHOULD happen BEFORE unit[i].
    (i.e., chunk_n ends at i-1, chunk_n+1 starts at i)

    Mandatory breaks (always included):
      - Heading boundary (unit.is_heading=True)
      - New paragraph start (is_first_of_paragraph=True) + similarity below threshold

    Semantic breaks:
      - Cosine similarity of (unit[i-1], unit[i]) below `percentile`-th percentile
        of all adjacent similarities
    """
    if len(units) < 2:
        return set()

    breakpoints: set[int] = set()

    # Mandatory: heading start
    for i, u in enumerate(units):
        if u.is_heading and i > 0:
            breakpoints.add(i)

    # Semantic: cosine drop detection
    similarities: list[tuple[int, float]] = []
    for i in range(1, len(units)):
        prev_u = units[i - 1]
        curr_u = units[i]
        if prev_u.embedding is None or curr_u.embedding is None:
            continue
        sim = _cosine_sim(prev_u.embedding, curr_u.embedding)
        similarities.append((i, sim))

    if not similarities:
        return breakpoints

    # Threshold: alt P-th percentile (örn. P=25 → q1 altı)
    sim_values = [s for _, s in similarities]
    if len(sim_values) >= 4:
        threshold = float(np.percentile(sim_values, percentile))
    else:
        threshold = min(sim_values) - 0.001  # az veri → sadece mandatory breaks

    for idx, sim in similarities:
        if sim < threshold:
            # Sadece paragraph boundary'de uygula (cümle ortası bölme yok)
            # Eğer current sentence yeni paragraph başlıyorsa, semantic break VAR
            if units[idx].is_first_of_paragraph:
                breakpoints.add(idx)

    return breakpoints


def _pack_chunks(
    units: list[_SentenceUnit],
    breakpoints: set[int],
    *,
    config: SemanticChunkConfig,
) -> list[list[_SentenceUnit]]:
    """Breakpoints + token budget → chunk gruplandırma."""
    chunks: list[list[_SentenceUnit]] = []
    current: list[_SentenceUnit] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            chunks.append(current)
            current = []
            current_tokens = 0

    for i, u in enumerate(units):
        # Mandatory break check
        if i in breakpoints and current and current_tokens >= config.min_tokens:
            flush()

        # Hard cap check
        if current_tokens + u.token_count > config.max_tokens and current:
            flush()

        # Target tokens check (soft break — natural pacing)
        if (
            current_tokens + u.token_count > config.target_tokens
            and current_tokens >= config.min_tokens
            and u.is_first_of_paragraph
        ):
            flush()

        current.append(u)
        current_tokens += u.token_count

    flush()

    # Min size düzeltmesi: son chunk min altı → öncekiyle birleştir
    if len(chunks) >= 2:
        last_tokens = sum(u.token_count for u in chunks[-1])
        if last_tokens < config.min_tokens:
            chunks[-2].extend(chunks[-1])
            chunks.pop()

    return chunks


def _apply_overlap(
    chunks: list[list[_SentenceUnit]],
    *,
    overlap_sentences: int,
) -> list[list[_SentenceUnit]]:
    """Adjacent chunks arasında overlap N cümle ekle (#chatgpt önerisi)."""
    if overlap_sentences <= 0 or len(chunks) < 2:
        return chunks
    out: list[list[_SentenceUnit]] = [chunks[0]]
    for i in range(1, len(chunks)):
        prev_chunk = chunks[i - 1]
        curr_chunk = chunks[i]
        # Önceki chunk'ın son N cümlesini (heading hariç) curr başına ekle
        overlap_units = [u for u in prev_chunk[-overlap_sentences:] if not u.is_heading]
        if overlap_units:
            out.append(overlap_units + curr_chunk)
        else:
            out.append(curr_chunk)
    return out


async def semantic_chunk_text(
    text: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]] | None = None,
    config: SemanticChunkConfig | None = None,
) -> list[ChunkRecord]:
    """Semantic chunker — clean_text → chunk listesi.

    Args:
        text: Article cleaned_text
        title/subtitle: chunk prefix için bağlam (her chunk'a eklenir)
        embed_fn: Async batch embedding (list[str] → list[vec]).
            None ise structural-only fallback (cosine break skipped).
        config: chunker parametreleri

    Strateji (#661):
      1. Article → paragraph → sentence stream
      2. (Opsiyonel) Tüm cümlelere BATCH embedding
      3. Adjacent cosine similarity → percentile breakpoints
      4. Mandatory: heading + paragraph boundary (semantic drop varsa)
      5. Token budget enforcement
      6. Overlap N sentence
      7. Title + subtitle prefix
    """
    cfg = config or SemanticChunkConfig()
    if not text or not text.strip():
        return []

    units = _flatten_paragraphs_to_sentences(text)
    if not units:
        return []

    # Çok kısa article → tek chunk
    total_tokens = sum(u.token_count for u in units)
    if total_tokens < cfg.min_tokens:
        prefix = _make_prefix(title, subtitle) if cfg.title_prefix else ""
        body = " ".join(u.text for u in units)
        full_text = prefix + body
        return [
            ChunkRecord(
                chunk_index=0,
                chunk_text=full_text.strip(),
                token_count=estimate_tokens(full_text),
            )
        ]

    # Batch embedding (cost guard: tek call)
    if cfg.use_semantic_breaks and cfg.use_batch_embedding and embed_fn:
        try:
            texts = [u.text for u in units]
            embeddings = await embed_fn(texts)
            if len(embeddings) == len(units):
                for u, emb in zip(units, embeddings):
                    u.embedding = emb
            else:
                logger.warning(
                    "embedding count mismatch %d != %d, fallback structural",
                    len(embeddings), len(units),
                )
        except Exception as exc:
            logger.warning("batch embedding failed, fallback structural: %s", exc)

    # Breakpoint detection
    breakpoints = _compute_breakpoints(units, percentile=cfg.breakpoint_percentile)

    # Pack chunks
    chunks = _pack_chunks(units, breakpoints, config=cfg)

    # Overlap
    chunks = _apply_overlap(chunks, overlap_sentences=cfg.overlap_sentences)

    # Title prefix + ChunkRecord output
    prefix = _make_prefix(title, subtitle) if cfg.title_prefix else ""
    records: list[ChunkRecord] = []
    for idx, chunk_units in enumerate(chunks):
        body = " ".join(u.text for u in chunk_units)
        full_text = prefix + body
        records.append(
            ChunkRecord(
                chunk_index=idx,
                chunk_text=full_text.strip(),
                token_count=estimate_tokens(full_text),
            )
        )
    return records
