---
type: topic
title: "Contabo Object Storage — Sistemdeki Tüm Kullanım Aşamaları"
slug: "contabo-object-storage-usage"
category: "synthesis"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/core/storage.py"
  - "apps/api/app/workers/tasks/maintenance.py"
  - "apps/api/app/workers/celery_app.py"
  - "apps/api/app/api/admin_system.py"
  - "apps/api/app/api/admin_settings.py"
  - "apps/api/app/config.py"
  - "apps/api/app/models/article.py"
  - "infra/backup.sh"
  - ".env.example"
tags: ["contabo", "object-storage", "s3", "cold-tier", "backup", "code-derived"]
aliases: ["contabo-os-usage", "contabo-s3-asamalar", "object-storage-usage"]
---

# Contabo Object Storage — Sistemdeki Tüm Kullanım Aşamaları

> **TL;DR:** Contabo Object Storage (`https://eu2.contabostorage.com`, bucket `nodrat-prod`) Nodrat sistemde **5 farklı kod aşamasında** kullanılır: (1) cold tier archive task — 30+ gün eski raw_html'leri MinIO'dan taşır; (2) cold tier restore task — admin manuel geri yükleme; (3) restic backup — günlük encrypted snapshot; (4) admin telemetry — `/admin/system` bucket stats; (5) boto3 client factory — diğer 4'ün ortak adapter'ı. MVP-1.5 (#219 PR-4 + #330 backup migration) ile production'a girdi.

> ⚠️ **Önemli flag durumu:** Cold tier archive task'ının **`cold_tier.enabled` runtime setting'i** [`admin_settings.py:406`](../../apps/api/app/api/admin_settings.py:406)'de **default False**. Production'da admin panel'den enable edilmeden 30+ gün eski raw_html aktif olarak Contabo'ya taşınmaz. Backup pipeline ise her gün koşar ve flag'den bağımsızdır. **Doğrulama gereki:** Production app_settings'te `cold_tier.enabled` mevcut değer ne? Admin telemetry (`/admin/system`) bucket içinde `cold/` prefix object count >0 ise zaten enable edilmiş demektir.

## Bağlam

Kullanıcı 2026-05-10 sorusu: "Contabo Object Storage şu anki sistemde hangi aşamalarda kullanılıyor?" Wiki yüksek seviyede bahsetse de ([[contabo-vps]] entity, [[hot-cold-tier]] concept, [[data-pipelines]] §8) somut kod entegrasyonları (path:line refs, admin telemetry, settings flag, DB kolonları) tek yerde toplu değildi. Bu sayfa o boşluğu doldurur.

## Konfigürasyon — endpoint, bucket, credentials

| Anahtar | Değer | Kaynak |
|---|---|---|
| Endpoint | `https://eu2.contabostorage.com` | [config.py:60](../../apps/api/app/config.py:60), [.env.example:173](../../.env.example:173) |
| Region | `eu2` | [config.py:61](../../apps/api/app/config.py:61), [.env.example:174](../../.env.example:174) |
| Bucket | `nodrat-prod` (default) | [config.py:62](../../apps/api/app/config.py:62), [.env.example:175](../../.env.example:175) |
| Auth | `S3_ACCESS_KEY_ID` + `S3_SECRET_ACCESS_KEY` | [.env.example:176-177](../../.env.example:176) |
| Signature | S3v4 + path-style addressing | [storage.py:93-96](../../apps/api/app/core/storage.py:93) |
| Backup ayrıca | `RESTIC_PASSWORD` (encrypted snapshot key) | [.env.example:184](../../.env.example:184) |

`RESTIC_REPOSITORY` `infra/backup.sh:70`'te `s3:${S3_ENDPOINT_URL}/${S3_BUCKET}/restic` olarak türetilir — yani backup pipeline aynı bucket'ın `restic/` prefix'ine yazar.

## Aşama 1️⃣ — Cold tier archive (30+ gün raw_html → Contabo)

> **Akış:** MinIO (hot, VPS NVMe) → gzip compress → Contabo Object Storage (cold, S3). DB'de `archived_at` + `cold_storage_key` set; MinIO'dan kaynak silinir (hot disk free).

| Detay | Değer |
|---|---|
| Task | `tasks.maintenance.cold_tier_archive` |
| Async impl | [`_archive_one`](../../apps/api/app/workers/tasks/maintenance.py:47) (per-article) |
| Batch wrapper | [`_cold_tier_archive_async`](../../apps/api/app/workers/tasks/maintenance.py:163) |
| Beat schedule | Günlük **03:30 UTC** (backup 04:00'tan **önce** → tutarlı state) — [celery_app.py:181-188](../../apps/api/app/workers/celery_app.py:181) |
| Settings flag | `cold_tier.enabled` default **False** ([admin_settings.py:406](../../apps/api/app/api/admin_settings.py:406)) |
| Runtime tunable | `cold_tier.batch_size` (default 100), `cold_tier.max_age_days` (default 30) — DB override beat kwargs'i ezer (#353 pattern, [maintenance.py:194-202](../../apps/api/app/workers/tasks/maintenance.py:194)) |
| Bucket key formatı | `cold/raw-html/{yyyy}/{mm}/{article-id}.html.gz` ([storage.py:105](../../apps/api/app/core/storage.py:105)) |
| Object metadata | `article-id`, `original-size`, `archived-at` (ISO) ([maintenance.py:117-121](../../apps/api/app/workers/tasks/maintenance.py:117)) |
| Content type | `application/gzip` + `Content-Encoding: gzip` |
| Compression | `gzip.compress` — raw HTML 30-60 KB → ~5-10 KB (5-10x) ([maintenance.py:99](../../apps/api/app/workers/tasks/maintenance.py:99)) |
| DB kolon | `articles.archived_at` (TIMESTAMPTZ), `articles.cold_storage_key` (TEXT) — [models/article.py:111-117](../../apps/api/app/models/article.py:111), migration [20260506_1500](../../apps/api/alembic/versions/20260506_1500_articles_archived_at.py) |
| Idempotent | `archived_at NOT NULL` olanlar `_archive_one`'da `already_archived` döner ([maintenance.py:62-64](../../apps/api/app/workers/tasks/maintenance.py:62)) |
| Aday seçimi | `WHERE archived_at IS NULL AND raw_html_storage_path IS NOT NULL AND created_at < NOW()-30d ORDER BY created_at ASC LIMIT 100` ([maintenance.py:208-217](../../apps/api/app/workers/tasks/maintenance.py:208)); `idx_articles_archive_candidate` partial index'i destekler |

**Hata yolu:**
- `minio_missing` — DB'de path var ama MinIO'da obje yok → `archived_at` set edilmez, admin manuel inceleme.
- `cold_put_failed` — Contabo PUT fail → `summary.error` döner, `archived_at` set edilmez (sonraki run yeniden dener).
- Cold copy başarılı, MinIO delete fail → uyarı log'u; tekrar dispatch'te `already_archived` döner.

> **Kavramsal not:** Bu task `archived_at`'ı set eder ama [[hot-cold-tier]]'da vurgulandığı gibi **`articles.status='cleaned'` kalır** — RAG pipeline aynen çalışır. `articles.status='archived'` (#478 backfill, terminal failed) farklı bir kavramdır; UI'da "İşlenemiyor" etiketi (#483) bu ikincisi içindir.

## Aşama 2️⃣ — Cold tier restore (Contabo → MinIO, admin manuel)

> **Akış:** Cold (Contabo) → gzip decompress → MinIO PUT (hot tier'a geri); DB'de `archived_at`/`cold_storage_key` NULL'a reset.

| Detay | Değer |
|---|---|
| Task | `tasks.maintenance.cold_tier_restore` |
| Async impl | [`_restore_one`](../../apps/api/app/workers/tasks/maintenance.py:270) |
| Tetikleyici | Admin manual dispatch — reprocess / investigation |
| Beat schedule | **Yok** (manuel) |
| Hata durumları | `not_archived` (zaten hot'ta), `no_cold_key` (admin inceleme), `cold_get_failed`, `minio_put_failed` |

Bulk restore için ayrı batch task yok (henüz gerek olmadı — [maintenance.py:344-346](../../apps/api/app/workers/tasks/maintenance.py:344) yorumda not düşülmüş).

## Aşama 3️⃣ — System backup (restic → Contabo)

> **Akış:** PostgreSQL `pg_dump` + MinIO data dir snapshot + config dosyaları → restic encrypt → Contabo Object Storage'da `restic/` prefix.

| Detay | Değer |
|---|---|
| Script | [`infra/backup.sh`](../../infra/backup.sh) |
| Tetikleyici | Cron (sistem TZ Europe/Istanbul) **04:00** günlük — [backup.sh:4](../../infra/backup.sh:4) |
| Restic backend | `s3:${S3_ENDPOINT_URL}/${S3_BUCKET}/restic` ([backup.sh:70](../../infra/backup.sh:70)) |
| AWS env | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` `S3_*` env'lerinden export edilir ([backup.sh:71-72](../../infra/backup.sh:71)) |
| Yedek içerik | (1) `pg_dump --format=custom --no-owner --no-acl`; (2) `rsync /opt/nodrat/data/minio/`; (3) `.env` + `docker-compose*.yml` + `infra/` |
| Snapshot tag'leri | `auto` + `YYYY-MM-DD` |
| Retention | `keep-daily 7` + `keep-weekly 4` + `keep-monthly 6` ([backup.sh:171-176](../../infra/backup.sh:171)) |
| Flags | `--skip-minio`, `--skip-prune` (debug için) |
| Restore drill | Aylık (architecture.md §9, R-OPS-03 mitigation) — son drill tarihi belirsiz (TODO) |

> **Migration notu:** Önceki backup hedefi Backblaze B2'ydi. MVP-1.5 PR-2 (#330 / commit `714d5b2`) ile Contabo OS'a migrate edildi — aynı sağlayıcı içi transfer ücretsiz, restore drill maliyeti sıfırlandı. Bkz. [[contabo-vps-hosting]].

## Aşama 4️⃣ — Admin telemetry (`/admin/system` bucket stats)

> **Akış:** Admin paneli "System Health" sayfasında bucket içeriği `list_objects_v2` ile paginated taranır; top-level prefix bazlı (örn. `cold/`, `restic/`) size + count gruplanır. **Tek READ-only endpoint.**

| Detay | Değer |
|---|---|
| Endpoint | `GET /admin/system/health` ve özet `GET /admin/system/summary` |
| Schema | `ContaboInfo` ([admin_system.py:100-105](../../apps/api/app/api/admin_system.py:100)) — endpoint, bucket, size_gb, object_count, by_prefix |
| Collector | [`_collect_contabo_os`](../../apps/api/app/api/admin_system.py:247) (sync, paginated 1000 key/page) |
| Async wrapper | `await asyncio.to_thread(_collect_contabo_os)` ([admin_system.py:395](../../apps/api/app/api/admin_system.py:395)) — boto3 sync API'yi event loop'tan çıkar |
| Cache | 60s in-memory (boto3 round-trip overhead'i azaltmak için) |
| Hata davranışı | Exception → boş `ContaboInfo` (size=0, count=0) + log ([admin_system.py:286-293](../../apps/api/app/api/admin_system.py:286)) |
| UI etkisi | Admin "/admin/system" sayfasında VPS + Postgres + MinIO + **Contabo OS** + containers + backups bir arada gösterilir |

**Yan etki:** `cold/` prefix object count >0 ise cold tier archive task'ının en az bir kez gerçekten koştuğunu (yani `cold_tier.enabled=True` flip edilmiş olduğunu) doğrulamanın hızlı yolu.

## Aşama 5️⃣ — Boto3 client factory (`get_cold_storage_client`)

> **Rol:** Yukarıdaki 4 aşamadan 3'ü (1, 2, 4) bu factory üzerinden Contabo S3 client'ı oluşturur. Backup script (3) farklı — restic kendi S3 stack'iyle direkt bağlanır.

| Detay | Değer |
|---|---|
| Helper | [`get_cold_storage_client`](../../apps/api/app/core/storage.py:74) |
| Endpoint | `settings.s3_endpoint_url` |
| Auth | `settings.s3_access_key_id` + `settings.s3_secret_access_key.get_secret_value()` |
| Region | `settings.s3_region` |
| Imza | S3v4, path-style ([storage.py:93-96](../../apps/api/app/core/storage.py:93)) |
| Bucket key helper | [`build_cold_storage_key(article_id, year, month)`](../../apps/api/app/core/storage.py:100) — `cold/raw-html/{yyyy}/{mm}/{id}.html.gz` |

`get_s3_client` ([storage.py:52](../../apps/api/app/core/storage.py:52)) ise **MinIO** için ayrı bir factory — endpoint farkı (`localhost:9100`, SSL toggle), aynı path-style. İki factory'nin karışmaması önemli: cold tier task `_archive_one` ikisini de kullanır (read MinIO, write Contabo).

## Bucket içi prefix haritası (production)

```
nodrat-prod/
├── cold/
│   └── raw-html/
│       └── 2026/
│           ├── 04/{article-id}.html.gz
│           └── 05/{article-id}.html.gz
└── restic/
    ├── config        # restic repository metadata
    ├── data/         # encrypted blob store
    ├── index/        # snapshot index
    ├── keys/
    └── snapshots/    # snapshot pointers
```

Admin telemetry her iki prefix'i ayrı sayar; hangi tür veri ne kadar yer kaplıyor net görünür.

## Çıkarımlar

1. **Contabo OS = tek S3 backend, iki ayrı amaç.** Cold tier archive (uygulama veri yaşam döngüsü) ve restic backup (disaster recovery) — aynı bucket farklı prefix. Cross-contamination yok çünkü key namespace ayrı.
2. **Cold tier feature gate'li, backup değil.** `cold_tier.enabled=False` default — production'da explicit enable gerekir; backup ise her gün koşar ve flag-bağımsız. Bu ayrım kritik: kullanıcı "cold tier aktif mi?" sorusunda **app_settings tablosunu** veya `/admin/system` bucket stats'ı kontrol etmek zorunda; config.py default'una bakmak yanıltıcı.
3. **Admin telemetry = blackbox değil.** `/admin/system`'de Contabo bucket'ı paginated taranıp prefix/size raporlanıyor; "cold tier ne kadar dolu?" sorusu admin panel'den anlık cevaplanır.
4. **Aynı sağlayıcı transfer = ücretsiz.** [[contabo-vps]] (VPS) → eu2.contabostorage.com (OS) trafiği egress quota'sına dahil değil. Bu, hot/cold tier ekonomisini ve aylık restore drill'ini ucuza getiren temel kurulum kararıdır ([[contabo-vps-hosting]]).
5. **Boto3 sync, FastAPI async.** `_collect_contabo_os` `asyncio.to_thread` ile thread pool'a düşürülür. Cold tier task ise zaten Celery worker context'inde sync çalışabilir. İki farklı pattern aynı boto3 client'ı paylaşıyor.

## İlişkiler

- **Beslediği kararlar:** [[contabo-vps-hosting]] (single-provider hosting + storage + backup)
- **İlgili varlıklar:** [[contabo-vps]] (host + Object Storage entity), [[celery-worker]] (cold tier task `default` queue'da koşar)
- **İlgili kavramlar:** [[hot-cold-tier]] (yüksek seviye HOT/COLD stratejisi)
- **İlgili topics:** [[data-pipelines]] §8 (Pipeline 8 overview — bu sayfa onun kod-seviye karşılığı)

## Açık sorular / TODO

- **Production'da `cold_tier.enabled` mevcut değer:** True mu, False mu? Admin panel `/admin/settings` veya `/admin/system` cold/ prefix object count ile doğrulanmalı.
- **Cold tier monthly drill:** Restore prosedürü `cold_tier_restore` ile ne sıklıkta test ediliyor? Son test tarihi belirsiz (yedek drill aylık ama cold tier restore drill ayrı).
- **Bucket size alarmı:** 250 GB plan limit; Contabo OS dolduğunda nasıl davranıyor (PUT 507 mı, soft warning mi)? Admin telemetry'ye eşik bazlı alarm eklendi mi?
- **Backup retention vs cold tier retention:** Backup `keep-monthly 6` (6 ay); cold tier raw_html için kalıcı saklama (hiç pruning yok). Yıllar içinde cold/ prefix sınırsız büyüyebilir; archive→delete politikası yok.
- **Restore latency benchmark:** [[hot-cold-tier]] 100-300ms diyor ama ölçüm tarihli değil. `_restore_one` üzerinde production timing log'u var mı?

## Kaynaklar

- [apps/api/app/core/storage.py](../../apps/api/app/core/storage.py) — boto3 client factory + key helper
- [apps/api/app/workers/tasks/maintenance.py](../../apps/api/app/workers/tasks/maintenance.py) — `_archive_one`, `_restore_one`, batch wrapper
- [apps/api/app/workers/celery_app.py §beat_schedule](../../apps/api/app/workers/celery_app.py) — 03:30 UTC schedule
- [apps/api/app/api/admin_system.py](../../apps/api/app/api/admin_system.py) — `_collect_contabo_os` telemetry
- [apps/api/app/api/admin_settings.py §cold_tier.*](../../apps/api/app/api/admin_settings.py) — flag + tunable defaults
- [apps/api/app/config.py §S3 cold tier](../../apps/api/app/config.py) — endpoint/bucket/region defaults
- [apps/api/app/models/article.py:111-117](../../apps/api/app/models/article.py:111) — `archived_at` + `cold_storage_key` kolonları
- [apps/api/alembic/versions/20260506_1500_articles_archived_at.py](../../apps/api/alembic/versions/20260506_1500_articles_archived_at.py) — DB migration
- [infra/backup.sh](../../infra/backup.sh) — restic + Contabo backup script
- [.env.example §S3 cold tier + Backup](../../.env.example) — env değişken şeması
- [docs/engineering/architecture.md §5.4 Hot/Cold tier](../../docs/engineering/architecture.md), [§9 Backup](../../docs/engineering/architecture.md) — yüksek seviye doküman
