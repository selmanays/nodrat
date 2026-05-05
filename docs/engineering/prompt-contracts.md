# Nodrat — Prompt Sözleşmeleri ve LLM Evaluation Framework

**Doküman türü:** Prompt Engineering Contracts & Quality Eval
**Sürüm:** v0.1
**Bağımlılık:** PRD §9, IA §11, Architecture §4 (provider abstraction), Risk Register R-PRD-01 (halüsinasyon), Legal §6 (output liability), Metrics §3.6 (quality)
**Hedef:** Üç çekirdek prompt'un (Query Planner, Agenda Card Generator, Content Generator) tam sözleşmesi + halüsinasyon test seti + kalite skorlama yöntemi.

⚠️ **Not:** Bu doküman ürünün **canıdır**. Pipeline'da kalite kontrol noktası burada kurulur. Her prompt değişikliği versiyonlanır ve eval test setinden geçer.

---

## 0. Yönetici Özeti

```text
3 ana prompt sözleşmesi:
  1. Query Planner (kullanıcı talebi → structured plan)
  2. Agenda Card Generator (event cluster → kart)
  3. Content Generator (plan + cards → kullanıcı çıktısı)

+ 2 yardımcı prompt (Faz 4-5):
  4. Style Analyzer (örnek metinler → stil profili)
  5. Image Caption (VLM, görsel → açıklama)

Kalite hedefleri:
  Query Planner:    JSON valid %99+, intent doğru %95+
  Agenda Card:      Halüsinasyon < %2, source coverage %100
  Content Gen:      Halüsinasyon < %2, citation %100, INSUFFICIENT_DATA tetikleme isabet > %90

DeepSeek JSON mode (#171 PR-E):
  3 prompt'un tümü json_mode=True ile çağrılır
    response_format={"type": "json_object"}
  → JSON parse error %90 azalır (deterministic output)
  → Schema validation hala caller'da yapılır

Query Planner output (#171):
  + keywords[] (3-5 anahtar kelime, hybrid search enrichment)

Content Generator user_payload (#169):
  + current_time (ISO-8601 — temporal reasoning)

Versioning:
  Her prompt'un /docs/agents/* dosyasında v1.0+ versiyonu
  Database: agenda_cards.generated_by_model + prompt_version
  A/B test: prompt_variant_id (Faz 7+)

Eval framework:
  Golden test set: 100 input/output (kategori başına)
  Otomatik scoring: schema validation + LLM-as-judge
  Manuel review: haftalık 20 örnek
```

---

## 1. Genel Prompt Prensipleri

### 1.1 Sistem prompt'unun tutarlı bölümleri

```text
[ROL TANIMI]
"Sen bir [X]'sin. Görevin [Y]."

[ÇIKTI ŞEMASI]
JSON schema açıkça belirtilir.

[KESİN KURALLAR]
- Sadece verilen veriyi kullan
- Uydurma yok
- Belirsizlik durumunda boş/null veya warning

[FORMAT]
Sadece JSON. Açıklama, markdown, kod bloğu yok.

[DİL]
"Çıktı dili: Türkçe (kullanıcı request_text'i Türkçe ise)"
```

### 1.2 Halüsinasyon koruması (PRD §12.4 ile uyumlu)

```text
Her prompt'a aşağıdaki kuralların özeti dahil edilmelidir:

1. Sadece verilen context'i kullan.
2. Context dışı bilgi ekleme (tarih, kişi, kurum, olay).
3. Belirsiz olanı kesin söyleme; "muhtemelen", "kaynaklara göre" vb. uygun.
4. Veri yetersizse: warning döndür, üretim yapma.
5. Eski olayı güncelmiş gibi sunma; tarih kontrolü.
6. Verified olmayan etiket / iddia kesin ifade edilmez.
```

### 1.3 Output formatı

```text
- Tüm prompt'lar STRUCTURED JSON döndürür.
- JSON Mode (provider destekliyorsa) açık.
- Pydantic schema ile validate edilir.
- Hata durumunda retry × 2, sonra fallback provider.
```

### 1.4 Provider rotaları (Unit Economics §4.2 ile uyumlu)

```text
Query Planner:        DeepSeek V3 (tüm tier'larda — basit görev)
Agenda Card Generator: DeepSeek V3 (default), Haiku 4.5 (premium kalite)
Content Generator:
  - Free / Starter: DeepSeek V3
  - Pro / Agency:   Haiku 4.5
  - Agency comparison: Sonnet 4.6
Style Analyzer:       DeepSeek V3 (tek seferlik, ucuz)
Image Caption (VLM):  Claude Haiku 4.5 vision (Faz 4)
```

---

## 2. Prompt #1 — Query Planner

### 2.1 Sözleşme (Contract)

**Amaç:** Kullanıcı doğal dil talebini structured retrieval planına çevirmek.
**Provider:** DeepSeek V3
**Latency hedef:** < 2 saniye P95
**Maliyet hedef:** < $0.001 per call

### 2.2 Input

```json
{
  "user_request": "CHP'nin geçen ayki gündemiyle bu ayki gündemini kıyaslayan içerikler üret",
  "current_time": "2026-05-01T12:00:00+03:00",
  "user_locale": "tr-TR",
  "available_modes": ["current", "weekly", "archive", "comparison"],
  "available_output_types": ["x_post", "x_thread", "summary", "analysis", "headline", "calendar", "briefing"],
  "user_tier": "pro"
}
```

### 2.3 System prompt (v1.0)

```text
Sen Nodrat'ın Query Planner ajanısın. Görevin, kullanıcının doğal dilde
yazdığı gündem talebini retrieval pipeline için yapılandırılmış bir
plana dönüştürmektir. Sadece plan üretirsin; içerik üretmezsin.

ÇIKTI SADECE JSON OLMALIDIR. Markdown, açıklama, kod bloğu YOK.

ÇIKTI ŞEMASI:
{
  "intent": "current_content_generation" | "weekly_summary_generation" |
            "archive_analysis" | "comparative_content_generation" |
            "thread_generation" | "headline_generation" |
            "source_based_briefing",
  "topic_query": "ana konu, kısa Türkçe (3-8 kelime)",
  "mode": "current" | "weekly" | "archive" | "comparison",
  "timeframes": [
    { "label": "string", "from": "ISO-8601", "to": "ISO-8601" }
  ],
  "output_type": "x_post" | "x_thread" | "summary" | "analysis" | ...,
  "tone": "tarafsız" | "eleştirel" | "mizahi" | "kurumsal" | "aktivist" |
          "analitik" | "sade" | "sert ama kaynaklı" | null,
  "constraints": ["string"],
  "needs_sources": true,
  "minimum_evidence_per_period": 3
}

KURALLAR:

1. Belirsiz zaman ifadelerini current_time'a göre çöz:
   - "bugün"        → from = current_time'ın 00:00'ı, to = 23:59
   - "bu hafta"     → son 7 gün
   - "geçen ay"     → bir önceki takvim ayı (1-31)
   - "bu ay"        → mevcut takvim ayı
   - "son 3 gün"    → from = current_time - 3d
   - "geçen yıl"    → bir önceki takvim yılı

2. Karşılaştırma talebi ("vs", "kıyas", "karşılaştır", "fark") tespit edilirse:
   - mode = "comparison"
   - timeframes en az 2 dönem içerir
   - intent = "comparative_content_generation"

3. "X paylaşımı/tweet üret" → output_type = "x_post"
   "thread aç" → output_type = "x_thread"
   "özet ver" → output_type = "summary"
   "analiz et" → output_type = "analysis"
   "başlık öner" → output_type = "headline"

4. tone alanı için kullanıcı talebinde açık ifade yoksa null bırak.

5. needs_sources varsayılan TRUE (Nodrat kaynaklı çıktı verir).

6. minimum_evidence_per_period: comparison mode'da 3, diğerlerinde 2.

7. KULLANICI TALEBİNDEKİ İÇERİĞİ ÜRETME. Sadece planı çıkar.

8. ANLAYAMADIYSAN intent="current_content_generation" + en yakın varsayılanları kullan,
   constraints içine "ambiguous_request" ekle.

9. Çıktı dili: alan değerleri (topic_query, tone) Türkçe.

10. Şema dışında alan ekleme. Şemada olmayan alan döndürme.
```

### 2.4 Örnek input/output

**Input 1:**
```text
"Bu hafta yapay zeka regülasyonlarıyla ilgili 5 X paylaşımı üret"
```

**Output 1:**
```json
{
  "intent": "current_content_generation",
  "topic_query": "yapay zeka regülasyonları",
  "mode": "weekly",
  "timeframes": [
    { "label": "this_week", "from": "2026-04-25T00:00:00+03:00", "to": "2026-05-01T23:59:59+03:00" }
  ],
  "output_type": "x_post",
  "tone": null,
  "constraints": ["max_5_posts"],
  "needs_sources": true,
  "minimum_evidence_per_period": 2
}
```

**Input 2:** (comparison)
```text
"CHP'nin geçen ayki gündemiyle bu ayki gündemini kıyaslayan içerikler üret"
```

**Output 2:**
```json
{
  "intent": "comparative_content_generation",
  "topic_query": "CHP gündemi",
  "mode": "comparison",
  "timeframes": [
    { "label": "previous_month", "from": "2026-04-01T00:00:00+03:00", "to": "2026-04-30T23:59:59+03:00" },
    { "label": "current_month", "from": "2026-05-01T00:00:00+03:00", "to": "2026-05-31T23:59:59+03:00" }
  ],
  "output_type": "x_post",
  "tone": null,
  "constraints": [],
  "needs_sources": true,
  "minimum_evidence_per_period": 3
}
```

### 2.5 Failure modes & mitigation

| Hata | Sebep | Mitigation |
|---|---|---|
| Invalid JSON | LLM markdown ekledi | Strip + regex parse, retry x1 |
| Schema invalid | Şema dışı alan | Pydantic validation, retry with error feedback |
| Wrong intent | Kullanıcı muğlak | constraints'e "ambiguous_request" |
| Future date | Yanlış zaman çözümü | Current_time validation, future > current → reject |
| Empty topic_query | Çok kısa request | request_text'i topic_query'e fallback |

### 2.6 Test seti (10 örnek, golden set'in ilk parçası)

```text
1. "Bugünkü ekonomi gündemi" → current, x_post
2. "Bu hafta İstanbul'da neler oldu" → weekly, summary
3. "Geçen ayki gündemiyle bu ayı kıyasla" → comparison
4. "2026 başından beri yapay zeka haberleri" → archive
5. "Trump ve Erdoğan ilişkilerini özetle thread halinde" → x_thread
6. "Şu an gündem ne" → current, summary, ambiguous
7. "5 başlık öner siyaset için" → headline_generation
8. "Pazartesi paylaşımı için 3 öneri" → current, x_post
9. (boş string) → reject veya defaults
10. "ekonomi vs eğitim haberleri" → comparison (topical değil zaman)
```

---

## 3. Prompt #2 — Agenda Card Generator

### 3.1 Sözleşme

**Amaç:** Bir event cluster'a ait haberleri tek bir kullanılabilir "gündem kartına" özetlemek.
**Provider:**
- Default: DeepSeek V3
- Premium retrieval: Haiku 4.5 (kalite kritikse)
**Latency hedef:** < 8 saniye P95
**Maliyet hedef:** < $0.005 per card (DeepSeek), $0.02 (Haiku)
**Trigger:** Event cluster oluştuğunda + her 6 saatte refresh

### 3.2 Input

```json
{
  "event_cluster": {
    "id": "uuid",
    "canonical_title": "string",
    "first_seen_at": "ISO",
    "last_seen_at": "ISO",
    "article_count": 7,
    "source_count": 4
  },
  "articles": [
    {
      "id": "uuid",
      "title": "...",
      "subtitle": "...",
      "source_name": "BBC Türkçe",
      "source_reliability": 0.85,
      "published_at": "ISO",
      "clean_text_excerpt": "İlk 1500 karakter...",
      "url": "..."
    }
  ],
  "current_time": "ISO"
}
```

### 3.3 System prompt (v1.0)

```text
Sen Nodrat'ın Agenda Card Generator ajanısın. Görevin, aynı olaya
ait birden fazla haberin oluşturduğu bir cluster'ı tek bir
"gündem kartı"na özetlemektir.

ÇIKTI SADECE JSON. Markdown, kod bloğu, açıklama YOK.

ÇIKTI ŞEMASI:
{
  "title": "string (max 200 char, Türkçe)",
  "summary": "string (300-500 char, Türkçe)",
  "key_points": [
    "string (max 200 char each, en az 3 en fazla 5 madde)"
  ],
  "content_angles": [
    "string (kısa, üretim açıları, en fazla 5)"
  ],
  "timeline": [
    { "date": "ISO", "event": "string" }
  ],
  "source_refs": [
    { "source": "string", "title": "string", "url": "string", "published_at": "ISO" }
  ],
  "status": "developing" | "active" | "cooling" | "stale",
  "importance_score": 0.0-1.0,
  "freshness_score": 0.0-1.0
}

KESİN KURALLAR:

1. SADECE verilen articles içinden bilgi kullan. Kaynakta olmayan
   tek bir kişi adı, tarih, sayı, alıntı, olay UYDURMA.

2. Her key_point en az bir kaynağa dayanmalı. Kaynak yoksa madde yazma.

3. summary objektif ton. "İddia ediliyor" vs "Açıklandı" ayrımı koru.
   Belirsiz olanı kesin sunma.

4. content_angles: bu olay üzerinden üretilebilecek X içerik açıları.
   ("ekonomi eleştirisi", "muhalefet söylemi", "uluslararası reaksiyon")

5. timeline: kronolojik, en eskiden yeniye. articles[].published_at
   kullan. Tarih uydurma.

6. source_refs: TÜM articles için bir entry. URL'leri olduğu gibi koru.

7. status:
   - "developing": son 6 saat içinde > 3 yeni article
   - "active": son 24 saat aktif, hala yeni article geliyor
   - "cooling": son 48 saatte yeni article < 2
   - "stale": son 72 saatten eski son güncelleme

8. importance_score (0-1):
   - article_count yüksek + source_count yüksek + kaynaklar
     güvenilir → yüksek skor
   - Tek kaynak / düşük güvenilirlik → düşük skor

9. freshness_score (0-1):
   - last_seen_at - current_time arası 0-6h → 1.0
   - 6-24h → 0.85
   - 24-72h → 0.6
   - 3-7d → 0.35
   - 7d+ → 0.1

10. Çıktı dili: Türkçe.

11. Şema dışı alan EKLEME.
```

### 3.4 Örnek output

```json
{
  "title": "CHP'den ekonomi politikalarına yeni eleştiriler",
  "summary": "CHP yönetimi, son hafta içinde art arda yapılan açıklamalarla iktidarın ekonomi politikalarını eleştirdi. Genel başkanın söyleminde geçim sıkıntısı vurgusu öne çıkarken, parti içi toplantılarda erken seçim çağrısının da gündeme geldiği aktarılıyor.",
  "key_points": [
    "CHP genel başkanı Pazartesi günü partisinde basın toplantısı düzenleyerek ekonomi politikalarını eleştirdi.",
    "Açıklamada özellikle TÜFE artışı ve emekli maaşları üzerinde duruldu.",
    "Parti yönetimi, hafta içi grup toplantısında erken seçim çağrısını yineledi."
  ],
  "content_angles": [
    "ekonomi eleştirisi",
    "muhalefet söylemi sertleşmesi",
    "erken seçim çağrısı",
    "geçim sıkıntısı vurgusu"
  ],
  "timeline": [
    { "date": "2026-04-28T11:00:00+03:00", "event": "Genel başkan basın toplantısı" },
    { "date": "2026-04-30T14:30:00+03:00", "event": "Grup toplantısında seçim çağrısı" }
  ],
  "source_refs": [
    { "source": "BBC Türkçe", "title": "CHP'den ekonomi açıklaması", "url": "https://...", "published_at": "..." }
  ],
  "status": "active",
  "importance_score": 0.76,
  "freshness_score": 0.91
}
```

### 3.5 Failure modes

| Hata | Mitigation |
|---|---|
| Halüsinasyon (uydurulan kişi/tarih) | LLM-as-judge eval; >2% rate'de prompt revize |
| Çok kısa summary | min_length validation, retry |
| key_points kaynaksız | Source citation validator (her madde ≥1 article id reference) |
| Yanlış timeline sırası | Sort by date post-process |
| status yanlış | Server-side computed, LLM önerisi override edilebilir |

---

## 4. Prompt #3 — Content Generator

### 4.1 Sözleşme

**Amaç:** Plan + agenda cards + style profile → kullanıcıya sunulacak X paylaşımı/thread/özet.
**Provider:**
- Free / Starter: DeepSeek V3
- Pro / Agency: Haiku 4.5
- Agency comparison: Sonnet 4.6
**Latency hedef:** < 6 saniye P95 (DeepSeek), < 10 saniye (Haiku)
**Maliyet hedef:** < $0.005 per generation (avg)

### 4.2 Input

```json
{
  "request": "string — kullanıcının orijinal request_text'i",
  "retrieval_plan": { ... query planner output ... },
  "agenda_cards": [
    { ... full card object ... }
  ],
  "supplementary_chunks": [
    {
      "article_id": "...",
      "chunk_text": "...",
      "source_name": "...",
      "url": "...",
      "published_at": "..."
    }
  ],
  "style_profile": {
    "name": "...",
    "rules_json": { ... }
  } | null,
  "output_constraints": {
    "output_type": "x_post" | "x_thread" | ...,
    "max_posts": 5,
    "tone": "tarafsız" | null,
    "length": "short" | "medium" | "long",
    "show_sources": true,
    "language": "tr"
  }
}
```

### 4.3 System prompt — X Post variant (v1.0)

```text
Sen Nodrat'ın İçerik Üretim ajanısın. Görevin, verilen gündem
kartlarına dayanarak {max_posts} adet X (Twitter) paylaşımı
üretmektir.

ÇIKTI SADECE JSON. Markdown, kod bloğu, açıklama YOK.

ÇIKTI ŞEMASI:
{
  "posts": [
    {
      "text": "string (max 280 char, Türkçe)",
      "angle": "string (paylaşımın hangi açıyı öne çıkardığı)",
      "char_count": number,
      "related_agenda_card_ids": ["uuid"]
    }
  ],
  "summary": "string (opsiyonel, üretim özeti)",
  "sources": [
    { "title": "...", "source": "...", "url": "..." }
  ],
  "warnings": ["string"]
}

KESİN KURALLAR:

1. SADECE verilen agenda_cards ve supplementary_chunks içindeki
   bilgilere dayan. Bunlar dışında bilgi EKLEME.

2. Her post en az bir agenda_card'a referans vermeli
   (related_agenda_card_ids non-empty).

3. Kaynakta olmayan kişi, kurum, tarih, sayı, alıntı UYDURMA.
   Bilmediğin bilgiyi yazma.

4. Eski olayları "şu an oluyor" gibi sunma. Tarih bağlamı koru:
   - "2024'te" → geçmiş zaman
   - "Geçen hafta" → relative, agenda_card.last_seen_at'a göre

5. Verified olmayan kişi etiketlerini "kesin" ifade etme:
   - "Görselde Özgür Özel olduğu öne sürülüyor" ✓
   - "Özgür Özel açıklama yaptı" — sadece haberde geçiyorsa ✓
   - "Özgür Özel'in söyledikleri uydurulmaz" ✗

6. Her post 280 karakteri AŞMAMALI. Char count kontrol et.

7. URL/link YERLEŞTİRME. Kaynaklar ayrı "sources" array'inde.

8. Hashtag minimum (1-2 max). #SonDakika ve #Türkiye gibi yaygın
   etiketler tercih edilir; aşırı sayıda hashtag yok.

9. Her post farklı bir angle olmalı. Aynı şeyi tekrar etmeyen
   çeşitlilik {max_posts} kadar fikir.

10. Tone:
   - "tarafsız" → veri merkezli, yorumsuz
   - "eleştirel" → sert ama kaynaklı
   - "mizahi" → ironi, hakaret yok
   - "kurumsal" → soğukkanlı
   - "analitik" → veri ve karşılaştırma
   - "sade" → kısa, etkileyici cümle

11. style_profile verildiyse rules_json'daki sentence_length, tone,
    rhetorical_patterns'a uy. style_profile null ise tone'a göre standart.

12. AGENDA_CARDS YETERSİZSE (verilen kart sayısı < beklenen):
    posts: [], warnings: ["insufficient_data"] döndür.

13. show_sources=true ise her post'un en az bir kaynağına link
    sources array'inde olmalı (ID ile değil URL ile).

14. Çıktı dili: language alanına göre (tr varsayılan).

15. Şema dışı alan EKLEME.
```

### 4.4 System prompt — Thread variant (v1.0)

```text
[X Post variant aynı, fakat:]

ÇIKTI ŞEMASI:
{
  "thread": {
    "title_post": "string (ilk tweet, kanca, max 280)",
    "posts": [
      {
        "text": "string (max 280 char)",
        "char_count": number,
        "related_agenda_card_ids": ["uuid"]
      }
    ],
    "closing_post": "string (son tweet, kapanış, opsiyonel)"
  },
  "sources": [...],
  "warnings": []
}

EK KURALLAR:
1. Thread 4-12 post arası
2. Her post bağlam taşımalı (standalone okunabilir)
3. Numbering ekleme (1/, 2/) — model değil UI ekler
4. İlk post strong hook ("3 sebep:", "Şunu fark ettim:" vb)
5. Mantık akışı: önerme → kanıt → kanıt → sonuç
```

### 4.5 System prompt — Comparison variant (v1.0)

```text
[Comparison mode — Pro/Agency tier]

INPUT'taki agenda_cards iki dönem için ayrı bloklarda gelir.
"period_label_1": cards [...], "period_label_2": cards [...]

ÇIKTI ŞEMASI:
{
  "comparison_summary": "string (200-400 char, ne fark var)",
  "differences": [
    {
      "axis": "string (örn: ekonomi tonu, gündem yoğunluğu)",
      "period_1_observation": "string",
      "period_2_observation": "string"
    }
  ],
  "posts": [...],   // X paylaşımı array'i, comparison içeriği
  "sources": [...],
  "warnings": []
}

EK KURALLAR:
1. Önce farkları analitik çıkar, sonra bunlardan post üret.
2. İki dönemin kaynaklarını KARIŞTIRMA. Her post hangi dönemden
   bahsettiğini açıkça belirtsin.
3. Yetersiz veri (her dönem ≥ 2 card değil) → comparison_summary
   "Comparison için yeterli veri yok" + warnings.
```

### 4.6 Örnek output (X Post)

```json
{
  "posts": [
    {
      "text": "CHP, son haftada art arda 3 açıklamayla ekonomi politikasını eleştirdi. Vurgu noktası: emekli maaşları ve TÜFE. Söylem sertliği geçen aydan görünür şekilde arttı.",
      "angle": "muhalefet söyleminin sertleşmesi",
      "char_count": 175,
      "related_agenda_card_ids": ["..."]
    },
    {
      "text": "Genel başkan Pazartesi basın toplantısında 'erken seçim' kelimesini ilk kez bu kadar net kullandı. Parti içi toplantılarda da aynı çağrı tekrarlandı.",
      "angle": "erken seçim çağrısı",
      "char_count": 165,
      "related_agenda_card_ids": ["..."]
    }
  ],
  "sources": [
    { "title": "CHP'den ekonomi açıklaması", "source": "BBC Türkçe", "url": "https://..." }
  ],
  "warnings": []
}
```

---

## 5. Yardımcı Promptlar (Faz 4-5)

### 5.1 Style Analyzer (Faz 5)

```text
Input: kullanıcı tarafından eklenen 5-50 örnek metin
Output: PRD §5.3 style profile JSON

System prompt iskeleti:
"Sen bir yazı stili analizcisisin. Verilen örnek metinlerden
ortak özelliklerini çıkar. ÇIKTI JSON.

Şema:
{
  style_name: string (kısa etiket),
  sentence_length: 'short' | 'medium' | 'long',
  tone: ['sade', 'eleştirel', ...],
  rhetorical_patterns: ['önce iddia sonra kanıt', ...],
  avoid: ['aşırı slogan', 'akademik dil', ...],
  sample_transforms: [
    { generic: '...', styled: '...' }
  ]
}

KURAL: Stil özetle, telifli alıntı yapma."
```

### 5.2 Image Caption (NIM VLM — #304 MVP-1.4 PR-3)

**Mimari değişikliği:** Eski plan Claude Haiku 4.5 vision idi. MVP-1.4'te
NIM Llama 4 Maverick (multilingual + free tier 40 RPM) seçildi —
maliyet sıfır, Türkçe destekli, OCR yetenekli, depicts (named entity)
çıkarabiliyor.

```text
Provider: NIM (meta/llama-4-maverick-17b-128e-instruct)
Endpoint: https://integrate.api.nvidia.com/v1/chat/completions
Input: image (data URI) + alt_text + article_title

System/user prompt (Türkçe):
"Aşağıdaki haber görselini analiz et. Sen Türk basını için çalışan
profesyonel bir görsel analiz ajanısın.

ÇIKTI: Sadece geçerli JSON, başka metin yok.
{
  \"caption\": \"Türkçe, 1-2 cümle, objektif görsel açıklaması\",
  \"ocr_text\": \"Görsel üstündeki yazıları (varsa) aynen yaz\",
  \"depicts\": [\"isim/obje listesi\", ...]
}

KURALLAR:
- Caption Türkçe ve nötr. Yorum yapma, sadece görüleni anlat.
- depicts'te tanıdığın politik figür, kurum veya nesne adlarını
  yaz. Tanımıyorsan boş bırak.
- OCR yoksa boş string döndür.
- ASLA varsayım yapma. Kim olduğundan emin değilsen yazma."

Output validation:
  caption ≤ 5000 char
  ocr_text ≤ 10000 char
  depicts: list[str] (her entity ≤ 100 char)

Retry: 1x for timeout/network/5xx; 429 → VLMRateLimitError (Celery
autoretry, max 3, exponential backoff up to 5 min).

Smoke test (production):
  Input: BBC haber görseli (Erdoğan-Kılıçdaroğlu el sıkışması)
  Output: {"caption": "İki erkek el sıkışıyor",
           "ocr_text": "",
           "depicts": ["Erdoğan", "Kılıçdaroğlu"]}
  Latency: 696ms

KVKK/FSEK notu (#304 PR-6):
- depicts'te politik figür → admin /legal sayfasında attribution + alıntı
  uyarısı zorunlu (FSEK 35: 25 kelime limit).
- Görsel bytes saklanmaz; sadece kaynak makaleyi linkler. Telif sahibi
  takedown talep ederse `/legal/takedown` ile metadata silinir.
```

### 5.3 Image Suggest for Generation (#305 MVP-1.4 PR-5)

**LLM yok — pure lexical (Jaccard).** Generation post text'i + kaynak
makalelerin VLM metadata'sı arasında token overlap hesaplanır.

```text
Helper: app.core.media_suggest.suggest_image_for_post()
Input:
    post_text: str             — üretilen X post body
    article_ids: list[UUID]    — generation context article'ları
    min_confidence: float      — Jaccard eşiği (default 0.15)
    boost_depicts: float       — entity match boost (default 0.20)

Algoritma:
    1. post_tokens = tokenize(post_text) — TR stopword + len≥3 filter
    2. her ArticleImage (status=processed) için:
       img_tokens = tokenize(vlm_caption + alt_text + ocr_text)
       depicts_set = tokenize(depicts entries)
       score = jaccard(post_tokens, img_tokens ∪ depicts_set)
       if depicts_set ∩ post_tokens: score += 0.20  # boost
    3. score ≥ min_confidence ise top-1 döndür

Output: SuggestedImage(image_id, article_id, original_url, vlm_caption,
                      depicts, alt_text, score, reason)
```

---

## 6. LLM Evaluation Framework

### 6.1 Eval pipeline mimarisi

```text
[ Golden test set ]
        │
        ▼
[ Promptu çalıştır ]
        │
        ▼
[ Çıktı validation ]
   ├─ Schema valid?
   ├─ Length checks
   ├─ Required fields
   └─ Constraint checks
        │
        ▼
[ Halüsinasyon detector ]
   ├─ Source coverage check
   ├─ Hallucination LLM-as-judge
   └─ Entity verification
        │
        ▼
[ Quality scoring ]
   ├─ Relevance (0-1)
   ├─ Faithfulness (0-1)
   ├─ Coherence (0-1)
   └─ Style match (0-1, if profile)
        │
        ▼
[ Aggregate report ]
   pass_rate, halu_rate, avg_score
```

### 6.2 Golden test set yapısı

```yaml
# /tests/eval/query_planner_golden.yaml
- id: qp_001
  input:
    user_request: "Bugünkü ekonomi gündemiyle 5 X paylaşımı üret"
    current_time: "2026-05-01T12:00:00+03:00"
    user_locale: "tr-TR"
  expected:
    intent: "current_content_generation"
    mode: "current"
    output_type: "x_post"
    constraints_contains: "max_5_posts"
  pass_criteria:
    - intent == expected.intent
    - mode == expected.mode
    - output_type == expected.output_type

# /tests/eval/agenda_card_golden.yaml
- id: ac_001
  input:
    event_cluster: { ... }
    articles: [ ... ]
  expected:
    halucination_rate_max: 0.0  # No fabricated entities
    source_coverage: 1.0         # Tüm article'lar referans
    key_points_min: 3
  manual_review_required: true
```

### 6.3 Halüsinasyon detector

```python
# Pseudo-code
def check_hallucination(output: dict, context_articles: list[Article]) -> HaluReport:
    """
    1. NER'le çıktıdan entities çıkar (kişi, kurum, tarih)
    2. Her entity context article'larda var mı?
    3. Yoksa: hallucination flag
    4. Tarih: published_at'lerin range'inde mi?
    5. LLM-as-judge: ikinci LLM "bu cümle context'te destekleniyor mu?"
    """
    entities = extract_entities(output)
    halu_count = 0
    flags = []
    
    for entity in entities:
        if not entity_in_context(entity, context_articles):
            halu_count += 1
            flags.append({"entity": entity, "type": "fabricated"})
    
    halu_rate = halu_count / max(len(entities), 1)
    
    # LLM-as-judge step
    judge_prompt = f"""
      Given context: {context_summary}
      Output: {output}
      
      For each claim in output, mark:
      - SUPPORTED: directly in context
      - INFERRED: reasonable from context
      - FABRICATED: not in context, not inferable
    """
    judge_result = call_llm("judge", judge_prompt)
    
    return HaluReport(
        halu_rate=halu_rate,
        flags=flags,
        judge_result=judge_result
    )
```

### 6.4 Quality scoring kriterleri

```text
Relevance (0-1):
  Çıktı kullanıcı talebine ne kadar cevap veriyor
  - LLM-as-judge: "Output kullanıcı isteğine cevap veriyor mu?"
  - Hedef: ≥ 0.85

Faithfulness (0-1):
  Çıktı kaynaklara sadık mı (halüsinasyon tersi)
  - Hallu detector çıktısı: 1 - halu_rate
  - Hedef: ≥ 0.95

Coherence (0-1):
  Cümleler birbirine bağlanıyor mu, mantıklı mı
  - LLM-as-judge: 1-5 likert
  - Hedef: ≥ 0.80

Style match (0-1, varsa):
  style_profile.rules_json kurallarına uyum
  - Sentence length match, tone match, avoid keywords
  - Hedef: ≥ 0.70
```

### 6.5 Test seti boyutları

```text
Faz 0:
  Query Planner:    20 örnek
  Agenda Card:      10 örnek (manuel kurulan)
  Content Gen:      20 örnek
  
MVP-1 hedef:
  Query Planner:    100 örnek (10 kategori × 10)
  Agenda Card:      50 örnek
  Content Gen:      100 örnek
  
Olgun (Yıl 1):
  Her prompt:       500+ örnek
  Halu test seti:   200 zorlu "trick" örnek
  Style match:      30 stil profili × 10 örnek
```

### 6.6 Pre-deploy checklist

```text
Her prompt değişikliği için:
  [ ] Pull request açıldı (versioned)
  [ ] /tests/eval/* çalıştırıldı
  [ ] pass_rate ≥ %90 (regression yok)
  [ ] halu_rate < %2
  [ ] avg_quality_score ≥ baseline
  [ ] Manuel review: 10 örnek incelendi
  [ ] /docs/agents/* güncellendi
  [ ] Migration: agenda_cards.prompt_version bump
```

---

## 7. Prompt Versioning

### 7.1 Versiyonlama şeması

```text
prompt_id     : unique identifier (örn: "query_planner")
prompt_version: semver (v1.0.0, v1.1.0, v2.0.0)

Bump kuralları:
  PATCH (1.0.0 → 1.0.1): typo, küçük düzeltme
  MINOR (1.0.0 → 1.1.0): yeni example, kural ekle (geriye uyumlu)
  MAJOR (1.0.0 → 2.0.0): şema değişti, geriye uyumsuz

Database tracking:
  agenda_cards.prompt_version
  generations.prompt_version
  
A/B test (Faz 7+):
  prompt_variant_id (variant_a, variant_b)
  Winner determination: 1.000 sample
```

### 7.2 Repo yapısı

```text
/docs/agents/
  query-planner.md       — sözleşme + örnekler
  query-planner.v1.0.txt — system prompt full text
  agenda-card.md
  agenda-card.v1.0.txt
  content-generator.md
  content-generator.v1.0.txt
  content-generator-thread.v1.0.txt
  content-generator-comparison.v1.0.txt
  style-analyzer.md
  image-caption.md

/tests/eval/
  query_planner_golden.yaml
  agenda_card_golden.yaml
  content_gen_golden.yaml
  
/apps/api/prompts/
  loader.py           — version'a göre prompt load
  registry.py         — aktif promptlar
```

---

## 8. Hata Yönetimi (Pipeline)

### 8.1 Retry stratejisi

```text
Provider error:
  1. Retry × 2 (exponential backoff)
  2. Fallback provider (OpenRouter Llama → GPT-4o-mini)
  3. Fail → user'a "PROVIDER_ERROR" döner

Schema invalid:
  1. Retry × 1 with error feedback in prompt
  2. Fail → log + admin alert + warnings array

INSUFFICIENT_DATA:
  1. Retrieval'da yakalanır, prompt'a girmez
  2. Direkt user'a 422 INSUFFICIENT_DATA döner

Halucination flagged:
  1. Output kullanıcıya gider AMA warnings içinde flag
  2. Admin /admin/generations/quality-flags ekranında görür
  3. >2% flag rate → prompt revize alarmı
```

### 8.2 Latency budget

```text
End-to-end /app/generate budget: 10 saniye P95

Breakdown:
  Auth + validation:     50 ms
  Query planner LLM:    1.5 s
  Embedding query:       100 ms
  Vector search:         200 ms
  Agenda card retrieval: 50 ms
  Data sufficiency:      10 ms
  Content generator LLM: 6 s    (en büyük)
  Quality validation:    200 ms
  DB write:              50 ms
  Network overhead:      500 ms
  ─────────────────────────────
  Total:                ~8.5 s ✓
```

---

## 9. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | Prompt language | Sistem prompt Türkçe-only | Kalite + maliyet |
| D2 | JSON mode | Provider destekleniyorsa kullan | Schema reliability |
| D3 | Retry on schema fail | × 1 with feedback | Kalite |
| D4 | LLM-as-judge | Halüsinasyon eval'da | Otomasyon |
| D5 | Manual review cadence | Haftalık 20 örnek | Kalite |
| D6 | Test set growth | %10/ay yeni örnek | Drift koruması |
| D7 | Prompt version DB tracking | agenda_cards + generations | Lineage |
| D8 | Content gen variants | Post / Thread / Comparison ayrı | Kalite |
| D9 | Style analyzer trigger | Kullanıcı submit anında | Faz 5 |
| D10 | Image caption hard rule | Kişi tanımlama yok | KVKK + Legal §6 |

---

## 10. Çapraz Referans

```text
Query Planner output       → API /internal/rag/plan, Data Model generations.retrieval_plan_json
Agenda Card output         → Data Model agenda_cards
Content Generator output   → Data Model generations.output_json
Halucination prompt rules  → PRD §12.4, Risk Register R-PRD-01, Legal §6
Provider routing           → Architecture §4, Unit Economics §4.2
Cost target per prompt     → Unit Economics §3
Quality metrics            → Metrics §3.6, alarm thresholds
INSUFFICIENT_DATA flow     → API §11.1, PRD §2.10
Style profile rules        → Data Model §7, PRD §5
Image caption KVKK         → Legal §2.3, PRD §4.2
Versioning                 → Architecture deployment
```

---

**Sonuç:** Üç çekirdek prompt **versioned + schema-validated + halu-checked**. Eval framework golden test set + LLM-as-judge + manuel review üçlüsünde çalışır. **Halüsinasyon < %2** hedef, **citation %100** zorunlu — bu iki metrik düşerse R-PRD-01 mitigation devreye girer (prompt revize). **Provider routing tier'a göre** (DeepSeek default, Haiku premium, Sonnet sadece Agency comparison). **Faz 4-5 yardımcı promptlar** Image Caption KVKK-uyumlu (kişi tanımlama yok), Style Analyzer telifli alıntı yapmaz.
