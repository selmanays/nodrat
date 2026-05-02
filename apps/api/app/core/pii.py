"""PII Redaction Module — KRİTİK güvenlik bileşeni.

Her LLM provider çağrısı öncesi prompt payload'undan kişisel veriyi
otomatik temizler. Avukat ön-görüşü gereği zorunlu (docs/legal/opinion-integration.md §3.1).

KAPSAM:
    - email                 → [email_redacted]
    - Türk telefon          → [phone_redacted]
    - IP adresi             → [ip_redacted]
    - TC kimlik (luhn)      → [id_redacted]
    - IBAN TR               → [iban_redacted]
    - UUID                  → [ref_redacted]

NOT: Bu modül BLOCKER seviyesindedir. Her LLM çağrısı yapan kod path'i
bu modülden geçmeli. Production'da bypass YOKTUR.

Risk: docs/strategy/risk-register.md R-LGL-01 (KVKK), R-LGL-11 (yurt dışı transfer)
Test: tests/unit/test_pii_redaction.py — ≥%99 effectiveness hedef (#45)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final


# Pre-compiled regex patterns (performance + readability)
EMAIL_PATTERN: Final = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# TR phone: +90, 0 ile başlayan veya direkt 10 hane
# Separators: space, hyphen, parens (yaygın yazım biçimleri)
# #235 — start boundary (?<!\d) zorunlu: 11-hane TC/hesap no içindeki 10-hane
# subsequence false-positive olarak telefon olarak yakalanıyordu.
TR_PHONE_PATTERN: Final = re.compile(
    r"(?<!\d)(?:\+90|0)?[\s\-]*\(?\d{3}\)?[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"
)

# IPv4 (basic)
IP_PATTERN: Final = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)

# TC kimlik: 11 hane (luhn-like check ayrıca yapılır)
TC_PATTERN: Final = re.compile(r"\b\d{11}\b")

# IBAN TR: TR + 24 hane (toplam 26 char)
# Boşluklu format de desteklenir: "TR33 0006 1005 1978 6457 8413 26"
# Toplam 24 hane garanti edilir (ara boşluklar ihtiyari).
IBAN_TR_PATTERN: Final = re.compile(
    r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b|\bTR\d{24}\b"
)

# UUID v4 (lowercase + uppercase)
UUID_PATTERN: Final = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


# Replacement tokens — LLM'e gidecek
REPLACEMENT_EMAIL: Final = "[email_redacted]"
REPLACEMENT_PHONE: Final = "[phone_redacted]"
REPLACEMENT_IP: Final = "[ip_redacted]"
REPLACEMENT_TC: Final = "[id_redacted]"
REPLACEMENT_IBAN: Final = "[iban_redacted]"
REPLACEMENT_UUID: Final = "[ref_redacted]"


@dataclass
class RedactionResult:
    """Redaction sonucu — telemetri ve audit için."""

    text: str
    """Redact edilmiş metin (LLM'e gidecek)."""

    counts: dict[str, int] = field(default_factory=dict)
    """Tip başına redact sayısı: {"email": 2, "phone": 1, ...}"""

    @property
    def total_redactions(self) -> int:
        """Toplam redact edilen item sayısı."""
        return sum(self.counts.values())

    @property
    def has_pii(self) -> bool:
        """Herhangi PII tespit edildi mi?"""
        return self.total_redactions > 0


def is_valid_tc(candidate: str) -> bool:
    """Türk Kimlik No için Luhn-like algoritma kontrolü.

    11 hane + son hane checksum. False positive azaltır:
    sıradan 11 haneli sayılar (örn. fatura no) yanlışlıkla
    TC olarak işaretlenmesin.

    Algoritma:
        - 11 hane olmalı
        - İlk hane 0 olamaz
        - 10. hane = (1+3+5+7+9. haneler × 7 - 2+4+6+8. haneler) mod 10
        - 11. hane = ilk 10 hanenin toplamının mod 10'u
    """
    if len(candidate) != 11 or not candidate.isdigit():
        return False
    if candidate[0] == "0":
        return False

    digits = [int(d) for d in candidate]

    odd_sum = digits[0] + digits[2] + digits[4] + digits[6] + digits[8]
    even_sum = digits[1] + digits[3] + digits[5] + digits[7]

    digit_10 = (odd_sum * 7 - even_sum) % 10
    if digit_10 != digits[9]:
        return False

    digit_11 = sum(digits[:10]) % 10
    return digit_11 == digits[10]


def redact(text: str) -> RedactionResult:
    """Metinden PII'yi temizle.

    Pre-LLM call'da kullanılır. Tüm provider katmanında zorunlu.

    Args:
        text: Temizlenecek input metin (kullanıcı prompt'u, vb.)

    Returns:
        RedactionResult: temizlenmiş metin + tip-bazlı sayım

    Examples:
        >>> result = redact("Merhaba, email'im ahmet@example.com.")
        >>> result.text
        "Merhaba, email'im [email_redacted]."
        >>> result.counts
        {'email': 1}
    """
    counts: dict[str, int] = {
        "email": 0,
        "phone": 0,
        "ip": 0,
        "tc": 0,
        "iban": 0,
        "uuid": 0,
    }

    # 1. Email
    def _email_repl(m: re.Match[str]) -> str:
        counts["email"] += 1
        return REPLACEMENT_EMAIL

    redacted = EMAIL_PATTERN.sub(_email_repl, text)

    # 2. IBAN (TC'den önce — IBAN içinde 11 hane TC false-positive olabilir)
    def _iban_repl(m: re.Match[str]) -> str:
        counts["iban"] += 1
        return REPLACEMENT_IBAN

    redacted = IBAN_TR_PATTERN.sub(_iban_repl, redacted)

    # 3. UUID
    def _uuid_repl(m: re.Match[str]) -> str:
        counts["uuid"] += 1
        return REPLACEMENT_UUID

    redacted = UUID_PATTERN.sub(_uuid_repl, redacted)

    # 4. IP
    def _ip_repl(m: re.Match[str]) -> str:
        counts["ip"] += 1
        return REPLACEMENT_IP

    redacted = IP_PATTERN.sub(_ip_repl, redacted)

    # 5. TC kimlik (luhn validation)
    def _tc_repl(m: re.Match[str]) -> str:
        candidate = m.group(0)
        if is_valid_tc(candidate):
            counts["tc"] += 1
            return REPLACEMENT_TC
        return candidate  # Luhn fail: bırak (false positive azalt)

    redacted = TC_PATTERN.sub(_tc_repl, redacted)

    # 6. Türk telefon — en sona, IP/IBAN/UUID/TC'leri önce yakaladıktan sonra
    def _phone_repl(m: re.Match[str]) -> str:
        # Telefon en az 10 rakam, en fazla 13 (with +90)
        digits_only = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits_only) <= 13:
            counts["phone"] += 1
            return REPLACEMENT_PHONE
        return m.group(0)

    redacted = TR_PHONE_PATTERN.sub(_phone_repl, redacted)

    return RedactionResult(text=redacted, counts=counts)


def redact_messages(messages: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Chat messages listesindeki content alanlarını redact et.

    LLM API çağrısı için chat formatına uygun yardımcı.

    Args:
        messages: [{"role": "user", "content": "..."}, ...]

    Returns:
        (redacted_messages, total_counts)
    """
    redacted_messages: list[dict[str, str]] = []
    total_counts: dict[str, int] = {
        "email": 0,
        "phone": 0,
        "ip": 0,
        "tc": 0,
        "iban": 0,
        "uuid": 0,
    }

    for msg in messages:
        if "content" in msg and isinstance(msg["content"], str):
            result = redact(msg["content"])
            new_msg = {**msg, "content": result.text}
            for key, val in result.counts.items():
                total_counts[key] += val
            redacted_messages.append(new_msg)
        else:
            redacted_messages.append(msg)

    return redacted_messages, total_counts
