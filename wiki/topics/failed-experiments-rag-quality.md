---
type: topic
title: "RAG kalite denemelerinde başarısız 4 deneme — öğrenme kataloğu"
slug: "failed-experiments-rag-quality"
status: "live"
created: "2026-05-14"
updated: "2026-05-18"
tags: ["learning", "experiments", "rag", "anti-patterns"]
aliases: ["denenmis-basarisizlar", "rag-rerank-failures"]
---

# RAG kalite denemelerinde başarısız 6 deneme

> **Amaç:** Aynı yaklaşımları yeniden denemeyi önleyen ders kataloğu. Niş entity recall problemleri için "şunu deneyelim?" sorusu çıktığında ilk bu sayfa kontrol edilmelidir.

## Başarısız denemeler özeti

| # | Deneme | Tarih | Hipotez | Sonuç | Sebep |
|---|---|---|---|---|---|
| 1 | **Cross-encoder rerank** | #758 (2026-05-12) | NIM mistral-4b + bge-reranker-v2-m3 ile top-K reorder kalite artırır | NDCG 0.627 → 0.509, recall 8/11 → 7/11 | Target zaten top-K dışında — rerank ne sıralasın? |
| 2 | **Sub-chunk indexing** | #769 (2026-05-13) | Chunk'ları 2-4 mikrochunk'a böl, semantic dilution azalır | Recall 0.727 → 0.727 (delta yok), 29,804 ekstra satır | Sorun chunk boyutu DEĞİL — semantic encoding katmanı zayıf |
| 3 | **LLM rerank A/B** | #783 (2026-05-14) | DeepSeek "passage cevaplıyor mu" judgement kalite artırır | Recall aynı, +%18 latency | Pipeline (RRF + critical_entities + chunk_keywords) yeterli — LLM ek katkı vermez |
| 4 | **Tier'lı RESCUE** | #791 (2026-05-14) | ALL → OR + match_count + tier'lı K niche_007/009 kurtarır | recall@5 0.818 → 0.636 (regresyon), niche_007/009 yine NF | Geniş rescue precision'ı bozar (rakip article top'a çıkar) |
| 5 | **#927 Faz-B — meta_norm + keyword collation** | #988/PR#989 (2026-05-18) | #939 `COLLATE "tr-TR-x-icu"` pattern'ini sparse `meta_norm` + keyword path'e taşı → Türkçe-entity recall artar | recall@5 0.727 → **0.636** (2-koşum AFTER tutarlı), niche_003 stabil top-3 (2,3) → stabil **9-10**; niche_007/009 yine NF (sıfır upside); recall@10 0.818 sabit. **Revert PR #992.** | Collation **RRF-scoring stream'ini** (sparse K=60 + keyword K=15-30) besliyor → C-locale'de kaçan Türkçe-uppercase rakip chunk'lar RRF'e doluyor, niche_003 hedefi geri itiliyor (plan R-B). #939'un RESCUE/FILTER'da güvenli olması (ayrı stream / K=12 bonus / sadece-daraltma) sparse+keyword-**scoring**'de güvenli olduğunu GARANTİ ETMEZ — kanıt benchmark'tan (varsayım değil) |
| 6 | **#927 Faz-C — Wikidata-alias entity genişletme** | #997 (2026-05-18, CLOSED not-planned, MERGE EDİLMEDİ) | Elle sözlük DEĞİL — Wikidata topluluk-kürate `labels\|aliases` (#863 zinciri reuse): planner backstop-sonrası grounded critical_entity → eş-ad → RESCUE/FILTER OR-term → niche_007/009 (ABD↔Amerika, 15 Temmuz↔darbe) recall artar | flag-OFF ×2 == baseline (r@5=0.727 r@10=0.818 NF={007,009}) → **kanıtlanabilir no-op**; flag-ON ×2 **İDENTİK** (r@5=0.727 r@10=0.818, Δ=**0.000**, latency bütçe-içi). Sıfır upside, sıfır regresyon. Branch merge edilmedi (Faz-B precedent). | Mekanizma **çalıştı** (alias'lar doğru kablolandı/çözüldü) ama 2 NF vakası eş-ad-substring problemi DEĞİL: **niche_009** `15 temmuz`→Wikidata **yanlış-anlam** (takvim "July 15" Q-ID'si, 2016 darbe girişimi değil → İngilizce gürültü); **niche_007** alias doğru (`abd`→Amerika/ABD) ama makale single-chunk (282 token) RRF-ranking/answer-extraction sorunu, substring zaten bulunabilir. **Ders: çıplak TR haber-olay keyword → Wikidata `wbsearchentities` ilk-sonuç QID disambiguation GÜVENİLMEZ; eş-ad ancak hata gerçekten substring-form-miss ise yardımcı (golden 2 NF farklı kök). Eş-ad ihtiyacı zaten #863/#967/#973 Wikipedia-yolu ile chat'te karşılanıyor.** |

## Genel ders — niş entity problemleri için ANTI-PATTERN'lar

**❌ "Rerank ile düzelt"** — Cross-encoder, LLM rerank, custom reranker.
  - Sebep: Niş entity sorgularında target article zaten retrieval-katmanı kaybediyor, top-K dışında. Rerank top-K içinde sıralar — dışındakini içeri sokmaz.
  - Kanıt: #758 cross-encoder + #783 LLM rerank — her ikisi başarısız.

**❌ "Chunk boyutunu küçült"** — Sub-chunk, micro-chunk, sentence-level chunking.
  - Sebep: Kök sebep semantic vector'ün sayısal/yüzde/meta bilgiyi yakalayamaması. Daha küçük parça daha fazla gürültü demek.
  - Kanıt: #769 micro-chunk recall delta = 0.

**❌ "Filter'i yumuşat / OR-mantığı"** — Tier'lı match_count, partial-match rescue.
  - Sebep: Geniş rescue rakip article'ları top'a iter. Niş entity için ALL koşulu doğru (precision koruma).
  - Kanıt: #791 tier'lı RESCUE: regresyon -2 query.

## Başarılı yaklaşımlar (kontrast)

| # | Yaklaşım | PR | Etki |
|---|---|---|---|
| 1 | **Per-chunk LLM keywords + question_keywords** | #779 | recall@5 niş entity'lerde +%15 |
| 2 | **Critical entities MUST_MATCH (ALL, K=12 rescue)** | #779 | Target article surface — niche_006 ✅ |
| 3 | **tsvector FTS (PostgreSQL native BM25)** | #782 | Sparse 5s → 1s |
| 4 | **Answer-aware generation (extract_numerical_spans)** | #788 | Generation paragraf seçimi düzelir |
| 5 | **HyDE conditional** | #684 PR-C | Hypothetical doc semantic alan açar |
| 6 | **Multi-query batch embedding** | #684 PR-D | Raw + topic + hyde RRF combine |

**Genel pattern:** RagFlow-vibe yaklaşımlar (BM25 + keywords + tsvector) işe yaradı. Rerank-only / chunker-only yaklaşımlar başarısız oldu.

## niche_007/009 kalıcı durum

> 🚫 **GÜNCELLEME — #927 Faz-C (2026-05-18): "entity synonym expansion" HİPOTEZİ TEST EDİLDİ ve ÇÜRÜTÜLDÜ.** Aşağıdaki "Çözüm yolu" tam olarak denendi (Wikidata topluluk-kürate alias, elle sözlük değil) → **sıfır upside** (tablo #6). niche_007/009 **eş-ad-substring problemi DEĞİL** — yeni teşhis: niche_009 çıplak `15 temmuz` Wikidata'da **takvim-günü** Q-ID'sine eşleşiyor (2016 darbe girişimi değil → alias = İngilizce takvim gürültüsü); niche_007 alias doğru çözülüyor (`abd`→Amerika/ABD/Amerika Birleşik Devletleri) ama hedef makale single-chunk (282 token) — sorun **RRF-ranking/answer-extraction**, entity zaten bulunabilir. **Bu sorguları synonym expansion ile yeniden çözmeye ÇALIŞMA.**

Bu iki sorgu **başlangıçta entity-synonym** sanıldı (yanlış teşhis — #927 Faz-C ile çürütüldü):
- niche_007: `critical_entities = ['hürmüz boğazı', 'abd']` — alias DOĞRU çözülüyor ama makale 1-chunk; dense+sparse RRF top-15'e sokmuyor (substring/synonym sorunu değil)
- niche_009: `critical_entities = ['15 temmuz', 'mağdur']` — `15 temmuz` çıplak-keyword → Wikidata yanlış-anlam (takvim günü); gerçek sorun meta-sorgu + büyük-chunk + HyDE-bağımlı (golden failure_reason)

**Çözüm yolu (ÇÜRÜTÜLDÜ — #927 Faz-C):** ~~Query rewriting + entity synonym expansion~~ — Wikidata-alias denendi, mekanizma çalıştı ama bu 2 vakanın kök-nedeni eş-ad-miss değil (çıplak-keyword→QID disambiguation güvenilmez + answer-extraction/ranking problemi). Eş-ad genişletme ancak hata GERÇEKTEN substring-form-miss ise yardımcı; #842/#863/#967/#973 Wikipedia-yolu bu ihtiyacı chat tarafında zaten karşılıyor.

Ama bu **ayrı sprint** — bu seansta öğrenildi ki niş sorgular için rerank/filter/chunk müdahalesi ÇALIŞMAZ; çözüm RETRIEVAL ÖNCESİ katmanda (query/planner) olmalı. (Not: #927 Faz-C planner-katmanı synonym de denedi → yine çözmedi; bu 2 vaka muhtemelen chunking/answer-extraction epic'i gerektirir, recall-retrieval değil.)

> 🔧 **Epic #927 (2026-05-17) — bu ailenin production kanıtı + iş kaydı:** conv 74eecc15 "Özgür özelle ilgili son haberler neler" → planner kusursuz (`critical_entities=['özgür özel']`, since_h=169h) ama sistemdeki 14-15 May Özgür Özel haberleri (embedded, 7g penceresinde) retrieval'a gelmedi → fallback eski-prototipik "Karabük mitinginde konuştu" verdi. Kök: entity **yüzey-form varyasyonu** — başlıkta ardışık "Özgür Özel" yok (apostrof/ek "Özel'den"/"Özgür Özel'in", eşad "CHP Genel Başkanı Özel"); sparse `meta_norm` ILIKE + critical_entities RESCUE `LIKE '%özgür özel%'` **ardışık-substring** mantığında → varyasyonlu entity'yi kaçırır; dense (bge-m3) niş-olay'ı prototipik-haber'e kaybediyor. niche_007/009 ile **aynı sınıf** (entity-synonym/form). Epic [#927](https://github.com/selmanays/nodrat/issues/927) açıldı — entity-normalized/token-bazlı match, benchmark-driven (recall@10=0.818 regresyon kontrolü), Ç2–Ç5 (scope-aware dürüstlük, #930/#931 merged) kapsamından **bilinçli izole** edildi. Bkz [[chat-knowledge-evolution]] #928/#929 satırları + ders #27.

> ✅ **GERÇEK kök bulundu — #939 (2026-05-17), epic #927 ilk teslimat:** Yukarıdaki "yüzey-form varyasyonu / ardışık-substring" bir HİPOTEZDİ; kullanıcının 3 gerçek Evrensel URL'siyle gerçek kök kanıtlandı: **PostgreSQL C-locale `LOWER()` Türkçe büyük harf (Ö Ü Ç Ş Ğ İ) küçültmüyor** (`datcollate=C`). RESCUE/FILTER `LOWER(...) LIKE :ent` — `:ent` Python `.lower()` küçük, SQL C-locale → "Özgür Özel" büyük kalır → Türkçe entity ASLA eşleşmez. **niche_007/009'un Türkçe-tarafı budur** ("entity-synonym broken" tam değil yanlış teşhisti). Fix: RESCUE/FILTER `LOWER(x COLLATE "tr-TR-x-icu")` ([[turkish-collation-entity-match]]). **Benchmark: recall@5 0.636→0.727, recall@10 0.818→0.909 (+%9, regresyon YOK); `niche_009` ("15 Temmuz" — Türkçe entity) NF→rank#9 KURTARILDI; niche_003 #6→#3.** `niche_007` hâlâ NF — ikinci entity "abd↔Amerika" GERÇEK synonym sorunu (Türkçe-collation değil; #927 sonraki teslimat: meta_norm/agenda/keyword + synonym). PR [#940](https://github.com/selmanays/nodrat/pull/940).

> ⚠️ **#927 Faz-A ✅ / Faz-B ❌ (2026-05-18) — collation-yeri kritik + baseline yeniden-ölçüldü (D1):**
> - **Faz-A (PR #985, KALICI):** agenda-card sparse path collation (`retrieval.py:878-880`). V2 agenda'yı ölçmez (kod-doğrulandı) → prod-trace smoke: canlı DB `LOWER(title) LIKE '%özel%'` 39→**132** (+93), `%çin%` 746→905. Düşük risk, kalıcı.
> - **Faz-B (PR #989 → revert #992):** meta_norm + keyword path collation. **GATE FAIL** — yukarıdaki tablo #5. Özet: niche_003 stabil top-3 → 9-10, recall@5 0.727→0.636 (2-koşum tutarlı), **sıfır upside** (niche_007/009 yine NF, recall@10 sabit). Revert sonrası baseline-restore doğrulandı (niche_003 rank=3, recall@5=0.727).
> - **Ders:** `COLLATE` **RESCUE/FILTER + agenda'da güvenli** (ayrı stream/daraltma) ama **sparse `meta_norm` + keyword RRF-scoring stream'inde net-negatif** (rakip-flood → sıra-kayması, kazanım yok). Kademe-1(b)(c) için saf-collation YANLIŞ katman.
> - **Baseline gerçeği (D1, ÖLÇÜLDÜ):** Bu sayfadaki "#939 → recall@10 0.818→**0.909**" iddiası **canlı V2 prod-parity ile uyuşmuyor**: 2026-05-18 ölçümü recall@10 = **0.818**, recall@5 = 0.727 (post-Faz-A, 2-koşum stabil), NF = {niche_007, niche_009}. (#939'un 0.909'u farklı/iyimser ölçüm ya da drift — "memory'ye değil ölçüme güven" deseninin bir örneği daha.) #927 regresyon kapısı bu ÖLÇÜLEN değere göre.
> - **Faz-B-bis / Kademe-1(b)(c) (DÜŞÜRÜLDÜ, kullanıcı kararı #988):** Faz-B sıfır-upside + FILTER zaten #939-collation'lı → Faz-B-bis gereksiz/tasarımsız. Collation tarafı #939+Faz-A ile "tamamlandı".
> - **Faz-C ❌ (#997, 2026-05-18, CLOSED not-planned — MERGE EDİLMEDİ):** "asıl recall lever" sanılan Wikidata-alias entity genişletme. flag-OFF spike disiplini: foundation (`wikidata_aliases` #863-reuse + `QueryPlan.entity_synonyms` + planner D3 backstop-sonrası + RESCUE/FILTER OR-term + `retrieval.entity_alias_expansion_enabled` default-OFF). **GATE: flag-OFF ×2 == baseline (r@5=0.727 r@10=0.818) → kanıtlanabilir no-op (14 unit + 175 regression pass); flag-ON ×2 İDENTİK (Δ=0.000, latency bütçe-içi).** Sıfır upside + sıfır regresyon. Kök (çözülen synonym dökümü): niche_009 `15 temmuz`→Wikidata **yanlış-anlam** (takvim Q-ID); niche_007 alias doğru ama single-chunk ranking/answer-extraction (substring-miss değil). Tablo #6. **Ders: çıplak TR haber-olay keyword→`wbsearchentities` ilk-QID disambiguation güvenilmez; bu 2 NF farklı kök-nedene sahip. Kullanıcı kararı: Faz-B precedent'i (merge etme, #997 not-planned CLOSE — main'de ölü kod yok); foundation gerekirse branch `fix/997-wikidata-alias-expansion` (`093fe92`) / issue'dan kurtarılır.**
> - **Faz-D ⏭️ ATLANDI (kanıt-yönlü pivot, 2026-05-18):** Snowball stemmer = aynı entity-match katmanı; #947 DAR `_STEM_SUFFIXES` yaygın çekimleri zaten karşılıyor + **zaten test-kilitli** (`test_query_planner_prompt.py:496-518`). Faz-B+C ampirik: aynı-sınıf müdahale bu 2 NF'yi oynatmıyor → koşmaya değmez (Snowball kodu yok → Snowball-özel pytest gate de gereksiz). **#927 EPIC CLOSED/COMPLETED** — entity-match-katmanı tükendi; kalan niche_007/009 ayrı chunking/answer-extraction epic'i (kanıtlanmış farklı kök, recall-retrieval değil).

## İlişkiler

- [[cross-encoder-rerank-disabled]] — #758 eval kanıt
- [[chunk-keyword-extraction]] — başarılı temel
- [[critical-entity-must-match]] — başarılı mekanizma
- [[perf-sprint-2026-05-14]] — hız sprintı
- [[benchmark-production-parity]] — V2 eval framework

## Kaynaklar

- [PR #758 cross-encoder revert](https://github.com/selmanays/nodrat/pull/758)
- [PR #769 sub-chunk cleanup](https://github.com/selmanays/nodrat/pull/769)
- [PR #783 LLM rerank off](https://github.com/selmanays/nodrat/pull/783)
- [PR #791 tier'lı RESCUE revert](https://github.com/selmanays/nodrat/pull/791)
- [Issue #927 Faz-B revert PR #992](https://github.com/selmanays/nodrat/pull/992)
- [Issue #997 Faz-C — Wikidata-alias spike NEGATİF (CLOSED not-planned)](https://github.com/selmanays/nodrat/issues/997) — branch `fix/997-wikidata-alias-expansion` (`093fe92`, merge edilmedi); gate audit: `apps/api/tests/eval/score_history/fazc_997/GATE_RESULT.md`
