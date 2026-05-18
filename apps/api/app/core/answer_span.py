"""Answer span extraction — niş "kaç X / yüzde kaç" sorgu cevapları için
chunk içi numerical/named span çıkarımı (#710 Faz 7c Aşama 1).

Telemetri amaçlı — diagnostic tooling. Aşama 2'de bu helper query-side eşleştirme
için kullanılacak (numerical span × query pattern boost).

Pattern'lar Faz 7a NER prompt'undaki numerical entity tanımıyla uyumlu
(workers/tasks/entities.py _NER_PROMPT_SYSTEM number examples).
"""

from __future__ import annotations

import re

# Yüzde/oran (TR + EN)
_PCT = re.compile(
    r"(?:yüzde\s+\d+(?:[,\.]\d+)?|%\s*\d+(?:[,\.]\d+)?|\d+(?:[,\.]\d+)?\s*%)",
    flags=re.IGNORECASE,
)

# Kesir (1/3, 2/5)
_FRAC = re.compile(r"\b\d+/\d+\b")

# Para (TL, dolar, avro, drahmi vb.)
_MONEY = re.compile(
    r"\d+(?:[,\.]\d+)?\s*(?:milyon|milyar|bin)?\s*"
    r"(?:tl|dolar|avro|euro|drahmi|usd|tlrl|sterlin|yen|yuan)",
    flags=re.IGNORECASE,
)

# Adet/miktar (Türkçe miktar birimleri).
# Arada bir modifier kelimesi olabilir: "3 ana kent", "21 farklı ülke", "5 büyük şehir".
# Pattern: \d+ [optional modifier] unit
_QUANTITY = re.compile(
    r"\b\d+(?:[,\.]\d+)?\s*"
    r"(?:[a-zçğıöşü]+\s+)?"  # optional modifier (TR lowercase word, e.g. "ana", "büyük", "farklı")
    r"(?:ülke|kent|şehir|ilçe|kişi|asker|metre|km|kilometre|hektar|"
    r"fide|fidan|gün|saat|dakika|hafta|ay|yıl|sn|saniye|"
    r"skor|puan|gol|sayı|gönderi|tweet|paylaşım|maç)\b",
    flags=re.IGNORECASE,
)

# Skor (16-14, 84-82) — sporda yaygın
_SCORE = re.compile(r"\b\d{1,3}-\d{1,3}\b")

# Sıralı (30. hafta, 2. yarı)
_ORDINAL = re.compile(
    r"\b\d+\.\s*(?:hafta|gün|ay|yıl|yarı|tur|sezon|dakika)\b", flags=re.IGNORECASE
)

# Tarihsel yıl (MÖ 408, 1980, 2026 — niş tarih)
_HISTORICAL_YEAR = re.compile(r"\b(?:MÖ|MS)\s*\d{1,4}\b")


_PATTERNS = (
    _PCT,
    _FRAC,
    _MONEY,
    _QUANTITY,
    _SCORE,
    _ORDINAL,
    _HISTORICAL_YEAR,
)


def extract_numerical_spans(text: str, *, max_per_pattern: int = 5) -> list[str]:
    """Chunk text'inden numerical span listesi çıkar (deduplicated + ordered).

    Args:
        text: chunk_text veya cleaned text
        max_per_pattern: her pattern için max match (noise koruması)

    Returns:
        Unique span'lar, görünme sırasında. Boş text → [].
    """
    if not text:
        return []

    seen: set[str] = set()
    out: list[str] = []
    for pat in _PATTERNS:
        matches = list(pat.finditer(text))[:max_per_pattern]
        for m in matches:
            span = m.group(0).strip()
            # Lowercase normalize for dedup; preserve original casing in output
            key = " ".join(span.lower().split())
            if key not in seen and 2 <= len(span) <= 60:
                seen.add(key)
                out.append(span)
    return out


__all__ = ["extract_numerical_spans"]
