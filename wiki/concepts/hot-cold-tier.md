---
type: concept
title: "Hot/Cold storage tier"
slug: "hot-cold-tier"
category: "architecture-pattern"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/engineering/architecture.md§5.4"
  - "INDEX.md§5b"
tags: ["storage", "tier", "retention", "cost-optimization", "object-storage"]
aliases: ["storage-tiers", "hot-cold", "retention-strategy"]
---

# Hot/Cold storage tier

> **TL;DR:** Sık erişilen veriler (son 30 gün) VPS lokal NVMe + Postgres + MinIO'da (HOT); 30+ gün eski raw HTML, eski yüksek-res görseller ve restic snapshot'lar Contabo Object Storage'da (COLD). Aynı sağlayıcı içi transfer ücretsiz; egress maliyeti sıfırlanır. MVP-1.5 (Epic #215) ile aktif.

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

## Retention task (architecture.md §5.4)

```sql
-- Celery beat: gece 03:00 UTC
-- tasks.maintenance.archive_old_html
WHERE last_seen_at < NOW() - INTERVAL '30 days'
  AND raw_html_storage_path IS NULL  -- henüz arşivlenmemiş
→ gzip body_html → Contabo OS PUT
→ DB'de body_html = NULL, storage_path = 's3://...'
→ idempotent (batch limit: 500 article/run)
```

Restore senaryosu:
```python
# Eski article'ın raw HTML'i lazım olduğunda:
storage_path → boto3 GET → gzip decode → response
# Latency: 100-300ms (eu2.contabostorage'tan)
```

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]] (storage abstraction'ın eşdeğeri), [[binary-quantization]] (HOT tier'da 32x sıkışma).
- **İlgili varlıklar:** [[contabo-vps]] (HOT host) + Object Storage (COLD).
- **İlgili kararlar:** [[contabo-vps-hosting]] — tek-sağlayıcı kararı bu tier yaklaşımını mümkün kıldı.
- **İlgili topics:** —

## Açık sorular / TODO

- **30 gün cutoff doğru mu?** Audit/legal için raw HTML lazım olma sıklığı ne? 30 gün altında "henüz arşivlenmemiş" kategorisi hangi pattern'de tüketiliyor? Veri lazım — Sentry/access log analizi yapılabilir.
- **Restore latency hedef:** 100-300ms acceptable mi `audit/legal` use case'i için? UI'a sürmediğinden tolerable, ama saatte 1000+ restore yapılırsa cumulative impact?
- **Cold tier retention:** Object Storage'da retention süresi ne? Yıllarca tutulacak mı yoksa N yıl sonra silme/archive (örn. Glacier-tier) opsiyonu var mı?

## Kaynaklar

- [docs/engineering/architecture.md §5.4 (Hot/Cold tier)](../../docs/engineering/architecture.md)
- [docs/engineering/architecture.md §9 (Backup ve DR)](../../docs/engineering/architecture.md)
- [INDEX.md §5b (MVP-1.5 milestone)](../../INDEX.md) — Epic #215, body_html drop, cold-tier retention
