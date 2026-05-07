---
type: source
title: "architecture.md — Teknik Mimari ve Deployment"
slug: "architecture-md"
source_path: "docs/engineering/architecture.md"
source_version: "v0.2"
source_updated: "2026-05-08"
ingested_on: "2026-05-07"
re_synced_on: "2026-05-08"
created: "2026-05-07"
updated: "2026-05-08"
tags: ["source", "engineering", "architecture", "deployment"]
aliases: ["arch.md", "teknik-mimari"]
---

# architecture.md — Özet

> Bu sayfa [`docs/engineering/architecture.md`](../../docs/engineering/architecture.md)'ın LLM-üretilmiş özetidir. Doğruluk kaynağı her zaman orijinal dokümandır.

## Doküman bilgisi

- **Yol:** [`docs/engineering/architecture.md`](../../docs/engineering/architecture.md)
- **Sürüm:** v0.2 (DeepSeek migration sync, #405)
- **Son güncelleme:** 2026-05-08
- **İlk içe alma:** 2026-05-07 (v0.1)
- **Re-sync:** 2026-05-08 (v0.2 — §0/§4.2/§4.3 DeepSeek native API + v4-flash)
- **Boyut:** ~1250 satır

## Ne içerir

Tek VPS üzerinde Docker Compose ile orkestre edilen, FastAPI + Next.js + Postgres+pgvector + Redis + MinIO + Caddy stack'inin servis topolojisi, network izolasyonu, secrets yönetimi (sops + age), deployment akışı (GitHub Actions → SSH), backup stratejisi (restic + B2/Contabo Object Storage), provider abstraction katmanı (LLM/embedding/rerank), worker queue mimarisi (Celery, 5 grup), monitoring planı ve MVP-1 → ölçek geçiş yol haritası.

## Ana çıkarımlar

1. **Monolith başlangıç + queue ile bölünebilirlik** (A1 prensibi). API tek FastAPI; worker'lar Celery tasks. İleride ayrı VPS'e taşınabilir.
2. **Provider abstraction zorunlu** (A3, PRD F0-R4). Hiçbir kod direkt provider SDK'sına bağlı olmaz — tüm LLM/embedding/rerank ModelProvider Protocol üzerinden.
3. **MVP-1 default LLM stack (v0.2 itibarıyla):** DeepSeek native API + `deepseek-v4-flash` (thinking-disabled) chat default; NIM endpoint fallback. NIM `nvidia/nv-embedqa-e5-v5` embedding (1024-dim). Chat: `DEEPSEEK_API_KEY`, embedding: `NIM_API_KEY` (ayrı). Cost: $0.27 input cache miss / $0.07 cache hit / $1.10 output per 1M, 2026-05-31'e kadar %75 kampanya indirimi.
4. **Tier-based routing:** Free/Starter/Trial → DeepSeek native API + `deepseek-v4-flash`; Pro/Agency → Claude Haiku 4.5; Agency comparison_generation → Sonnet 4.6.
5. **Storage hot/cold tier (MVP-1.5+):** son 30 gün → VPS lokal; 30+ gün raw_html + eski görseller → Contabo Object Storage (eu2.contabostorage.com).
6. **Binary quantization (MVP-1.5 PR-6):** pgvector embedding'lere 32x sıkışmalı `bit(1024)` ek kolon + HNSW hamming index. Default flag False, eval gate sonrası aktif.
7. **Local model fallback:** LocalBgeM3Provider + LocalBgeRerankerProvider (HF cache build-time preload). NIM bağımlılığını kaldırmak için (PR-8/PR-9, #223/#224).
8. **Sops + age secrets** (`infra/.env.encrypted` repo'da OK; private key VPS-only).
9. **Network izolasyonu:** edge (caddy/web/api public-facing) ↔ internal (postgres/redis/minio/workers). Postgres ve Redis dış dünyaya kapalı.
10. **Backup zorunlu** (R-OPS-03): pg_dump günlük, MinIO snapshot haftalık, restic + B2 → Contabo Object Storage encrypted off-server. Aylık restore drill (RTO <90 dk).

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
- [[deepseek-v3]] — default LLM, DeepSeek native API + `deepseek-v4-flash` (§0, §4.2, §4.3 v0.2)
- [[claude-haiku-4-5]] — premium LLM, Pro+ tier (§4.3)
- [[nim-bge-m3]] — embedding provider (§4.2, §5.6)
- [[contabo-vps]] — hosting + Object Storage (§5.4 — INDEX'le güncel)
- [[celery-worker]] — Celery 5 worker stack ve queue grupları (§3)

### Concepts
- [[provider-abstraction]] — A3 prensibi, ModelProvider Protocol (§4.1, §1)
- [[hot-cold-tier]] — storage tier stratejisi (§5.4)
- [[binary-quantization]] — pgvector 32x sıkışma (§5.5)

### Decisions
- [[deepseek-default-llm]] — DeepSeek default LLM (§4.2, §0; INDEX §4)
- [[claude-haiku-premium-llm]] — Claude Haiku 4.5 premium tier (§4.3; INDEX §4)
- [[contabo-vps-hosting]] — Contabo VPS hosting (INDEX §4) — ⚠️ kaynakla çelişkili

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

> ⚠️ **Çelişki — Hosting:** Bu doküman §0'da MVP-1 hosting için "Hetzner CCX23 (4 vCPU, 16 GB)" yazıyor. Ancak [INDEX.md](../../INDEX.md) §4 (locked decisions) ve §5b (milestone tablosu) "Contabo Cloud VPS 40 (12 vCPU / 48 GB / 250 GB NVMe), MVP-1.5'ten itibaren dedicated" diyor. INDEX daha güncel (v1.4, 2026-05-07). architecture.md v0.1 (2026-05-01) sürümü kaynak güncellemesi bekliyor.

> ⚠️ **Çelişki — Backup:** §9.1 "B2 (encrypted)" diyor, §5.4 "Contabo Object Storage" diyor (MVP-1.5 ile geçiş). INDEX'te de "Contabo Object Storage (S3-comp), MVP-1.5'ten itibaren; öncesinde Backblaze B2" net. Geçiş tarihi 2026-04 civarı. architecture.md §9 güncellenmeli.

> ⚠️ **Çelişki — Embedding model:** §4.2'de "NIM `nim_bge_m3` aslında BAAI/bge-m3'ten farklı bir model serve ediyor (cosine ≈ 0, orthogonal)". Bu kritik bilgi #345 migration ile çözülecek (LocalBgeM3Provider'a flip + DB chunk re-embed). [[nim-bge-m3]] entity sayfasında detay.

- **Açık karar:** §12.1 darboğaz tahminleri MVP-1.5 sonrası ne kadar geçerli? CCX43 → Contabo VPS geçişiyle CPU/RAM artışı bu hesabı revize etti mi?
- **Açık karar:** Faz 2+ Prometheus + Grafana stack ne zaman aktif? Şu an §10.1 Sentry + Better Uptime "MVP-1 minimum"u kullanılıyor. MVP-2 milestone'unda yer var mı?

## Sürüm değişikliği takibi

| Sürüm | Tarih | Değişiklik | Wiki etkisi |
|---|---|---|---|
| v0.1 | 2026-05-01 | initial | sayfalar oluşturuldu (2026-05-07 ingest) |
| v0.1 (eskimiş) | 2026-05-08 | Kod tabanı §0/§4.2/§4.3'ten ileri sapmış (DeepSeek native API + v4-flash, #163/#361/#378/#379) | [[deepseek-v3]] entity + [[deepseek-default-llm]] decision + [[provider-abstraction]] adapter listesi güncellendi (PR #403); kaynak doküman bekliyor |
| v0.2 | 2026-05-08 | DeepSeek migration sync — §0/§4.2/§4.3 kod tabanına hizalandı ([PR #405](https://github.com/selmanays/nodrat/pull/405)) | wiki ⚠️ DeepSeek migration çelişki bloğu kaldırıldı (resolved); diğer 3 çelişki açık (hosting Hetzner/Contabo, backup B2/Contabo OS, embedding nim_bge_m3 model adı) |
