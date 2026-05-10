---
type: entity
title: "Contabo Cloud VPS 40 + Object Storage"
slug: "contabo-vps"
category: "infra"
status: "live"
created: "2026-05-07"
updated: "2026-05-10"
sources:
  - "INDEX.md§4"
  - "INDEX.md§5b"
  - "README.md§Çekirdek kararlar"
  - ".claude/skills/nodrat-dev/SKILL.md§Manuel deploy"
  - "apps/api/app/core/storage.py"
  - "apps/api/app/workers/tasks/maintenance.py"
  - "apps/api/app/api/admin_system.py"
  - "infra/backup.sh"
tags: ["infrastructure", "hosting", "production", "contabo", "object-storage"]
aliases: ["nodrat-vps2", "production-vps", "contabo-cloud-vps-40"]
---

# Contabo Cloud VPS 40 + Object Storage

> **TL;DR:** Nodrat'ın production hosting'i. 12 vCPU / 48 GB RAM / 250 GB NVMe Cloud VPS, €20/ay 12-ay sözleşme. Backup için aynı sağlayıcının Object Storage hizmeti (eu2.contabostorage.com). MVP-1.5'ten itibaren dedicated.

## Tanım

Contabo, Almanya merkezli bir hosting sağlayıcı. "Cloud VPS 40" planı, Cloud VPS hattının üst basamağı — 12 vCPU AMD Ryzen, 48 GB DDR4 RAM, 250 GB NVMe SSD. Dedicated tier (paylaşımlı CPU değil) — predictable performance. Aynı sağlayıcı içi Object Storage transferi ücretsiz, bu da backup egress maliyetini sıfırlıyor.

## Nodrat'ta kullanım

- **Hangi servisleri host eder:** Tüm Docker Compose stack — caddy, web, api, postgres, redis, minio, 5 worker, scheduler. Bkz. [[architecture-md]] §2.1.
- **Hangi MVP'de devreye girdi:** MVP-1.5 (Epic #215, 2026-05-06 delivered). Öncesi Contabo Cloud VPS 10 (paylaşımlı, 4 vCPU / 8 GB RAM, IP: 173.212.238.104, port 2222) — production hep Contabo ekosistemi içinde, sadece plan upgrade'i.
- **Backup hedefi:** Contabo Object Storage — restic ile encrypted, retention 7 gün + 4 hafta + 6 ay. Aylık restore drill (R-OPS-03). Önceki backup hedefi Backblaze B2'ydi; MVP-1.5 PR-2 (#330, commit `714d5b2`) ile Contabo OS'a migration yapıldı.

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

- **MVP-1 — MVP-1.4:** Contabo Cloud VPS 10 üzerinde production (~$5/ay, 4 vCPU / 8 GB RAM / 75 GB NVMe, IP: 173.212.238.104, port 2222). Backup hedefi Backblaze B2.
  > **Not:** [[architecture-md]] v0.1 bu fazı "Hetzner CCX23" olarak dokümante ediyordu — bu yalnızca **draft planlama dili**ydi. Production hiçbir zaman Hetzner üzerinde çalışmadı; başından beri Contabo ekosisteminde.
- **MVP-1.5 (2026-04-2026-05):** Contabo Cloud VPS 40'a yükseltme (yeni IP 164.68.107.205, port 22). Backup hedefi Contabo Object Storage'a migration (#330 / `714d5b2`). Cold-tier retention, body_html drop, pgvector binary quantization scaffold aktif edildi.
- **MVP-1.6+:** Contabo Cloud VPS 40'ta operasyonel sürdürülüyor. Eski VPS 10 (173.212.238.104) decommission yolunda — eski `.env` ve B2 artıkları gözden geçirilince kapatılacak.

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

## Object Storage — kod entegrasyonu (5 aşama)

Contabo Object Storage (`eu2.contabostorage.com`, bucket `nodrat-prod`) sistemde 5 farklı kod yolundan kullanılır. Detaylı sentez ve kod referansları için: [[contabo-object-storage-usage]].

| # | Aşama | Yön | Kod giriş noktası |
|---|---|---|---|
| 1 | Cold tier archive (30+ gün raw_html) | WRITE | [`_archive_one`](../../apps/api/app/workers/tasks/maintenance.py:47), beat 03:30 UTC |
| 2 | Cold tier restore (admin manuel) | READ + write MinIO | [`_restore_one`](../../apps/api/app/workers/tasks/maintenance.py:270) |
| 3 | Restic backup (pg_dump + minio + config) | WRITE | [`infra/backup.sh:70`](../../infra/backup.sh:70) cron 04:00 |
| 4 | Admin telemetry — bucket stats | READ-only | [`_collect_contabo_os`](../../apps/api/app/api/admin_system.py:247) |
| 5 | Boto3 client factory (1+2+4 ortak) | — | [`get_cold_storage_client`](../../apps/api/app/core/storage.py:74) |

> **Flag durumu:** Cold tier archive ([1] + [2]) `cold_tier.enabled` runtime setting'ine bağlı, default **False** ([admin_settings.py:406](../../apps/api/app/api/admin_settings.py:406)). Backup ([3]) flag-bağımsız her gün koşar.

## Kararlar (locked)

- [[contabo-vps-hosting]] — bu varlığa bağlı locked karar (MVP-1.5'te Contabo VPS 10 → Contabo VPS 40 upgrade'i + Backblaze B2 → Contabo OS backup migration'ı).

## İlişkiler

- **İlgili kavramlar:** [[hot-cold-tier]] (Object Storage cold tier), [[binary-quantization]] (NVMe ile uyumlu pgvector quantization).
- **İlgili varlıklar:** [[celery-worker]] (bu VPS'te koşar).
- **İlgili kararlar:** [[contabo-vps-hosting]].
- **İlgili topics:** [[contabo-object-storage-usage]] (kod-seviye 5 aşama sentezi), [[data-pipelines]] §8 (Pipeline 8 overview).

## Açık sorular / TODO

- **architecture.md temizliği:** v0.2 (#405, 2026-05-08) yalnızca DeepSeek migration'ını sync etti. §0/§2.1/§5.1/§9.1/§13'te hâlâ "Hetzner CCX23" ve "Backblaze B2" referansları var — production hiç Hetzner kullanmadı, B2 ise MVP-1.5'te Contabo OS'a migrate edildi. Ayrı `nodrat-dev` görevi ile §0/§2.1/§5.1/§9.1/§13 sync edilmeli.
- **Contabo uptime sürdürülebilirliği:** Contabo geçmişte ara sıra outage'lar yaşadı. SLA durumu ve gözlem dashboard'ları izleniyor mu? Better Uptime alarmı aktif mi?
- **Yatay ölçek:** MRR ≥ $5K sonrası worker'lar farklı VPS'e taşınabilir (architecture.md §12.2). Contabo'da multi-VPS private network konfigürasyonu test edilmeli.

## Kaynaklar

- [INDEX.md §4 (Çekirdek kararlar — locked)](../../INDEX.md)
- [INDEX.md §5b (Milestone tablosu — MVP-1.5)](../../INDEX.md)
- [README.md (Çekirdek kararlar)](../../README.md)
- [.claude/skills/nodrat-dev/SKILL.md (Manuel deploy fallback)](../../.claude/skills/nodrat-dev/SKILL.md)
- [docs/engineering/architecture.md §5.4 (Hot/Cold tier)](../../docs/engineering/architecture.md) — Object Storage entegrasyon
- [docs/strategy/unit-economics.md §2.4](../../docs/strategy/unit-economics.md) — VPS cost
