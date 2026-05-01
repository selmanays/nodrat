"""Text chunker — RAG için article cleaned_text'i chunk'lar (#18).

PRD §2.3 + data-model.md §4.1.

Hedefler:
  - Chunk size 200-900 token (avg ~500)
  - Overlap 50-100 token (default 80)
  - Title + subtitle prefix her chunk'ta (bağlam)
  - Token count: heuristik (whitespace split * 1.3) — tiktoken yok
    Türkçe için ortalama ~%5 sapma kabul edilir (#43 eval framework
    sonuç doğrulayacak)

Output: list[ChunkRecord] — caller article_chunks tablosuna persist eder.

Anti-pattern (HARD STOP):
  - Boş chunk üretilmez
  - chunk_index sıralı + unique per article (DB UNIQUE constraint var)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Heuristic token coefficient — Türkçe word ≈ 1.3 token (rough average).
TR_TOKEN_COEFFICIENT = 1.3

# Default chunk parametreleri
DEFAULT_TARGET_TOKENS = 500
DEFAULT_MAX_TOKENS = 900
DEFAULT_MIN_TOKENS = 200
DEFAULT_OVERLAP_TOKENS = 80


def estimate_tokens(text: str) -> int:
    """Heuristik token count (Türkçe için ~%5 sapma).

    Üretim için yeterli; precision gerekirse tiktoken eklenir.
    """
    if not text:
        return 0
    word_count = len(text.split())
    return int(word_count * TR_TOKEN_COEFFICIENT)


def _split_paragraphs(text: str) -> list[str]:
    """Çift satır sonu ile paragraflara böl, boşları temizle."""
    if not text:
        return []
    parts = re.split(r"\n{2,}", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _build_overlap(words: list[str], overlap_tokens: int) -> list[str]:
    """Son N kelimeyi al — overlap için."""
    if overlap_tokens <= 0 or not words:
        return []
    # overlap_tokens'i kelimeye çevir (token / 1.3)
    overlap_words = max(1, int(overlap_tokens / TR_TOKEN_COEFFICIENT))
    return words[-overlap_words:]


@dataclass
class ChunkRecord:
    """Tek chunk — caller article_chunks tablosuna INSERT eder."""

    chunk_index: int
    chunk_text: str
    token_count: int
    """Heuristik token count (estimate_tokens ile)"""

    @property
    def char_length(self) -> int:
        return len(self.chunk_text)


@dataclass
class ChunkingConfig:
    """Chunker parametreleri — admin override için."""

    target_tokens: int = DEFAULT_TARGET_TOKENS
    max_tokens: int = DEFAULT_MAX_TOKENS
    min_tokens: int = DEFAULT_MIN_TOKENS
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS

    title_prefix: bool = True
    """Her chunk'ın başına 'TITLE: …\\n\\nSUBTITLE: …\\n\\n' eklenir mi?"""


def _make_prefix(title: str | None, subtitle: str | None) -> str:
    """Chunk prefix string'i oluştur (bağlam için)."""
    parts: list[str] = []
    if title:
        parts.append(f"BAŞLIK: {title.strip()}")
    if subtitle:
        parts.append(f"ALT BAŞLIK: {subtitle.strip()}")
    return "\n\n".join(parts) + ("\n\n" if parts else "")


def chunk_text(
    text: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    config: ChunkingConfig | None = None,
) -> list[ChunkRecord]:
    """clean_text → chunk listesi.

    Strateji:
      1. Paragraflara böl
      2. Sırayla bir window'da topla, target_tokens'a yaklaşırken bitir
      3. max_tokens aşılırsa zorunlu split (paragraph dahi büyükse cümle bazlı)
      4. Overlap: son chunk'ın son N token'ını yeni chunk'ın başına ekle
      5. min_tokens altındaki son chunk'ı bir öncekiyle birleştir
    """
    cfg = config or ChunkingConfig()
    if not text or not text.strip():
        return []

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    prefix = _make_prefix(title, subtitle) if cfg.title_prefix else ""
    prefix_tokens = estimate_tokens(prefix) if prefix else 0

    chunks: list[list[str]] = []  # list of paragraph lists
    current: list[str] = []
    current_tokens = 0

    def flush_current() -> None:
        nonlocal current, current_tokens
        if current:
            chunks.append(current)
            current = []
            current_tokens = 0

    for paragraph in paragraphs:
        p_tokens = estimate_tokens(paragraph)

        # Tek başına büyük paragraf — cümlelere böl
        if p_tokens > cfg.max_tokens:
            # Önce mevcut window'u kapat
            flush_current()
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            sub_window: list[str] = []
            sub_tokens = 0
            for s in sentences:
                if not s.strip():
                    continue
                s_tokens = estimate_tokens(s)
                if sub_tokens + s_tokens > cfg.max_tokens and sub_window:
                    chunks.append(sub_window)
                    sub_window = []
                    sub_tokens = 0
                sub_window.append(s)
                sub_tokens += s_tokens
            if sub_window:
                chunks.append(sub_window)
            continue

        # Window dolarsa flush
        if (
            current_tokens + p_tokens > cfg.target_tokens
            and current_tokens >= cfg.min_tokens
        ):
            flush_current()

        # Hard cap (target overshoot)
        if current_tokens + p_tokens > cfg.max_tokens:
            flush_current()

        current.append(paragraph)
        current_tokens += p_tokens

    flush_current()

    # Min size düzeltmesi: son chunk min_tokens altındaysa öncekiyle birleştir
    if len(chunks) >= 2:
        last_text = "\n\n".join(chunks[-1])
        last_tokens = estimate_tokens(last_text)
        if last_tokens < cfg.min_tokens:
            chunks[-2].extend(chunks[-1])
            chunks.pop()

    # Overlap + prefix uygulayarak ChunkRecord listesi üret
    records: list[ChunkRecord] = []
    prev_words: list[str] = []
    for idx, paragraphs_in_chunk in enumerate(chunks):
        body = "\n\n".join(paragraphs_in_chunk)
        body_words = body.split()
        overlap_text = " ".join(prev_words) + (" " if prev_words else "")
        full_body = overlap_text + body
        full_text = prefix + full_body

        tok = estimate_tokens(full_text)
        records.append(
            ChunkRecord(
                chunk_index=idx,
                chunk_text=full_text.strip(),
                token_count=tok,
            )
        )

        prev_words = _build_overlap(body_words, cfg.overlap_tokens)

    return records
