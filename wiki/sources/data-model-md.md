---
type: source
title: "docs/engineering/data-model.md — Veri Modeli (DDL + Migration Stratejisi)"
slug: "data-model-md"
status: "ingested-summary"
source_path: "docs/engineering/data-model.md"
source_version: "v0.6 (2026-06-16 — §3.2 `config_json` sitemap-ingestion alanları (#1527: sitemap_url/subsitemap_pattern/subsitemap_latest/url_include/max_age_days/max_items) + §3.1 `reliability_score` per-source bandları (#1524). Önceki inline kayıt v0.2: 2026-05-15 denetim staleness sync — §5.x: `generations` DROP'lu net (eski "korunur" çelişkisi giderildi); `training_samples` şeması güncel (generation_id nullable/FK-yok, message_id, sample_type, CHECK research_answer, partial UNIQUE, split=sha256(message_id)); `messages.sources_used` cited-only + `cite` alanı; `thinking_steps` güncel phase'ler. Önceki: v0.1)"korunur" çelişkisi giderildi); `training_samples` şeması güncel (generation_id nullable/FK-yok, message_id, sample_type, CHECK research_answer, partial UNIQUE, split=sha256(message_id)); `messages.sources_used` cited-only + `cite` alanı; `thinking_steps` güncel phase'ler. Önceki: v0.1)"korunur" çelişkisi giderildi); `training_samples` şeması güncel (generation_id nullable/FK-yok, message_id, sample_type, CHECK research_answer, partial UNIQUE, split=sha256(message_id)); `messages.sources_used` cited-only + `cite` alanı; `thinking_steps` güncel phase'ler. Önceki: v0.1)"korunur" çelişkisi giderildi); `training_samples` şeması güncel (generation_id nullable/FK-yok, message_id, sample_type, CHECK research_answer, partial UNIQUE, split=sha256(message_id)); `messages.sources_used` cited-only + `cite` alanı; `thinking_steps` güncel phase'ler. Önceki: v0.1)"korunur" çelişkisi giderildi); `training_samples` şeması güncel (generation_id nullable/FK-yok, message_id, sample_type, CHECK research_answer, partial UNIQUE, split=sha256(message_id)); `messages.sources_used` cited-only + `cite` alanı; `thinking_steps` güncel phase'ler. Önceki: v0.1)"korunur" çelişkisi giderildi); `training_samples` şeması güncel (generation_id nullable/FK-yok, message_id, sample_type, CHECK research_answer, partial UNIQUE, split=sha256(message_id)); `messages.sources_used` cited-only + `cite` alanı; `thinking_steps` güncel phase'ler. Önceki: v0.1)"korunur" çelişkisi giderildi); `training_samples` şeması güncel (generation_id nullable/FK-yok, message_id, sample_type, CHECK research_answer, partial UNIQUE, split=sha256(message_id)); `messages.sources_used` cited-only + `cite` alanı; `thinking_steps` güncel phase'ler. Önceki: v0.1)"
created: "2026-05-11"
updated: "2026-05-11"
ingest_method: "summary-only (full entity/concept extraction deferred)"
tags: ["docs", "data-model", "ddl", "alembic", "schema", "engineering"]
---

# Source: docs/engineering/data-model.md

> **TL;DR:** Nodrat'ın tüm veritabanı şeması, migration stratejisi (Alembic), seed verileri, index stratejisi ve bakım görevlerinin kanonik kaynağı. PostgreSQL 16 + pgvector. 13 ana bölüm, 30+ tablo, 1455 satır.

## Section Map (alt başlıklar)

| § | Başlık | Anahtar İçerik |
|---|---|---|
| 0 | Yönetici Özeti | Stack özeti + design principles |
| 1 | Migration Stratejisi | Alembic; forward-compatible kurallar; extension setup |
| 2 | Faz 0 — Identity & Access | `users`, `sessions` |
| 3 | Faz 1 — Source Management | `sources`, `source_configs`, `source_health`, `articles`, `article_images`, `crawler_jobs`, `failed_jobs`, `model_providers` |
| 4 | Faz 2 — RAG Layer | **`article_chunks` (pgvector)**, `event_clusters`, `event_articles`, **`agenda_cards`**, `provider_call_logs` |
| 5 | Faz 3 — User Generation | `generations`, `usage_events`, `saved_generations`, `admin_audit_log`, `training_samples` (#567 MVP-1.7), `app_settings` + `app_prompts` (#262 MVP-1.2) |
| 6 | Faz 4 — Visual Intelligence | `entities` (NER, #667), `articles_v_entities` |
| 7 | Faz 5 — Style Cloning | training profile tables |
| 8 | Faz 6 — Billing | billing/quota tables |
| 9 | Triggers ve Otomasyonlar | DB trigger'lar |
| 10 | Seed Verileri (MVP-1) | initial data |
| 11 | Index Stratejisi | ivfflat, gin, btree, trgm |
| 12 | Maintenance Görevleri | VACUUM, REINDEX, autovacuum |
| 13 | Karar Noktaları | lock'lu mimari kararlar |

## #696 Sprint açısından önemli tablolar

- **`article_chunks`** §4.1 — embedding 1024-dim, pgvector ivfflat index. NER stream chunk seviyesinde RRF input
- **`entities`** §6.1 — NER backfill burada birikti (4391 article × ~16 entity = 69k row). `entity_normalized` (lowercase + strip_quote_variants); GIN trgm index. #691 Faz 6.1 `_ner_idf_match_aids` exact + ILIKE bu tablo üzerinde
- **`event_articles`** §4.3 — `agenda_cards.event_id` ↔ `articles.id` köprüsü. #696 Faz A chunks-suite mapping bu tabloyu kullanıyor (`_map_card_ids_to_articles`)
- **`provider_call_logs`** §4.5 — DeepSeek cost telemetri; admin /performance pipeline-comparison input
- **`generations`** §5.1 — kullanıcı `/api/generate` çıktıları, citation + warnings JSON
- **`app_settings`** §5.X — admin paneli runtime tunable config. #696 B7+C8 sonrası 9 yeni `retrieval.*` key burada saklanır

## İlişkiler

- [[ner-pipeline]] — entities tablosu üzerinde Faz 6 implementation
- [[idf-entity-weighting]] — `entity_normalized` exact + ILIKE strateji (#696)
- [[ragflow-tier-rebuild]] — article_chunks pgvector mimari kararı
- [[pipeline-optimization]] — PR-A DB pool tuning (#684)

## Versiyon takibi

| Doküman v | Tarih | Notlar |
|---|---|---|
| v0.3 | 2026-05-08 | Pre-MVP-1.7 |
| v0.4 | 2026-05-10 | training_samples (#567) eklendi, MVP-1.7 SFT Foundation |
| (gelecek) | — | #698 ile DB pool 5→10/20 + max_connections=500 yansıması bekleniyor |

## Açık takip

1. **Detay entity/concept extraction** — bu sayfa sadece source özetidir. Her tablo için kendi wiki sayfası gelecek sprintte
2. #698 docs/ stale güncellemesi sonrası bu source pages'e karşılık geliyor
3. Migration stratejisi (§1.2 forward-compatible) için kendi concept sayfası adayı

## Kaynaklar

- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) (v0.4)
