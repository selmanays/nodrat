---
type: decision
title: "Taze haber için adanmış hızlı embed lane (clean→aranabilir saniyeler)"
slug: "fresh-article-fast-embed-lane"
category: "infra"
status: "live"
created: "2026-05-16"
updated: "2026-05-16"
sources:
  - "apps/api/app/workers/tasks/embedding.py (FAST_EMBED_QUEUE, fast kwarg)"
  - "apps/api/app/workers/tasks/articles.py (clean→chunk fast dispatch)"
  - "docker-compose.yml (worker_embedding_fast)"
  - "GitHub PR #894 (#893)"
tags: ["infra", "ingestion", "embedding", "celery", "freshness", "performance"]
aliases: ["fast-embed-queue", "embedding_fast_queue", "worker_embedding_fast"]
---

# Taze haber için adanmış hızlı embed lane

> **TL;DR:** Yeni ingest edilen makalenin `cleaned` → chunk+embed
> (aranabilir) zinciri, bulk re-chunk/re-embed/maintenance/sft/backfill
> ile **paylaşılan `embedding_queue`**'da FIFO bekliyordu → prod ölçüm
> clean→aranabilir **ortalama ~2dk, max ~9dk**. Kullanıcı bu pencerede
> sorduğunda güncel haber "bulunamadı" dönüyordu (kanıt: conv beee3455,
> "Antalya yoğurt" — chunk cevaptan 78sn SONRA oluştu). Çözüm: yalnız
> **clean ANINDA** tetiklenen taze zincir ADANMIŞ `embedding_fast_queue`'ye
> yönlenir; ona adanmış `worker_embedding_fast` consumer'ı bulk'tan ASLA
> bloke olmaz. Prod kanıt: clean→aranabilir **~30sn, sıfır kuyruk
> beklemesi** (önceden 2-9dk). Embedding modeli/chunking/retrieval
> mimarisi DEĞİŞMEDİ — yalnız dispatch kuyruğu.

## Bağlam — neden gerekti

Nodrat'ın marka vaadi güncellik ("no drat"). Kullanıcılar ağırlıkla
güncel olayları yakalamak için geliyor. Ingest pipeline:

```
scrape (crawl_queue) → clean (crawl_queue, status='cleaned')
   └─ chunk_article (embedding_queue) → embed_article_chunks (embedding_queue)
```

`embedding_queue` **paylaşımlı**: `tasks.embedding.*` + `tasks.maintenance.*`
(re-embed/cold-tier bulk) + `tasks.sft_curator.*` + `backfill-missing-chunks`
(2 saatte bir 50-chain batch) + re-chunk/backfill bulk. Bulk iş varken
taze makalenin chunk/embed task'ı FIFO'da bunların ARKASINDA bekliyordu.

**Prod kanıt (conv beee3455, 2026-05-16):** "Antalya'da 1 ton yoğurt
imha edildi" makalesi 08:00:24 cleaned, ama chunk'ı **08:03:28**
oluştu (kullanıcı 08:01:58 sordu → 08:02:10 "bulunamadı"); embedding
~08:08:55. Sistemik ölçüm: `cleaned→embedded` ort. ~2dk, **max ~8m44s**
(600 makale/24s). Kullanıcı dar tazelik penceresinde sordu → doğru ama
istenmeyen "bulunamadı".

> ℹ️ Bu bir retrieval/muhakeme/sohbet-bağlam bug'ı DEĞİLDİ — pipeline
> doğru çalışıyordu, makale o an henüz aranabilir değildi. Kök: ingest→
> aranabilir **gecikmesi** (ayrı altyapı katmanı).

## Karar

**Taze (gerçek-zamanlı) zincir için adanmış öncelik lane'i.** Yalnız
`clean` ANINDA tetiklenen zincir ayrılır:

| Yol | Kuyruk | Consumer | Değişti mi |
|---|---|---|---|
| **Taze:** clean → `chunk_article(fast=True)` → `embed_article_chunks(fast=True)` | `embedding_fast_queue` | **`worker_embedding_fast`** (adanmış, `-Q embedding_fast_queue --concurrency=2`) | YENİ |
| **Bulk:** backfill-missing-chunks, maintenance re-embed, re-chunk, sft | `embedding_queue` | `worker_embedding` (`--concurrency=4`) | DEĞİŞMEDİ |

Mekanik:
- `embedding.py`: `FAST_EMBED_QUEUE="embedding_fast_queue"` sabiti +
  `fast: bool=False` kwarg `chunk_article`/`embed_article_chunks`
  (+ `_async`) zinciri boyunca taşınır. Dispatch site'ları (chunk→embed
  zinciri ve embed self-redispatch) `fast` ise `queue=FAST_EMBED_QUEUE,
  priority=9`, değilse aynen önceki davranış.
- `articles.py` clean→chunk dispatch (tek taze giriş noktası):
  `chunk_article.apply_async(..., kwargs={"fast":True},
  queue=FAST_EMBED_QUEUE, priority=9)`.
- `docker-compose.yml`: `worker_embedding_fast` servisi — aynı image/
  env/bge-m3 modeli, yalnız `-Q embedding_fast_queue`.
- **Bulk callers** (`backfill_missing_chunks`, `embedding.py` re-chunk,
  maintenance) `fast` vermez → varsayılan `False` → `embedding_queue`
  aynen. Yeni opsiyonel kwarg = tüm mevcut çağıranlar otomatik etkisiz.

## Why

- **Endişeleri ayır:** "taze haber hızlı aranabilir olmalı" (her zaman,
  yüksek öncelik) ≠ "bulk re-embed/backfill" (throughput, arka plan).
  Tek paylaşımlı FIFO kuyruk ikisini birbirine bağlıyordu → tazelik
  bulk'a kurban. Adanmış lane = taze hiç beklemez.
- **Kalite/mimari korunur:** aynı `BAAI/bge-m3`, aynı chunking mantığı,
  aynı retrieval. Sadece DISPATCH kuyruğu farklı (idempotent, geri
  alınabilir). Embedding makinesine dokunulmadı.
- **Dayanıklılık:** `worker_embedding_fast` düşse, mevcut
  `backfill-missing-chunks` beat (2h, normal kuyruk) `cleaned` ama
  chunk'sız makaleleri yakalar (`fast` vermeden) → yeni failure mode
  YOK; en kötü ihtimalle eski davranışa düşer.
- **Düşük maliyet:** concurrency 2 (taze hacim « bulk); 12 vCPU
  bütçesini bozmaz.

## Alternatifler

| Alternatif | Reddetme nedeni |
|---|---|
| Celery `priority` (tek kuyruk) | Redis broker'da kesin önceliği garanti etmez (drain round-robin'e yakın); bulk hâlâ araya girer |
| `worker_embedding`'i `embedding_fast_queue`'yi de tüketsin | İzolasyon kalmaz — bulk task'lar fast worker slotlarını da doldurur |
| Embedding'i clean task'ı içinde senkron yap | Clean (crawl_queue) bloklanır, throughput çöker; mimari karışır |
| Retrieval'da "çok yeni olabilir" UX yaması | Gecikmeyi çözmez, yalnız maskeler (band-aid) |

## İlişkiler

- Retrieval hazinesi: [[chunks-first-retrieval]]
- Entity recall pipeline: [[ner-pipeline]]
- Tüketen mimari: [[agentic-generate-orchestration]] (`search_news`
  bu chunk'ları arar — taze lane onları saniyeler içinde görünür kılar)
- Kök analizin geldiği zincir: [[chat-knowledge-evolution]]

## Kaynaklar

- `apps/api/app/workers/tasks/embedding.py` (`FAST_EMBED_QUEUE`,
  `chunk_article`/`embed_article_chunks` `fast` kwarg + dispatch)
- `apps/api/app/workers/tasks/articles.py` (clean→chunk fast dispatch)
- `docker-compose.yml` (`worker_embedding_fast`)
- `apps/api/app/workers/celery_app.py` (`backfill-missing-chunks` 2h
  güvenlik ağı — değişmedi)
- GitHub PR #894 (#893). Prod mechanism smoke: dispatch→received ~0s,
  chunk 14s + embed 15s = clean→aranabilir ~30sn (önceden 2-9dk).
