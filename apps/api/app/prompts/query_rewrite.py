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
- ÖNCE AYIR — soru KONUYA mı, ASİSTANA/SİSTEME mi? Son mesaj asistanın \
KENDİSİNE yönelikse ("sen kimsin", "senin yeteneklerin/amacın ne", \
"nasılsın", "ne yapabilirsin") ya da konuşmanın KENDİSİ hakkındaysa \
("az önce ne dedin", "neden öyle dedin", "özetle") — bu bir konu \
follow-up'ı DEĞİLDİR. "sen/senin/sana"yı konuşmanın öznesine ASLA \
çözme; mesajı OLDUĞU GİBİ bırak (downstream sistem kimlik/meta olarak \
ele alır). Sadece konunun KENDİSİ (kişi/olay/şey) hakkındaki atıfları \
çöz.
- Son mesaj önceki konuşmadaki KONUYA atıf içeriyorsa (zamir: "o", "bu", \
"onun"; veya "ilk bölüm", "daha detaylı açıkla", "kaç yıl önce", \
"peki ya X", "adı neydi", "konusu neydi" gibi) — atıf edilen özneyi \
sorguya ekle.
- KRİTİK — REFERANS YAKINLIĞI: Atıf/zamir konuşmanın EN GENİŞ konusuna \
değil, EN SON odaklanılan SPESİFİK özneye işaret eder. Konuşma bir \
alt-konuya daraldıysa, takip eden atıflar o alt-konuyu izler. \
(İlke: en yakın antecedent — en son netleşen spesifik özne.)
- DISAMBIGUATION: Entity birden çok şeye gelebiliyorsa (ör. aynı ad \
hem dizi hem güncel proje) ayırt edici bağlamı ekle (hangi dizi/kişi/yıl). \
Geçmişte hangi anlamda kullanıldıysa onu koru.
- Konuşma uzasa bile (3+, 5+ tur) her turda en son spesifik özneyi izle; \
bağlamı kaybetme.
- Müstakil/yeni bir soruysa neredeyse aynen bırak (minimal dokunuş).
- Çıktı SADECE arama sorgusu: tek satır, Türkçe, açıklama YOK, tırnak YOK.
- Sorgu kısa ve öz olsun (haber/Wikipedia araması için entity-odaklı).

ÖRNEK MANTIK (kalıp değil, ilke):
- Geçmiş "X dizisi ne zaman" + "ilk bölümün adı neydi" → "X dizisi ilk bölüm adı"
- Sonra "konusu neydi" → (en son özne: o ilk bölüm) → "X dizisi <ilk bölüm adı> konusu"
- Aynı-ad çakışması: geçmiş bir DİZİ hakkındaysa, son mesaj "konusu" → \
  dizi bağlamını koru (güncel başka-anlam projesine kayma)
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
