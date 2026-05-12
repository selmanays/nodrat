---
type: source
title: "docs/engineering/prompt-contracts.md — Prompt Sözleşmeleri + LLM Evaluation Framework"
slug: "prompt-contracts-md"
status: "ingested-summary"
source_path: "docs/engineering/prompt-contracts.md"
source_version: "v0.4"
created: "2026-05-11"
updated: "2026-05-11"
ingest_method: "summary-only"
tags: ["docs", "prompts", "llm", "eval", "engineering"]
---

# Source: docs/engineering/prompt-contracts.md

> **TL;DR:** Nodrat LLM prompt'larının kanonik sözleşmesi: schema, deterministic settings, eval golden set kuralları, versioning, hata yönetimi. 3 ana prompt (Query Planner, Agenda Card Generator, Content Generator) + Faz 4-5 yardımcılar + LLM Evaluation Framework. 1109 satır.

## Section Map

| § | Başlık | Kapsam |
|---|---|---|
| 0 | Yönetici Özeti | Prompt design prensipleri |
| 1 | Genel Prompt Prensipleri | System message, response_format JSON, temperature, top_p, max_tokens, retry |
| 2 | **Prompt #1 — Query Planner** | Kullanıcı sorgusunu enrich: topic, keywords, intent, geographic_focus |
| 3 | **Prompt #2 — Agenda Card Generator** | Daily/weekly card composition (title + summary + key_points + content_angles) |
| 4 | **Prompt #3 — Content Generator** | Kullanıcı /generate çıktısı (article-grounded, citation-aware) |
| 5 | Yardımcı Promptlar (Faz 4-5) | NER extraction, VLM image tag, HyDE, style cloning |
| 6 | **LLM Evaluation Framework** | Golden set yaml schema; metric tablosu; runner |
| 7 | Prompt Versioning | semver; A/B rollout |
| 8 | Hata Yönetimi (Pipeline) | retry logic; fallback; insufficient_data response |
| 9 | Karar Noktaları | locked decisions |
| 10 | Çapraz Referans | prd.md / api-contracts / architecture |

## #696 Sprint açısından önemli prompt'lar

### HyDE (§5 yardımcı)

PR-C #686 sonrası **conditional**: default ON, ama generic kategori sorgularında skip:
- entity-suz + ≤3 kelime + soru kelimesi yok → skip
- niş/soru → HyDE çalışır (Karşıyaka hakemleri, Trump 6 Mayıs)

**Etki:** generic trafiği TTFT -1-2sn, cost -%15-20.

### Content Generator (§4)

PR-D #688 sonrası `content_max_tokens` default **1500** (eski 2000). Streaming ~1-2sn kısalır, cost -%25.

### NER Extraction (§5 yardımcı)

Faz 6 #667 + Faz 7a #679 — DeepSeek V4 Flash json_mode:
- Input: title + subtitle + body[:6000] (Faz 7a body excerpt 3000→6000)
- Output: 40 entity (kişi/yer/kurum/etkinlik/sayı/yüzde/oran)
- Cost: ~$0.0008/article
- #684 PR-B ile 4391 article backfill (~$3.4)

## Golden set'ler (§6 Eval Framework)

`apps/api/tests/eval/golden_sets/`:

| Set | Sorgu sayısı | Suite | Notlar |
|---|---|---|---|
| `retrieval_golden_tr.yaml` | 55 | cards (legacy) + chunks (#696 mapping) | Admin RAG İzlencesi default |
| `niche_chunks_golden.yaml` | 11 | chunks | Niş entity stress (Karşıyaka, Tutak, Trump) |
| `agenda_card_golden.yaml` | ~30 | cards | Agenda card composition eval |
| `content_generator_golden.yaml` | ~30 | content | Content quality eval |
| `query_planner_golden.yaml` | ~30 | planner | Topic/keywords extraction eval |
| `hallucination_traps.yaml` | ~20 | content | Halüsinasyon yakalama (F-16 21 ülke vs.) |
| `pii_redaction_full.yaml` | ~40 | preprocessing | PII redaction eval |

## İlişkiler

- [[hyde-feature-flag]] — HyDE prompt conditional (PR-C)
- [[ner-pipeline]] — Faz 6 NER extraction prompt
- [[pipeline-optimization]] — content_max_tokens defaults
- [[eval-benchmark-divergence]] — cards vs chunks golden set suite

## Versiyon takibi

| Doküman v | Tarih | Notlar |
|---|---|---|
| v0.3 | 2026-05-09 | Pre Faz 6 NER prompt |
| v0.4 | 2026-05-11 | Faz 6 NER prompt + Faz 7a numerical entity (#679); HyDE conditional (#686 PR-C); content_max_tokens 1500 (#688 PR-D) |
| (gelecek #698) | — | Tüm yeni defaults yansıması |

## Açık takip

1. **#698 stale güncellemesi**: HyDE always-on → conditional anlatımı; content_max_tokens 2000→1500
2. **Numerical entity (Faz 7a)** kendi concept sayfası adayı (#679)
3. **Insufficient_data response** prompt'u (§8) — halüsinasyon yasağı sonrası critical pattern (#677)

## Kaynaklar

- [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) (v0.4)
