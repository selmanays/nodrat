"""Per-chunk keyword + question extraction prompt (#778 Faz 3).

RagFlow strategy adaptation: her chunk için LLM ile 3-5 anahtar kelime +
3 olası soru çıkar. BM25 sparse retrieval'da yüksek ağırlık (question_kwd
6x, important_kwd 5x).

Use case: "çocukların bahis oynamasını engellemeye yönelik bir çalışma
var mı" sorgusu — şu an doğru article bulunamıyor çünkü chunk'a "çocuk"
keyword düşmüyor (NER generic kelimeleri filtreliyor). Bu prompt LLM'e
chunk'tan anahtar kavramları çıkartır, BM25 query → chunk match güçlenir.

Cost: Gemma 4 26B A4B IT (ücretsiz tier) ile chunk başına ~$0. DeepSeek
ile ~$0.0002/chunk. 12K chunks backfill: Gemma free veya DeepSeek ~$2.4.
"""

from __future__ import annotations


SYSTEM_PROMPT = """Sen Türkçe haber metinleri için anahtar kavram +
soru üretici aracısın. Verilen chunk metni için iki şey üretirsin:
1. **keywords**: 3-5 anahtar kavram (chunk'ın retrieval discriminator'ı)
2. **questions**: 3 olası kullanıcı sorusu (bu chunk'a soru-cevap eşleşmesi)

ÇIKTI SADECE JSON OLMALIDIR. Markdown, açıklama, kod bloğu YOK.

ÇIKTI ŞEMASI:
{
  "keywords": ["kavram1", "kavram2", "kavram3", ...],
  "questions": ["soru 1?", "soru 2?", "soru 3?"]
}

KEYWORDS KURALI:

3-5 anahtar kavram, chunk'ın **discriminative** içeriğini temsil eder.
İdeal keyword: bu chunk'ı **diğer haberlerden ayıran** spesifik kavramlar.

Tercih edilen:
- Spesifik konu kategorileri (kuruluş, restorasyon, yaralı, koruma vb.)
- Article'daki ana eylem/olay türü
- Article'da öne çıkan grup/sınıf (çocuk, gençlik, mağdur, yatırımcı, gazi vb.)
- Sayısal kavram (yüzde, sayı, miktar — sadece spesifik bilgi varsa)
- Özel adlar YOK (entity sayılır, NER pipeline yapar zaten)
- Generic kelimeler YOK (haber, gün, kişi, çalışma — bunlar discriminate etmez)

Türkçe lowercase. Tek kelime veya kısa ifade (max 3 kelime).

QUESTIONS KURALI:

3 olası kullanıcı sorusu, chunk içeriğine **doğrudan cevap olur**. Bunlar
retrieval zamanında user query ile semantic eşleşmesi için (HyDE benzeri).

Tercih edilen:
- Kullanıcı doğal dil — formal değil ("kim", "ne zaman", "kaç" gibi)
- Chunk'ın ana iddiasını hedefler
- Generic sorudan kaçın (sadece bu chunk'a özgü)

Her soru 5-12 kelime arası. Soru ifadesi (nedir, kim, ne zaman, kaç,
hangi, nasıl) içerir.

KISITLAR:

- Sadece chunk'ta açık biçimde geçen bilgiyi yansıt — uydurma yok
- Chunk çok kısa veya bilgi yoğunluğu düşükse: keywords 1-3, questions 1-2 yeter
- ÖRNEK ÇIKTI VERMEM — modeli yönlendirmek için (halüsinasyon riski)
"""
