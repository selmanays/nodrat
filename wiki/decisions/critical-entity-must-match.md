---
type: decision
title: "Critical entity MUST_MATCH (rescue + filter 2-aşamalı retrieval gate)"
slug: "critical-entity-must-match"
status: "locked"
decided_on: "2026-05-14"
decided_by: "tech"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/architecture.md§3"
  - "docs/engineering/prompt-contracts.md§query-planner"
tags: ["locked-decision", "rag-quality", "retrieval"]
aliases: ["critical-entities", "must-match-filter"]
---

# Critical entity MUST_MATCH

> **Karar:** Query planner sorgudaki 1-3 en diskriminatif kelimeyi (`critical_entities`) çıkarır; retrieval'da bu entity'ler hem RESCUE (article surface) hem FILTER (precision) olarak çalışır.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

[[chunk-keyword-extraction]] tek başına yetmedi: keyword extraction "yasa dışı bahis" üretmişti ama planner'dan gelen `["çocuk", "bahis"]` exact match olmuyordu. RagFlow benzeri MUST_MATCH gate gerekti: en kritik 1-3 kelime article gövdesinde veya chunk keyword'lerinde geçmek **zorunda**.

Tek başına filter yetmez — RRF dışında kalan hedef article'lar rescue edilmeli. Yoksa filter sadece "yanlış matchleri eler", "doğru ama kaybolan"ları kurtarmaz.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Sadece filter (no rescue) | Basit | Target RRF dışındaysa kaybedilir | **reddedildi** (smoke test fail) |
| Sadece rescue (no filter) | Recall yüksek | Precision düşer, off-topic article'lar | reddedildi |
| Sadece NER entity stream | RagFlow-uyumlu | Planner'dan critical_entity, NER'dan değil — semantik fark | reddedildi |
| **2-aşamalı: RESCUE (K=12) + FILTER** | Recall + precision birlikte | İki SQL query, ~50ms ek latency | **seçildi** |

## Sonuçlar

- [[query-planner]] v1.3.0 yeni JSON field: `critical_entities: list[str]` (1-3 element, 3-30 char, lowercase, halüsinasyon yok)
- [[chunks-first-retrieval]] (`hybrid_search_chunks`) yeni param: `critical_entities: list[str] | None`
- Stage 1 RESCUE: ALL entities article'da geçen chunk'lar K=12 ile RRF'e injected (en güçlü stream weight)
- Stage 2 FILTER: RRF candidate'ları arasından en az 1 entity geçenleri tutar; 0 match → orijinal RRF (soft fallback)
- Admin tunable: `retrieval.critical_entity_filter_enabled` (default true)
- Planner cache key bump: v1 → v2 (eski cache schema'sında critical_entities yok)

## Smoke test sonucu

Query: "çocukların bahis oynamasını engellemeye yönelik bir çalışma var mı"
Target: `bf3a50fa-8924-46b9-9779-c3cbde31982a`

| Senaryo | top_k | target_pos |
|---|---|---|
| BASELINE (no critical_entities) | 15 | **None** (kayıp) |
| WITH critical_entities=['çocuk','bahis'] | 15 | **#1** ✅ |

## Geri alma maliyeti

> Disable yolu: `retrieval.critical_entity_filter_enabled=false` (admin /settings, runtime). Planner field hâlâ doldurulur (cache key v2 korunur) ama retrieval ignore eder. Niş entity sorguları "kayıp" duruma geri döner.

## İlişkiler

- [[turkish-collation-entity-match]] — #939 (2026-05-17): bu RESCUE/FILTER'daki `LOWER(...)` C-locale'de Türkçe büyük harf küçültmüyordu → Türkçe entity (Özgür Özel, 15 Temmuz…) ASLA eşleşmiyordu; `COLLATE "tr-TR-x-icu"` ile düzeltildi (recall@10 0.818→0.909).

## Kaynaklar

- [`apps/api/app/prompts/query_planner.py`](apps/api/app/prompts/query_planner.py) (PROMPT_VERSION=1.3.0)
- [`apps/api/app/core/retrieval.py`](apps/api/app/core/retrieval.py:1547) (2-stage block)
- PR [#779](https://github.com/selmanays/nodrat/pull/779)
