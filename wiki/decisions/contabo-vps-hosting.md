---
type: decision
title: "Contabo Cloud VPS 40 hosting"
slug: "contabo-vps-hosting"
status: "locked"
decided_on: "2026-05-07"
decided_by: "founder"
created: "2026-05-07"
updated: "2026-05-08"
sources:
  - "INDEX.md§4"
  - "INDEX.md§5b"
  - "README.md§Çekirdek kararlar"
tags: ["locked-decision", "infrastructure", "hosting", "cost"]
aliases: ["contabo-hosting", "vps-decision"]
---

# Contabo Cloud VPS 40 hosting

> **Karar:** Production hosting MVP-1.5'ten itibaren Contabo Cloud VPS 40 (12 vCPU / 48 GB RAM / 250 GB NVMe) üzerinde çalışır, 12 ay sözleşmeyle €20/ay. Backup için aynı sağlayıcının Object Storage hizmeti (eu2.contabostorage.com). Önceki konfigürasyon: Contabo Cloud VPS 10 (4 vCPU / 8 GB) + Backblaze B2 backup.
> **Durum:** locked (MVP-1.5 Epic #215 ile delivered).
> **Tarih:** 2026-05-07 (INDEX v1.4 ile resmileşti — MVP-1.5 sürümünde Contabo VPS 10 → VPS 40 yükseltmesi + B2 → Contabo OS backup migration'ı). Kaynak doküman 2026-05-08'de v0.3'e güncellendi (#410, [PR](https://github.com/selmanays/nodrat/pull/410)).

## Bağlam

Production hosting **başından beri Contabo ekosisteminde**. MVP-1 production Contabo Cloud VPS 10 (paylaşımlı, 4 vCPU / 8 GB RAM / 75 GB NVMe, IP: 173.212.238.104, port 2222, ~$5/ay) üzerinde çalıştı. Backup hedefi Backblaze B2'ydi (off-server, restic encrypted).

> **Not:** [docs/engineering/architecture.md](../../docs/engineering/architecture.md) v0.1 §0'da "Hetzner CCX23 (4 vCPU / 16 GB / 240 GB, ~$29/ay)" yazıyordu — bu **draft planlama dili**ydi, hiç deploy edilmedi. Production hep Contabo. v0.3 (#410) ile bu draft mention'ları temizlendi.

MVP-1.5 öncesi Contabo VPS 10'da şu sıkıntılar gözlendi:

1. **CPU darboğazı** — embedding worker + image VLM + Celery beat + retrieval aynı 4 vCPU'da yarış. Latency artıyor.
2. **RAM yetmiyor** — Postgres shared_buffers + bge-m3 local model preload (~2.3 GB) + bge-reranker (568 MB) + workers + Next.js SSR aynı 8 GB'a sığmıyor.
3. **NVMe IO** — pgvector cosine search ve binary quantization HNSW build için NVMe latency kritik.
4. **Backup egress maliyeti** — B2 → VPS arası restore egress (özellikle aylık restore drill) ücretli; aynı-sağlayıcı (Contabo) egress free.

Karar Contabo ekosistemi içinde **plan upgrade** + **backup migration** ile tek-sağlayıcı netliği, daha geniş kaynak ve sıfır egress'i bir arada sağladı.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Contabo VPS 10 (devam) | Mevcut, ucuz (~$5/ay) | CPU/RAM yetmiyor (yukarıda) | Reddedildi (MVP-1.5'te) |
| Hetzner CCX23 (architecture.md v0.1 draft önerisi) | Olgun, dokümanda planlandı | Hiç deploy edilmedi; ek vendor relasyonu gereksiz | Reddedildi (sürekli Contabo'ydu, devam); draft v0.3 ile temizlendi |
| AWS / GCP / Azure | Olgun, full ecosystem | 5-10x maliyet, vendor lock | Reddedildi (early stage için overkill) |
| DigitalOcean Droplet 8 vCPU/16 GB | Tanıdık, düz arayüz | Maliyet ~$96/ay, daha az RAM | Reddedildi |
| S3 / R2 / Wasabi (backup için) | S3 uyumlu | Cross-vendor egress ücreti | Reddedildi (Contabo OS aynı sağlayıcı, free egress) |

## Sonuçlar

- **Etkilenen varlıklar:** [[contabo-vps]]
- **Etkilenen kavramlar:** [[hot-cold-tier]] (Contabo Object Storage cold tier), [[binary-quantization]] (NVMe ile uyumlu)
- **Etkilenen kod:** [`infra/`](../../infra/) — Caddyfile, docker-compose.yml, deploy script.
- **Etkilenen dokümanlar:**
  - [INDEX.md](../../INDEX.md) §4 (locked) ve §5b (milestone tablosu) güncellendi.
  - [README.md](../../README.md) "MVP-1.5 Infra Migration" durumu güncel.
  - [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) §2.4 — VPS cost line revize edildi.
- **Etkilenen workflow:** [`.claude/skills/nodrat-dev/SKILL.md`](../../.claude/skills/nodrat-dev/SKILL.md) "manuel deploy fallback" bölümünde VPS bilgisi (host, port, user, SSH key path) Contabo bilgileriyle güncel.

## Geri alma maliyeti

Bu karar değiştirilirse (örn. başka sağlayıcıya geçiş):

1. **Veri migrasyonu** — Postgres dump + Object Storage rsync (~50-100 GB).
2. **DNS değişikliği** — A record + Cloudflare update.
3. **TLS sertifika regenerate** — Caddy auto-issue Let's Encrypt yeni IP'de.
4. **Backup pipeline rewrite** — B2 veya yeni S3 endpoint için restic config.
5. **Downtime** — tahmini 1-2 saat (DNS propagation dahil).

Tahmini değişiklik süresi: 1 hafta planlama + 1 gün migration window.

## Geri alma tetikleyicileri (ne olursa Contabo'dan ayrılırız)

- Sürdürülebilir uptime <%99 (Contabo'nun bilinen ara sıra outage'ları paylaşılan platformda).
- Compliance ihtiyacı (KVKK için TR-içi datacenter zorunlu olursa — şu an yok).
- Müşteri PII sınır geçişi endişesi (MVP-3 sonrası enterprise müşteri talebi).

## İlişkiler

- **Bağlı varlıklar:** [[contabo-vps]]
- **Bağlı kavramlar:** [[hot-cold-tier]]
- **Bağlı kararlar:** —
- **Bağlı topics:** —

## Kaynaklar

- [INDEX.md §4 (Çekirdek kararlar — locked)](../../INDEX.md)
- [INDEX.md §5b (Milestone tablosu — MVP-1.5)](../../INDEX.md)
- [README.md (MVP-1.5 Infra Migration)](../../README.md)
- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) — kaynak doküman v0.3 (#410): §0/§2.1/§5.1/§9.1/§13 Contabo Cloud VPS 40 + Contabo Object Storage ile sync
- [docs/strategy/unit-economics.md §2.4](../../docs/strategy/unit-economics.md) — VPS cost line
