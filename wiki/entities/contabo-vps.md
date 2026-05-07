---
type: entity
title: "Contabo Cloud VPS 40 + Object Storage"
slug: "contabo-vps"
category: "infra"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "INDEX.md§4"
  - "INDEX.md§5b"
  - "README.md§Çekirdek kararlar"
  - ".claude/skills/nodrat-dev/SKILL.md§Manuel deploy"
tags: ["infrastructure", "hosting", "production", "contabo"]
aliases: ["nodrat-vps2", "production-vps", "contabo-cloud-vps-40"]
---

# Contabo Cloud VPS 40 + Object Storage

> **TL;DR:** Nodrat'ın production hosting'i. 12 vCPU / 48 GB RAM / 250 GB NVMe Cloud VPS, €20/ay 12-ay sözleşme. Backup için aynı sağlayıcının Object Storage hizmeti (eu2.contabostorage.com). MVP-1.5'ten itibaren dedicated.

## Tanım

Contabo, Almanya merkezli bir hosting sağlayıcı. "Cloud VPS 40" planı, Cloud VPS hattının üst basamağı — 12 vCPU AMD Ryzen, 48 GB DDR4 RAM, 250 GB NVMe SSD. Dedicated tier (paylaşımlı CPU değil) — predictable performance. Aynı sağlayıcı içi Object Storage transferi ücretsiz, bu da backup egress maliyetini sıfırlıyor.

## Nodrat'ta kullanım

- **Hangi servisleri host eder:** Tüm Docker Compose stack — caddy, web, api, postgres, redis, minio, 5 worker, scheduler. Bkz. [[architecture-md]] §2.1.
- **Hangi MVP'de devreye girdi:** MVP-1.5 (Epic #215, 2026-05-06 delivered). Öncesi Hetzner CCX23 ile başlamıştı.
- **Backup hedefi:** Contabo Object Storage — restic ile encrypted, retention 7 gün + 4 hafta + 6 ay. Aylık restore drill (R-OPS-03).

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| CPU | 12 vCPU AMD Ryzen | INDEX §4 |
| RAM | 48 GB DDR4 | INDEX §4 |
| Disk | 250 GB NVMe SSD | INDEX §4 |
| Maliyet | €20/ay (12 ay sözleşme) | INDEX §4 |
| OS | Ubuntu 22.04 LTS | architecture.md §0 |
| Hostname | `nodrat-vps2` | nodrat-dev SKILL.md |
| Production IP | 164.68.107.205 | nodrat-dev SKILL.md |
| SSH port | 22 | nodrat-dev SKILL.md |
| SSH user | root | nodrat-dev SKILL.md |
| SSH key path | `~/.ssh/vps_deploy` | nodrat-dev SKILL.md |
| Repo path | `/opt/nodrat` | nodrat-dev SKILL.md |
| Object Storage endpoint | eu2.contabostorage.com (S3-compatible) | INDEX §4 |
| Object Storage replication | Triple-replication | architecture.md §5.4 |
| Egress quota | 32 TB dahil | architecture.md §5.4 |

## Rolü ve faz ilişkisi

- **MVP-1 — MVP-1.4:** Hetzner CCX23 üzerinde production (~$29/ay, 4 vCPU / 16 GB / 240 GB NVMe). Architecture.md v0.1 bu sürümü dokümante ediyor.
- **MVP-1.5 (2026-04-2026-05):** Contabo VPS 40'a migration. Object Storage geçişi, cold-tier retention, body_html drop, pgvector binary quantization scaffold.
- **MVP-1.6+:** Contabo VPS 40'ta operasyonel sürdürülüyor.

## Manuel deploy bilgisi

GitHub Actions runner allocation fail durumunda VPS'e direkt SSH ile deploy yapılabilir. Detay: [`.claude/skills/nodrat-dev/SKILL.md`](../../.claude/skills/nodrat-dev/SKILL.md) "Manuel deploy fallback" bölümü.

```bash
# Tipik manuel deploy çağrısı
rsync -avz --delete --exclude=".git" \
  -e "ssh -i $HOME/.ssh/vps_deploy -p 22" \
  apps infra docker-compose.yml \
  "root@164.68.107.205:/opt/nodrat/"

ssh -i ~/.ssh/vps_deploy root@164.68.107.205 \
  "cd /opt/nodrat && docker compose --env-file .env up -d --force-recreate"
```

## Kararlar (locked)

- [[contabo-vps-hosting]] — bu varlığa bağlı locked karar (MVP-1.5'te Hetzner'dan geçiş).

## İlişkiler

- **İlgili kavramlar:** [[hot-cold-tier]] (Object Storage cold tier), [[binary-quantization]] (NVMe ile uyumlu pgvector quantization).
- **İlgili varlıklar:** [[celery-worker]] (bu VPS'te koşar).
- **İlgili kararlar:** [[contabo-vps-hosting]].
- **İlgili topics:** —

## Açık sorular / TODO

- **architecture.md güncellemesi:** v0.1 §0 / §9 / §12'de hala Hetzner yazıyor — kaynak doküman bu varlığa uygun değil. Issue açılıp güncellenmeli (bkz. [[contabo-vps-hosting]]'in çelişki notu).
- **Contabo uptime sürdürülebilirliği:** Contabo geçmişte ara sıra outage'lar yaşadı. SLA durumu ve gözlem dashboard'ları izleniyor mu? Better Uptime alarmı aktif mi?
- **Yatay ölçek:** MRR ≥ $5K sonrası worker'lar farklı VPS'e taşınabilir (architecture.md §12.2). Contabo'da multi-VPS private network konfigürasyonu test edilmeli.

## Kaynaklar

- [INDEX.md §4 (Çekirdek kararlar — locked)](../../INDEX.md)
- [INDEX.md §5b (Milestone tablosu — MVP-1.5)](../../INDEX.md)
- [README.md (Çekirdek kararlar)](../../README.md)
- [.claude/skills/nodrat-dev/SKILL.md (Manuel deploy fallback)](../../.claude/skills/nodrat-dev/SKILL.md)
- [docs/engineering/architecture.md §5.4 (Hot/Cold tier)](../../docs/engineering/architecture.md) — Object Storage entegrasyon
- [docs/strategy/unit-economics.md §2.4](../../docs/strategy/unit-economics.md) — VPS cost
