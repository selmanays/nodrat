"""Post-generation answer quality detection (#819 Faz 2 follow-up).

Plan: /Users/selmanay/.claude/plans/nerdi-in-ekilde-faz-2-unified-nebula.md

LLM cevabı kendisi "kaynaklarda yok" tipi refusal döndürdüğünde,
Wikipedia teklif etmeyi tetikleyen detection mekanizması.

Bu **deterministik bir sinyal** — chat_answer system prompt'unda LLM'e
"Veri yetersizliğinde içerik üretme. Kaynakta yoksa 'Verilen kaynaklarda
bu bilgi yer almıyor' de" kuralı verilmiş (apps/api/app/prompts/chat_answer.py).
LLM bu kuralı izlediği için refusal çıktısı Türkçe'de yapısal olarak tahmin
edilebilir.

NOT (#818 mimari fix mirası):
- Pre-generation confidence skoru (5-signal) "kaynaklarda konu geçiyor mu?"
  sorusunu cevaplar — semantic + entity hit yüksekse skor yüksek olabilir
- Ama "konu detayı (yaş, tarih, miktar) var mı?" sorusu pre-gen yakalanamaz
- LLM cevap üretirken bu detay yokluğunu fark eder ve refusal yapar
- Bu modül o refusal'ı yakalar → retroactively Wikipedia teklif eder

Pattern listesi `chat_answer.py:PROMPT_VERSION` ile bağlantılı — prompt
yeniden yazılırsa bu liste güncellenmelidir (bağımlılık bilinçli).

Test: apps/api/tests/unit/test_answer_quality.py
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# chat_answer prompt'undaki kanonik refusal pattern'ı:
#   "Verilen kaynaklarda bu bilgi yer almıyor"
# LLM bu varyantları üretir — Türkçe için yapısal olarak deterministik.
# Her pattern lowercase + accent-insensitive match için normalize edilir.
_REFUSAL_REGEX_PATTERNS: tuple[str, ...] = (
    # Birincil pattern (prompt'tan direkt)
    r"verilen\s+kaynaklarda\b.*?(yer\s+almıyor|bulunmuyor|yok|mevcut\s+değil|içermiyor)",
    # Genel "kaynak" + olumsuzluk yakınında
    r"kaynaklarda\b.*?\b(yer\s+almıyor|bulunmuyor|mevcut\s+değil|içermiyor)",
    r"kaynaklarda\b.*?\b(bilgi|veri|detay|bilgisi)\b.*?\byok\b",
    r"kaynaklarda\b.*?\bbilgi\s+bulunmuyor",
    # Direkt refusal ifadeleri
    r"bilgi\s+(bulun(mu|amı)yor|mevcut\s+değil|yer\s+almıyor)",
    r"yeterli\s+(bilgi|veri|kaynak)\s+(yok|bulunmuyor|mevcut\s+değil)",
    r"elimde\s+(bu\s+)?(bilgi|veri|yeterli)\s*(yok|bulunmuyor)",
    r"hakkında\s+(bilgi|veri|detay)\s+(yok|bulunmuyor|içermiyor)",
)

# Pre-compiled regexler (process-local, thread-safe)
_COMPILED_REFUSAL_PATTERNS = tuple(
    re.compile(p, flags=re.IGNORECASE | re.DOTALL) for p in _REFUSAL_REGEX_PATTERNS
)


def is_answer_refusal(answer_text: str) -> tuple[bool, str | None]:
    """Cevap 'kaynaklarda yok' tipi refusal mı?

    Args:
        answer_text: LLM tarafından üretilmiş cevap (post-generation).

    Returns:
        (True, matched_pattern) eğer refusal detected
        (False, None) aksi halde

    Detection mantığı:
        chat_answer prompt'unda LLM'e "Veri yetersizliğinde içerik üretme,
        'Verilen kaynaklarda bu bilgi yer almıyor' de" kuralı var. LLM bu
        kurala göre refusal'ı yapısal yazıyor — regex'le yakalanır.

    Yan etki yok — pure function.
    """
    if not answer_text:
        return False, None

    # Türkçe karakterleri normalize:
    # - lowercase
    # - "İ".lower() Python'da "i̇" (combining dot above) üretir → strip
    # - boşluk collapse
    lowered = answer_text.lower().replace("̇", "")
    normalized = " ".join(lowered.split())

    for i, pattern in enumerate(_COMPILED_REFUSAL_PATTERNS):
        match = pattern.search(normalized)
        if match:
            logger.debug(
                "answer refusal detected (pattern #%d): %s",
                i, match.group(0)[:100],
            )
            return True, _REFUSAL_REGEX_PATTERNS[i]

    return False, None


__all__ = ["is_answer_refusal"]
