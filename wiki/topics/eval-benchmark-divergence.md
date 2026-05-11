---
type: topic
title: "Eval benchmark divergence — cards vs chunks path"
slug: "eval-benchmark-divergence"
category: "rag"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "apps/api/tests/eval/retrieval_benchmark.py (cards/chunks suite)"
  - "apps/api/tests/eval/niche_chunks_benchmark.py (chunks-only)"
  - "apps/api/app/api/admin_rag.py /benchmark/run endpoint"
  - "GitHub Issue #696 (Faz A — suite param fix)"
tags: ["rag", "eval", "benchmark", "retrieval", "telemetry"]
---

# Eval Benchmark Divergence — Cards vs Chunks Path

> **TL;DR:** Nodrat'ta **iki ayrı retrieval pipeline** var (`hybrid_search_agenda_cards` ve `hybrid_search_chunks`). Production `/api/generate/stream` chunks path'ini kullanır (NER + IDF dahil). Eski admin benchmark cards path'ini ölçüyordu → niş entity sorguları NER'siz seyrek skor → benchmark history'de 6 Mayıs NDCG 0.85 → 11 Mayıs NDCG 0.07 dramatik düşüş. **Gerçek production performansı düşmedi**; ölçüm yanlış path'i izledi. PR #696 Faz A ile admin benchmark `suite=chunks` default'a alındı.

## İki path neden var?

Nodrat **dual retrieval mimarisi** (PRD §2.7):

1. **agenda_cards** — Editör-LLM hibrit "öne çıkan haberler" özetleri
   - `agenda_cards` tablosu: title, summary, key_points, embedding
   - Cardlevel daily/weekly mode (RAPTOR clustering)
   - Kullanım: ana sayfa "gündem", trending haber kartları

2. **article_chunks** — Article gövdesi chunklarının semantic + sparse retrieval'i
   - `article_chunks` tablosu: chunk_text, embedding, NER entities (etkilesim)
   - Sparse (BM25) + dense (cosine) + RRF füzyon + parent-doc + NER stream
   - Kullanım: kullanıcı /generate prompt → uzun içerik üretimi

### Production akışı (kullanıcı /generate)

```text
User → /api/generate/stream
  → app_generate_stream.py
    → hybrid_search_chunks()
      ← article_chunks + NER + parent-doc
    → context = top chunks
    → LLM content generation
  ← streamed answer
```

## Skor çöküşünün anatomisi (6 Mayıs → 11 Mayıs)

### Pre-#684 timeline

- **4-6 Mayıs:** Admin benchmark `hybrid_search_agenda_cards` — NDCG@10 = 0.77-0.85
  - Golden set 55 sorgu, agenda card focused (1 Mayıs bankalar, emekli zammı, vs.)
  - Cards retrieval bu sorgulara iyi yanıt veriyor (agenda card amacı bu)
- **11 Mayıs 02:00:** Faz 6 NER pipeline merge (#667/#668) — cards path'e NER eklenmedi
  - NER backfill başlatıldı (chunks corpus'ta 9 → 4391 article entity)
- **11 Mayıs 11:30:** Bizim wiki yorumumuz "regression" — yanlış hipotezdi
- **11 Mayıs 13:32:** Faz 6.1 (PR #693) chunks path NER scoring overhaul
- **11 Mayıs 14:35 + 16:32:** Admin benchmark cards path → NDCG@10 = 0.07 (10x düşüş)

### Asıl sebep

Golden set sorguları **niş/agenda hibrit** içeriyor:
- Bazı sorgu agenda card sorusu (1 Mayıs bankalar) → cards path iyi
- Bazı sorgu niş entity sorusu (Karşıyaka maç skoru) → chunks path NER'le iyi
- Eski golden 50 sorgu — agenda focused
- Yeni golden 55 sorgu — 5 yeni sorgu niş entity ağırlıklı

Cards path NER yok → niş entity sorgular fail → ortalama NDCG@10 düştü.

**Aynı anda production /api/generate (chunks path) NER ile iyi cevaplar üretti** çünkü chunks path NER + IDF (Faz 6.1) kullanıyor. Kullanıcı kalitesinin yükseldiği bu yüzden gözlendi.

## Çözüm (PR #696 Faz A)

### Suite parametresi

`retrieval_benchmark.py`'a `suite: cards|chunks` param eklendi:

```bash
# Production-faithful (default admin)
python -m tests.eval.retrieval_benchmark --suite chunks --golden retrieval_golden_tr.yaml

# Legacy cards
python -m tests.eval.retrieval_benchmark --suite cards
```

### Card → article mapping

Cards golden set'i article_id ile karşılaştırılamaz (cards.id != article.id). Çözüm:

```sql
SELECT ac.id::text AS cid, ea.article_id::text AS aid
FROM agenda_cards ac
JOIN event_articles ea ON ea.event_id = ac.event_id
WHERE ac.id::text = ANY(:ids)
```

Bir card multi-article (event = haber kümesi). Mapping `dict[card_id, list[article_id]]` → chunks suite skor article düzeyinde hesaplar.

### Admin endpoint default

`POST /admin/rag/benchmark/run?suite=chunks` (default) — production'a sadık ölçüm. Frontend RAG İzlencesi sayfasında suite dropdown.

## Ölçülen sonuçlar (PR #696 sonrası, 55 sorgu)

| Suite | recall@5 | recall@10 | recall@20 | NDCG@10 |
|---|---|---|---|---|
| cards (legacy) | %7-12 | %15-20 | %25-30 | 0.07 |
| **chunks (production)** | **43.4%** | **57.9%** | **65.9%** | ~0.5 |

Chunks suite cards'a göre 6x iyileşme. Bu, **gerçek production performansı**.

Niş chunks_benchmark (11 sorgu, chunks-only):
- recall@5: **63.6%** (Faz 6.1 hedefi)
- recall@10: **72.7%**

İki benchmark farklı suite ölçer; production kalitesini chunks path ölçer.

## Telemetri (PR #696 Faz B)

`/admin/rag/inspect-query?suite=chunks` artık NER pipeline'ı gözler:
- Query entity'leri + df_map
- Mode (multi_and / single_rare / no_match)
- Target article aid sample

`/admin/rag/ner-stats` proce-lifetime mode dağılımı.

## Önerilen evaluation politikası

1. **Admin benchmark history** = chunks suite (production-faithful, default)
2. **Cards suite ölçümü** = agenda card retrieval kalitesi (ayrı amaç)
3. **niche_chunks_benchmark** = niş entity stress test (11 sorgu)
4. Her 3'ünü periyodik (haftalık) koş; cards ile chunks ayrı trend grafik

## İlişkiler

- [[idf-entity-weighting]] — chunks path'inde NER scoring detay
- [[ner-pipeline]] — NER extraction worker + entities tablosu
- [[pipeline-optimization]] — #684 sprint context
- [[cards-path-ner-out-of-scope]]
- [[api-contracts-md]]
- [[prompt-contracts-md]]

## Açık takip

1. Cards path'ine NER stream eklenebilir mi? (önerilmedi — agenda amaç farklı)
2. Golden set niş vs agenda ayrıştırılabilir (ayrı suite/golden sub-set)
3. Production sorgu örnekleminden golden set genişletme (data-driven)

## Kaynaklar

- [Issue #696](https://github.com/selmanays/nodrat/issues/696) — Faz A admin benchmark suite fix
- [PR #693](https://github.com/selmanays/nodrat/pull/693) — chunks path NER overhaul (Faz 6.1)
