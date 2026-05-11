---
type: source
title: "architecture.md — Teknik Mimari ve Deployment"
slug: "architecture-md"
source_path: "docs/engineering/architecture.md"
source_version: "v0.5"
source_updated: "2026-05-11 (#714 — A9 cards path NER eklendi)"
ingested_on: "2026-05-07"
re_synced_on: "2026-05-11"
created: "2026-05-07"
updated: "2026-05-11 (#698 v0.4 — PR-A pool/concurrency/max_connections yansıması)"
tags: ["source", "engineering", "architecture", "deployment"]
aliases: ["arch.md", "teknik-mimari"]
---

# architecture.md — Özet

> Bu sayfa [`docs/engineering/architecture.md`](../../docs/engineering/architecture.md)'ın LLM-üretilmiş özetidir. Doğruluk kaynağı her zaman orijinal dokümandır.

## Doküman bilgisi

- **Yol:** [`docs/engineering/architecture.md`](../../docs/engineering/architecture.md)
- **Sürüm:** v0.3 (Hetzner/B2 staleness cleanup, #410)
- **Son güncelleme:** 2026-05-08
- **İlk içe alma:** 2026-05-07 (v0.1)
- **Re-sync history:**
  - 2026-05-08 — v0.1 → v0.2 (#405): §0/§4.2/§4.3 DeepSeek native API + v4-flash
  - 2026-05-08 — v0.2 → v0.3 (#410): §0/§1/§2.1/§5.1/§7/§8/§9/§12.1/§13 Hetzner/B2 → Contabo
- **Boyut:** ~1250 satır

## Ne içerir

Tek Contabo Cloud VPS 40 üzerinde Docker Compose ile orkestre edilen, FastAPI + Next.js + Postgres+pgvector + Redis + MinIO + Caddy stack'inin servis topolojisi, network izolasyonu, secrets yönetimi (sops + age), deployment akışı (GitHub Actions → SSH), backup stratejisi (restic + Contabo Object Storage), provider abstraction katmanı (LLM/embedding/rerank), worker queue mimarisi (Celery, 5 grup), monitoring planı ve MVP-1 → ölçek geçiş yol haritası.

## Ana çıkarımlar

1. **Monolith başlangıç + queue ile bölünebilirlik** (A1 prensibi). API tek FastAPI; worker'lar Celery tasks. İleride ayrı VPS'e taşınabilir.
2. **Provider abstraction zorunlu** (A3, PRD F0-R4). Hiçbir kod direkt provider SDK'sına bağlı olmaz — tüm LLM/embedding/rerank ModelProvider Protocol üzerinden.
3. **MVP-1 default LLM stack (v0.2 itibarıyla):** DeepSeek native API + `deepseek-v4-flash` (thinking-disabled) chat default. Local BAAI/bge-m3 embedding (1024-dim, VPS CPU). Chat: `DEEPSEEK_API_KEY`. Cost: $0.27 input cache miss / $0.07 cache hit / $1.10 output per 1M, 2026-05-31'e kadar %75 kampanya indirimi.
4. **Tier-based routing:** Free/Starter/Trial → DeepSeek native API + `deepseek-v4-flash`; Pro/Agency → Claude Haiku 4.5; Agency comparison_generation → Sonnet 4.6.
5. **Storage hot/cold tier (MVP-1.5+):** son 30 gün → VPS lokal; 30+ gün raw_html + eski görseller → Contabo Object Storage (eu2.contabostorage.com).
6. **Binary quantization (MVP-1.5 PR-6):** pgvector embedding'lere 32x sıkışmalı `bit(1024)` ek kolon + HNSW hamming index. Default flag False, eval gate sonrası aktif.
7. **Local model fallback:** LocalBgeM3Provider + LocalBgeRerankerProvider (HF cache build-time preload). NIM bağımlılığını kaldırmak için (PR-8/PR-9, #223/#224).
8. **Sops + age secrets** (`infra/.env.encrypted` repo'da OK; private key VPS-only).
9. **Network izolasyonu:** edge (caddy/web/api public-facing) ↔ internal (postgres/redis/minio/workers). Postgres ve Redis dış dünyaya kapalı.
10. **Backup zorunlu** (R-OPS-03): pg_dump günlük, MinIO snapshot haftalık, restic + Contabo Object Storage (eu2.contabostorage.com) encrypted off-server (öncesinde Backblaze B2, MVP-1.5'te migrate edildi #330/`714d5b2`). Aylık restore drill (RTO <90 dk).

## Dokümanın bölüm haritası

```
§0  Yönetici özeti — stack lock-in, deployment, MVP-1 minimum
§1  Mimari prensipler (A1-A9)
§2  Servis topolojisi (compose haritası, Caddyfile)
§3  Worker mimarisi (queue grupları, retry, beat schedule, site profiles, image VLM)
§4  Provider katmanı (Protocol, adapter listesi, routing, cost tracking)
§5  Storage stratejisi (Postgres, MinIO, Redis, Hot/Cold tier, binary quantization, local providers)
§6  Network & güvenlik (ufw, SSH, TLS, container izolasyon)
§7  Secrets yönetimi (.env şeması, Fernet, sops + age workflow)
§8  Deployment akışı (manual setup, CI/CD, zero-downtime hedef)
§9  Backup ve disaster recovery (matris, drill, RPO/RTO)
§10 Monitoring & observability (MVP-1 minimum, Faz 2+ Prometheus, audit log)
§11 Geliştirme ortamı (local dev, klasör yapısı)
§12 MVP-1 → ölçek geçiş planı (darboğazlar, yatay ölçek)
§13 Karar noktaları (D1-D10 tablosu)
§14 Çapraz referans
```

## Bu kaynaktan üretilen wiki sayfaları

### Entities
- [[deepseek]] — default LLM, DeepSeek native API + `deepseek-v4-flash` (§0, §4.2, §4.3 v0.2)
- [[claude-haiku-4-5]] — premium LLM, Pro+ tier (§4.3)
- [[local-bge-m3]] — embedding provider (§4.2, §5.6)
- [[contabo-vps]] — hosting + Object Storage (§5.4 — INDEX'le güncel)
- [[celery-worker]] — Celery 5 worker stack ve queue grupları (§3)

### Concepts
- [[provider-abstraction]] — A3 prensibi, ModelProvider Protocol (§4.1, §1)
- [[hot-cold-tier]] — storage tier stratejisi (§5.4)
- [[binary-quantization]] — pgvector 32x sıkışma (§5.5)

### Decisions
- [[deepseek-default-llm]] — DeepSeek default LLM (§4.2, §0; INDEX §4)
- [[claude-haiku-premium-llm]] — Claude Haiku 4.5 premium tier (§4.3; INDEX §4)
- [[contabo-vps-hosting]] — Contabo VPS hosting (§0, §2.1, §5.1, §9.1, §13 v0.3 ile sync; INDEX §4)

### Topics
- [[llm-provider-strategy]] — tier-based routing + fallback chain sentezi

## Çapraz referanslar (kaynak içinde)

- [docs/product/prd.md](../../docs/product/prd.md) §6, §1.9, §7.2 — gereksinimler, retry, queue
- [docs/product/information-architecture.md](../../docs/product/information-architecture.md) §3, §13 — sayfa/entity haritası, faz mapping
- [docs/strategy/risk-register.md](../../docs/strategy/risk-register.md) §4, R-OPS-03 — MVP-1 kapsamı, backup riski
- [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) §2.4, §4, §6 — VPS maliyet, provider maliyet
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) — DDL + indeksler
- [docs/engineering/api-contracts.md](../../docs/engineering/api-contracts.md) — endpoint healthcheck
- [docs/engineering/threat-model.md](../../docs/engineering/threat-model.md) — TLS, security headers
- [docs/legal/compliance-brief.md](../../docs/legal/compliance-brief.md) §2, §5 — KVKK, 5651 audit log
- [infra/sops-setup.md](../../infra/sops-setup.md) — pratik kurulum

## Açık sorular / belirsizlikler

> ✅ **Embedding stack:** Local BAAI/bge-m3 (sentence-transformers, VPS CPU, 1024-dim). Tek provider — runtime config `app_settings` tablosu üzerinden yönetilir.
