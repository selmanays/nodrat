---
type: entity
title: "Celery worker stack"
slug: "celery-worker"
category: "service"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/engineering/architecture.md§3"
  - "docs/engineering/architecture.md§2.2"
tags: ["worker", "queue", "celery", "redis", "async"]
aliases: ["worker", "celery-stack", "queue-worker"]
---

# Celery worker stack

> **TL;DR:** Nodrat'ın asenkron iş yığını. Celery 5 + Redis broker üzerinde 5 ayrı queue grubu (crawl, image VLM, cleaning, embedding, event/RAPTOR, generation, scheduler) farklı concurrency profilleriyle koşuyor. Tüm bu container'lar tek VPS'te ([[contabo-vps]]) çalışır ama mantıksal olarak ayrı.

## Tanım

Celery, Python ekosistemindeki olgun task queue framework'ü. Nodrat'ta tüm I/O-bound (HTTP fetch, LLM çağrısı) ve CPU-bound (text cleaning, dedup) işler API request'inden ayrılıp Celery worker'larına devredilir. Bu, FastAPI'nin sync olarak tied-up olmasını engeller ve user-facing latency'i düşük tutar.

Redis hem Celery broker (queue), hem de result backend olarak kullanılır. Beat scheduler (celery beat) periyodik görevleri tetikler.

## Nodrat'ta kullanım

- **Hangi servisler:** `apps/api/app/workers/` altında task fonksiyonları, `apps/api/app/celery_app.py` worker giriş noktası.
- **Hangi VPS'te koşar:** [[contabo-vps]] — Docker Compose ile her queue grubu ayrı container.
- **Hangi MVP'de aktif:** MVP-1'den beri.

## Queue grupları (architecture.md §3.1)

| Queue | Görev | Concurrency | Worker container |
|---|---|---|---|
| `crawl_queue` | RSS fetch, article discover/fetch/extract, source category | 2 (HTTP-bound) | `worker_scraper` |
| `image_vlm_queue` | NIM Llama 4 Maverick VLM (caption + OCR + depicts) | 2 (NIM 40 RPM) | `worker_image_vlm` |
| `cleaning_queue` | Article clean, dedupe (CPU-bound) | 2 | `worker_cleaner` |
| `embedding_queue` | Article embed (NIM/local), batch=100 | 1 (rate limit) | `worker_embedding` |
| `event_queue` | Event cluster, agenda_card.generate, raptor.weekly_summary | 1 (LLM-bound) | `worker_rag` |
| `generation_queue` | User.generate (sync API'den de tetiklenir) | 3 (per-tier limited) | `worker_rag` |
| `billing_queue` | (Faz 6) subscription.sync, webhook.process | 1 | (planned) |
| ~~`media_queue`~~ | DEPRECATED — #304 ile `image_vlm_queue`'a birleşti | — | — |
| ~~`vision_queue`~~ | DEPRECATED — Faz 4 iptal, MVP-1.4'te VLM aktif | — | — |

## Beat schedule (MVP-1)

```python
'crawl-all-sources':           crontab(minute='*/15')           # her 15 dk
'event-clustering':            crontab(minute=0, hour='*')      # saatlik
'agenda-card-refresh':         crontab(minute=15, hour='*')     # saatlik (#175)
'build-weekly-summary-cards':  crontab(minute=0, hour=2)        # gece 02:00 (RAPTOR)
'cleanup-old-snapshots':       crontab(minute=0, hour=3)        # gece 03:00
'database-backup':             crontab(minute=0, hour=4)        # gece 04:00
'source-health-check':         crontab(minute=0, hour='*/6')    # 6 saatte bir
'backfill-pending-images':     crontab(minute='*/5')            # her 5 dk (image VLM)
'retry-failed-images':         crontab(minute=20, hour='*')     # saatte 1 (max_age=72h)
```

## Retry policy (architecture.md §3.2)

| Hata tipi | Politika |
|---|---|
| HTTPError 429 | exp backoff, max=3, source-level cooldown |
| HTTPError 5xx | retry=3 |
| Timeout | retry=2 |
| ParserError | retry=0 → `failed_jobs` |
| MediaError | retry=2 (image VLM için 3) |
| VLMRateLimitError, VLMTimeoutError, ImageDownloadError | autoretry |
| ImageRejected, VLMError | permanent fail (DB 'failed', retry yok) |

Dead letter: tüm başarısız job → `failed_jobs` tablosu, admin panelinden manuel retry.

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]] — generation/embedding worker'ları provider katmanı kullanır.
- **İlgili varlıklar:** [[contabo-vps]] (host), [[deepseek]] / [[claude-haiku-4-5]] (LLM çağrıları), [[local-bge-m3]] (embedding).
- **İlgili kararlar:** —
- **İlgili topics:** —
- [[data-pipelines]]
- [[mvp-1-scope]]
- [[mvp-1-scope-lock]]
- [[own-slm-strategy]]
- [[pii-redaction-mandatory]]
- [[queue-management]]
- [[risk-source-fragility]]
- [[sft-data-pipeline]]
- [[architecture-md]]

## Açık sorular / TODO

- **Generation queue per-tier limit:** "concurrency: 3 per-tier limited" ne demek? Free tier user'lar arasında fair-scheduling mi var? Implementation detayı net değil.
- **PgBouncer:** architecture.md §12.1'de "1.000+ user'da PgBouncer" yazıyor. Worker'lar postgres connection'ı doğrudan açıyor — pool sınırı (default 100) ne zaman dolar?
- **Worker fragmenter:** §12.1 "CCX43'e upgrade → worker'ları farklı container'larda fragmenter". Contabo VPS 40'a geçince bu plan revize gerekiyor.

## Kaynaklar

- [docs/engineering/architecture.md §3 (Worker mimarisi)](../../docs/engineering/architecture.md)
- [docs/engineering/architecture.md §2.2 (Compose servisleri)](../../docs/engineering/architecture.md)
- [docs/engineering/architecture.md §12 (Ölçek geçiş)](../../docs/engineering/architecture.md)
