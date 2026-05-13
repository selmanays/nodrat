"""Text chunker — RAG için article cleaned_text'i chunk'lar (#18, #652 Faz 1).

PRD §2.3 + data-model.md §4.1.

Strategy (#652 Faz 1 — RAGFlow-tier recall):
  - **Sentence-window splitting**: paragraph yerine cümle-bazlı sliding window
  - **Smaller chunks**: target 256 token (eski 500), max 384 (eski 900),
    min 100 (eski 200), overlap 64 (eski 80)
  - **Niş bilgi koruması**: 1275 char article 1 chunk yerine 4-5 chunk olur,
    her cümle/paragraph kendi vector'üne sahip → semantic dilution azalır
  - Title + subtitle prefix her chunk'ta (bağlam taşıyıcı)
  - Token count: heuristik (whitespace split * 1.3) — tiktoken yok
    Türkçe için ortalama ~%5 sapma kabul edilir

Output: list[ChunkRecord] — caller article_chunks tablosuna persist eder.

Anti-pattern (HARD STOP):
  - Boş chunk üretilmez
  - chunk_index sıralı + unique per article (DB UNIQUE constraint var)

Migration note:
  - Mevcut 109K chunk re-chunk gerekir (Faz 1 PR'da rechunk_articles celery
    task tetiklenir)
  - Embedding cost ~$50 (109K × bge-m3 NIM tier — kabul edilebilir)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Heuristic token coefficient — Türkçe word ≈ 1.3 token (rough average).
TR_TOKEN_COEFFICIENT = 1.3

# Default chunk parametreleri — #652 Faz 1 (RAGFlow tier):
#   Önceden: target=500, max=900, min=200, overlap=80
#   Yeni:    target=256, max=384, min=100, overlap=64
# Niş bilgi (hakem isimleri, % rakamı, kişi sözü) artık küçük chunks'larda
# kendi semantic uzayında ayrı durur → cosine sim dilution azalır.
DEFAULT_TARGET_TOKENS = 256
DEFAULT_MAX_TOKENS = 384
DEFAULT_MIN_TOKENS = 100
DEFAULT_OVERLAP_TOKENS = 64

# Microchunk parametreleri (#767 — Adım 1: 2-level chunking).
# Macro chunks (256-400 token) arama için fazla geniş — niş bilgi (sayı, %,
# kişi adı 1-2 cümlede gömülü) chunk skorunda dilute oluyor. Microchunks
# (128-200 token) arama indeksi olarak kullanılır, parent macro LLM context.
DEFAULT_MICRO_TARGET_TOKENS = 128
DEFAULT_MICRO_MAX_TOKENS = 200
DEFAULT_MICRO_MIN_TOKENS = 50


# Cümle ayırıcı regex — Türkçe punctuation desteği. Standart noktalama dışında
# Türkçe'de kullanılan üç nokta (…) ve emoji-aware boundary'leri korur.
# Kısaltmaların yanlış bölünmesini önlemek için sonrasında boşluk ZORUNLU.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÇĞİıÖŞÜ\"'“‘])")


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


def _split_sentences(paragraph: str) -> list[str]:
    """Paragraph → cümle listesi (#652 Faz 1 — sentence-window için).

    Türkçe noktalama desteği. Çok kısa parçalar (örn. madde işareti '-')
    bir önceki cümleye bağlanır.
    """
    if not paragraph:
        return []
    raw = _SENTENCE_SPLIT_RE.split(paragraph.strip())
    sentences: list[str] = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        # 3 char altı cümleler (madde işareti, fragment) önceki ile birleştir
        if len(s) < 3 and sentences:
            sentences[-1] = sentences[-1] + " " + s
        else:
            sentences.append(s)
    return sentences


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
    """Her chunk'ın başına 'BAŞLIK: …\\n\\nALT BAŞLIK: …\\n\\n' eklenir mi?"""


@dataclass
class MicrochunkConfig:
    """Microchunk parametreleri (#767 — 2-level chunking).

    Macro chunk (256-400 token) → split → microchunks (128-200 token).
    Microchunks arama indeksi olarak kullanılır; macro chunk LLM context'i
    olarak parent-doc merge ile döner. `chunker.micro_*` settings runtime
    tunable.
    """

    target_tokens: int = DEFAULT_MICRO_TARGET_TOKENS
    max_tokens: int = DEFAULT_MICRO_MAX_TOKENS
    min_tokens: int = DEFAULT_MICRO_MIN_TOKENS

    title_prefix: bool = True
    """Microchunk başına da macro chunk başlık prefix'i eklenir mi?"""


def _make_prefix(title: str | None, subtitle: str | None) -> str:
    """Chunk prefix string'i oluştur (bağlam için)."""
    parts: list[str] = []
    if title:
        parts.append(f"BAŞLIK: {title.strip()}")
    if subtitle:
        parts.append(f"ALT BAŞLIK: {subtitle.strip()}")
    return "\n\n".join(parts) + ("\n\n" if parts else "")


def _flush_window(
    sentences: list[str],
    chunks: list[list[str]],
    *,
    cfg: ChunkingConfig,
) -> None:
    """Mevcut sentence window'unu chunks listesine push et."""
    if sentences:
        chunks.append(list(sentences))


def microchunk_text(
    macro_chunk_text: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    config: MicrochunkConfig | None = None,
) -> list[ChunkRecord]:
    """Macro chunk text'ini microchunk'lara böl (#767 Adım 1).

    Strateji:
      - Macro chunk genelde "BAŞLIK: ...\\n\\nALT BAŞLIK: ...\\n\\n<body>"
        formatında — title/subtitle prefix'i ayır, body'yi cümlelere böl
      - Sentence-window pack ile micro target_tokens (128) hedefli pack
      - Title/subtitle prefix opsiyonel olarak her micro'ya eklenir
      - Tek başına ÇOK kısa macro (< micro_min_tokens) → tek microchunk olarak kalır

    Output: chunk_index 0-based, parent macro'nun çocukları.
    """
    cfg = config or MicrochunkConfig()
    if not macro_chunk_text or not macro_chunk_text.strip():
        return []

    # Prefix'i ayır (varsa) — yeniden eklemek için
    text_body = macro_chunk_text
    detected_prefix = ""
    if cfg.title_prefix:
        # Macro chunk_text örnek: "BAŞLIK: ...\n\nALT BAŞLIK: ...\n\n<body>"
        # ya da "BAŞLIK: ...\n\n<body>" — \n\n ile ilk 2 line'ı ayır
        lines = macro_chunk_text.split("\n\n", 2)
        prefix_parts: list[str] = []
        body_start_idx = 0
        for i, line in enumerate(lines[:2]):
            if line.startswith("BAŞLIK:") or line.startswith("ALT BAŞLIK:"):
                prefix_parts.append(line)
                body_start_idx = i + 1
            else:
                break
        if prefix_parts:
            detected_prefix = "\n\n".join(prefix_parts) + "\n\n"
            text_body = "\n\n".join(lines[body_start_idx:])

    # Title/subtitle parametre olarak geldiyse onu kullan (override)
    if title or subtitle:
        detected_prefix = _make_prefix(title, subtitle) if cfg.title_prefix else ""

    if not text_body.strip():
        return []

    # Body'yi cümlelere böl
    paragraphs = _split_paragraphs(text_body) or [text_body]
    all_sentences: list[str] = []
    for p in paragraphs:
        all_sentences.extend(_split_sentences(p))

    if not all_sentences:
        return []

    # Sentence-window pack — micro target
    chunks: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in all_sentences:
        s_tokens = estimate_tokens(sentence)
        # Tek başına çok uzun cümle → kabul (max_tokens'ı aşar)
        if s_tokens > cfg.max_tokens:
            if current:
                chunks.append(list(current))
                current = []
                current_tokens = 0
            chunks.append([sentence])
            continue

        if current_tokens + s_tokens > cfg.target_tokens and current_tokens >= cfg.min_tokens:
            chunks.append(list(current))
            current = []
            current_tokens = 0

        if current_tokens + s_tokens > cfg.max_tokens:
            chunks.append(list(current))
            current = []
            current_tokens = 0

        current.append(sentence)
        current_tokens += s_tokens

    if current:
        # min_tokens altında ise önceki micro'ya birleştir (yetim micro yok)
        if current_tokens < cfg.min_tokens and chunks:
            chunks[-1].extend(current)
        else:
            chunks.append(current)

    # Çok kısa macro (1 cümle) → tek microchunk olarak kalır
    if not chunks and all_sentences:
        chunks = [all_sentences]

    records: list[ChunkRecord] = []
    for idx, sents in enumerate(chunks):
        body = " ".join(sents).strip()
        full_text = (detected_prefix + body).strip()
        records.append(
            ChunkRecord(
                chunk_index=idx,
                chunk_text=full_text,
                token_count=estimate_tokens(full_text),
            )
        )

    return records


def chunk_text(
    text: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    config: ChunkingConfig | None = None,
) -> list[ChunkRecord]:
    """clean_text → chunk listesi (#652 Faz 1 — sentence-window).

    Strateji:
      1. Paragraflara böl
      2. Her paragraph içinde cümlelere böl (sliding sentence window)
      3. Window'a cümle ekle, target_tokens'a yaklaşırken yeni window aç
      4. min_tokens altında bittiyse bir sonraki paragraph'a taşır
      5. Overlap: son window'un son N token'ını yeni window'a prefix'le
      6. Title + subtitle prefix HER chunk'a (LLM context)

    Niş bilgi (hakem isimleri, % rakamı, kişi sözü) daha küçük chunks'lar
    sayesinde her chunk'ta dominant semantic vector'e sahip — cosine sim
    sorgu vector'üne yakın hale gelir.
    """
    cfg = config or ChunkingConfig()
    if not text or not text.strip():
        return []

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    prefix = _make_prefix(title, subtitle) if cfg.title_prefix else ""

    # Tüm paragraph'ları cümlelere düzleştir (article-wide sentence stream)
    all_sentences: list[str] = []
    for p in paragraphs:
        # Tek cümlelik kısa paragraph (başlık benzeri) tek cümle olarak kalır
        sentences = _split_sentences(p)
        all_sentences.extend(sentences)

    if not all_sentences:
        return []

    # Sentence-window pack:
    # Her chunk için cümle ekle → target_tokens'a yaklaşırken kapat.
    # max_tokens ZORUNLU split (tek bir cümle target'i aşıyorsa kabul).
    chunks: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in all_sentences:
        s_tokens = estimate_tokens(sentence)

        # Tek başına çok büyük cümle → kabul (max_tokens'ı aşar ama kaçınılmaz)
        # Mevcut window'u kapat, bu cümleyi kendi window'unda gönder
        if s_tokens > cfg.max_tokens:
            if current:
                _flush_window(current, chunks, cfg=cfg)
                current = []
                current_tokens = 0
            chunks.append([sentence])
            continue

        # Window dolduğunda flush
        # Hedef: target_tokens, hard cap: max_tokens
        if current_tokens + s_tokens > cfg.target_tokens and current_tokens >= cfg.min_tokens:
            _flush_window(current, chunks, cfg=cfg)
            current = []
            current_tokens = 0

        # Hard cap kontrol (target overshoot ama min_tokens altındayken)
        if current_tokens + s_tokens > cfg.max_tokens:
            _flush_window(current, chunks, cfg=cfg)
            current = []
            current_tokens = 0

        current.append(sentence)
        current_tokens += s_tokens

    # Son window
    if current:
        # min_tokens altında ise önceki chunks varsa birleştir, yoksa kabul
        last_tokens = current_tokens
        if last_tokens < cfg.min_tokens and chunks:
            # Önceki window'a ekle
            chunks[-1].extend(current)
        else:
            chunks.append(current)

    # Çok kısa article (1 sentence, < min_tokens) — yine de tek chunk üret
    # (boş dönmek istemiyoruz; caller min_tokens guard yapar)
    if not chunks and all_sentences:
        chunks = [all_sentences]

    # Overlap + prefix uygulayarak ChunkRecord listesi üret
    records: list[ChunkRecord] = []
    prev_words: list[str] = []
    for idx, sentences_in_chunk in enumerate(chunks):
        body = " ".join(sentences_in_chunk)
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
