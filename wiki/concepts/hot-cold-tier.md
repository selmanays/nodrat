---
type: concept
title: "Hot/Cold storage tier"
slug: "hot-cold-tier"
category: "architecture-pattern"
status: "live"
created: "2026-05-07"
updated: "2026-05-10"
sources:
  - "docs/engineering/architecture.md§5.4"
  - "INDEX.md§5b"
  - "apps/api/app/workers/tasks/maintenance.py"
  - "apps/api/app/api/admin_settings.py"
tags: ["storage", "tier", "retention", "cost-optimization", "object-storage"]
aliases: ["storage-tiers", "hot-cold", "retention-strategy"]
---

# Hot/Cold storage tier

> **TL;DR:** Sık erişilen veriler (son 30 gün) VPS lokal NVMe + Postgres + MinIO'da (HOT); 30+ gün eski raw HTML, eski yüksek-res görseller ve restic snapshot'lar Contabo Object Storage'da (COLD). Aynı sağlayıcı içi transfer ücretsiz; egress maliyeti sıfırlanır. MVP-1.5 (Epic #215) ile aktif.

> ⚠️ **İsim çakışması — `archived` iki farklı kavramdır:** (1) **`articles.archived_at`** field (cold tier maintenance — bu sayfa); raw_html S3'e taşındı, **article hala `status='cleaned'` ve RAG'da kullanılır**. (2) **`articles.status='archived'`** value (#478 backfill, terminal state); 72h+ failed retry'dan vazgeçilmiş, content yok, kalıcı işlenemez. UI'da **"İşlenemiyor"** etiketi (#483) bu ikincisi içindir. Detay: [[queue-management]] §"Operasyonel olaylar".

## Tanım

Hot/cold tier, "verilerin erişim sıklığına göre fiyat-performans optimizasyonu" prensibinin storage'a uygulanması. NVMe gibi hızlı ama görece pahalı medya sadece **gerçekten lazım olan** veri için kullanılır; arşivsel veri ucuz Object Storage'a taşınır. Nodrat tüm veriyi aynı sağlayıcı (Contabo) içinde tuttuğu için tier'lar arası transfer ücretsiz — egress maliyeti, sık karşılaşılan bir cost-trap, sıfırlanır.

## Neden Nodrat'ta var

Üç sorun çözülüyor:

1. **NVMe darboğazı.** pgvector cosine search her sorguda çalışır → NVMe latency kritik. Eski raw_html'in NVMe'de durması bu kritik veriyi sıkıştırır.
2. **Disk büyümesi.** Yıl 1 ölçek tahmini ~80 GB Postgres + ~500 GB MinIO. 250 GB NVMe yetmez.
3. **Backup egress.** B2'den (önceki backup hedefi) restore için egress ücretli. Aylık restore drill (R-OPS-03) ucuz olmalı. Aynı sağlayıcı içi transfer free olduğu için Contabo Object Storage net win.

## HOT tier — VPS lokal

```text
Konum:        /var/lib/postgresql + /var/lib/minio (volume)
Veri:
  • articles (metadata + clean_text)
  • article_chunks + embedding (1024-dim, vector + bit)  ← retrieval bundan
  • agenda_cards + summary + embedding
  • event_clusters
  • Son 30 gün thumbnail (UI render)

Boyut: 20-50 GB (1 yıl, 25 kaynak)
Latency: <5ms (NVMe)
```

Retrieval pipeline tamamen HOT tier'a bağlı: `user query → bge-m3 embed → agenda_cards.embedding cosine search`. Recency-only fallback yasak (A9 prensibi).

## COLD tier — Contabo Object Storage

```text
Endpoint:     eu2.contabostorage.com (S3-compatible)
Replication:  Triple-replication
Egress:       32 TB/ay dahil (free)
Veri:
  • 30+ gün eski raw_html.gz
  • Orijinal yüksek-res görseller (UI thumbnail HOT'ta)
  • restic DB snapshot'ları
  • Eski source HTML snapshot'ları (audit/legal/debug)

Boyut: 100-500 GB (yıllar boyu, sabit aylık artış)
Latency: 100-300ms (PUT/GET)
```

## Tier ne neden?

| Veri | Tier | Neden |
|---|---|---|
| `articles.clean_text` | HOT | Generation pipeline her sorguda kullanır |
| `article_chunks.embedding` | HOT | pgvector cosine — NVMe latency kritik |
| `agenda_cards` | HOT | Daily/weekly retrieval, hot path |
| Son 30 gün thumbnail | HOT | UI render, latency-sensitive |
| 30+ gün `raw_html` | COLD | Sadece audit/legal/debug — saniyeler içinde fetch yeterli |
| Orijinal yüksek-res görsel | COLD | UI thumbnail HOT'ta yeterli, original arşiv için |
| restic DB snapshot | COLD | Disaster recovery — ihtiyaç anında pull |

## Retention task — kod gerçeği (architecture.md §5.4)

> **Doğru beat schedule + flag durumu (kod kanıtlı, 2026-05-10):**

```python
# tasks.maintenance.cold_tier_archive — günlük 03:30 UTC (apps/api/app/workers/celery_app.py:181)
# Settings flag: cold_tier.enabled default False (admin_settings.py:406) — manuel enable
# Aday: WHERE archived_at IS NULL AND raw_html_storage_path IS NOT NULL
#         AND created_at < NOW() - 30d  ORDER BY created_at ASC LIMIT 100
# Akış: MinIO GET → gzip.compress → Contabo PUT (cold/raw-html/{yyyy}/{mm}/{id}.html.gz)
#         → DB UPDATE archived_at + cold_storage_key → MinIO DELETE
# Idempotent: archived_at NOT NULL olanlar 'already_archived' döner
# Runtime tunable: cold_tier.batch_size (100), cold_tier.max_age_days (30)
```

> ⚠️ **Çelişki / dikkat:** Bu sayfa "MVP-1.5'ten beri aktif" diyor; kod ise `cold_tier.enabled` default False bırakıyor (manuel admin enable gerek). **Production'daki gerçek durum:** admin panel `/admin/settings` veya `/admin/system` → Contabo bucket `cold/` prefix object count >0 ise enable edilmiş demektir. Backup pipeline (restic) flag'den bağımsız her gün koşar.

Restore senaryosu (admin manuel — `tasks.maintenance.cold_tier_restore`):

```python
# _restore_one (maintenance.py:270)
# 1) Cold GET: cold.get_object(Bucket=s3_bucket, Key=article.cold_storage_key)
# 2) gzip.decompress
# 3) MinIO PUT (raw_html_storage_path'e geri)
# 4) DB UPDATE archived_at=NULL, cold_storage_key=NULL
# Latency: 100-300ms (eu2.contabostorage'tan)
```

Bulk restore task yok; manuel single-article (admin endpoint).

## Admin telemetry — cold tier ne kadar dolu?

`/admin/system` endpoint'i Contabo bucket'ını paginated tarar (`list_objects_v2`, 1000 key/page) ve top-level prefix bazlı (`cold/`, `restic/`) size + count rapor eder. Detay: [[contabo-object-storage-usage]] §Aşama 4.

Hızlı kontrol:
```python
# apps/api/app/api/admin_system.py:247 _collect_contabo_os
# returns ContaboInfo(endpoint, bucket, size_gb, object_count, by_prefix={cold/, restic/})
# 60s in-memory cache; asyncio.to_thread ile FastAPI async loop'tan sync boto3 ayrıştırılır
```

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]] (storage abstraction'ın eşdeğeri), [[binary-quantization]] (HOT tier'da 32x sıkışma).
- **İlgili varlıklar:** [[contabo-vps]] (HOT host) + Object Storage (COLD).
- **İlgili kararlar:** [[contabo-vps-hosting]] — tek-sağlayıcı kararı bu tier yaklaşımını mümkün kıldı.
- **İlgili topics:** [[contabo-object-storage-usage]] (5 aşama kod-seviye sentez), [[data-pipelines]] §8.

## Açık sorular / TODO

- **30 gün cutoff doğru mu?** Audit/legal için raw HTML lazım olma sıklığı ne? 30 gün altında "henüz arşivlenmemiş" kategorisi hangi pattern'de tüketiliyor? Veri lazım — Sentry/access log analizi yapılabilir.
- **Restore latency hedef:** 100-300ms acceptable mi `audit/legal` use case'i için? UI'a sürmediğinden tolerable, ama saatte 1000+ restore yapılırsa cumulative impact?
- **Cold tier retention:** Object Storage'da retention süresi ne? Yıllarca tutulacak mı yoksa N yıl sonra silme/archive (örn. Glacier-tier) opsiyonu var mı?

## Kaynaklar

- [docs/engineering/architecture.md §5.4 (Hot/Cold tier)](../../docs/engineering/architecture.md)
- [docs/engineering/architecture.md §9 (Backup ve DR)](../../docs/engineering/architecture.md)
- [INDEX.md §5b (MVP-1.5 milestone)](../../INDEX.md) — Epic #215, body_html drop, cold-tier retention
