# Nodrat — Prompt Sözleşmeleri ve LLM Evaluation Framework

**Doküman türü:** Prompt Engineering Contracts & Quality Eval
**Sürüm:** v0.4
**Son güncelleme:** 2026-06-18 (v0.10 — #1617 §4: `SYSTEM_PROMPT_NODRAT_AGENT` "Cevap biçimi" KAPSAM dengeleyici — spesifik/tek-olgu soruda bile kaynaktaki ilgili çevre bilgiyi (`[n]`) kırpma; "Şişirme yok" = kaynak-DIŞI üretme/lafı uzatma yasağı, kaynaktakini kırpma DEĞİL; "kaynakta ek bağlam yoksa zorlama" halü-koruması. Grounding kuralları aynen; `app_prompts` override yok → kod default canlı; `retrieval.content_top_k` prod'da zaten 10; API eval golden yeşil.) · 2026-05-17 (v0.9 — #927 zinciri §4: query_planner PROMPT_VERSION 1.4.0→1.6.0 (#942 kelime-kesme yasağı / #947 kök-form ZORUNLU) + `parse_response` kod-backstop kökleştir/düşür (`_canonical_token`; DAR `_STEM_SUFFIXES` over-stem koruması) + planner_cache prompt_version invalidation; #929 REWRITE itiraz≠parametre; #928 NODRAT_AGENT scope-aware tazelik dürüstlüğü). v0.8 — #888 §4: sohbet hafızası is_related'dan decouple (followup_block koşulsuz; #884'ün çalışma önkoşulu — kök mimari). v0.7 — #884 condense AÇIK ÖZNE İSTİSNASI + agent "anma≠tanım"/proaktif tutarlılık. v0.6 — #879 temporal-grounding. v0.5 — denetim staleness sync. Önceki: 2026-05-11 (v0.4 — #686 HyDE; #688 content_max_tokens; #677 halüsinasyon yasağı)
**Bağımlılık:** PRD §9, IA §11, Architecture §4 (provider abstraction), Risk Register R-PRD-01 (halüsinasyon), Legal §6 (output liability), Metrics §3.6 (quality)
**Hedef:** Üç çekirdek prompt'un (Query Planner, Agenda Card Generator, Content Generator) tam sözleşmesi + halüsinasyon test seti + kalite skorlama yöntemi.

> **v0.4 değişikliği (2026-05-11):**
> - **HyDE conditional (#686 PR-C):** Eski "her sorguda HyDE LLM call" → conditional skip. Generic kategori sorgularında (entity-suz + ≤3 kelime + soru kelimesi yok) HyDE atlanır → TTFT -1-2sn, cost -%15-20. Niş/soru sorgular (Karşıyaka hakemleri, Trump 6 Mayıs) HyDE ile devam.
> - **Content Generator max_tokens 2000 → 1500 (#688 PR-D):** DeepSeek `content_max_tokens` runtime tunable (`llm.content_max_tokens`, admin override mümkün). Streaming ~1-2sn kısalır, cost -%25.
> - **Faz 7a numerical entity NER (#679):** Yardımcı NER extraction prompt'una "number" type için ÖNCELIK eklendi (yüzde/oran/adet/tarihsel yıl). Entity cap 30→40.
> - **Halüsinasyon yasağı (#677):** Insufficient_data response zorunlu — Wikipedia ortak bilgiyi uydurma sıkı dilbilim ile yeniden yazıldı.

> **v0.2 değişikliği (2026-05-08, MVP-2.1 epic [#391](https://github.com/selmanays/nodrat/issues/391)):** Content Generator PROMPT_VERSION **1.0.0 → 1.1.0** ([PR #418](https://github.com/selmanays/nodrat/pull/418)). 4 SYSTEM_PROMPT_* (X_POST / SUMMARY / THREAD / HEADLINE) artık tamamen STATIC: `{max_posts}` / `{item_count}` placeholder'ları kaldırıldı, sayı bilgisi `output_constraints.max_posts`'tan okunur. Tone instruction dynamic append KALDIRILDI; rule 10 kanonik 9-tone tablosu tek doğruluk kaynağı. Content Generator retrieval top_k 10 → 5 (admin tunable `retrieval.content_top_k`, range 3-10). Detay: §4 + §7.1 changelog.

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

Aktif sürümler:
  Query Planner:           v1.0  (deepseek-v4-flash, JSON mode)
  Agenda Card Generator:   v1.0  (deepseek-v4-flash, JSON mode)
  Content Generator:       v1.1.0 (#392 MVP-2.1 — tüm SYSTEM_PROMPT_* STATIC,
                                   tone instruction dynamic append yok,
                                   max_posts user_payload.output_constraints'tan)
  Style Analyzer:          v1.0  (Faz 5)
  Image Caption (NIM VLM): v1.0  (#304 MVP-1.4)

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
Query Planner:        DeepSeek V4 Flash (tüm tier'larda — basit görev)
Agenda Card Generator: DeepSeek V4 Flash (default), Haiku 4.5 (premium kalite)
Content Generator:
  - Free / Starter: DeepSeek V4 Flash
  - Pro / Agency:   Haiku 4.5
  - Agency comparison: Sonnet 4.6
Style Analyzer:       DeepSeek V4 Flash (tek seferlik, ucuz)
Image Caption (VLM):  Claude Haiku 4.5 vision (Faz 4)
```

---

## 2. Prompt #1 — Query Planner

### 2.1 Sözleşme (Contract)

**Amaç:** Kullanıcı doğal dil talebini structured retrieval planına çevirmek.
**Provider:** DeepSeek V4 Flash
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
  "minimum_evidence_per_period": 2,
  "critical_entities": ["yapay zeka", "regülasyon"]
}
```

> **PROMPT_VERSION 1.3.0 (#778, 2026-05-14):** `critical_entities` field eklendi (1-3 element, 3-30 char, lowercase). Sorgudaki en diskriminatif kelimeleri tespit eder; retrieval'da MUST_MATCH gate olarak kullanılır (RESCUE + FILTER 2-aşamalı). Halüsinasyon yasak — sadece sorguda VAR olan kelimeler. Detay: [[wiki:critical-entity-must-match]]. Cache key v1 → v2.

> **PROMPT_VERSION 1.4.0 (#809, 2026-05-15 Faz 2):** Yeni `query_class` field (4 sınıf: `news_query | general_knowledge | meta_query | mixed`). Mevcut `intent` (content-generation) ile karıştırılmamalı — `query_class` kullanıcı sorgusunun NE tür bilgi gerektirdiğini söyler. 8 few-shot örnek prompt'a inject. Default `news_query` (Nodrat news-first sistem).
>
> ⚠️ **SUPERSEDED (#823→#845):** "Confidence Router (5-signal score) bu sınıfa göre Layer 1/2 **routing** yapar" artık GEÇERSİZ. Confidence router + tiered routing **terk edildi** (agentic tool-use'a geçildi). `query_class` chat akışında **routing yapmaz**; `search_news` çağrılırsa planner meta'sından gelen telemetri etiketidir (aksi halde `conversational`). Güncel mimari: §4 "Tool-use akışı (#845…)" + [[wiki:agentic-generate-orchestration]] + [[wiki:llm-tool-use-wikipedia]]. `query-class-classification`/`tiered-knowledge-architecture` wiki sayfaları telemetri-only/SUPERSEDED bağlamında okunmalı.
>
> 🔧 **news_query timeframe çıktı kontratı (#906, 2026-05-16):** `query_class == "news_query"` için `timeframes` **ASLA boş dönmez**. Prompt talimatı örtük güncellik ("günün/son gelişmeler/son dakika") → en az "son 7 gün" üretmeyi söyler, AMA bu garanti **prompt'a değil deterministik koda** bağlıdır (`query_planner._apply_news_recency_default`, #909): `plan_query`'nin üç dönüş noktasında (cache-hit / #785 short-query bypass / parsed) `news_query` + boş `timeframes` → varsayılan son 7 gün enjekte edilir. Gerekçe: prompt talimatı olasılıksal + #785 bypass planner LLM'i hiç çağırmaz + #270 DB prompt-override kod-içi `SYSTEM_PROMPT`'u runtime değiştirir → prompt yolu güvenilmez. `general_knowledge`/`meta_query`/`mixed` ve LLM'in açık aralık ürettiği sorgular etkilenmez. Bu timeframe `execute_search_news`'te retrieval `since_hours`'ını sürer (architecture.md §"Query Planner default timeframe"; dar pencere boş→90g fallback). Detay: [[wiki:news-timeframe-retrieval-contract]].

> 🔧 **PROMPT_VERSION 1.5.0 (#942, 2026-05-17):** §CRITICAL_ENTITIES'e **KELİMEYİ BÖLME/KESME yasağı** + Türkçe çekim-ek kuralı + few-shot ("özelle"→"özel" DOĞRU; "özel"→"öz" YANLIŞ). Kök: planner LLM ham/ekli/noktalı sorguda entity'yi kelime-ortasından kesiyordu ("Özgür özelle…???" → `['özgür öz']`) → C-locale-fixli (#939) RESCUE bile eşleştiremiyor → eski haber. **PROMPT_VERSION 1.6.0 (#947):** §CRITICAL_ENTITIES **KÖK-FORM ZORUNLU** — çekim ekli form ("özelle"/"depremde") YASAK, eksiz kök yaz ("özel"/"deprem"); haber metni eki farklı çeker, entity birebir eşleştirilir.

> 🔧 **`parse_response` kod-backstop (#942/#945/#947 — prompt olasılıksal, deterministik garanti):** `query_planner.parse_response(user_request=…)` opsiyonel; verildiğinde `critical_entities` her token'ı ham sorguya göre normalize edilir (`_canonical_token`/`_entity_canonical`): (a) ham sorguda TAM kelime + TR-ek ise **KÖKE indir** ("özgür özelle"→"özgür özel"); (b) bir sorgu-kelimesinin kök+TR-ek'i ise token zaten kök → korunur; (c) kelime-kesme/uydurma ("öz"~"özgür") → entity **düşürülür** (`critical_entity_dropped_not_grounded`/`critical_entity_stemmed` warning). Tam-kelime eşleşmesi her uzunlukta korunur (`'15 temmuz'` #944 regresyon guard). Kökleştirme **DAR `_STEM_SUFFIXES`** kullanır — tek-harf ünlü ekleri (-a/-ı/-ya) soyulmaz ("rusya"/"gazze"/"boğazı" over-stem'den korunur; geniş `_TR_SUFFIXES` yalnız grounding dalında). `user_request=None` → backstop atlanır (geriye-uyumlu). Bonus: `'İ'.lower()`=i+U+0307 combining → kelime-bölünmesi düzeltildi. **Planner cache invalidation:** `planner_cache._cache_key` artık `prompt_version` (PROMPT_VERSION) bileşeni içerir — prompt/planner değişince eski gün-içi cache otomatik MISS (önceden PROMPT_VERSION'suz + 24h TTL → deploy-öncesi bozuk plan 24h servis). Detay: [[wiki:planner-critical-entity-tr-guard]] · [[wiki:planner-cache-key-v2]].

> 🔧 **REWRITE_SYSTEM_PROMPT — İTİRAZ/ŞİKAYET follow-up (#929, 2026-05-17):** `query_rewrite` condense, kullanıcının önceki cevaba İTİRAZINI ("bu son haber olamaz", "neden 14 gün öncesini verdin", "yanlış") bir arama PARAMETRESİ olarak görmez. İtiraz kelimeleri ("14 gün öncesi") standalone sorguya FİLTRE olarak EKLENMEZ; standalone = önceki SUBSTANTIVE sorunun standalone hali, itiraz yalnız özgün niyeti (güncellik/doğruluk) PEKİŞTİRİR. #851/#854/#884 coreference ailesinin 4. ayrımı (asistan/kimlik · talimat-odaklı · açık-özne · **itiraz/şikayet**). #884 dersi: prompt ancak gerekli sinyal context'te varsa bağlayıcı → #928 `recency_requested` kod-sinyaliyle desteklenir. Detay: [[wiki:conversational-query-rewriting]].

> 🔧 **SYSTEM_PROMPT_NODRAT_AGENT — scope-aware tazelik dürüstlüğü (#928, 2026-05-17):** Veri yeterince taze değilken (retrieval recall taze haberi getiremeyince) sistem eski haberi "son haber" diye sunmaz (C1/C6 ihlali = sahte güncellik). Scope-aware dürüstlük: "son N günde daha yeni bulamadım, en güncel kayıt <tarih>"; kullanıcı tazelik itirazında savunma/tekrar YOK, kabul + toparlama. Bu prompt kuralı **deterministik kod-sinyaliyle desteklenir** (prompt tek başına yetmez — #906/#879 deseni): `execute_search_news` result_text başına KOD-ÜRETİLEN "DİKKAT—TAZELİK" yönergesi enjekte eder (bkz api-contracts §17.5.6 `freshness_gap_days`). Detay: [[wiki:news-timeframe-retrieval-contract]] (#928/#929 conv 74eecc15 ailesi).

**Faz 2 meta_query özel prompt (#815) — SUPERSEDED (#845):** `apps/api/app/prompts/meta_query.py` dosyası repo'da kalsa da **chat akışı (`app_research_stream.py`) ÇAĞIRMAZ**. `_stream_meta_query_answer` handler #845'te silindi. Güncel davranış: meta sorular (örn. "az önce ne dedin") agentic akışta `SYSTEM_PROMPT_NODRAT_AGENT` ile **tool çağırmadan doğrudan** cevaplanır (retrieval atlanır, ayrı prompt/handler yok). `sources_used=[]` yine geçerli (tool yok → cite yok). Detay: §4 + [[wiki:agentic-generate-orchestration]].

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
- Default: DeepSeek V4 Flash
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
- Free / Starter: DeepSeek V4 Flash
- Pro / Agency: Haiku 4.5
- Agency comparison: Sonnet 4.6
**Latency hedef:** < 6 saniye P95 (DeepSeek), < 10 saniye (Haiku)
**Maliyet hedef:** < $0.005 per generation (avg)
**PROMPT_VERSION:** **1.1.0** (#392, 2026-05-08; MVP-2.1)
**Retrieval:** Content Generator için `top_k = 5` agenda card + `top_k_supplementary = 4` chunk (önceki: 10/8). Admin runtime tunable: `retrieval.content_top_k` (range 3-10), `retrieval.supplementary_top_k` (range 2-8).
**Cache mekaniği:** SYSTEM_PROMPT_* tamamen STATIC olduğu için DeepSeek implicit prompt cache hit ratio hedef ≥%40. Cache miss durumu prompt prefix değişikliği yapılmadığı sürece beklenmemeli.

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

### 4.3 System prompt — X Post variant (v1.1.0)

> **v1.1.0 değişikliği (#392):** SYSTEM_PROMPT artık tamamen STATIC. `{max_posts}` interpolasyonu kaldırıldı; üretilecek post sayısı `user_payload.output_constraints.max_posts` alanından okunur. Bu sayede DeepSeek implicit prompt cache hit oranı yükseltilir. Tone instruction artık dynamic append değil — kural 10'daki kanonik 9-tone tablosu tek doğruluk kaynağı; tone seçimi user_payload'dan gelir. **Tam metin** için kanonik kaynak: [`apps/api/app/prompts/content_generator.py`](../../apps/api/app/prompts/content_generator.py) `SYSTEM_PROMPT_X_POST`.

```text
Sen Nodrat'ın İçerik Üretim ajanısın. Görevin, verilen gündem
kartlarına dayanarak X (Twitter) paylaşımları üretmektir. Üreteceğin
post sayısı kullanıcı payload'undaki `output_constraints.max_posts`
alanında belirtilir; TAM o sayıda post üret (ne fazla ne az).

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
    posts: [], warnings: ["insufficient_data"] döndür.

13. ⛔ ALAKA KONTROLÜ — MUTLAK KURAL (halüsinasyon koruması, v1.1.0):

    İLK ADIM (içerik üretmeden ÖNCE) bu kontrolü yap:
    request_text → ana konu/varlık çıkar.
    agenda_cards.title + summary → kapsadıkları konuyu çıkar.
    Kartlar request'in ANA KONUSUNU doğrudan kapsamıyorsa:
      → posts=[], warnings=["irrelevant_sources"], DUR.

    YASAK: "Kaynaklar konuyu kapsamıyor ama yine de özet üreteyim" — HAYIR.
    YASAK: status=completed + warning ekleyip içerik döndürmek — HAYIR.
    DOĞRU: alakasızsa boş + warning + dur.

14. FSEK uyumu: 25 kelimeden uzun direct quote yok (R-LGL-02 hard cap).

15. show_sources=true ise her post'un en az bir kaynağına link
    sources array'inde olmalı (ID ile değil URL ile).

16. Çıktı dili: language alanına göre (tr varsayılan).

17. Şema dışı alan EKLEME.
```

### 4.4 System prompt — Thread variant (v1.1.0)

> **v1.1.0 değişikliği (#392):** SYSTEM_PROMPT_THREAD STATIC. `{item_count}` kaldırıldı; thread post sayısı `output_constraints.max_posts` (4-12 range) üzerinden okunur. Tone tablosu §4.3 ile aynı 9-tone kanonik. Kanonik tam metin: `apps/api/app/prompts/content_generator.py` `SYSTEM_PROMPT_THREAD`.

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

### 4.5 System prompt — Comparison variant (v1.1.0)

> **v1.1.0 değişikliği (#392):** SYSTEM_PROMPT_COMPARISON STATIC. Sayı bilgisi user_payload üzerinden. Tone tablosu §4.3 ile uyumlu. Kanonik tam metin: `apps/api/app/prompts/content_generator.py`.

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

## 4.x Prompt #3b — Chat Answer (#795 Perplexity-style)

Conversation-based chat deneyimi için Content Generator'ın chat varyantı.
`/research/conversations/{id}/messages` endpoint'inden tetiklenir. Plain text
streaming çıktısı (X-Post JSON wrap YOK).

**Source:** `apps/api/app/prompts/research_answer.py:SYSTEM_PROMPT_NODRAT_AGENT` (#845; eski `SYSTEM_PROMPT_CHAT_ANSWER` + `TOOL_USE_INSTRUCTION` artık kullanılmıyor — chat akışında)

**Tetikleyici endpoint:** `POST /research/conversations/{id}/messages`

> **#845 — agentic RAG-as-tool (GÜNCEL):** Ön-retrieval KALDIRILDI. Chat akışı artık `render_nodrat_agent_prompt(current_date)` system prompt'u + iki tool (`search_news` BİRİNCİL — Nodrat haber arşivi; `search_wikipedia` evergreen) ile çalışır. LLM orkestre eder: selamlama/kimlik/konuşma-meta → tool çağırmadan doğrudan & güvenli yanıt (Nodrat = güncel olay araştırma motoru, sohbet botu DEĞİL, Wikipedia amaç gibi pazarlanmaz); substantive → tool zorunlu (C1). **Güncel tarih system prompt'a enjekte** (sistem now, TR UTC+3 — model "bugünü" uydurmaz). condense (#833) korundu. `search_news` mevcut retrieval pipeline'ı **sarmalar** (planner→embed→hybrid_search→RRF→critical_entities; kalite değişmedi). Aşağıdaki "Verilen kaynaklar" inline formatı artık yok — kaynaklar tool sonucundan gelir. Detay: `wiki/decisions/agentic-generate-orchestration.md`.

**Sözleşme (#845 öncesi — tarihsel; tool-use #823→#842):**
- Markdown output (streaming-friendly, JSON yok; react-markdown render)
- Multi-source synthesis **ZORUNLU** (Perplexity-vibe)
- **Yapı içeriğe göre** (editoryal — hardcoded kalıp YOK): kısa soru → kısa cevap, analiz → paragraf/başlık/liste (#829, eski "tek paragraf default" kaldırıldı)
- Her cümlede min 1 kaynak `[n]` / `[Wn]` citation (önemli iddialarda min 2)
- Halüsinasyon koruması: SADECE verilen kaynaklarda/tool sonucunda olan bilgi (C1)
- **TOOL_USE_INSTRUCTION** (offer_tools=True iken base prompt'a eklenir): (a) haber kaynakları sorudaki ENTITY hakkında değilse — keyword eşleşse bile — `search_wikipedia` çağır (#834 entity-relevance); (b) tool `query` = SADECE kanonik Türkçe madde adı, soru/sezon/bölüm/niteleyici çıkar (#842 — niteleyici relevance bozar, "Stargate SG-1 4. sezon" → yanlış sayfa); (c) **grounding/C1 backstop:** cevaptaki her olgu dönen araç metninde LİTERAL olmalı; sorulan spesifik detay yoksa scope-aware "özette yer almıyor" de, uydurma + sahte `[Wn]` YOK (#842 — output pattern-match DEĞİL, sadece input prompt); (d) **cevap biçimi:** iç süreç (kaynak yetersizliği / neden Wikipedia / kaç adım) anlatılmaz (#842 meta-leak)

**Input format (chat-style user message):**
```text
Soru: <effective_query>          # #835 — condense çıktısı (HAM mesaj DEĞİL)

## Önceki konuşma bağlamı (varsa follow-up)
- Kullanıcı: ... / Asistan: ... (Bu cevabın kaynakları: ...)

Verilen kaynaklar:
[1] <source_name> — <article_title>
<chunk_text>
---
[2] ...
```

**Output format:** Markdown Türkçe yanıt, tek `[n]` citation namespace (#851 — `[Wn]` kaldırıldı; news/wiki ayrımı `source_type` ile UI'da). Eski mesajlarda `[Wn]` render backward-compat.

**Tool-use akışı (#845 agentic + #848 çok-turlu + #851):** Tools = `[search_news, search_wikipedia]` (search_news birincil; `wikipedia.enabled=False` → sadece search_news). **MAX 3 turlu döngü:** her tur `generate_text(convo, tools=...)` **non-streaming** (#840 DSML-safe) → `decision.tool_calls` varsa dispatch (search_news: db/now/user closure → planner+embed+hybrid_search sarmalı; search_wikipedia: #842) + sonuç convo'ya → **döngü tekrar** (LLM yetersizse diğer tool'u çağırabilir — #848). `tool_calls` yoksa `decision.text` = final. MAX dolduysa toolsuz zorla cevap. Final → `_simulate_stream`. **#851 — tek `[n]` cite namespace + döngü-global sayaç** (`cite_start`/`cite_n`; `[Wn]` prefix kaldırıldı, `source_type` news/wiki ayrımını taşır; multi-round çakışma yok). **C1 referans-bütünlüğü backstop:** final cevapta citation token VAR ama `all_sources` BOŞ → kanıtlı sahte → 1× `tool_choice="required"` düzeltici tur (`_CITE_TOKEN_RE` yapısal invariant, #819 DEĞİL). **cited-only:** `sources_used` = cevapta `[n]` token'ı geçen kaynaklar; `sources_considered` = taranan tümü. Prompt (Nodrat agent, #851): evergreen sabit olgu→search_wikipedia; agentic recovery; tool çağrılmadan citation YASAK; öznel çıkarım/niteleme + imza YASAK. condense scope (#851): asistan/kimlik/meta soru topic-follow-up değil → değiştirilmez. **#854:** talimat-odaklı follow-up önceki soruyu taşır; condense+loop+tool `asyncio.wait_for` latency tavanı + zarif degrade (admin-tunable `chat.*` settings); `chat_nodrat_agent`+`chat_query_rewrite` artık PROMPT_REGISTRY'de + `prompts_store` ile admin-tunable (kod default fallback). Admin: dead confidence settings kaldırıldı; SFT/DPO/halu messages-based, agentic uyumlu (prompt_version 2.0.0). **#857:** DeepSeek non-streaming `generate_text` bazen tool-call'u DSML özel-token'ı olarak `message.content`'e basıyor (yapısal `tool_calls` boş) — `deepseek.py:_parse_dsml_tool_calls` adapter katmanında parse + normalize eder (ham XML cevaba sızmaz; agentic loop standart `tool_calls` görür). #840 "non-streaming hep yapısal" varsayımı bu adapter normalize ile tamamlandı. **#860:** gerçek prod formatı ÇİFT `<｜｜DSML｜｜...` (iki U+FF5C), #857 cleaner tek-`｜` varsaymıştı → `_DSML_MARKER_RE` artık `[｜|]+` (1+ ayraç toleranslı) + `strip_dsml_markup()` SON GÜVENLİK AĞI (format ne olursa olsun ham markup kullanıcıya gitmez) + forced-final "tool çağırma, cevap yaz" + boşsa scope-aware fallback. **#879 (temporal grounding — #845 regresyon fix):** `execute_search_news` `retrieval.py`'nin ürettiği `published_at`'i düşürüyordu; #845 prompt'a enjekte edilen "bugün" ile birleşince LLM tarihsiz haberi bugüne sabitliyordu (eski olay → "bugün"). Fix: her blok `(yayın tarihi: YYYY-MM-DD\|bilinmiyor)` + `sources[].published_at` + result_text yönergesi + `SYSTEM_PROMPT_NODRAT_AGENT` genel temporal kuralı (haber/olay zamanı = yayın tarihi, **bugün DEĞİL**; yayın≠bugün → "bugün" deme; "en son" = en yeni yayın tarihli + tarihi belirt; çoklu tarih → kronoloji; kullanıcı tarihi düzeltirse kabul). Retrieval ranking/parametre DEĞİŞMEDİ — zaten üretilen veri LLM'e iletildi. **#884 (condense açık-özne + anma≠tanım/proaktif tutarlılık):** condense scope'a 3. ayrım — `REWRITE_SYSTEM_PROMPT` **AÇIK ÖZNE İSTİSNASI**: son mesaj kendi açık öznesini içeriyor (özel ad/sayı/kod, zamir/elips DEĞİL) ise o özne standalone öznedir, önceki turun farklı entity'si öne EKLENMEZ (referans-yakınlığı yalnız zamir/elipste). #851 asistan-kimlik / #854 talimat-carry ile kardeş. + `SYSTEM_PROMPT_NODRAT_AGENT`: **"anma ≠ tanım"** (asıl konusu Z olan, X'i yalnız anan kaynak X'i tanımlamaz) + **proaktif tutarlılık** (aynı konuşmada kurulmuş olguyla çelişen yeni iddiayı sessizce kesinmiş sunma; cevap öncesi uzlaştır). Genel ilke (entity-hardcode yok); #851/#854/#842/#863/#879 scope korunur. **#888 (sohbet hafızası is_related'dan decouple — kök mimari; #884 prompt kuralının ÇALIŞMA ÖNKOŞULU):** answer LLM'e önceki konuşma bloğu (`followup_block`) eskiden yalnız `if is_related:` (embedding cosine vs önceki user mesajı, eşik 0.65) ekleniyordu → kısa/konu-evrilen follow-up'ta is_related=False → LLM hiçbir önceki turu görmez → kendi cevabıyla çelişir, #884 proaktif-tutarlılık işlevsiz kalır (context'te tutarlı olunacak veri yok). Fix: `followup_block` koşulsuz (`if _rw_ctx:` — Step 1.5 condense'in zaten koşulsuz hesapladığı context reused, ek DB yok) + OTORİTER çerçeve. `is_related` yalnız retrieval-reuse'da kalır (ayrı endişe). condense (#833) bu decouple'ı zaten yapmıştı; #888 aynı ilkeyi answer LLM'e propagate eder. **İlke:** sohbet hafızası retrieval-benzerlik heuristic'ine TABİ DEĞİLDİR; bir prompt-kuralı (tutarlılık/grounding) ancak gereken bağlam LLM context'inde gerçekten varsa bağlayıcıdır. **#1058 (cited-only HARD invariant + C1 backstop genişleme + Fix B′ force-retrieval — prod-audit conv 865e36e3):** `_CITE_TOKEN_RE` yalnız sayısal `[n]` arıyordu → pivot-sonrası bağlamlı takip ("nerede yaptı bu açıklamayı") 0 kaynakla elle `[Forbes Türkiye]` (sayısal-olmayan sahte atıf) uydurdu, C1 backstop atladı, halüsinasyon servis edildi. Fix (3 katman, flag-gated default-ON; cevap-üretim çekirdeği DOKUNULMADI): **(A)** `_is_substantive` (cevap `strip()` ≥120 char → olgusal; selamlama/kimlik/meta kısa = dışlanır) — 0 kaynak + substantive cevap sayısal `[n]` OLMASA da düzeltici tur **ve** servis öncesi sert red ("doğrulanabilir kaynak bulunamadı … kaynaksız cevap vermiyorum"); **(B′)** condense `effective_query`'yi bağlamlı yeniden yazdıysa (`_contextualized`) ilk tur `tool_choice="required"` (bellekten cevap yapısal imkânsız — kullanıcının "önceki kaynakları öncelikle"sinin risk-sınırlı hali; derin chunk-cascade DEĞİL, eval-gate'li ertelendi); **(C)** `format_context_block(..., include_sources=False)` — condense bağlamına önceki cevabın kaynak ADLARI SIZMAZ (uydurma atıf tohumu; condense SÖZLEŞMESİ korunur, legacy birebir yalnız opt-in `include_sources=True`, çağıran yok → byte-eş). Settings: `research.cited_only_strict` / `research.followup_force_retrieval` (default True). C1 hâlâ yapısal token-kontrolü (#819 ifade-eşleştirme DEĞİL) — yalnız biçim-dar (`[n]`) → substantive-eşik eklendi. Detay: [[wiki:research-cited-only-hard-invariant]] (prod Playwright doğrulandı). **#1059 (retrieval aşama şeffaflığı — gözlem-only):** agentic loop'a 6 ek `_log_step` (yalnız SSE `thinking_step`; kontrol-akışı/cevap/citation invariantı DEĞİŞMEZ): `retrieval_forced` (Fix B′), `grounding_retry` (C1 düzeltici tur), `tool_result` (tur başına bulunan kaynak), `citation_filter` (cited-only N/M), `cited_only_refused` (#1058 hard-refuse), `generating`. `ThinkingPanel` PHASE_LABEL/ICON yayılan tüm fazları okunur Türkçe etiketle gösterir (`thinking_steps` JSONB freeform/enum-suz → geçmiş persist mesajlar da düzelir; geri-uyumlu). Kullanıcının istediği 3-kademeli chunk-cascade DEĞİL (eval-gate'li ayrı iş; panel aşama-güdümlü → ileride ekstra UI işi gerekmez). Detay: [[wiki:research-retrieval-transparency]]. **#1067 (RC3 — cited-only/grounding HARD invariant 0-kaynak→dolaylı-kaynak GENELLEMESİ):** #1058 yalnız 0-kaynağı kapsıyordu. Prod-teşhis (conv quirky-gates Q4): KAYNAK VAR ama ana iddia kaynak metinde DOĞRUDAN yok — "Özel'in Kocaeli iddiası neydi", korpusta yalnız Çelik **reddiyesi** (Özel'in iddiası YOK); model "tepkisinden **anlaşıldığı kadarıyla** Özel … iddiada bulunmuş" geriye-çıkarsama. #1058 yakalamaz (1 kaynak); cosine-validator yakalamaz (anma≠tanım, topical-benzerlik yüksek). **Hibrit C:** (A) `SYSTEM_PROMPT_NODRAT_AGENT` §Halüsinasyon "anma≠tanım" genişletildi → X'in iddiası Y'nin tepkisinden ÇIKARSANMAZ; "anlaşıldığı kadarıyla/tepkisinden anlaşıl…" YASAK + iç-süreç sızıntısı yasağı ("arama sonuçlarında…"). (B) `_verify_primary_grounding` — ayrı hafif async dayanak-denetçisi (`_generate_followups` deseni, cheap tier, saf `_parse_faithfulness_verdict` DIRECT/INDIRECT/UNSUPPORTED en-katı-kazanır; kanıt = tool-result metni — kaynak kartında metin YOK #845); INDIRECT/UNSUPPORTED → #1058'i genelleştir: dürüst kapsam-sınırı (rekonstrüksiyon engellenir) + `faithfulness_reframed` step. `asyncio.wait_for`+except→DIRECT (degrade-safe). #1058 ile karşılıklı dışlayan (`not all_sources` vs `all_sources`). Flag `research.faithfulness_guard_enabled` default-ON; flag-off byte-eş; cevap-çekirdeği DOKUNULMADI; verifier ham çıktı ana cevaba giremez (#819/#840). **RC2 (kapsama-boşluğu telemetri):** RC3-B (`indirect:VERDICT`) + #1058 (`zero_source`) noktalarında greppable `coverage_gap reason=… q=…` `logger.warning` (observability-only — cevap/şema/akış DOKUNULMAZ, `contextlib.suppress`, q-trunc; korpus kodla tamamlanamaz → ÖLÇÜLÜR). **#1073 hotfix:** `logger.info` prod effective-WARNING'de sızıyordu (telemetri görünmez) → `logger.warning` (canlı-doğrulama ile yakalandı; ders: telemetri eklemek yetmez, emit-edildiğini doğrula). Prod Playwright/log doğrulandı. RC1 (L1 Gate-1 `is_standalone_query` sıralama) ayrı — bu §4 cevap-kontratı dışı, [[wiki:l1-recency-anchored-context]]. Detay: [[wiki:research-cited-only-hard-invariant]]. **#1076 RC3-B v2 — LLM-verifier → yapısal marker-detect (DÜRÜST REVİZE; kullanıcı prod'da yakaladı):** #1067 RC3-B'nin v1 yaklaşımı (`_verify_primary_grounding` cheap-tier LLM verifier + `_parse_faithfulness_verdict` DIRECT/INDIRECT/UNSUPPORTED) **prod son 90dk: 4/8 yanlış-pozitif** (agenda "Bugünkü gündemde ne var?" 10-source, aggregate "Özel dün neler yaptı" 20-source, topic-partial "Çocukların bahis çalışması var mı" 8-source Gürlek-doğrudan, single-direct "Özel bugün neler yaptı" 1-doğrudan) — LLM-verifier "ana iddia tek-iddia" varsayımıyla multi-claim/aggregate sınıflarını modellemiyor; NLP-faithfulness LLM-only judgment kanıtlı **calibration-fragile** (literatür: NLI-fine-tune yokken structural rule doğru araç). **Kritik bulgu:** 4 yanlış-pozitifin hiçbirinde rekonstrüksiyon-marker'ı YOKtu; Özel/Çelik orijinalinde "anlaşıldığı kadarıyla" VARDI → marker doğru sinyali. **v2 (#1077 — TESLİM):** `_verify_primary_grounding`+`_parse_faithfulness_verdict`+`_FAITHFULNESS_VERIFIER_PROMPT`+`_FAITHFULNESS_TIMEOUT_S` SİL; `_RECONSTRUCTION_MARKER_RE` ("anlaşıldığı kadarıyla / tepkisinden anlaşıl / olduğu anlaşılıyor / tepkisine bakılırsa / anlaşıldığına göre / yansıdığı kadarıyla / olduğu sanılıyor / muhtemelen X demiş") + saf `_has_reconstruction_marker` EKLE. Gate: marker var → reframe + `faithfulness_reframed` + `_log_coverage_gap("reconstruction_marker", q)`. Cheap (LLM call YOK), deterministik, calibration-stable. **Prod-kanıt 5 Playwright testi:** 4 yanlış-pozitif sorgu yeniden = `reframed=false` hepsi, gerçek grounded cevap (`031ba46a`/`16226b20`/`98098a80`/`8f08dbeb`); 5. Özel/Kocaeli (reconstruction-risk) bu sefer LLM RC3-A prompt'a sadık (anma≠tanım davranışı, marker yok → doğru cevap). AST proof 13/13 (6 reconstruction varyantı yakalanır + 4 yanlış-pozitif sınıf FIRE-etmez + 3 edge-safe); API eval golden yeşil; #1058 ile karşılıklı dışlayan; flag adı korunur. **Ders:** "yaptım" yetmez — test seti prod-çeşitliliği temsil etmeli (sınıf-temelli); genel-amaçlı LLM faithfulness-judgment'lar calibration-fragile (Goodhart-law prompt-tweaking'e); yapısal regex doğru araç. Detay: [[wiki:research-cited-only-hard-invariant]] (v1→v2 callout).

**X-Post farkı:** `SYSTEM_PROMPT_X_POST` JSON döner (legacy). Chat varyantı markdown, single yanıt.

---

## 4.y Prompt #3c — Conversational Query Rewrite (condense, #833)

Multi-turn follow-up mesajını planner'dan ÖNCE standalone arama sorgusuna çevirir (Perplexity/LangChain "condense question" standardı). Planner SYSTEM_PROMPT preserve-first kuralı follow-up rewriting'i engellediği için izole adım gerekli (#832 plan_input enrichment başarısızlığı).

**Source:** `apps/api/app/prompts/query_rewrite.py:REWRITE_SYSTEM_PROMPT`

**Tetikleyici:** `_chat_stream_body` Step 1.5 — conversation context VARSA (multi-turn). İlk mesajda atlanır (ekstra LLM call yok).

**Sözleşme:**
- Input: konuşma geçmişi (content + assistant kaynak özeti) + son ham mesaj
- Output: tek satır standalone Türkçe arama sorgusu (açıklama/tırnak YOK)
- **Referans yakınlığı:** atıf konuşmanın en geniş konusuna değil, EN SON odaklanılan spesifik özneye (en yakın antecedent — #838)
- **Disambiguation:** aynı-ad çakışmasında ayırt edici bağlam ekle (geçmişteki anlam korunur)
- Multi-turn dayanıklı (3+, 5+ tur): her turda en son spesifik özneyi izler
- Müstakil soruda minimal dokunuş
- Provider: chat-capable (DeepSeek), `max_tokens=80`, `temp=0.3`, ~300-500ms

**effective_query akışı:** condense çıktısı planner (`plan_query`) + retrieval (`query_text`/embed) + `gen_user_msg` "Soru:" + tool query'ye tutarlı akar (#835 — bir yerde ham kalırsa bağlam kopar).

---

## 4.z Prompt #3d — Query Clarification (0-kaynak niyet-anlama, #1701)

Korpusta dayanak kaynak bulunamayan (0-kaynak) / anlaşılmayan sorguda, bland "bulamadım" yerine kullanıcının NİYETİNİ anlamaya çalışıp kısa açıklama + 2-3 netleştirme önerisi üretir. [Cited-only invariant](../../wiki/decisions/research-cited-only-hard-invariant.md) gereği 0-kaynakta uydurma cevap yasak; bu prompt o boşluğu **citation-safe** netleştirmeyle doldurur.

**Source:** `apps/api/app/prompts/query_clarification.py:SYSTEM_PROMPT` (+ `parse_clarification`); çağıran `modules/generations/query_clarification.py:generate_clarification`.

**Tetikleyici:** `app_research_stream` 0-kaynak bloğu — `_cited_only_strict` **VE** `not all_sources` **VE** `_is_substantive(final_text)` + flag `research.clarification.enabled` (ON). Geniş korpus çoğu sorguya tangential kaynak bulduğundan gerçek-0-kaynak nadir (aksi halde cited-only dürüst-refüze devrede).

**Sözleşme:**
- Input: `render_user_payload(query)` — yalnız ham sorgu (korpus dayanağı yok bilgisiyle).
- Output **satır-bazlı** (JSON DEĞİL — küçük-model JSON güvenilmezliği #819/#840): `MESAJ: <1-2 cümle açıklama + olası niyet>` + `- <öneri>` satırları. `parse_clarification` tolerant: MESAJ yoksa ilk düz satır mesaj; öneriler dedupe + limit 3; mesaj yoksa None (caller degrade eder).
- **Kurallar:** ASLA olgusal cevap/tarih/sayı UYDURMA (yalnız netleştirme + öneri); öneriler kullanıcının ağzından somut yeniden-ifade; typo düzelt ("kuantm"→"Kuantum"); asistan-jargonu/editoryal dil YOK (#851/#958).
- Provider: chat-capable (DeepSeek v4-flash), `max_tokens=300`, `temp=0.4`, `asyncio.wait_for` 10s; best-effort cost-log (`operation="clarification"`). Prompt admin-tunable (`prompts_store("query_clarification")`, kod fallback).
- **Gösterim:** `final_text`=mesaj; öneriler **`followup_suggestions`** SSE slotuna (mevcut chip mekanizması; yeni event/frontend YOK). Bkz. `wiki/concepts/zero-source-clarification.md`.

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

### 7.1.1 Changelog

**Content Generator**

| Sürüm | Tarih | PR / Issue | Değişiklik | Bump |
|---|---|---|---|---|
| v1.0.0 | 2026-05-01 | initial | İlk yayın — X Post / Thread / Comparison / Summary / Headline variant'ları | — |
| **v1.1.0** | **2026-05-08** | [#392](https://github.com/selmanays/nodrat/issues/392) / [PR #418](https://github.com/selmanays/nodrat/pull/418) | 4 SYSTEM_PROMPT_* (X_POST/SUMMARY/THREAD/HEADLINE) tamamen STATIC: `{max_posts}` / `{item_count}` placeholder'ları kaldırıldı. Sayı bilgisi `user_payload.output_constraints.max_posts`'tan okunur. Tone instruction dynamic append KALDIRILDI; rule 10 kanonik 9-tone tablosu. Kural 13 alaka kontrolü zorunlu hale getirildi. **Hedef:** DeepSeek implicit prompt cache hit ratio ≥%40, content top_k 10→5 ile birlikte ~$/req -%25. **Eval-gated:** halü <%2 + citation accuracy ≥%95 production monitor. | MINOR |

**Query Planner / Agenda Card Generator**

v1.0.0 (2026-05-01) — değişiklik yok. PROMPT_VERSION sabit 1.0.

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

## 9b. Pivot — Editöryal Ton + Listeleme Kuralı (Faz 1/4)

> Plan rev.12. `SYSTEM_PROMPT_NODRAT_AGENT` (research_answer.py) STATIC
> invariant korunur — yalnız `{current_date}` placeholder (#981
> implicit prompt-cache prefix bozulmaz). prompts_store → eval → kod
> default (#854 deseni).

**Faz 1 (#1023) — editöryal ton:**

- Asistan/sohbet nezaket kalıpları **YASAK**: "Elbette", "Tabii ki",
  "Harika soru", "Umarım yardımcı olmuştur", "yardımcı olayım".
- **Kapsam-dışı / asistan-dışı istek** → genel asistana DÖNÜŞME;
  "haber ve gündem araştırma kapsamı dışında" yumuşak yönlendirme
  (Karar bloğu item 6; rule 5 SONRASI, Halüsinasyon ÖNCESİ).
- Opsiyonel editöryal başlıklar ("Öne çıkan gelişme", "Kaynakların
  aktardığına göre") — **ZORUNLU kalıp DEĞİL** ("sabit şablon YOK"
  kuralıyla çelişmez).
- Legacy `SYSTEM_PROMPT_CHAT_ANSWER`: "araştırmacı asistanısın" →
  "araştırma motorusun".

**Faz 4 (#1029) — geçmiş istenirse:** kendi geçmişini SENTEZLEME/
UYDURMA YASAK → L3 listeleme servisine yönlendir; "sahte geçmiş =
marka ihlali" çerçevesi (Karar bloğu item 7). Mevcut C1/grounding
omurgası (#958/#964/#842/#967/#970) KORUNDU — regresyon yok
(eval-golden #851/#928/#888/#884 yeşil).

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

MVP-2.1 Pipeline Performance Optimization (Epic #391, kapanış 2026-05-08):
  Content Gen v1.0.0 → v1.1.0    → §4 + §7.1.1 changelog
  #392 prompt prefix stability   → §4.3 SYSTEM_PROMPT static + cache hit ≥%40
  #393 content top_k 10 → 5      → §4.1 retrieval section
  #394 citation batch            → cost_tracker / citation.py (kod-only)
  #395 settings request-cache    → settings.py (kod-only)
  #396 short query rerank skip   → retrieval.py (kod-only)
  #397 normalize dedup           → retrieval.py (kod-only)
  #398 citation embedding reuse  → citation.py (kod-only)
  Sub-issues: #392-#398 (7/7 closed)
  PR'lar: #411 + #416 + #418 (3 batch)
  Tracking: wiki/topics/pipeline-performance-baseline.md
```

---

**Sonuç:** Üç çekirdek prompt **versioned + schema-validated + halu-checked**. Eval framework golden test set + LLM-as-judge + manuel review üçlüsünde çalışır. **Halüsinasyon < %2** hedef, **citation %100** zorunlu — bu iki metrik düşerse R-PRD-01 mitigation devreye girer (prompt revize). **Provider routing tier'a göre** (DeepSeek default, Haiku premium, Sonnet sadece Agency comparison). **Faz 4-5 yardımcı promptlar** Image Caption KVKK-uyumlu (kişi tanımlama yok), Style Analyzer telifli alıntı yapmaz.
