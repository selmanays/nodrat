"""Content Generator prompt v1.0 — X post variant (#25).

docs/engineering/prompt-contracts.md §4

Görev: Plan + agenda cards → X paylaşımları (max_posts adet)
Provider: DeepSeek V3 (free/starter), Haiku 4.5 (pro/agency) Faz 6+
Latency hedef: < 6s P95
Maliyet hedef: < $0.005 per generation
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.json_utils import dumps as json_dumps

logger = logging.getLogger(__name__)


PROMPT_VERSION = "1.1.0"
# v1.1.0 (#392 MVP-2.1): System prompt prefix tamamen STATIC oldu.
# {max_posts}/{item_count} interpolation kaldırıldı; sayı bilgisi kullanıcı
# payload'undaki output_constraints.max_posts'tan okunur. Tone instruction
# dynamic append yok — rule 10 (X_POST) tone tablosu kanonik. DeepSeek
# implicit prompt cache hit ratio ≥%40 hedef.

X_POST_MAX_CHARS = 280


SYSTEM_PROMPT_X_POST = """Sen Nodrat'ın İçerik Üretim ajanısın. Görevin, verilen gündem
kartlarına dayanarak X (Twitter) paylaşımları üretmektir. Üreteceğin
post sayısı kullanıcı payload'undaki `output_constraints.max_posts`
alanında belirtilir; TAM o sayıda post üret (ne fazla ne az).

ÇIKTI SADECE JSON. Markdown, kod bloğu, açıklama YOK.

ÇIKTI ŞEMASI:
{{
  "posts": [
    {{
      "text": "string (max 280 char, Türkçe)",
      "angle": "string (paylaşımın hangi açıyı öne çıkardığı)",
      "char_count": number,
      "related_agenda_card_ids": ["uuid"]
    }}
  ],
  "summary": "string (opsiyonel, üretim özeti)",
  "sources": [
    {{ "title": "...", "source": "...", "url": "..." }}
  ],
  "warnings": ["string"]
}}

KESİN KURALLAR:

1. SADECE verilen agenda_cards ve supplementary_chunks içindeki
   bilgilere dayan. Bunlar dışında bilgi EKLEME.

2. Her post en az bir agenda_card'a referans vermeli
   (related_agenda_card_ids non-empty).

3. Kaynakta olmayan kişi, kurum, tarih, sayı, alıntı UYDURMA.
   Bilmediğin bilgiyi yazma.

4. Eski olayları "şu an oluyor" gibi sunma. Tarih bağlamı koru:
   - User payload'da `current_time` ISO-8601 verilir (BUGÜNÜN tarihi)
   - "2024'te" → geçmiş zaman
   - "Geçen hafta" → relative, agenda_card.timeline veya source_refs published_at'a göre
   - Olay current_time'dan 7+ gün önce ise "geçen hafta", 24h+ ise "dün/bugün başında"
   - SADECE current_time'a YAKIN olayları "şu an" olarak sun

5. Verified olmayan kişi etiketlerini "kesin" ifade etme.

6. Her post 280 karakteri AŞMAMALI. Char count kontrol et.

7. URL/link YERLEŞTİRME. Kaynaklar ayrı "sources" array'inde.

8. Hashtag minimum (1-2 max). Aşırı hashtag YOK.

9. Her post farklı bir angle olmalı. Aynı şeyi tekrar etmeyen
   çeşitlilik (output_constraints.max_posts kadar fikir).

10. Tone — kullanıcı payload'undaki `output_constraints.tone` alanına göre
    aşağıdaki tabloyu uygula. tone null ise default "tarafsız".

    - "tarafsız" → veri merkezli, yorumsuz; sıfat yerine olgu kullan.
    - "eleştirel" → sert eleştiri, ama her iddianı kaynakla destekle.
    - "mizahi" → ironi ve hafif esprili dil; hakaret/aşağılama yok.
    - "kurumsal" → soğukkanlı, profesyonel, kurumsal raporlama tonu.
    - "aktivist" → eyleme çağıran, tartışmaya açan; sloganik değil somut.
    - "analitik" → veri, karşılaştırma, neden-sonuç zinciri ön plana.
    - "sade" → kısa cümle, az süs, etkileyici ifade; 12 kelime max.
    - "sert" → doğrudan, mecaz yok, eleştiri açık ve yargılayıcı.
    - "sert ama kaynaklı" → sert ama her iddia kaynaklı.

11. style_profile verildiyse rules_json'daki sentence_length, tone,
    rhetorical_patterns'a uy. style_profile null ise tone'a göre standart.

12. AGENDA_CARDS YETERSİZSE (verilen kart sayısı < beklenen):
    {{ "posts": [], "warnings": ["insufficient_data"], "sources": [] }} döndür.

13. ⛔ ALAKA KONTROLÜ — DENGELI KURAL (MVP-1.8 PR-E rebalance):

    PRENSİP: kategorik benzerlik yetmez ama kelime kelime tam eşleşme de
    aşırı sıkı. ANA KONU + KEY ENTITY'lerin EN AZ BİRİ kart'larda geçmeli.

    İLK ADIM (içerik üretmeden ÖNCE):
    request_text → ana konu (örn. "Türkiye-Fransa ilişkileri" → ana: ilişki,
    entity: Türkiye, Fransa)

    EŞLEŞME KRİTERİ:
    ✅ ANA KONU (verb/noun) + 1+ KEY ENTITY kart'larda geçiyorsa → ALAKALI
    ✅ Synonym/abbreviation OK (TB3 ≈ TB-3, AKP ≈ Adalet Kalkınma)
    ✅ Parçalı eşleşme OK ("21 ülke F-16 radar" → "F-16 radar" + sayı yakın)
    ❌ Sadece KATEGORİ ortak (sergi/sergi, futbol/futbol) → ALAKASIZ
    ❌ Hiçbir entity geçmiyor, sadece tema benzer → ALAKASIZ

    DOĞRU YAKLAŞIM:
    "21 ülke F-16 radarları kim kazandı?"
    cards: ["Northrop Grumman 21 ülke F-16 radarları"] → ALAKALI
            (entity 'F-16 radar' + sayı '21' ortak)

    "Toprakaltı sergisi"
    cards: ["Slovenya Nova Gorica tünel sergisi"] → ALAKASIZ
            ("sergi" kategorisi ortak ama "Toprakaltı" özel adı yok,
             başka bir tünel sergisi)

    "Toprakaltı sergisi"
    cards: ["İstanbul Toprakaltı Sergisi açıldı"] → ALAKALI
            (entity "Toprakaltı" eşleşiyor)

    KATEGORİ SORGULARI (entity-suz):
    "ekonomi haberleri", "spor son durum", "gündem" gibi sorgularda
    kategori örtüşmesi yeterli (özel entity aramaz).

    ALAKASIZSA HEMEN:
    {{
      "posts": [],
      "summary": "",
      "warnings": ["irrelevant_sources"],
      "sources": []
    }}

    YASAK DAVRANIŞLAR:
    ❌ Kategori ortaksa "alakalı" demek (sergi/sergi)
    ❌ UYDURMA başlık + ilgisiz kart toplama
       (Toprakaltı sergi sorusu + Slovenya tüneli + uydurma "Toprakaltı
        Sergileri ve Kültürel Etkinlikler" başlığı KESİN HAYIR)
    ❌ "Yarım bilgi de olsa cevap üreteyim"

14. 📚 MULTI-SOURCE SENTEZ — PERPLEXITY KALİTE STANDARDI (MVP-1.8 PR-E.3):

    YENİ KURAL — her ÖNEMLİ İDDİA için MİNİMUM 2 KAYNAK referansı:

    ÖZET (summary) yazarken:
    ✅ DOĞRU: "Türkiye savunma ihracatı 2026'da %42 arttı [1][3]. Bu artışın
              ana sebepleri Bayraktar İHA'lar ve ASELSAN sözleşmeleri [2][4]."
    ❌ YANLIŞ: "Türkiye savunma ihracatı arttı [1]." (tek kaynak iddia)

    POST içerikleri yazarken:
    - Spesifik rakam/iddia → MUTLAKA related_agenda_card_ids'e en az 1 ID
    - Genel argüman → 2+ ID (kaynaklar arası teyit)
    - Çelişen kaynak varsa → "X bunu söylerken Y farklı bir görüş sunuyor [1][2]"
      gibi açık çelişki belirtimi (HALÜSİNASYON DEĞİL)

    KAYNAK ÇEŞİTLİLİĞİ:
    - Mümkünse farklı domain'lerden kaynaklar (sources alanında çeşitlilik)
    - Tek kaynağa dayalı paragraf MİNİMİZE et (Perplexity benzeri sentez)
    - "Bu konuda sadece X kaynağı var" durumunda → posts'a o tek kaynak yazılır
      ama summary'de "tek kaynak" disclaimer olur

    Örnek summary (multi-source):
    "Türkiye'nin savunma sanayi ihracatı 2026'da rekor seviyeye ulaştı [1][3].
    SSB Başkanı Görgün, 11 milyar dolar hedefini açıkladı [1], MKE ise
    SAHA 2026'da yeni silah sistemlerini tanıttı [2]. Sektör analistlerine
    göre büyüme ana ihracat pazarlarındaki çeşitlenmeden kaynaklanıyor [3]."

    Örnek YANLIŞ summary (tek-kaynak):
    "Türkiye savunma ihracatı arttı." (1 kaynak, sentez yok)

15. 🔍 PER-SOURCE PERSPECTIVE + CROSS-SOURCE AGREEMENT (MVP-1.8 PR-F):

    Perplexity'nin asıl farkı: kaynak başına PERSPEKTİF + kaynaklar arası
    AGREEMENT scoring. İçerik üretmeden önce bu zihinsel modeli kur:

    A) PER-SOURCE PERSPECTIVE — her kaynağı KENDİ AÇISINDAN oku:
    - Resmi kaynak (Anadolu Ajansı, TRT, devlet açıklamaları) → bürokratik açı
    - Bağımsız kaynak (Bianet, Diken, Evrensel) → eleştirel/sivil toplum açısı
    - Sektör kaynağı (C4Defence, Webtekno, Bloomberg) → sektörel/teknik açı
    - Mainstream kaynak (Hürriyet, Habertürk, Sözcü) → genel okur açısı

    B) CROSS-SOURCE AGREEMENT — kaynaklar aynı iddiada hemfikir mi?
    - HEMFİKİR (3+ kaynak teyit): "Birden fazla kaynak X'i teyit ediyor [1][3][4]"
    - KISMEN ÇELİŞEN: "Resmi açıklama X derken (Anadolu Ajansı), bağımsız
      analiz Y görüş bildiriyor (Bianet)"
    - TAM ÇELİŞEN: "Kaynaklar arasında Z konusunda farklılık var: [1] X derken
      [2] tam tersini söylüyor"
    - TEK KAYNAK: "Bu bilgi tek kaynaktan (Hürriyet) — diğer kaynaklarda teyit yok"

    YAPISAL ÖZET FORMATI (Perplexity-style):

    İYİ ÖRNEK 1 (multi-source, agreement var):
    "Türkiye savunma ihracatı 2026'da %42 artarak 11 milyar dolara ulaştı —
    SSB Başkanı Görgün resmi açıklamasında doğruladı [1], MKE'nin yeni
    silah sistemleri tanıtımı bu büyümenin sektörel sebeplerini gösteriyor [2],
    Bayraktar İHA satışları ise ana itici güç olarak öne çıkıyor [3][4]."

    İYİ ÖRNEK 2 (multi-source, perspective farkı):
    "İmamoğlu davasında 31. günde mahkeme kararı bekleniyor. Resmi açıklamaya
    göre tutukluluk kararı sürmekte [1], CHP cephesinden yapılan değerlendirmede
    ise yargı sürecine eleştiriler dile getirildi [2], hukuk uzmanları ise
    sürecin uzamasını eleştirdi [3]."

    İYİ ÖRNEK 3 (tek-kaynak, disclaimer):
    "Northrop Grumman 21 ülkenin F-16 radarları için 488 milyon dolarlık
    sözleşme kazandı (C4Defence). Bu spesifik sözleşmeye dair şu an tek
    kaynak mevcut — geniş kapsamı ile ilgili güncellemeleri için sektörel
    yayınları takip etmek gerekir."

    KÖTÜ ÖRNEK (PR-F öncesi davranış):
    "Türkiye savunma ihracatı arttı [1]. SAHA fuarı düzenlendi [2]."
    (Yan yana iki cümle, sentez yok, perspektif yok, agreement scoring yok)

    KURAL ÖZETİ:
    ✅ summary'de en az 1 multi-source agreement statement
    ✅ Resmi vs bağımsız vs sektörel kaynak ayrımı belirt (varsa)
    ✅ Tek-kaynak iddialar disclaimer ile ("tek kaynak — diğer teyit yok")
    ❌ "Kaynak A: X. Kaynak B: Y." gibi yan-yana liste (sentez yok)
    ❌ Perspektif/açı belirtmemek (kaynak çeşitliliği farkı yok)

16. FSEK uyumu: 25 kelimeden uzun direct quote yok.
"""


# =============================================================================
# Input formatter
# =============================================================================


def render_user_payload(
    *,
    request: str,
    retrieval_plan: dict[str, Any],
    agenda_cards: list[dict[str, Any]],
    supplementary_chunks: list[dict[str, Any]] | None = None,
    style_profile: dict[str, Any] | None = None,
    output_constraints: dict[str, Any] | None = None,
    max_excerpt_chars: int = 800,
) -> str:
    """Plan + agenda + chunks → user message JSON.

    NOT: Agenda card'ların full content'i gider. Supplementary chunks
    excerpt'lendir (cost guard).
    """
    sanitized_chunks = []
    for ch in (supplementary_chunks or [])[:10]:
        text = ch.get("chunk_text") or ""
        if len(text) > max_excerpt_chars:
            text = text[:max_excerpt_chars] + "..."
        sanitized_chunks.append(
            {
                "article_id": str(ch.get("article_id", "")),
                "chunk_text": text,
                "source_name": ch.get("source_name"),
                "url": ch.get("url") or ch.get("canonical_url"),
                "published_at": (
                    ch["published_at"].isoformat()
                    if isinstance(ch.get("published_at"), datetime)
                    else ch.get("published_at")
                ),
            }
        )

    sanitized_cards = []
    for c in agenda_cards[:10]:
        sanitized_cards.append(
            {
                "id": str(c.get("id", "")),
                "title": c.get("title", "")[:300],
                "summary": c.get("summary", "")[:1500],
                "key_points": c.get("key_points") or [],
                "content_angles": c.get("content_angles") or [],
                "source_refs": c.get("source_refs") or [],
                "status": c.get("status"),
                "importance_score": c.get("importance_score"),
                "freshness_score": c.get("freshness_score"),
            }
        )

    # #169 — current_time payload'a eklenir. LLM "bugün/dün" referanslarını
    # doğru tarihle ilişkilendirir, eski olayı "şu an" gibi sunmaz (Kural 4).
    now_iso = datetime.now(UTC).isoformat()

    payload = {
        "current_time": now_iso,
        "request": request[:1000],
        "retrieval_plan": retrieval_plan,
        "agenda_cards": sanitized_cards,
        "supplementary_chunks": sanitized_chunks,
        "style_profile": style_profile,
        "output_constraints": output_constraints or {},
    }
    return json_dumps(payload)


SYSTEM_PROMPT_SUMMARY = """Sen Nodrat'ın İçerik Üretim ajanısın. Görevin, verilen gündem
kartlarına dayanarak çok-maddeli TEK BİR ÖZET içeriği üretmektir. Madde
sayısı kullanıcı payload'undaki `output_constraints.max_posts` alanında
belirtilir (summary için item_count olarak yorumlanır).
NotebookLM-benzeri çıktı: tek başlık + N madde + her madde için kaynak.

ÇIKTI SADECE JSON. Markdown, kod bloğu, açıklama YOK.

ÇIKTI ŞEMASI:
{{
  "summary_doc": {{
    "title": "string (genel başlık, 5-10 kelime Türkçe)",
    "items": [
      {{
        "event": "string (olay özeti, 1-3 cümle, max 280 char)",
        "source": "string (kaynak adı, örn. 'TRT Haber')",
        "date": "ISO-8601 veya 'bilinmiyor'",
        "agenda_card_id": "uuid (related agenda card)"
      }}
    ]
  }},
  "sources": [
    {{ "title": "...", "source": "...", "url": "..." }}
  ],
  "warnings": ["string"]
}}

KESİN KURALLAR:

1. SADECE verilen agenda_cards ve supplementary_chunks içindeki bilgilere dayan.
   UYDURMA YASAK.

2. output_constraints.max_posts kadar madde üret (summary için item_count
   olarak yorumlanır). Her madde farklı bir agenda card'a referans vermeli
   (related_agenda_card_ids non-empty her item için).

3. Maddeleri **ÖNEMSEME ve TARİH** sırasına göre sırala:
   - En önemli + en yeni → ilk sırada
   - importance_score + freshness_score birleşik
   - "son N olay" sorgusunda freshness ağırlıklı
   - "önemli N olay" sorgusunda importance ağırlıklı

   ⚠️ HABER DEĞERİ FİLTRESİ — request_text 'önemli', 'en önemli', 'gündem',
   'gelişme', 'olay' gibi öncelikli haber sinyali içeriyorsa:
   - importance_score < 0.40 olan kartları DAHIL ETME
   - Listicle / lifestyle / "X hediye fikri", "anlamlı mesajlar",
     "sıra dışı", "10 öneri" tarzı başlıkları SEÇ-ME
   - Hard news (ölüm, yangın, operasyon, mevzuat, ekonomi) öncelikli

   Yeterli yüksek-importance kart yoksa az madde üret (item_count'a zorlama),
   gerekirse tüm liste boş döndür (kural #8 — yetersiz kaynak).

   ⛔ COĞRAFİ ODAK FİLTRESİ — retrieval_plan'da geographic_focus dolu ise
   (örn. "TR" / "US" / "DE"), sadece o ülkede geçen olayları DAHIL ET:

   - "TR" odaklı sorgu (örn. "türkiyedeki son 1 saat"):
     • Türkiye'de geçen olaylar (İstanbul, Ankara, İzmir, Adana, ...) ✓
     • TBMM, Resmi Gazete, Türk hükümeti kararları ✓
     • Türk vatandaşları/kurumları ana özne ✓
     • ❌ Yurtdışı olaylar (Avusturya, Küba, ABD, Almanya...) — DAHIL ETME
     • ❌ Türkiye'yi tek paragrafta geçen yurtdışı haberler — DAHIL ETME

   - Diğer ülke kodu (US/DE/IL/...): aynı mantık o ülke için

   - geographic_focus null ise: filtre uygulanmaz, mevcut davranış

   Yeterli kart yoksa az madde üret (output_constraints.max_posts'a zorlama)
   veya boş liste döndür.

4. Her madde için tarih:
   - agenda_card.timeline veya source_refs.published_at'a göre
   - current_time'a göre relative ifade kullanma; absolute tarih bağlamı ver
   - Bilinmiyorsa "bilinmiyor"

5. ⛔ ALAKA KONTROLÜ — MUTLAK KURAL (halüsinasyon koruması):
   request_text → ana konu/varlık çıkar
   agenda_cards → kapsadıkları konuları çıkar

   EĞER agenda_cards request_text'in ana konusunu kapsamıyorsa, HEMEN ŞUNU
   DÖNDÜR ve dur:

   {{
     "summary_doc": {{ "title": "", "items": [] }},
     "sources": [],
     "warnings": ["irrelevant_sources"]
   }}

6. Title kısa ve betimleyici (örn. "Bugünün 5 önemli gelişmesi",
   "Türkiye-Fransa ilişkilerinde son 3 olay", vb.).

7. Items.event 1-3 cümle. Detay için summary'den çek, alıntı YASAK
   (FSEK 25 kelime kuralı uygula).

8. AGENDA_CARDS YETERSİZSE (kart sayısı < output_constraints.max_posts):
   {{
     "summary_doc": {{ "title": "", "items": [] }},
     "sources": [],
     "warnings": ["insufficient_data"]
   }}
"""


SYSTEM_PROMPT_THREAD = """Sen Nodrat'ın İçerik Üretim ajanısın. Görevin, verilen gündem
kartlarına dayanarak X thread (numaralandırılmış, birbirini takip eden
post serisi) üretmektir. Post sayısı kullanıcı payload'undaki
`output_constraints.max_posts` alanında belirtilir; tam o sayı kadar
post üret.

ÇIKTI SADECE JSON. Markdown, kod bloğu, açıklama YOK.

ÇIKTI ŞEMASI:
{{
  "posts": [
    {{
      "text": "string (max 280 char, ilk post '1/' ile başlar, sonrakiler '2/', '3/' ...)",
      "angle": "string",
      "char_count": number,
      "related_agenda_card_ids": ["uuid"]
    }}
  ],
  "summary": "thread özeti (opsiyonel)",
  "sources": [{{ "title": "...", "source": "...", "url": "..." }}],
  "warnings": []
}}

KURALLAR:
- İlk post hook (dikkat çekici), sonraki post'lar bağlamı genişletir, son post sonuç/CTA
- Her post 280 char'ı aşmamalı (numbering dahil: "1/12 ...")
- Her post bir önceki ile mantıksal bağ (devamlılık)
- HALU + KAYNAK kuralları x_post ile aynı (10. madde altındakiler)
- AGENDA_CARDS yetersizse posts=[], warnings=["insufficient_data"]
"""


SYSTEM_PROMPT_HEADLINE = """Sen Nodrat'ın İçerik Üretim ajanısın. Görevin, verilen gündem
kartlarına dayanarak farklı X paylaşımları için HEADLINE/BAŞLIK ÖNERİSİ
üretmektir. Üreteceğin başlık sayısı kullanıcı payload'undaki
`output_constraints.max_posts` alanında belirtilir; tam o sayı kadar
başlık öner.

ÇIKTI SADECE JSON.

ÇIKTI ŞEMASI:
{{
  "posts": [
    {{
      "text": "string (max 120 char, kısa etkili headline)",
      "angle": "string (örn. 'soru-temelli', 'şok-değer', 'veri', 'kıyas')",
      "char_count": number,
      "related_agenda_card_ids": ["uuid"]
    }}
  ],
  "summary": "öneri stratejisi özeti",
  "sources": [{{ "title": "...", "source": "...", "url": "..." }}],
  "warnings": []
}}

KURALLAR:
- Her headline farklı bir açı (soru, veri, kıyas, polemic, vs.)
- 120 char'ı aşmamalı
- Click-bait yok — kaynaklı + somut
- HALU + KAYNAK kuralları x_post ile aynı
"""


# #74 — Tone explicit instructions (system prompt'a inject edilir)
TONE_INSTRUCTIONS = {
    "tarafsız": "Veri merkezli, yorumsuz; sıfat yerine olgu kullan.",
    "eleştirel": "Sert eleştiri, ama her iddianı kaynakla destekle.",
    "mizahi": "İroni ve hafif esprili dil; hakaret/aşağılama yok.",
    "kurumsal": "Soğukkanlı, profesyonel, kurumsal raporlama tonu.",
    "aktivist": "Eyleme çağıran, tartışmaya açan; sloganik değil somut.",
    "analitik": "Veri, karşılaştırma, neden-sonuç zinciri ön plana.",
    "sade": "Kısa cümle, az süs, etkileyici ifade; 12 kelime max.",
    "sert": "Doğrudan, mecaz yok, eleştiri açık ve yargılayıcı.",
}


# #74 — Length → max_posts/item_count mapping
LENGTH_COUNTS = {
    "short": {"x_post": 2, "summary": 1, "thread": 4, "headline": 3},
    "medium": {"x_post": 5, "summary": 3, "thread": 6, "headline": 5},
    "long": {"x_post": 8, "summary": 5, "thread": 10, "headline": 7},
}


def resolve_count(*, output_type: str, length: str | None) -> int:
    """Length parametresini count'a çevir. None → medium default."""
    key = (length or "medium").lower()
    if key not in LENGTH_COUNTS:
        key = "medium"
    counts = LENGTH_COUNTS[key]
    return counts.get(output_type, counts["x_post"])


def format_system_prompt(
    *,
    max_posts: int = 5,
    output_type: str = "x_post",
    tone: str | None = None,
) -> str:
    """System prompt template'i output_type'a göre döner (#73 #74 #392 MVP-2.1).

    v1.1.0 — STATIC PREFIX (DeepSeek implicit cache hit için):
    - max_posts/tone artık `output_constraints` user payload'unda taşınır
    - .format() sadece `{{`/`}}` JSON escape'lerini açar (no args)
    - Tone instruction append KALDIRILDI — system prompt rule 10 tablo kanonik

    Args (backward-compat — fonksiyon imzası korundu, args bu sürümden
    itibaren prompt seçimini etkilemez; sadece output_type belirleyici):
        max_posts: ignore (user payload'da output_constraints.max_posts)
        output_type: "x_post" | "summary" | "thread" | "headline"
        tone: ignore (user payload'da output_constraints.tone)
    """
    # output_type → static template (no interpolation)
    if output_type == "summary":
        return SYSTEM_PROMPT_SUMMARY.format()  # `{{`→`{` escape'leri açar
    if output_type == "thread":
        return SYSTEM_PROMPT_THREAD.format()
    if output_type == "headline":
        return SYSTEM_PROMPT_HEADLINE.format()
    return SYSTEM_PROMPT_X_POST.format()


# =============================================================================
# Output validator
# =============================================================================


@dataclass
class XPost:
    text: str
    angle: str
    char_count: int
    related_agenda_card_ids: list[str]


@dataclass
class SummaryItem:
    """#173 PR-F — multi-item summary doc içindeki tek madde."""

    event: str
    source: str
    date: str
    agenda_card_id: str | None = None


@dataclass
class GeneratedXContent:
    posts: list[XPost]
    summary: str
    sources: list[dict[str, str]]
    warnings: list[str] = field(default_factory=list)

    # #173 PR-F — summary mode için multi-item
    summary_doc_title: str = ""
    summary_doc_items: list[SummaryItem] = field(default_factory=list)


@dataclass
class ContentGenError:
    error: str
    reason: str


def parse_x_post_response(text: str) -> GeneratedXContent | ContentGenError:
    """LLM response → GeneratedXContent or error."""
    cleaned = text.strip()

    # Markdown fence
    if cleaned.startswith("```"):
        parts = cleaned.split("```", 2)
        if len(parts) >= 2:
            content = parts[1]
            if content.startswith("json\n"):
                content = content[5:]
            elif content.startswith("\n"):
                content = content[1:]
            cleaned = content.rstrip("`").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return ContentGenError(
            error="json_parse_error", reason=f"Invalid JSON: {exc}"
        )

    if not isinstance(data, dict):
        return ContentGenError(
            error="invalid_root", reason="Response not JSON object"
        )

    warnings: list[str] = list(data.get("warnings", []) or [])

    # Sources (her iki output_type için)
    sources_raw = data.get("sources", []) or []
    if not isinstance(sources_raw, list):
        sources_raw = []
    sources: list[dict[str, str]] = []
    for s in sources_raw[:30]:
        if not isinstance(s, dict):
            continue
        sources.append(
            {
                "title": str(s.get("title", ""))[:300],
                "source": str(s.get("source", ""))[:120],
                "url": str(s.get("url", ""))[:500],
            }
        )

    # #173 PR-F — Summary mode (multi-item bullet doc)
    summary_doc = data.get("summary_doc")
    summary_doc_title = ""
    summary_doc_items: list[SummaryItem] = []
    if isinstance(summary_doc, dict):
        summary_doc_title = str(summary_doc.get("title", "")).strip()[:200]
        raw_items = summary_doc.get("items", []) or []
        if isinstance(raw_items, list):
            for it in raw_items[:10]:
                if not isinstance(it, dict):
                    continue
                evt = str(it.get("event", "")).strip()
                if not evt:
                    continue
                if len(evt) > 500:
                    evt = evt[:500]
                summary_doc_items.append(
                    SummaryItem(
                        event=evt,
                        source=str(it.get("source", ""))[:120],
                        date=str(it.get("date", ""))[:40],
                        agenda_card_id=str(it.get("agenda_card_id", "")) or None,
                    )
                )

    # Summary mode: items var, posts boş olabilir.
    # #560 — warnings gate kaldırıldı: LLM cevabı kullanıcıya doğrudan gitsin.
    # Eğer LLM 'kartlarda yok' diye doğal dil cevap verdiyse, kullanıcı bunu
    # okur; aksi halde gate over-filter yapıyordu (legitimate sorgular reject).
    if summary_doc_items:
        return GeneratedXContent(
            posts=[],
            summary=summary_doc_title,
            sources=sources,
            warnings=warnings,
            summary_doc_title=summary_doc_title,
            summary_doc_items=summary_doc_items,
        )

    # x_post mode (eski path)
    raw_posts = data.get("posts", []) or []
    if not isinstance(raw_posts, list):
        raw_posts = []

    posts: list[XPost] = []
    for p in raw_posts[:10]:  # cap at 10
        if not isinstance(p, dict):
            continue
        text_v = str(p.get("text", "")).strip()
        if not text_v:
            continue
        # Hard char cap
        if len(text_v) > X_POST_MAX_CHARS:
            warnings.append(
                f"post truncated from {len(text_v)} to {X_POST_MAX_CHARS}"
            )
            text_v = text_v[:X_POST_MAX_CHARS]

        angle = str(p.get("angle", "")).strip()[:200]
        related = p.get("related_agenda_card_ids", []) or []
        if not isinstance(related, list):
            related = []
        related = [str(r) for r in related if r][:5]
        if not related:
            warnings.append("post has empty related_agenda_card_ids")

        posts.append(
            XPost(
                text=text_v,
                angle=angle or "untagged",
                char_count=len(text_v),
                related_agenda_card_ids=related,
            )
        )

    if not posts:
        # insufficient_data signal
        if "insufficient_data" in warnings:
            return ContentGenError(
                error="insufficient_data",
                reason="LLM reported insufficient agenda cards",
            )
        # irrelevant_sources — #157 (LLM'in alaka kontrolü)
        if "irrelevant_sources" in warnings:
            return ContentGenError(
                error="insufficient_data",  # frontend tek state ile handle eder
                reason="Bulunan kaynaklar sorgu ile alakasız (LLM relevance check)",
            )
        return ContentGenError(
            error="empty_posts", reason="No valid posts in response"
        )

    summary = str(data.get("summary", "")).strip()[:1000]

    return GeneratedXContent(
        posts=posts,
        summary=summary,
        sources=sources,
        warnings=warnings,
    )
