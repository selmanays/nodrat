---
type: concept
title: "pgvector binary quantization"
slug: "binary-quantization"
category: "technique"
status: "draft"        # default flag False, eval gate öncesi
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/engineering/architecture.md§5.5"
  - "INDEX.md§5b"
tags: ["pgvector", "quantization", "embedding", "performance", "storage"]
aliases: ["pgvector-quantization", "bit-quantization", "hnsw-hamming"]
---

# pgvector binary quantization

> **TL;DR:** `vector(1024)` (float32, 4 KB/chunk) embedding kolonu yanına ek `bit(1024)` (1 bit/dim, 128 B/chunk) kolonu — 32x sıkışma. HNSW hamming index ile hızlı candidate retrieval, sonra full vector ile rerank. MVP-1.5 PR-6 (#221) ile scaffold edildi; default flag False, eval gate sonrası primary'ye alınacak.

## Tanım

Binary quantization, embedding vektörünün her boyutunu sign-bit'e indirgemektir: pozitif değer → 1, negatif → 0. 1024-boyutlu float32 vektör (4096 byte) → 1024-bit binary (128 byte). Hamming distance binary vektörler arasında 32-64 bit CPU instruction'ı ile çok hızlı hesaplanır. HNSW (Hierarchical Navigable Small World) index'i bit_hamming_ops üzerinde candidate retrieval'i milisaniyeler içinde yapar.

Tipik retrieval pipeline iki aşamalı olur:

1. **Coarse search** — bit vektör HNSW ile top-K candidate (örn. K=100). Çok hızlı.
2. **Rerank** — full float32 vektörle precise cosine similarity, sadece candidate'lar için. Düşük latency.

## Neden Nodrat'ta var

İki problem:

1. **Storage.** 1024-dim float32 chunk × 1M chunk = 4 GB. 100K agenda card × 1024-dim = 400 MB. Yıl 1 büyümesinde RAM'e fit etmek için sıkışma şart.
2. **Latency.** Postgres ivfflat (vector_cosine_ops) bile büyük corpus'ta saniyeler tüketir. HNSW + bit hamming sub-100ms hedefler.

## Schema (architecture.md §5.5)

```sql
ALTER TABLE article_chunks
ADD COLUMN embedding_binary bit(1024);

CREATE INDEX idx_article_chunks_embedding
  ON article_chunks USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX idx_article_chunks_embedding_binary
  ON article_chunks USING hnsw (embedding_binary bit_hamming_ops)
  WITH (m=16, ef=64);
```

## Dual-write at insertion

Embedding worker INSERT'te aynı SQL'de iki kolonu doldurur — extra round-trip yok:

```sql
INSERT INTO article_chunks (chunk_id, content, embedding, embedding_binary)
VALUES (..., ..., $1, binary_quantize($1));
```

`binary_quantize()` pgvector'ün native fonksiyonu; her dim'i 1 bit'e map eder.

## Backfill task

Mevcut chunks (eski INSERT'ler `embedding_binary` IS NULL) için:

```python
# tasks.maintenance.quantize_chunks
SELECT chunk_id FROM article_chunks
WHERE embedding IS NOT NULL AND embedding_binary IS NULL
LIMIT 500;

UPDATE article_chunks
SET embedding_binary = binary_quantize(embedding)
WHERE chunk_id IN (...);

# Idempotent, single-SQL batch update
```

Smoke (2026-05-06): 2167 chunk backfilled, 8.5 MB float → 270 KB binary = **31x compression** (1024 dim için 32x teorik, %3 overhead bit alignment).

## Settings flag (eval gate öncesi)

```python
# default False
vector_quantization.enabled
vector_quantization.backfill_batch  # default 500
```

Roadmap: search routing flag ile switch-able yapılacak. Eval benchmark (NDCG@10 düşüşü ≤ %3) sonrası primary'ye alınacak.

## Eval gate (#347 — açık)

Quantization NDCG@10'u nominal düşürür (binary distance approximate). Kabul kriteri:

```text
Acceptance: NDCG@10 düşüşü ≤ %3
Test set: 100 query × top-10 retrieval
Compare:  full vector vs (binary candidates → full rerank top-100)
```

Eval geçmeden flag flip yok — yanlış retrieval pipeline citation'ı bozar, halü riski artar.

## Latency etki tahmini

```text
Mevcut (full vector ivfflat):
  agenda_cards (10K rows):     ~50ms
  article_chunks (1M rows):    ~500ms

Hedef (binary HNSW + rerank):
  agenda_cards:                ~10ms
  article_chunks:              ~80ms (binary 30ms + rerank 50ms)
```

## İlişkiler

- **İlgili kavramlar:** [[hot-cold-tier]] (HOT tier'da NVMe ile uyumlu), [[provider-abstraction]] (embedding provider değişikliği quantization'ı etkilemez).
- **İlgili varlıklar:** [[local-bge-m3]] (1024-dim embedding kaynağı), [[contabo-vps]] (HNSW build için RAM yeterli — 48 GB).
- **İlgili kararlar:** —
- **İlgili topics:** —
- [[contabo-vps-hosting]]
- [[data-pipelines]]
- [[mvp-roadmap]]
- [[risk-catalog]]
- [[architecture-md]]
- [[risk-register-md]]

## Açık sorular / TODO

- **Eval gate test set:** 100 query mi yeterli? Türkçe corpus için representative seed query setinin nereden geleceği belirlenmeli.
- **HNSW parametre tuning:** `m=16, ef=64` default değerler. Nodrat corpus'una özel optimal değerler için sweep gerekir mi?
- **Memory footprint:** HNSW index in-memory tutulur — 48 GB RAM 1M chunk için sığar mı? Doc'a göre HNSW genelde dim × n × ~25 byte ≈ 25 MB her 1K chunk. 1M chunk için ~25 GB — sınır değer.

## Kaynaklar

- [docs/engineering/architecture.md §5.5 (Binary quantization)](../../docs/engineering/architecture.md)
- [docs/engineering/architecture.md §5.6 (Local model providers)](../../docs/engineering/architecture.md) — local bge-m3 ile entegrasyon
- [INDEX.md §5b (MVP-1.5)](../../INDEX.md) — Epic #215, scaffolds delivered
