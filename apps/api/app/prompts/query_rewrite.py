"""Conversational query rewrite — follow-up → standalone (#833).

Plan: Perplexity / LangChain ConversationalRetrievalChain "condense
question" adımı. Planner SYSTEM_PROMPT'unun preserve-first kuralı
follow-up rewriting'i engelliyor (plan_input'a talimat gömmek çalışmadı —
#832 production'da kanıtlandı: "ilk bölümün adı neydi" → planner Stargate
bağlamını ignore edip "Daha 17 dizisi" getirdi).

Çözüm: planner'dan ÖNCE ayrı, izole, hafif bir LLM call. Konuşma
geçmişi + son mesaj → tek başına anlaşılır arama sorgusu. Bu standalone
sorgu planner + retrieval'a temiz gider (preserve-first kuralı standalone
query'de zaten doğru çalışır).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


REWRITE_SYSTEM_PROMPT = """Sen bir arama sorgusu yeniden yazıcısısın. \
Görevin: konuşma geçmişi + kullanıcının son mesajına bakıp, son mesajı \
TEK BAŞINA (standalone) anlaşılır bir arama sorgusuna çevirmek.

KURALLAR:
- Son mesaj önceki konuşmaya atıf içeriyorsa (zamir: "o", "bu", "onun"; \
veya "ilk bölüm", "daha detaylı açıkla", "kaç yıl önce", "peki ya X", \
"adı neydi" gibi) — atıf edilen ASIL konu/entity'yi açıkça sorguya ekle.
- Müstakil/yeni bir soruysa neredeyse aynen bırak (minimal dokunuş).
- Çıktı SADECE arama sorgusu: tek satır, Türkçe, açıklama YOK, tırnak YOK.
- Sorgu kısa ve öz olsun (haber/Wikipedia araması için entity-odaklı).

ÖRNEK MANTIK (kalıp değil, ilke):
- Geçmiş "X dizisi ne zaman yayınlandı" + son mesaj "ilk bölümün adı neydi"
  → "X dizisi ilk bölüm adı"
- Geçmiş "Y konusu" + son mesaj "daha detaylı açıkla" → "Y detayları"
"""


def build_rewrite_user_prompt(history: str, message: str) -> str:
    return (
        f"Konuşma geçmişi:\n{history}\n\n"
        f"Kullanıcının son mesajı: {message}\n\n"
        f"Standalone arama sorgusu:"
    )


async def condense_followup_query(
    provider,
    history: str,
    message: str,
    *,
    model: str | None = None,
) -> str | None:
    """Follow-up mesajı standalone arama sorgusuna çevir.

    Args:
        provider: chat-capable ModelProvider (generate_text).
        history: _recent_conversation_context çıktısı (content + kaynak özeti).
        message: kullanıcının ham son mesajı.

    Returns:
        Standalone sorgu (tek satır) veya None (hata/boş → caller ham
        mesaja düşer).
    """
    from app.providers.base import Message as ProviderMessage

    if not history or not message:
        return None
    try:
        result = await provider.generate_text(
            messages=[
                ProviderMessage(role="system", content=REWRITE_SYSTEM_PROMPT),
                ProviderMessage(
                    role="user",
                    content=build_rewrite_user_prompt(history, message),
                ),
            ],
            model=model,
            max_tokens=80,
            temperature=0.3,
        )
        text = (result.text or "").strip().strip('"').strip()
        # İlk satırı al (LLM bazen açıklama ekler)
        first_line = text.split("\n", 1)[0].strip()
        if not first_line or len(first_line) > 300:
            return None
        return first_line
    except Exception as exc:
        logger.warning("condense_followup_query failed: %s", exc)
        return None


__all__ = ["condense_followup_query", "REWRITE_SYSTEM_PROMPT"]
