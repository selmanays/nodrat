---
type: topic
title: "RAG kalite denemelerinde başarısız 4 deneme — öğrenme kataloğu"
slug: "failed-experiments-rag-quality"
status: "live"
created: "2026-05-14"
updated: "2026-05-17"
tags: ["learning", "experiments", "rag", "anti-patterns"]
aliases: ["denenmis-basarisizlar", "rag-rerank-failures"]
---

# RAG kalite denemelerinde başarısız 4 deneme

> **Amaç:** Aynı yaklaşımları yeniden denemeyi önleyen ders kataloğu. Niş entity recall problemleri için "şunu deneyelim?" sorusu çıktığında ilk bu sayfa kontrol edilmelidir.

## Başarısız denemeler özeti

| # | Deneme | Tarih | Hipotez | Sonuç | Sebep |
|---|---|---|---|---|---|
| 1 | **Cross-encoder rerank** | #758 (2026-05-12) | NIM mistral-4b + bge-reranker-v2-m3 ile top-K reorder kalite artırır | NDCG 0.627 → 0.509, recall 8/11 → 7/11 | Target zaten top-K dışında — rerank ne sıralasın? |
| 2 | **Sub-chunk indexing** | #769 (2026-05-13) | Chunk'ları 2-4 mikrochunk'a böl, semantic dilution azalır | Recall 0.727 → 0.727 (delta yok), 29,804 ekstra satır | Sorun chunk boyutu DEĞİL — semantic encoding katmanı zayıf |
| 3 | **LLM rerank A/B** | #783 (2026-05-14) | DeepSeek "passage cevaplıyor mu" judgement kalite artırır | Recall aynı, +%18 latency | Pipeline (RRF + critical_entities + chunk_keywords) yeterli — LLM ek katkı vermez |
| 4 | **Tier'lı RESCUE** | #791 (2026-05-14) | ALL → OR + match_count + tier'lı K niche_007/009 kurtarır | recall@5 0.818 → 0.636 (regresyon), niche_007/009 yine NF | Geniş rescue precision'ı bozar (rakip article top'a çıkar) |

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

Bu iki sorgu **entity-synonym** problemi:
- niche_007: `critical_entities = ['hürmüz boğazı', 'abd']` — article "ABD" yerine "Amerika" diyor olabilir, target rescue olmuyor
- niche_009: `critical_entities = ['mağdur', 'röportaj']` — article "şehit annesi" diyor, "mağdur" meta-kelime, geçmiyor

**Çözüm yolu (gelecek sprint):** Query rewriting + entity synonym expansion. Planner LLM'e "critical_entities + 1-2 eş-anlamlı varyant" çıkartma kuralı eklenir. Veya retrieval'da `contains-any-form` (form variants) check.

Ama bu **ayrı sprint** — bu seansta öğrenildi ki niş sorgular için rerank/filter/chunk müdahalesi ÇALIŞMAZ; çözüm RETRIEVAL ÖNCESİ katmanda (query/planner) olmalı.

> 🔧 **Epic #927 (2026-05-17) — bu ailenin production kanıtı + iş kaydı:** conv 74eecc15 "Özgür özelle ilgili son haberler neler" → planner kusursuz (`critical_entities=['özgür özel']`, since_h=169h) ama sistemdeki 14-15 May Özgür Özel haberleri (embedded, 7g penceresinde) retrieval'a gelmedi → fallback eski-prototipik "Karabük mitinginde konuştu" verdi. Kök: entity **yüzey-form varyasyonu** — başlıkta ardışık "Özgür Özel" yok (apostrof/ek "Özel'den"/"Özgür Özel'in", eşad "CHP Genel Başkanı Özel"); sparse `meta_norm` ILIKE + critical_entities RESCUE `LIKE '%özgür özel%'` **ardışık-substring** mantığında → varyasyonlu entity'yi kaçırır; dense (bge-m3) niş-olay'ı prototipik-haber'e kaybediyor. niche_007/009 ile **aynı sınıf** (entity-synonym/form). Epic [#927](https://github.com/selmanays/nodrat/issues/927) açıldı — entity-normalized/token-bazlı match, benchmark-driven (recall@10=0.818 regresyon kontrolü), Ç2–Ç5 (scope-aware dürüstlük, #930/#931 merged) kapsamından **bilinçli izole** edildi. Bkz [[chat-knowledge-evolution]] #928/#929 satırları + ders #27.

> ✅ **GERÇEK kök bulundu — #939 (2026-05-17), epic #927 ilk teslimat:** Yukarıdaki "yüzey-form varyasyonu / ardışık-substring" bir HİPOTEZDİ; kullanıcının 3 gerçek Evrensel URL'siyle gerçek kök kanıtlandı: **PostgreSQL C-locale `LOWER()` Türkçe büyük harf (Ö Ü Ç Ş Ğ İ) küçültmüyor** (`datcollate=C`). RESCUE/FILTER `LOWER(...) LIKE :ent` — `:ent` Python `.lower()` küçük, SQL C-locale → "Özgür Özel" büyük kalır → Türkçe entity ASLA eşleşmez. **niche_007/009'un Türkçe-tarafı budur** ("entity-synonym broken" tam değil yanlış teşhisti). Fix: RESCUE/FILTER `LOWER(x COLLATE "tr-TR-x-icu")` ([[turkish-collation-entity-match]]). **Benchmark: recall@5 0.636→0.727, recall@10 0.818→0.909 (+%9, regresyon YOK); `niche_009` ("15 Temmuz" — Türkçe entity) NF→rank#9 KURTARILDI; niche_003 #6→#3.** `niche_007` hâlâ NF — ikinci entity "abd↔Amerika" GERÇEK synonym sorunu (Türkçe-collation değil; #927 sonraki teslimat: meta_norm/agenda/keyword + synonym). PR [#940](https://github.com/selmanays/nodrat/pull/940).

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
