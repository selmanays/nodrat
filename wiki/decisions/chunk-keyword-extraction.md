---
type: decision
title: "Per-chunk LLM keyword + question extraction (RagFlow adaptation)"
slug: "chunk-keyword-extraction"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/data-model.md§5"
  - "docs/engineering/architecture.md§3"
tags: ["locked-decision", "rag-quality", "retrieval"]
aliases: ["per-chunk-keywords", "question-keywords"]
---

# Per-chunk LLM keyword + question extraction

> **Karar:** Her `article_chunks` satırı için LLM ile 3-5 keyword + 3 olası soru çıkarılır, `keywords` + `question_keywords` TEXT[] kolonlarında saklanır.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

RagFlow mimari analizinde tespit edilen kritik eksiklik: niş entity sorgularında (örn. "çocukların bahis oynamasını engellemeye yönelik çalışma") embedding semantic match yeterli değildi. DeepSeek planner doğru entity'leri çıkarsa bile retrieval streams (BM25 sparse, dense embedding, NER, summary) hedef article'ı surface edemiyordu. RagFlow BM25 field weighting (question_kwd 6x, important_kwd 5x) bizim mimaride yoktu.

Açılış vakası: article `bf3a50fa-8924-46b9-9779-c3cbde31982a` ("Bakan Gürlek: Yasa dışı bahisle ilgili yeni bir çalışma yapıyoruz"). BASELINE retrieval'da target_pos=None (15 sonuçta yok). Per-chunk keyword + critical_entities rescue stream eklendikten sonra target_pos=#1.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Mevcut BM25 + dense yeterli | 0 maliyet | Niş entity'lerde recall düşük | **reddedildi** (target #1 yerine None) |
| TF-IDF chunk keyword (rule-based) | LLM çağrısı yok | Türkçe morpholoji, eş anlamlılar zayıf | reddedildi |
| Cross-encoder rerank ile telafi | Hızlı | #758'de model loading fail, kalite delta belirsiz | reddedildi (geçici) |
| **LLM per-chunk keywords (RagFlow pattern)** | Spesifik entity'ler, doğal Türkçe | Bulk maliyet ~\$2.50, 1-time | **seçildi** |

## Sonuçlar

- Hangi varlık/kavramları etkiler: [[ner-pipeline]], [[chunks-first-retrieval]], [[entity-match-relevance]]
- Migration `20260514_0100_chunk_keywords.py`: `article_chunks.keywords VARCHAR(80)[]`, `question_keywords VARCHAR(200)[]`, `keywords_updated_at TIMESTAMP`, 2 GIN index
- Backfill: 12815 chunk DeepSeek ile 68 dakikada tamamlandı (paralel script, 5 worker, 2.32 chunk/sec)
- Runtime: yeni chunk eklendiğinde Celery `extract_chunk_keywords` task'ı otomatik tetikler ([apps/api/app/workers/tasks/embedding.py:embedding_queue])
- Retrieval'da yeni stream: keyword match RRF K=15 (q_match) / K=20 (kw_match≥2) / K=30 (kw_match=1) — en güçlü stream weights
- Prompt admin-tunable: `chunk_keywords` key prompts_store registry'de

## Geri alma maliyeti

> Bu karar değiştirilirse:
> - Migration revert: 3 kolon + 2 index drop, kayıp 12K LLM extraction
> - Runtime task disable: `chunker.keyword_extraction_enabled=false` (admin /settings, restart yok)
> - Retrieval keyword stream disable: `retrieval.keyword_stream_enabled=false`
> - "Bahis çocuk" tipi niş entity sorguları regrese olur (#778 açılış vakası kanıt)

## Kaynaklar

- [`apps/api/alembic/versions/20260514_0100_chunk_keywords.py`](apps/api/alembic/versions/20260514_0100_chunk_keywords.py)
- [`apps/api/app/prompts/chunk_keywords.py`](apps/api/app/prompts/chunk_keywords.py)
- [`apps/api/scripts/backfill_chunk_keywords_parallel.py`](apps/api/scripts/backfill_chunk_keywords_parallel.py)
- [docs/engineering/data-model.md §5](docs/engineering/data-model.md)
- PR [#779](https://github.com/selmanays/nodrat/pull/779)
