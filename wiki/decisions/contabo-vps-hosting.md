---
type: decision
title: "Contabo Cloud VPS 40 hosting"
slug: "contabo-vps-hosting"
status: "locked"
decided_on: "2026-05-07"
decided_by: "founder"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "INDEX.md§4"
  - "INDEX.md§5b"
  - "README.md§Çekirdek kararlar"
tags: ["locked-decision", "infrastructure", "hosting", "cost"]
aliases: ["contabo-hosting", "vps-decision"]
---

# Contabo Cloud VPS 40 hosting

> **Karar:** Production hosting MVP-1.5'ten itibaren Contabo Cloud VPS 40 (12 vCPU / 48 GB RAM / 250 GB NVMe) üzerinde çalışır, 12 ay sözleşmeyle €20/ay. Backup için aynı sağlayıcının Object Storage hizmeti (eu2.contabostorage.com).
> **Durum:** locked (MVP-1.5 Epic #215 ile delivered).
> **Tarih:** 2026-05-07 (INDEX v1.4 ile resmileşti — MVP-1.5 sürümünde Hetzner CCX23'ten geçiş tamamlandı).

## Bağlam

MVP-1 başlangıcı [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §0'da Hetzner CCX23 (4 vCPU / 16 GB / 240 GB) ile planlanmıştı (~$29/ay). Ancak MVP-1.5 öncesi şu sıkıntılar kondu:

1. **CPU darboğazı** — embedding worker + image VLM + Celery beat + retrieval aynı 4 vCPU'da yarış. Latency artıyor.
2. **RAM yetmiyor** — Postgres shared_buffers 4GB + bge-m3 local model preload (~2.3 GB) + bge-reranker (568 MB) + workers + Next.js SSR aynı 16 GB'a sığmıyor.
3. **NVMe IO** — pgvector cosine search ve binary quantization HNSW build için NVMe latency kritik.
4. **Backup egress maliyeti** — B2 → VPS arası egress (özellikle restore drill aylık) ücretli; aynı-sağlayıcı (Contabo) egress free.

Karar tek bir ekosistem (Contabo: VPS + Object Storage) seçerek hem maliyet hem performans hem de operasyonel basitlik kazanıyor.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Hetzner CCX23 (devam) | Olgun, dokümana yazılı | CPU/RAM yetmiyor (yukarıda) | Reddedildi (MVP-1.5'te) |
| Hetzner CCX43 upgrade (8 vCPU / 32 GB) | Aynı ekosistem | ~$66/ay, RAM hala dar | Reddedildi (Contabo daha iyi cost/perf) |
| AWS / GCP / Azure | Olgun, full ecosystem | 5-10x maliyet, vendor lock | Reddedildi (early stage için overkill) |
| Hetzner Storage Box (backup için) | Hetzner ekosistem | S3-uyumlu değil, scriptler farklı | Reddedildi |
| DigitalOcean Droplet 8 vCPU/16 GB | Tanıdık, düz arayüz | Maliyet ~$96/ay, daha az RAM | Reddedildi |

## Sonuçlar

- **Etkilenen varlıklar:** [[contabo-vps]]
- **Etkilenen kavramlar:** [[hot-cold-tier]] (Contabo Object Storage cold tier), [[binary-quantization]] (NVMe ile uyumlu)
- **Etkilenen kod:** [`infra/`](../../infra/) — Caddyfile, docker-compose.yml, deploy script.
- **Etkilenen dokümanlar:**
  - [INDEX.md](../../INDEX.md) §4 (locked) ve §5b (milestone tablosu) güncellendi.
  - [README.md](../../README.md) "MVP-1.5 Infra Migration" durumu güncel.
  - [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) §2.4 — VPS cost line revize edildi.
- **Etkilenen workflow:** [`.claude/skills/nodrat-dev/SKILL.md`](../../.claude/skills/nodrat-dev/SKILL.md) "manuel deploy fallback" bölümünde VPS bilgisi (host, port, user, SSH key path) Contabo bilgileriyle güncel.

## ⚠️ Çelişki — kaynak güncellemesi gerekli

[`docs/engineering/architecture.md`](../../docs/engineering/architecture.md) v0.1 (2026-05-01) hala Hetzner CCX23 yazıyor:

- §0 Yönetici Özeti: "Platform: Hetzner CCX23 (Ubuntu 22.04 LTS)"
- §0 MVP-1 minimum: "4 vCPU, 16 GB RAM, 240 GB NVMe (~$29/ay Hetzner)"
- §0 Ölçek hedefi: "8 vCPU, 32 GB, 500 GB (~$66/ay)"
- §9.1 Backup matrisi: "B2 (encrypted)"
- §12.1 Darboğaz noktaları: "CCX43'e upgrade"

[`INDEX.md`](../../INDEX.md) v1.4 (2026-05-07) ise net olarak Contabo: "Hosting: Contabo Cloud VPS 40 (12 vCPU / 48 GB / 250 GB NVMe, 20€/ay 12-ay) — dedicated MVP-1.5'ten itibaren" ve "Backup: Contabo Object Storage (S3-comp) encrypted, restore drill aylık (MVP-1.5'ten itibaren; öncesinde Backblaze B2)".

> **Aksiyon:** [`docs/engineering/architecture.md`](../../docs/engineering/architecture.md) v0.2 sürümü gerekiyor. `nodrat-dev` skill'iyle issue/branch/PR akışıyla güncelle. Bu wiki sayfası dokümana güncellenince log'da güncellemeli ([[architecture-md]] source sayfasının changelog satırı).

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
- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) — eski Hetzner planı (güncellenmeli)
- [docs/strategy/unit-economics.md §2.4](../../docs/strategy/unit-economics.md) — VPS cost line
