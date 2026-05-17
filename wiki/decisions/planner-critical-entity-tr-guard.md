---
type: decision
title: "Planner critical_entities Türkçe kelime-kesme guard (prompt + kod backstop)"
slug: "planner-critical-entity-tr-guard"
category: "rag"
status: "locked"
decided_on: "2026-05-17"
decided_by: "tech"
created: "2026-05-17"
updated: "2026-05-17"
sources:
  - "apps/api/app/prompts/query_planner.py§SYSTEM_PROMPT-CRITICAL_ENTITIES"
  - "apps/api/app/prompts/query_planner.py§parse_response-backstop"
  - "GitHub Issue #942/#944 / PR #943/#945 / epic #927"
tags: ["locked-decision", "rag", "planner", "turkish", "entity", "prompt", "backstop", "927-family"]
aliases: ["critical-entities-stemguard", "planner-tr-word-cut"]
---

# Planner critical_entities Türkçe kelime-kesme guard (prompt + kod backstop)

> **Karar:** Planner LLM `critical_entities`'i Türkçe çekim eki + noktalama karşısında kelime-ortasından kesiyor ("özelle"→"özgür **öz**"). İki katman: (1) prompt kuralı + Türkçe few-shot, (2) kod backstop — entity token'ı ham sorguda TAM kelime veya TR-ek-soyulmuş kök değilse düş.
> **Durum:** locked · **Tarih:** 2026-05-17 · epic #927 (sorgu-tarafı; [[turkish-collation-entity-match]] #939 haber-tarafı eş)

## Bağlam — sorun

conv 72fc9b64/d6a30359/2f70db85 (#940 deploy SONRASI denetim): "Özgür özelle ilgili son haberler nedir???" **ilk soruda** hâlâ 3 May (eski) veriyor; itiraz turunda (condense temizlenmiş sorgu) 15-16 May zengin doğru geliyor → **"ilk soru yanlış / itiraz doğru" tutarsızlığı**.

**Kök neden (kanıtlı, prod `plan_query`):** Planner LLM, ham sorgudaki Türkçe çekim eki + noktalama karşısında entity'yi kelime-ortasından kesiyor:

| Sorgu | critical_entities |
|---|---|
| "Özgür **özelle** … nedir**???**" | `['özgür öz']` ❌ ("özel"→"öz" kesme) |
| "Özgür Özel son haberler" | `['haberler','özgür']` ❌ ("özel" kayıp) |
| "Özgür özelle ilgili son haberler nedir" | `['özgür özel']` ✓ |

Bozuk entity ('özgür öz') → [[turkish-collation-entity-match]] (#940) ile düzeltilmiş RESCUE/FILTER **bile** eşleştiremez ("özgür öz" hiçbir haberde yok) → 3 May fallback. Condense'li (itiraz) turlar daha temiz sorgu → bazen doğru entity → tutarsızlık. **#940 (haber-tarafı C-locale) ÇALIŞIYOR** (kanıt: itiraz turlarında 15-16 May zengin geliyor); bu AYRI cephe — **sorgu-tarafı entity çıkarımı**.

## Karar — iki katman (#906 dersi: prompt olasılıksal → kod-backstop şart)

1. **Prompt** (`SYSTEM_PROMPT` §CRITICAL_ENTITIES, PROMPT_VERSION 1.4.0→1.5.0): "Sorgudaki kelimeyi BÖLME/KESME. Türkçe çekim ekini (-le/-de/-nin/-e…) atabilirsin ama kökü bozma" + Türkçe few-shot (özelle→özel DOĞRU, özel→öz YANLIŞ, İmamoğlu'nun→imamoğlu, depremde→deprem).
2. **Kod backstop** (`parse_response(user_request opsiyonel)`): her entity token'ı ham sorguda **TAM kelime** (`token in qwords` — her uzunlukta) **VEYA** bir sorgu-kelimesinin **TR-ek-soyulmuş kökü** (`_TR_SUFFIXES` pragmatik set; len≥3 yalnız bu dalda — kısa kök yanlış-pozitif) olmalı; değilse entity düş + `critical_entity_dropped_not_grounded` warning. `user_request=None` → atlanır (geriye-uyumlu). Kompound'da HER token grounded olmalı. Bonus: `'İ'.lower()` = i + U+0307 (combining) → kelime-bölünmesi düzeltildi (prod'da da etkili: "İmamoğlu'nun").

RRF / #940 / retrieval mantığı **DEĞİŞMEZ**. Türkçe stemmer YOK (retrieval.py:1242) → pragmatik ek seti, mükemmel stemmer değil (backstop amacı: yarım-kök/uydurma elemek, doğru kökü garanti etmek prompt'ın işi).

## Alternatifler

| Alternatif | Karar |
|---|---|
| Yalnız prompt | reddedildi — LLM olasılıksal, bazen yine "özgür öz" (#906 dersi) |
| Yalnız kod backstop | reddedildi — kötüyü eler ama doğruyu üretmez (boş ce → filter yok) |
| Gerçek TR stemmer (zemberek/snowball) | ertelendi — büyük bağımlılık, ayrı iş (#927 ileri) |
| **Prompt + kod backstop (iki katman)** | **seçildi** — prompt doğru üretme şansını artırır, kod kötüyü kesin yakalar |

## Sonuçlar

- **Prod smoke:** "Özgür özelle ilgili son haberler nedir???" → `critical_entities=['özgür özel']` ✓ (önce `['özgür öz']`); **ilk soruda** 15-16 May Evrensel ([5] Özkan Yalım/Özgür Özel, [7] Özgür Özel yazışması), `newest_published_at` 3 May→**16 May**, `freshness_gap` 6-14→**1**. Tutarsızlık çözüldü.
- **Benchmark (prod-parity niche_chunks_v2):** recall@5 **0.727 korundu** (post-#940 ile aynı), mrr@10 0.557→**0.566** (sıralama iyileşti), regresyon yok.

> ⚠️ **#944/#945 regresyon dersi (benchmark-guard yakaladı):** İlk backstop (#942/#943) `_token_grounded` min-len kontrolü tam-kelime eşleşmesini de reddedip `niche_009` "**15** temmuz" entity'sini ("15" 2 char) düşürdü → recall@10 0.909→0.818. **Fix #945:** tam-kelime eşleşmesi (`token in qwords`) min-len'den BAĞIMSIZ; len≥3 yalnız kök-türetme dalını korur. recall@5 0.727'ye geri döndü, ce='15 temmuz' korunuyor (smoke kanıt). niche_009 recall@10'daki #9↔NF oynaması **critical_entities-bağımsız HyDE varyansı** (golden notes: hedef article'da "15 temmuz"/"mağdur" literal YOK → RESCUE/FILTER yapısal etkilemez; #939'da da NF'ydi, #940 şanslı #9). Ders: backstop guard'da "uydurma elemek" ile "meşru kısa/sayısal token'ı korumak" dengesi — tam-eşleşme her zaman üstün; benchmark-guard tek-PR regresyonu yakalar, "düşmemeli" sözü ölçümle doğrulanır.

> 🔧 **#947 — backstop "düşür"→"KÖKLEŞTİR" (3. iterasyon, conv 06a034cf):** #945 deploy 2h sonra "Özgür özelle ilgili son gelişmeler neler" ilk-soru yine 3 May. plan_query 4× → `['özgür özel']`×1 / **`['özgür özelle']`×3** — LLM kelime-KESMEYİ bıraktı (#942 çözdü) ama entity'yi çekim-EKLİ üretiyor ("özelle"). `_token_grounded` "özelle"yi ham sorguda TAM kelime görüp KABUL ediyordu (düşürmüyor, kökleştirmiyor) → RESCUE `LIKE '%özgür özelle%'` clean_text'teki "Özgür Özel" ile eşleşmez → eski haber. **Fix:** `_token_grounded`/`_entity_grounded` → `_canonical_token`/`_entity_canonical` (bool→str|None): TAM kelime + TR-ek ise KÖK döndür ("özgür özelle"→"özgür özel"); kelime-kesme (öz)→None düş; eksiz/sayısal aynen ("15 temmuz" #944 korunur). `parse_response` `critical_entity_stemmed:X->Y` warning + kök append. PROMPT_VERSION 1.5.0→**1.6.0**, prompt §CRITICAL_ENTITIES "kök-form ZORUNLU, ekli YASAK" + few-shot.
>
> ⚠️ **Over-stem felaketi öngörülüp önlendi:** `_TR_SUFFIXES` (geniş — grounding dalı) kökleştirmede kullanılsaydı tek-harf ünlü eki (-a/-ı/-ya) "rusya"→"rus", "gazze"→"gazz", "boğazı"→"boğaz" tüm özel-adları bozardı (recall felaketi). Ayrı **DAR `_STEM_SUFFIXES`** (ünsüz-başlı/belirgin çekim: ler/den/de/le/nin/lik… tek-harf ünlü HARİÇ) → "özelle"→"özel" olur ama "rusya"/"boğazı" korunur. Tasarım anında "bu kural neyi yanlış bozar?" sorusu (ders [[chat-knowledge-evolution]] #30). **Benchmark: recall@5 0.727 KORUNDU (post-#945 aynı; 5 iterasyon boyunca sabit), niche_008 "hürmüz boğazı" #7 korundu (over-stem yok); mrr 0.493 HyDE-varyans. Prod smoke: plan_query 3× kararlı `['özgür özel']`, execute_search_news newest 3 May→17 May.** Eş B: [[planner-cache-key-v2]] (#947 — cache key PROMPT_VERSION; bu fix'in canlıya anında yansımasının önkoşulu).

## Geri alma

> `parse_response` `user_request` çağrısını kaldır (None) → backstop atlanır; PROMPT_VERSION düşür → prompt kuralı geri. Şema/migration yok; tek commit.

## İlişkiler

- [[turkish-collation-entity-match]] — #939, aynı epic #927, **haber-tarafı eş** (DB C-locale); bu sayfa **sorgu-tarafı** (planner LLM). İkisi birlikte Türkçe entity match'i uçtan uca düzeltir.
- [[critical-entity-must-match]] — #778 MUST_MATCH; backstop bu entity'lerin kalitesini garanti eder
- [[conversational-query-rewriting]] — condense'li turlar daha temiz sorgu → tutarsızlığın "itiraz doğru" tarafı bu sayfanın bağlamı
- [[chat-knowledge-evolution]] — #942/#947 satırları + anti-pattern ders #29/#30
- [[chunks-first-retrieval]] — critical_entities RESCUE/FILTER tüketicisi
- [[planner-cache-key-v2]] — #947 B (cache key PROMPT_VERSION): bu sayfanın A-fix'i cache PROMPT_VERSION'suz olduğu için canlıya 24h gecikmeli yansıyordu; B önkoşul

## Kaynaklar

- [Issue #942](https://github.com/selmanays/nodrat/issues/942) / [#944](https://github.com/selmanays/nodrat/issues/944) · [PR #943](https://github.com/selmanays/nodrat/pull/943) / [#945](https://github.com/selmanays/nodrat/pull/945) · epic [#927](https://github.com/selmanays/nodrat/issues/927)
- [`apps/api/app/prompts/query_planner.py`](apps/api/app/prompts/query_planner.py) — SYSTEM_PROMPT §CRITICAL_ENTITIES, `_token_grounded`/`_entity_grounded`/`_norm_words_tr`, `parse_response`
- Prod kanıt: plan_query ce çıktıları (özgür öz→özgür özel); benchmark baseline/942/945
