---
type: decision
title: "NER pipeline — niş entity recall sıçraması (#667 Faz 6)"
slug: "ner-pipeline"
category: "rag"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "apps/api/app/workers/tasks/entities.py (DeepSeek extraction worker)"
  - "apps/api/alembic/versions/20260511_0200_entities_table.py (migration)"
  - "apps/api/app/core/retrieval.py (NER stream RRF entegrasyonu)"
  - "GitHub Issue #667 / PR #668"
tags: ["rag", "ner", "retrieval", "entity-extraction", "mvp-1-8"]
aliases: ["faz6", "named-entity-recognition"]
---

# NER Pipeline

> **TL;DR:** Faz 5 sonrası bge-m3 Türkçe niş entity semantic match sınırına takıldık (recall@5 stable %45.5). NER pipeline ile cap'li özel adları (kişi/yer/kurum/etkinlik) entities tablosunda exact match → embedding bypass → **recall@5: 45.5% → 63.6%**, recall@10: 45.5% → 81.8%.

## Bağlam — bge-m3 ceiling

Faz 1-5 mimari tamamlandı (smart-quote, semantic chunker, multi-query, HyDE, parent-doc, summary embedding, LLM rerank). Niş entity için recall@5 stable %45.5. Tabandaki sorun:

- bge-m3 multilingual embedding Türkçe için kalibre değil
- Niş bilgi (hakem isimleri, % rakamı, kişi sözü) article ortasında bir cümlede
- Sorgu vector'ü ile article ana tema vector'ü arasında cosine sim 0.40-0.55 → threshold 0.65 altı drop

Karşıyaka basketbol article'ı (hakemler) ve Fatih Tutak (kişi adı) bu sebeple top-15'e bile giremiyordu.

## Çözüm — NER + exact match

LLM tabanlı (DeepSeek) entity extraction → entities tablosu → sorgu içindeki cap'li token'lar **exact match** → ilgili article'lar RRF'e EN GÜÇLÜ stream (K=30).

### Migration (20260511_0200)

```sql
CREATE TABLE entities (
  id uuid PRIMARY KEY,
  article_id uuid REFERENCES articles(id) ON DELETE CASCADE,
  entity_text varchar(200),
  entity_normalized varchar(200),      -- lower + strip_quote_variants
  entity_type varchar(20),             -- person/place/org/event/money/number/misc
  mention_count int,
  first_position varchar(20),          -- title/subtitle/body
  created_at timestamptz
);
CREATE INDEX idx_entities_normalized ON entities (entity_normalized, entity_type);
CREATE INDEX idx_entities_article ON entities (article_id);
CREATE INDEX idx_entities_normalized_trgm ON entities USING gin (entity_normalized gin_trgm_ops);
UNIQUE (article_id, entity_normalized, entity_type);
```

### Extraction worker

`tasks.entities.extract_article_entities` — DeepSeek V3 json_mode:
- Input: title + subtitle + body[:3000]
- Output: 30 entity (kişi/yer/kurum/etkinlik/sayı)
- Cost: ~$0.0008/article (300-500 input + 100 output token)
- chunk_article zincirine eklendi → yeni article'lar otomatik NER

### Retrieval entegrasyonu

`hybrid_search_chunks` içine NER stream:
1. Query'den >=3 char entity adayı (mevcut `_extract_entity_candidates`)
2. `entities.entity_normalized ILIKE` search → matching article_id'ler
3. Bu article'ların ilk chunk'ları RRF'e priority stream (K_RRF=30 — sparse/dense üstü)
4. Parent-document retrieval ile article'ın diğer chunks'ları context'e

## Üretim sonucu — KAZANIM

| Metric | Pre-Faz | Faz 1-5 | **Faz 6 NER** |
|---|---|---|---|
| recall@5 | 27.3% | 45.5% | **63.6%** (+18 puan) |
| recall@10 | ~ | 45.5% | **81.8%** (+36 puan) |
| Toplam kazanım | baseline | %66 | **%133 göreceli** |

### Yeni düzelenler (Faz 6 katkısı)

| Sorgu | Önce | Şimdi |
|---|---|---|
| Karşıyaka hakemler | ❌ NOT IN TOP-10 | ✅ #1 |
| Fatih Tutak son işler | ❌ NOT IN TOP-10 | ✅ |
| Karşıyaka skor | ❌ NOT IN TOP-10 | ✅ top-10 |
| 15 Temmuz röportaj | ❌ NOT IN TOP-10 | ✅ top-10 |

### Hala başarısız 3 vaka (top-5/10)

- Rodos kaç kent — numerical niş ("kaç ana kent" rakamı)
- ABD Hürmüz % — yüzde rakamı niş bilgi
- Karşıyaka skor top-5 değil (top-10) — Habertürk SEO başlıklar domine

## Trade-off

**Pro:**
- recall@5 sıçraması (+18 puan tek faz)
- recall@10 +36 puan
- Cap'li özel adlar (kişi/yer/kurum) embedding bypass
- Vakaya özel kod yok — herhangi entity için aynı kural
- chunk_article zincirine eklendi (yeni article'lar otomatik)

**Con:**
- Cost: ~$0.0008/article DeepSeek call (109K article × $87 bir kerelik)
- Latency +500-800ms entity extraction (background worker, kullanıcı görmez)
- LLM hallucination riski (DeepSeek var olmayan entity uydurursa) — mention_count filter ile mitigate

## Backfill stratejisi

- chunk_article zincirine eklendi → yeni article'lar otomatik
- `backfill_entities` task — eski 109K cleaned article için bulk dispatch
- Test article'ları öncelikli işlendi (9 article × 18 saniye = ~2.5 dk)

## Açık iyileştirmeler (sonraki)

1. **Numerical entity extraction** — "yüzde 42", "488 milyon dolar", "21 ülke" daha sıkı yakalamak (Rodos kaç kent, ABD Hürmüz % için)
2. **Entity tip-bazlı RRF weight** — kişi entity match daha güçlü (Karşıyaka hakemler), place entity orta (Rodos), number entity güçlü (Rodos kaç kent)
3. **Embedding upgrade (Faz 7)** — bge-m3 → e5-multilingual-large for residual semantic queries

## İlişkiler

- [[ragflow-tier-rebuild]] — Faz 1-5 mimari (önceki epic)
- [[smart-quote-normalization]] — quote variants strip (#647)
- [[entity-match-relevance]] — prompt-level alaka kontrolü

## Kaynaklar

- [Issue #667](https://github.com/selmanays/nodrat/issues/667)
- [PR #668](https://github.com/selmanays/nodrat/pull/668)
- `apps/api/app/workers/tasks/entities.py` — DeepSeek extraction worker
- `apps/api/app/core/retrieval.py` — NER stream RRF entegrasyonu
- `apps/api/alembic/versions/20260511_0200_entities_table.py` — migration
