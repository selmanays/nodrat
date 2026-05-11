---
type: decision
title: "RAGFlow-tier rebuild — niş entity recall sıçraması (4 faz)"
slug: "ragflow-tier-rebuild"
category: "rag"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/core/chunker.py§30-220 (sentence-window splitter)"
  - "apps/api/app/core/retrieval.py§868-1010 (timeframe filter)"
  - "apps/api/app/core/rerank.py§285-450 (LLM answer-aware rerank)"
  - "apps/api/app/api/app_generate.py + app_generate_stream.py (HyDE always-on)"
  - "apps/api/app/prompts/query_planner.py (date extraction)"
  - "GitHub Epic #652 / PRs #653 #654 #655"
  - "RAGFlow DeepDoc paper https://arxiv.org/abs/2401.13089"
tags: ["rag", "retrieval", "chunker", "self-query", "hyde", "llm-rerank", "mvp-1-8"]
aliases: ["faz1-faz4", "ragflow-rebuild"]
---

# RAGFlow-tier rebuild

> **TL;DR:** Founder 11 niş entity sorgusu test etti, 7'si başarısız oldu (article DB'de var, retrieval bulamadı). DB analiz: ana sorun **chunker semantic dilution** (1275 char article 1 chunk halinde 262 token, niş bilgi gömülü). 4 fazlı RAGFlow-tier rebuild: (1) sentence-window chunker, (2) self-query date filter, (3) HyDE always-on, (4) LLM answer-aware rerank.

## Bağlam — testler ve kök sebep

Founder 2026-05-10 testleri (11 sorgu, 7 başarısız):

| Sorgu | Article | Eski chunks | Eski sonuç |
|---|---|---|---|
| Karşıyaka hakemleri | 1275 char | 1 chunk 262 tok | ❌ |
| Trump 6 Mayıs Truth Social | 3389 char | 1 chunk 605 tok | ❌ (yanlış tarih) |
| Rodos kaç kent | 7735 char | 2 chunk avg 770 | ❌ |
| ABD Hürmüz % | 1539 char | 1 chunk 282 tok | ❌ (LLM yanlış paragraf) |
| 15 Temmuz röportaj | 2709 char | 1 chunk 508 tok | ❌ (meta-sorgu) |
| Emine Aydınbelge | 2709 char | 1 chunk 508 tok | ❌ (kişi adı gömülü) |
| Sovyetler dağıldı | 24956 char | 5 chunk avg 947 | ❌ (uzun article) |

Ortak pattern: niş bilgi (hakem isimleri, % rakamı, kişi sözü, sayı, kişi adı) article ortasında bir cümle, ana tema ile cosine similarity dilute oluyor.

## Çözüm — 4 fazlı RAGFlow-tier rebuild

### Faz 1 — Chunker rewrite (PR #653)

**Defaults sertleştirme** (RAGFlow DeepDoc benzeri):
- target_tokens: 500 → **256**
- max_tokens: 900 → **384**
- min_tokens: 200 → **100**
- overlap_tokens: 80 → **64**

**Sentence-window splitting**:
- Article → paragraphs → cümleler (Türkçe noktalama, Ç/Ğ/İ/Ö/Ş/Ü)
- Sliding window: cümle-bazlı, target 256 token'a yaklaşırken kapat
- Niş bilgi her chunk'ta dominant → cosine sim sorgu vector'üne yakın

**Re-chunk task** (`tasks.embedding.rechunk_all`):
- Mevcut 9142 chunk yeniden böl
- only_old_config=True: avg_tokens > 256 olanlar
- Embedding zinciri otomatik (chunk_article → embed_chunks)

Çıktı: 24956 char Nükleer Mezarlar 5 chunk → **17 chunk**, Rodos 2 → 6 chunk.

### Faz 2 — Self-Query date filter (PR #654)

**Problem**: "Trump 6 Mayıs Truth Social paylaşımı" → 7 Mayıs'lı article döndü. Tarih disambiguation yok.

**Çözüm**:
- `hybrid_search_chunks` artık `timeframe_from`, `timeframe_to` parametreleri alır
- Sparse + dense path date_clause uygular (BETWEEN tf_from AND tf_to)
- query_planner prompt'a SPESİFİK TARİH bölümü:
  - "6 Mayıs 2026" → single day window
  - "Mayıs 2026" → full month
  - "1-5 Mayıs" → range
  - "geçen Çarşamba" / "dün" → relative single day

### Faz 3 — HyDE always-on (PR #654)

**Problem**: Meta-sorgu ("var mı / ne dedi / nedir") + dolaylı sorgular sparse-only mantığında semantic gap üretiyor.

**Çözüm**:
- `retrieval.hyde_enabled` default OFF → **ON**
- DeepSeek hipotetik passage (1-2 cümle) üretir → 3. varyant olarak RRF'e
- Streaming endpoint'e de HyDE eklendi (parity)
- Cost +%5, recall +%15 beklenir

### Faz 4 — Final-stage LLM answer-aware rerank (PR #655)

**Problem**: Cross-encoder relevance skorlar ama "Bu passage sorguyu CEVAPLAR mı?" sorusunu yapamaz. ABD Hürmüz % vakası bu pattern.

**Çözüm**:
- Cross-encoder sonrası top-3 passage'a DeepSeek "yes/no + score (1-10)" sorgusu
- Yes (≥6): combined_score +0.30 boost
- No (<4): -0.10 penalty
- **Question-type guard**: sadece soru-tipinde sorgular (?, kim, nedir, var mı, ne dedi, ...) — generic kategoride skip (cost guard)
- Top-3 reorder, top_k_final cap
- Settings flag `retrieval.llm_rerank_enabled` (default OFF, manuel ON)

## Eval framework

`tests/eval/golden_sets/niche_chunks_golden.yaml` (11 sorgu × ground-truth article_id founder doğruladı).

`tests/eval/niche_chunks_benchmark.py`: hybrid_search_chunks → recall@5 / recall@10 / mrr@10 + Pre-Faz-1 failures vs fixed analizi.

## Üretim doğrulama (Re-chunk %35 mixed-config'de)

| Sorgu | Pre | Post (Faz 1+2+3+4) |
|---|---|---|
| niche_001 Karşıyaka hakemler | ❌ | ❌ NOT IN TOP-10 |
| niche_002 Karşıyaka skor | ✅ | ❌ (regression — mixed config) |
| niche_003 Trump 6 Mayıs | ❌ | #7 (top-10 yakın) |
| niche_004 Diyarbakır kilise | ✅ | #1 ✅ |
| niche_005 Fatih Tutak | ✅ | ❌ (regression — mixed config) |
| niche_006 Rodos kaç kent | ❌ | ❌ NOT IN TOP-10 |
| niche_007 ABD Hürmüz % | ❌ | ❌ NOT IN TOP-10 |
| niche_008 Hürmüz kim söyledi | ✅ | #1 ✅ |
| niche_009 15 Temmuz röportaj | ❌ | ❌ NOT IN TOP-10 |
| niche_010 Emine Aydınbelge | ❌ | **#1 ✅** (kazanım!) |
| niche_011 Sovyetler dağıldı | ❌ | #6 ✅ (top-10) |

**Kazanım**: Emine Aydınbelge ❌→#1, Sovyetler ❌→#6, Trump 6 Mayıs ❌→#7.
**Regression** (geçici, mixed-config): Karşıyaka skor + Fatih Tutak (re-chunk %100 olunca düzelmesi beklenir).

> ⚠️ Re-chunk dispatched 3074 article, %35 tamamlandı (3349/9142 yeni chunks). Tam değerlendirme için worker tamamlanmasını bekle.

## Trade-off

**Pro:**
- Niş bilgi recall sıçraması: bge-m3 + sentence-window küçük chunks → her chunk dominant semantic
- Date disambiguation: planner'a tarih extraction kazandırıldı
- Meta-sorgu desteği: HyDE always-on
- Answer-aware rerank: final stage LLM "cevaplar mı?" check

**Con:**
- HyDE +1 LLM call (~200-500ms)
- LLM rerank +1 LLM call top-3 için (~500-800ms, sadece soru-tipinde)
- Total latency artışı: ~1-1.5sn (kabul edilebilir, recall kazanımı için)
- Re-chunk 109K → 9142 chunks (3074 article eligible) yeniden embed lazım: bir kerelik ~$5-10

## Faz 5 — Akıllı semantik chunking (deliver edildi, ceiling tespit edildi)

#661 Epic kapsamında 4 sub-PR delivered:
- **5.1 Semantic chunker** (`app/core/semantic_chunker.py`): paragraph + heading boundary + sentence-level BATCH embedding + percentile-based breakpoint (alt %50) + token budget 150/256/400 + overlap 2 sentence
- **5.2 Article summary embedding**: yeni column `articles.summary_embedding vector(1024)` + migration + embed task (title + subtitle + first_paragraph[:200])
- **5.3 Parent-document retrieval**: hybrid_search_chunks sonrası top-3 article'ın tüm chunks'ları LLM context'ine (max 5 chunks/article)
- **5.4 Migration**: alembic chain düzeltildi (bakinazik revision conflict), priority test article'lar semantic re-chunk + summary embed
- **5.5 Summary emb retrieval entegrasyonu (#665)**: hybrid_search_chunks içinde summary_emb dense search + RRF additional stream (K=80)

**Üretim sonucu**: recall@5 **45.5% → 45.5%** (değişmedi).

### Faz 5 net etki: SIFIR (kazanım yok)

Tabandaki neden — **bge-m3 Türkçe niş entity semantic match sınırı**. Mimari Faz 1-5 tamamen tamamlandı, retrieval pipeline RAGFlow-tier hale getirildi:
- ✅ Smart-quote normalization (#647)
- ✅ Chunks-first retrieval + multi-query rewrite + RRF (#624-#638)
- ✅ Date filter + HyDE + LLM answer rerank (#654-#655)
- ✅ Entity bonus + cross-encoder bypass (#659)
- ✅ Semantic chunker + parent-doc + article summary emb (#662, #665)

Ama 4 başarısız vaka (Karşıyaka hakemler, Rodos kaç kent, ABD Hürmüz %, 15 Temmuz röportaj) hepsi **dense embedding semantic gap** sebep: niş bilgi article ortasında bir cümlede, sorgu vector'ü article ana teması ile orta-düşük cosine sim, threshold 0.65 altı → drop. Summary embedding dense match de aynı sınırda — title + subtitle uyumlu olduğu zaman match etti (Emine Aydınbelge, Sovyetler) ama olmayanlar için fark yapmadı.

## Uzun vade — Faz 6 (sonraki sprint)

Mimari iyileştirmeler bge-m3 sınırına ulaştı. Daha iyi recall için artık **model değişikliği** veya **structural ek bilgi** gerekiyor:

- **Faz 6 — NER pipeline**: Türkçe NER (spaCy/LLM) → entities tablosu (kişi/yer/kurum/sayı) → exact-match inverted index + knowledge graph. "Emine Aydınbelge" / "Karşıyaka" / "Rodos" gibi cap'li özel adlar entity match ile bypass embedding limit.
- **Faz 7 — Embedding model upgrade**: bge-m3 → e5-multilingual-large veya gte-turkish-large. Türkçe niş semantic match için kalibre. Migration: 109K chunks × yeniden embed.

## İlişkiler

- [[smart-quote-normalization]] — quote variants strip (#647 kök fix)
- [[chunks-first-retrieval]] — chunks always-on (#637)
- [[multi-query-rewrite]] — multi-query + RRF
- [[hyde-feature-flag]] — HyDE artık always-on
- [[entity-match-relevance]] — prompt-level alaka kontrolü
- [[idf-entity-weighting]]
- [[ner-pipeline]]
- [[pipeline-optimization]]
- [[data-model-md]]

## Açık sorular / TODO

- [ ] Re-chunk %100 tamamlandığında benchmark tekrar çalıştır
- [ ] Karşıyaka skor + Fatih Tutak regression devam ediyor mu? (mixed-config sonrası ölçüm)
- [ ] Faz 5 (hierarchical) trade-off: 109K chunk re-process maliyeti vs kazanım
- [ ] Faz 6 (NER): spaCy Türkçe vs LLM-based extraction tercihi

## Kaynaklar

- [Epic #652](https://github.com/selmanays/nodrat/issues/652)
- [PR #653](https://github.com/selmanays/nodrat/pull/653) — Faz 1 chunker rewrite
- [PR #654](https://github.com/selmanays/nodrat/pull/654) — Faz 2+3 self-query + HyDE
- [PR #655](https://github.com/selmanays/nodrat/pull/655) — Faz 4 LLM rerank
- [RAGFlow DeepDoc paper](https://arxiv.org/abs/2401.13089) — hierarchical chunking + RAG patterns
- `apps/api/app/core/chunker.py` (sentence-window)
- `apps/api/app/core/retrieval.py` (date filter)
- `apps/api/app/core/rerank.py` (answer-aware LLM rerank)
- `apps/api/tests/eval/golden_sets/niche_chunks_golden.yaml` (11 ground-truth)
