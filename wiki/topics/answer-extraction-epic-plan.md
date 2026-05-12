---
type: topic
title: "Answer Extraction Epic — Faz 7c LESSONS LEARNED (plan hipotezleri çürütüldü)"
slug: "answer-extraction-epic-plan"
category: "rag"
status: "lessons-learned"
created: "2026-05-11"
updated: "2026-05-12 (post-mortem — Aşama 2 revert + B eval gate negatif)"
sources:
  - "apps/api/tests/eval/niche_chunks_benchmark.py"
  - "apps/api/tests/eval/golden_sets/niche_chunks_golden.yaml"
  - "apps/api/scripts/eval_rerank_ab.py (#750 eval runner)"
  - "wiki/decisions/cross-encoder-rerank-disabled.md (eval-confirmed)"
  - "GitHub Issue #710, #742 (Aşama 1 diagnostic delivered), #746/#748 (Aşama 2 revert), #750 (B eval negatif)"
tags: ["rag", "answer-extraction", "epic", "plan", "niche-benchmark", "faz-7c", "lessons-learned"]
---

# Answer Extraction Epic — Faz 7c LESSONS LEARNED

> **TL;DR (2026-05-12 güncel):** Plan dokümandaki 5 aşama hipotezi (numerical span + cross-chunk merge + meta-query + eval lock) **eval ile çürütüldü**. Aşama 1 (diagnostic tooling) delivered, ama Aşama 2 (query reformulation) regresyon yaptı ve revert edildi (PR #748). B opsiyonu (rerank eval) negatif (#752 kalıcı disabled). Production'da recall@5 **8/11 baseline** kabul edildi; 3 fail vakanın gerçek çözümü embedding/chunking re-strategy (β) — MVP-2 sprint.

## ⚠️ Post-mortem (2026-05-12) — niye plan başarısız oldu

**Tek cümle:** 3 fail vakasında (niş_006/007/009) doğru article RETRIEVAL seviyesinde top-K'a girmiyor. Plan hipotezleri (span extraction, cross-chunk merge, meta-query intent) hepsi **top-K içinde** işler — top-K dışı article için faydasız.

### Denemeler ve sonuçları

| Deneme | PR | Skor değişimi | Sonuç |
|---|---|---|---|
| **Aşama 1 — Diagnostic tooling** | #743 + #744 | recall@5 8/11 (telemetri kazanım), mrr 0.591 | ✅ KEPT |
| **Aşama 2 — Query reformulation** (entity-only + numerical reform + HyDE markers) | #747 | recall@5 8/11 (aynı), mrr 0.591 → **0.523 ⬇**, latency 16.5s → **36s ⬇**, niche_011 #1 → **#4** | ❌ Revert (#748) |
| **B — Rerank eval gate** (off vs local vs NIM) | #751 | local: 8/11 → **7/11 ⬇**, NIM: 8/11 → **7/11 ⬇**, NDCG@10 0.627 → 0.509/0.542 | ❌ Negatif, kalıcı disabled (#752) |

### Kök sebep — embedding/retrieval zaafı

Pipeline savunma katmanları:

```
1. Planner            ← genel niyet doğru
2. Embedding (bge-m3) ← ZAYIF HALKA (Türkçe niş entity ↔ ana article semantic mesafe)
3. Hybrid retrieval   ← Top-K'a doğru article'ı sokamıyor
4. Rerank (kapalı)    ← Top-K içinde işler, yokken çare değil
5. Content generator
```

Plan'ın 5 aşaması katman 3-4'te işlemeye çalışıyordu — gerçek zayıf halka katman 2 (embedding) / chunk segmentation.

### Gerçek çare opsiyonları (β stratejisi — MVP-2)

1. **Embedding model değişimi** — Faz 7b'de bge-m3 e5'i yenmişti, ama yeni Türkçe-specific modeller (trendyol-tr-bge, multilingual-e5-large-v2 vb.) test edilebilir.
2. **Re-chunk strategy** — niş bilgi article'ın ana paragrafından ayrı küçük chunk olsun; summary chunk fragmentleri eklenmeli (109K article re-chunk).
3. **Direct article search bypass** — niş sorgu detection → chunk yerine article title+summary direct embedding match.

## Mevcut Durum (post #693 Faz 6.1 + #696 D18 + #699 İ fix)

## Mevcut Durum (post #693 Faz 6.1 + #696 D18 + #699 İ fix)

**niche_chunks_benchmark deterministic 7/11 (recall@5 63.6%, recall@10 72.7%):**
- ✅ niche_001 Karşıyaka hakemler (multi_and rank #2)
- ❌ niche_002 Karşıyaka skor (top-10 dışı; multi-card score embed zayıf)
- ✅ niche_003 Trump 6 Mayıs (#1)
- ✅ niche_004 Diyarbakır kilise (#1)
- ✅ niche_005 Fatih Tutak (multi_and #2)
- ❌ niche_006 Rodos kaç kent (TOP-10 DIŞI)
- ❌ niche_007 Hürmüz yüzde kaç (TOP-10 DIŞI)
- ✅ niche_008 Hürmüz alıntı (#1)
- ❌ niche_009 Darbe röportaj (TOP-10 DIŞI)
- ✅ niche_010 Aydınbelge (#1)
- ✅ niche_011 Sovyetler (#1)

## Fail Analizi

### niche_006 — "Rodos Devleti'ni kaç ana kent bir araya gelerek kurdu"

**Doğru article:** 8b146f02 (Rodos Devleti tarih article)
**Sebep:** "3 ana kent" cevabı article'ın orta paragrafında sayısal entity olarak gömülü. Faz 7a numerical entity NER (#679) cap 30→40 ile eklendi ama:
- Article chunk size ~800 char — niş "3 ana kent" cevabı tek chunk içinde başka sayısallarla karışık
- Embedding similarity orta (~0.50) — "kaç ana kent" sorgusunun embedding'i "Rodos Devleti tarihi" article başlığıyla yakın değil
- NER stream: "Rodos" entity df muhtemelen 10+ (yaygın), boost zayıf
- LLM rerank doğru chunk'ı seçmiyor (cross-encoder)

**Çözüm pattern (answer extraction):**
- Chunk içinde "kaç X" sorusu için numerical span extraction
- "Rodos Devleti'ni X ana kent ... kurdu" pattern match (Faz 7a numerical NER'i query-side de uygula)

### niche_007 — "ABD'nin hürmüz boğazının yüzde kaçını kullanma hakkı var"

**Doğru article:** d2a47f33 (Hürmüz Boğazı article)
**Sebep:** Aynı article niche_008'de **#1 çıkıyor** ama niche_007'de fail. Fark: niche_008 "kim söyledi" (citation), niche_007 "yüzde kaç" (numerical).
- Article'da "yüzde 1" sayısı var ama farklı paragrafta
- LLM rerank "ABD'nin kullanma hakkı" sorgusunda "ABD" çok yaygın entity → noise
- Doğru paragraf rank top-15'te değil

**Çözüm pattern:**
- Multi-chunk merge: aynı article'ın farklı chunk'larından (parent-doc retrieval) numerical fragment + context birleştir
- Cross-chunk answer extraction

### niche_009 — "15 temmuz darbe girişimi esnasında yaralanan bir mağdurun rö"

**Doğru article:** 7761cd94 (darbe röportaj article — niche_010 ile aynı!)
**Sebep:** niche_010 (Aydınbelge ne dedi) #1 çıkıyor, niche_009 (mağdur röportaj) fail.
- Meta-sorgu — "röportaj" özellik değil, **soru kategorisi**
- HyDE conditional skip (kısa generic) — niş sorgu için HyDE gerekirdi
- Article başlığı/summary "Aydınbelge" entity ile dominantı; "mağdur röportaj" semantic mismatch
- Embedding similarity düşük

**Çözüm pattern:**
- HyDE conditional re-evaluate — "röportaj/söz/açıklama" semantic indicator için HyDE aktif kalsın
- Query type detection: "ne dedi" / "kim söyledi" / "röportaj" → meta-sorgu mode

## Faz 7c Plan (Önerilen)

### Aşama 1: Diagnostic Tooling (1 PR, ~2-3 saat)

- **/admin/rag/inspect-query** response'a yeni alanlar:
  - `answer_span_candidates: list[str]` — chunk içinde numerical/named entity extraction
  - `parent_doc_merge: dict` — aynı article'ın farklı chunk'larından merge sonucu
- niche_chunks_benchmark JSON output'a `expected_chunk_excerpt` + `retrieved_chunk_excerpts` ekle (debug)

### Aşama 2: Numerical Span Extraction (1-2 PR, ~5-8 saat)

- `_extract_numerical_spans(chunk_text)` helper — regex + Faz 7a NER number type
- Query'de "kaç X" pattern detection (Faz 7a number entity)
- Match: query numerical pattern × chunk numerical span → boost top-N

**Hedef:** niche_006 rank top-5'e

### Aşama 3: Cross-Chunk Answer Merge (1 PR, ~4-6 saat)

- Parent-doc retrieval'ı genişlet: 3 chunk yerine 5-7 chunk
- Multi-chunk synthesis prompt — LLM aynı article'ın farklı chunk'larından cevap birleştir
- `provider_call_logs.cross_chunk_merge_count` telemetri

**Hedef:** niche_007 rank top-5'e

### Aşama 4: Meta-Query Detection (1 PR, ~3 saat)

- Query Planner prompt'a "intent classifier" — "röportaj/söz/açıklama/kim_dedi" kategori
- Meta-query intent → HyDE her zaman aktif + parent-doc 5+ chunk
- niche_009 case test

**Hedef:** niche_009 rank top-5'e

### Aşama 5: Eval + Lock (1 PR, ~2 saat)

- niche_chunks_benchmark recall@5 hedef: **7/11 → 10/11 (90%+)**
- niche_chunks_benchmark recall@10 hedef: **8/11 → 11/11 (100%)**
- Production deploy + admin /rag/ner-stats yeni "answer_extraction_hits" metric

## Toplam Tahmin

- **5 PR** (~16-22 saat geliştirme + test)
- **3 yeni concept sayfası** (numerical-span-extraction, cross-chunk-answer-merge, meta-query-intent)
- **Faz 7c sprint** olarak konumlandır (MVP-1.9 candidate)

## Riskler

- **Cost artışı** — multi-chunk merge LLM call sayısı arttırır (+%20-30 cost)
- **Latency** — parent-doc 5-7 chunk = +200-400ms retrieval
- **False positive** — numerical span extraction common kelime sayıları ("100 yıl", "1 milyon" yaygın) → IDF benzer mantık gerek

## Re-evaluation

Faz 7c başarılı olursa MVP-1.9 release notes; başarısız (recall@5 < 8/11) → answer extraction yerine eval method ayarlama (HyDE optimization + niş chunk size yeniden değerlendirme).

## İlişkiler

- [[pipeline-optimization]] — kalan 3 fail liste
- [[ner-pipeline]] — Faz 6/6.1 + Faz 7a numerical entity
- [[idf-entity-weighting]] — IDF benzer mantık örnek
- [[eval-benchmark-divergence]] — cards vs chunks suite
- [[insufficient-data-pattern]] — fail case'lerde insufficient_data yerine answer extraction

## Kaynaklar

- [niche_chunks_benchmark.py](../../apps/api/tests/eval/niche_chunks_benchmark.py)
- [niche_chunks_golden.yaml](../../apps/api/tests/eval/golden_sets/niche_chunks_golden.yaml)
- [Issue #696](https://github.com/selmanays/nodrat/issues/696) D-takip
