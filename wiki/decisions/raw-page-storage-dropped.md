---
type: decision
title: "Ham haber sayfası (raw HTML) saklanmaz — cold-tier kaldırıldı"
slug: "raw-page-storage-dropped"
status: "locked"
decided_on: "2026-06-19"
decided_by: "founder"
created: "2026-06-19"
updated: "2026-06-19"
sources:
  - "docs/engineering/architecture.md§5.4"
  - "docs/legal/ropa.md§saklama"
  - "INDEX.md§5b"
tags: ["locked-decision", "storage", "retention", "cold-tier", "raw-html"]
aliases: ["raw-html-not-stored", "cold-tier-removed", "no-raw-page-storage"]
---

# Ham haber sayfası (raw HTML) saklanmaz — cold-tier kaldırıldı

> **Karar:** Ham haber sayfaları (raw HTML) **kalıcı saklanmaz**. Yalnız işlenmiş `body_html` + `clean_text` (+ chunks/embedding) tutulur; ham sayfa gerekirse **URL'den yeniden çekilir**.
> **Durum:** locked
> **Tarih:** 2026-06-19 (Epic #1634)

## Bağlam

MVP-1.5'te (#217/#219/#220) bir **hot/cold storage tier** niyeti tasarlandı: 30+ gün eski raw HTML'i MinIO (hot, VPS lokal) → Contabo Object Storage'a (cold) gzip'leyip taşı, `body_html`'i 24h sonra DROP et, gerekirse raw HTML'den re-extract et. Şema, task'lar, flag'ler, beat'ler, S3 client ve testler **tam kodlandı**.

**Ama 2026-06-19 audit'i (8-ajan workflow) ortaya koydu:** Ham HTML'i MinIO'ya yazan **upstream adım hiçbir zaman bağlanmadı** — fetch pipeline sayfayı çekip `body_html`/`clean_text` çıkardıktan sonra ham HTML'i **atıyordu**. `articles.raw_html_storage_path` repo-genelinde **0 kez yazılıyordu** → prod'da 23.9K makalenin **hepsinde NULL**, **0 arşiv**, MinIO `nodrat-snapshots` bucket'ı hiç oluşmadı. Yani cold-tier **fiilen hiç çalışmadı** (flag default OFF olmasının ötesinde, taşıyacağı veri yoktu). Daha tehlikelisi: `body_html_drop` "raw HTML'den re-extract mümkün" varsayımına dayanıyordu — bu yanlış olduğundan flag açılsaydı `body_html` **geri-dönülmez** silinirdi.

**Soru:** Yarım kalmış bu niyeti tamamlamak mı (raw HTML yakalamayı bağla), yoksa kaldırmak mı?

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| **Ham sayfayı saklama (seçildi)** | URL'ler zaten elde (gerekirse re-fetch); disk/maliyet/karmaşıklık sıfır; KVKK'da daha az veri | Bir makale sıfırdan re-extract edilemez (ama URL'den yeniden çekilebilir) | **seçildi** |
| Upstream capture'ı bağla + cold-tier'ı aktif et | Tam reproducibility (orijinal sayfa) | ~90 GB/yıl disk + Contabo maliyet + karmaşık idempotent ETL; çoğu haber için marjinal değer | reddedildi |
| Kodu olduğu gibi bırak (flag OFF) | Efor yok | Ölü/yanıltıcı kod + `body_html_drop` latent veri-kaybı tuzağı + docs/wiki yanlış "aktif" diyor | reddedildi |

## Sonuçlar

- **Kod (#1634 PR-1, 8799d5a):** `cold_tier_archive`/`cold_tier_restore` + `body_html_drop` task'ları, 6 settings flag, 2 beat, `build_cold_storage_key`, `minio_bucket_snapshots`, `test_cold_tier.py` kaldırıldı. `body_html` artık **kalıcı** (DROP edilmez).
- **Schema (#1634, migration 20260619_1300):** `raw_html_storage_path` + `cold_storage_key` + `archived_at` kolonları + `idx_articles_archive_candidate` index DROP edildi (hepsi NULL'dı → veri kaybı yok). Prod'da doğrulandı.
- **KORUNDU:** `body_html` (kalıcı), `s3_*` config + `get_cold_storage_client` (restic backup + admin disk telemetrisi kullanıyor), MinIO (görsel + genel obje deposu).
- **Etkilenen sayfalar:** [[hot-cold-tier]] (deprecated), [[data-pipelines]] (Pipeline-8 cold katmanı retired), [[queue-management]] (`archived_at` disambiguation güncellendi).
- **İlgili karar:** [[contabo-vps-hosting]] — Contabo Object Storage **backup için** geçerli kalır (cold-tier'dan bağımsız); bu karar değişmedi.

## Geri alma maliyeti

> Bu karar değiştirilirse (ham sayfa saklamaya geri dönülürse): (1) fetch pipeline'a raw HTML capture + MinIO upload adımı **eklenmeli** (hiç yoktu); (2) `raw_html_storage_path` kolonu + cold-tier task/flag/beat geri eklenmeli (migration); (3) docs (architecture §5.4, data-model, unit-economics, ropa.md KVKK) + wiki güncellenmeli. Yani "geri açmak" sıfırdan inşa demektir — özellik hiç çalışmadığı için kaybedilen bir şey yok.

## Kaynaklar

- [docs/engineering/architecture.md §5.4](../../docs/engineering/architecture.md) (RETIRED işaretli)
- [docs/legal/ropa.md](../../docs/legal/ropa.md) (KVKK saklama — "HTML snapshot 30 gün" kaldırıldı)
- GitHub: [Epic #1634](https://github.com/selmanays/nodrat/issues/1634) · PR #1635 (kod+schema) · #1636 (docs)
