---
type: decision
title: "Türkçe-collation entity match (C-locale LOWER bug)"
slug: "turkish-collation-entity-match"
category: "rag"
status: "locked"
decided_on: "2026-05-17"
decided_by: "tech"
created: "2026-05-17"
updated: "2026-05-17"
sources:
  - "apps/api/app/core/retrieval.py§critical_entities-RESCUE-FILTER"
  - "GitHub Issue #939 / PR #940 / epic #927"
tags: ["locked-decision", "rag", "retrieval", "turkish", "collation", "entity", "927-family"]
aliases: ["c-locale-lower-bug", "tr-TR-x-icu-collate"]
---

# Türkçe-collation entity match (C-locale LOWER bug)

> **Karar:** `critical_entities` RESCUE/FILTER'daki tüm `LOWER(x)` çağrıları `LOWER(x COLLATE "tr-TR-x-icu")` olur — PostgreSQL C-locale `LOWER()` Türkçe büyük harfleri (Ö Ü Ç Ş Ğ İ) küçültmediği için Türkçe entity exact-match'i tamamen çöküyordu.
> **Durum:** locked
> **Tarih:** 2026-05-17

## Bağlam — sorun

Prod conv 2f70db85/74eecc15: "Özgür özelle ilgili son haberler" → kullanıcının verdiği 3 gerçek Evrensel haberi (14-15 May, DB'de `cleaned`+embedded, başlıkta açık "Özgür Özel") retrieval'a **gelmiyor**; sistem 3 May Karabük (14g eski) veriyordu.

**Kök neden (kanıtlı, prod):**
- Veritabanı **C-locale** (`datcollate=C datctype=C`). PostgreSQL C-locale `LOWER()` yalnız ASCII a-z küçültür; Türkçe büyük harfleri (Ö Ü Ç Ş Ğ İ) **olduğu gibi bırakır**: `lower('Özgür Özel')` = `'Özgür Özel'`; `'özgür özel' = lower('Özgür Özel')` → **False**.
- `critical_entities` RESCUE/FILTER: `LOWER(a.title||subtitle||clean_text) LIKE :ent`. `:ent` Python `.lower()` ile tam küçük ("özgür özel"), SQL tarafı C-locale → "Özgür Özel" (büyük kalır) → **ASLA eşleşmez**. Türkçe-karakterli her entity (Özgür Özel, Çin, İzmir, Şahin, Hürmüz, 15 Temmuz…) bu "kesin kurtarma" katmanında kaçıyordu.
- Prod kanıt: 5 test haberi RESCUE LOWER LIKE = **False (5/5)**; tr-collation simülasyonu `lower(... COLLATE "tr-TR-x-icu") LIKE '%özgür özel%'` = **True (5/5)**.
- "3/10 May haberleri nasıl bulunuyordu?" (kullanıcının tutarlılık sorusu) → RESCUE'dan DEĞİL **dense embedding**'den (Türkçe-bağımsız vektör yolu, cosine 0.41-0.50). RESCUE 5 haberin hiçbirini yakalamıyordu (3 May dahil); 3/10 May dense'in zayıf sıralamasında öne çıkmıştı.

> ⚠️ **Üç deneme:** İlk iki teşhis ("coverage boşluğu" → title-only sorgu; "veri yok" → C-locale `chunk_text ILIKE` yine yanlış) **kullanıcının sezgisiyle çürütüldü** ("mümkün değil haber olmaması"). Kök ancak kullanıcı gerçek URL verince + tr-collation simülasyonuyla bulundu. Ders: yüzeysel SQL sorgusu (LIKE/ILIKE) C-locale'de Türkçe'de **kendisi de kırık** — teşhis aracı buggy olunca yanlış sonuç verir.

## Karar — `LOWER(x COLLATE "tr-TR-x-icu")`

`retrieval.py` critical_entities MUST_MATCH bloğu, 4 nokta (RESCUE `title||clean_text LIKE` + RESCUE keyword `LIKE`; FILTER `~*` + FILTER keyword `=ANY`): `LOWER(x)` → `LOWER(x COLLATE "tr-TR-x-icu")`. Operatör/mantık DEĞİŞMEZ. ICU `tr-TR-x-icu` collation prod'da mevcut (kanıt: `lower('Özgür Özel' COLLATE "tr-TR-x-icu")` = `'özgür özel'`).

**Kapsam DAR (kullanıcı onaylı — epic #927 ilk teslimat):** Yalnız kanıtlanan RESCUE/FILTER. Sparse `meta_norm` ILIKE, agenda `title_norm`, keyword path aynı C-locale sınıfı ama Python pre-normalize (`normalize_tr_query` `.lower()` Türkçe-doğru) ile kısmen örtülü → ayrı denetim+teslimat (#927).

> **#927 Faz-A (2026-05-18, PR #985) — agenda-card sparse path:** `retrieval.py:878-880` `title_norm_sql`/`summary_norm_sql`/`canon_norm_sql` → `LOWER(<quote-strip> COLLATE "tr-TR-x-icu")` (#939 RESCUE pattern birebir; `_build_sql_quote_strip` korunur, Python `:q`/`:phrase` zaten `.lower()` → değişmez; RRF/similarity/parent-doc DEĞİŞMEZ). V2 benchmark agenda-card'ı ölçmez (kod-doğrulandı: `niche_chunks_benchmark_v2` yalnız `hybrid_search_chunks` — D2) → **prod-trace mechanism smoke**: canlı prod DB `LOWER(title) LIKE '%özel%'` = **39** vs `LOWER(title COLLATE "tr-TR-x-icu")` = **132** (+93); `%çin%` 746→905 (+159) → Türkçe-uppercase entity'ler artık agenda-card'da görünür. 86 retrieval pytest yeşil. Kalan #927: meta_norm + keyword (Faz-B), Wikidata-alias (Faz-C), stemmer-spike (Faz-D).

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| DB-wide collation değiştir (C → tr-TR/ICU) | Sistemik kök | initdb/dump-restore, tüm index rebuild, devasa risk/kesinti | reddedildi |
| Python `unaccent`/translate map (SQL fonksiyon) | Bağımsız | extension yok; ASCII-leştirme entity-anlamı bozar | reddedildi |
| "Esnek arama" (token-AND: özgür VE özel ayrı) | Sezgisel | Precision felaketi (prod: 15 alakasız çöp — Hürmüz/Trump/DEM) | reddedildi |
| **Hedefli `COLLATE "tr-TR-x-icu"` (RESCUE/FILTER)** | Dar, kanıtlı, evergreen, index-nötr, geri-alınabilir | Diğer LOWER noktaları ayrı teslimat ister | **seçildi** |

## Sonuçlar

- **Benchmark (prod-parity, niche_chunks_v2):** baseline recall@5 **0.636→0.727**, recall@10 **0.818→0.909** (+%9, regresyon YOK), avg_latency 40.9s→37.5s. `niche_009` ("15 Temmuz" — Türkçe entity) **NF → rank#9 kurtarıldı**; `niche_003` #6→#3. `niche_007` ("abd↔Amerika" synonym) hâlâ NF — bu Türkçe-collation değil synonym sınıfı (#927 sonraki teslimat).
- **Prod smoke:** "Özgür özelle ilgili son haberler" → kullanıcının verdiği Evrensel 15 May haberleri ([5] "Özkan Yalım Özgür Özel ifade", [7] "Özgür Özel'den Özkan Yalım yazışması") artık sonuçlarda; `newest_published_at` 2026-05-03 → **2026-05-16**, `freshness_gap_days` 6-14 → **1**.
- **niche_007/009 yeniden çerçeveleme:** [[failed-experiments-rag-quality]]'de "entity-synonym broken, query rewriting gelecek sprint" diye yıllardır dökümante problem — kısmen (Türkçe-entity tarafı) bu C-locale bug'ıydı; #939 ile niche_009 kurtarıldı.
- Etkilenen: [[chunks-first-retrieval]] (critical_entities RESCUE/FILTER), [[critical-entity-must-match]] (#778 — Türkçe-doğru artık), [[chat-knowledge-evolution]] (ders #28), epic #927 (ilk teslimat).

## Geri alma maliyeti

> `retrieval.py` 4 noktada `COLLATE "tr-TR-x-icu"` kaldır → C-locale bug geri döner (Türkçe entity RESCUE/FILTER çöker, recall@10 0.909→0.818). Index/şema/migration etkisi YOK (yalnız sorgu-içi collate); geri alma tek commit.

## İlişkiler

- [[chunks-first-retrieval]] — critical_entities RESCUE/FILTER bu sayfanın bloğu
- [[critical-entity-must-match]] — #778 MUST_MATCH; Türkçe entity artık doğru eşleşir
- [[failed-experiments-rag-quality]] — niche_007/009 ailesi; gerçek kök kısmen budur
- [[chat-knowledge-evolution]] — #939 satırı + anti-pattern ders #28
- [[news-timeframe-retrieval-contract]] — #928/#929 (Ç2-Ç5) ile aynı conv ailesi (74eecc15)
- [[planner-critical-entity-tr-guard]] — #942/#945, **sorgu-tarafı eş**: bu sayfa haber-tarafını (DB C-locale) çözer; o sayfa planner LLM'in entity'yi Türkçe ek+noktalama'da kelime-kesmesini (prompt+kod backstop) çözer. İkisi birlikte Türkçe entity match uçtan uca.
- [[llm-tool-use-wikipedia]] — #967 `_wiki_norm_title` bu dersi (TR `İ`→`i`, `I`→`ı`, U+0307; Python `lower()` TR-bilmez) Wikipedia kanonik-başlık eşleştirmesinde **Python-side** yeniden uygular: collation tuzağı DB-only değil, string-karşılaştıran her yeni kodun ortak gereği.

## Kaynaklar

- [Issue #939](https://github.com/selmanays/nodrat/issues/939) · [PR #940](https://github.com/selmanays/nodrat/pull/940) · epic [#927](https://github.com/selmanays/nodrat/issues/927)
- [`apps/api/app/core/retrieval.py`](apps/api/app/core/retrieval.py) — critical_entities RESCUE (STAGE 1) / FILTER (STAGE 2)
- Prod kanıt: 5-haber RESCUE False→True; benchmark baseline/fixed (`/tmp/bench_baseline.json`, `/tmp/bench_fixed.json`)
