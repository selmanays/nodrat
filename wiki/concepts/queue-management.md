---
type: concept
title: "Queue management — Celery broker introspection + DLQ severity"
slug: "queue-management"
category: "architecture-technique"
status: "live"
created: "2026-05-08"
updated: "2026-05-08"
sources:
  - "apps/api/app/workers/celery_app.py"
  - "apps/api/app/api/admin_queue.py"
  - "apps/api/app/core/celery_introspect.py"
  - "apps/api/app/workers/tasks/articles.py"
  - "apps/api/alembic/versions/20260508_1900_failed_jobs_severity.py"
  - "apps/web/src/app/admin/queue/page.tsx"
  - "Epic #443, PR #447, #449, #454, #456"
tags: ["queue", "celery", "redis", "dlq", "observability", "admin", "architecture"]
aliases: ["queue-observability", "kuyruk-yonetimi", "dlq-severity"]
---

# Queue management — Celery broker introspection + DLQ severity

> **TL;DR:** Nodrat'ta worker kuyruğu = Celery + Redis broker. Admin gözlem `/admin/queue` sayfasında 4 ana kuyruğu (crawl_queue, embedding_queue, event_queue, image_vlm_queue) izler. Pending sayım Redis LLEN, çalışan sayım `celery inspect().active()`, 24h success/fail ilgili tablo transitions. DLQ (`failed_jobs`) 3 severity sınıfı tutar: `error` (gerçek hata), `warning` (geçici/öngörülen), `permanent_info` (RSS re-emit gibi info-level — auto-resolved). Admin retry endpoint Celery'ye `apply_async` ile gerçek dispatch yapar.

## Bağlam

Epic [#443](https://github.com/selmanays/nodrat/issues/443) öncesi `/admin/queue` sayfası iki temel hata barındırıyordu:

1. **Overview kartları `crawler_jobs` tablosundan sayım yapıyordu** — ama bu tabloya hiçbir Celery worker yazmıyordu. 16 hücrenin 12'si yapısal olarak yanlış (sürekli 0 ya da ölü ledger satırları gösteriyordu).
2. **Retry endpoint Celery'ye dispatch yapmıyordu** — sadece `crawler_jobs` insert ediyor + `failed_jobs.resolved_at` set ediyordu. "Tekrar dene" butonuna basınca hiçbir iş gerçekten broker'a girmiyordu.

Ek olarak DLQ:

3. **74 `article.duplicate_content` kaydı** alarm yorgunluğu yaratıyordu — bu kayıtlar gerçek hata değil, RSS re-emit / republish sırasında oluşan info-level olaylar.

## Mimarinin üç katmanı

### 1) Celery broker introspection ([core/celery_introspect.py](../../apps/api/app/core/celery_introspect.py))

Pending task sayımı için Redis LLEN, aktif task sayımı için `celery_app.control.inspect().active()`:

```python
async def get_queue_depths(queue_names) -> dict[str, int]:
    """Redis LLEN — broker'da pickup bekleyen task sayımı (O(1))."""

async def get_active_counts_by_queue(queue_names) -> dict[str, int]:
    """celery inspect().active() — worker'da çalışan task sayımı.
    routing_key + name fallback ile queue bazlı toplama."""

async def get_worker_count() -> int:
    """inspect().ping() — aktif worker sayısı (broker bağlantı sağlığı)."""
```

`task_routes` config'i ile birebir çalışır:

| Celery queue | Pipeline (data-pipelines.md) | Task prefix |
|---|---|---|
| `crawl_queue` | 1 — Source Crawl | `tasks.sources.*`, `tasks.articles.*` |
| `embedding_queue` | 2 — Embedding + 8 — Maintenance | `tasks.embedding.*`, `tasks.maintenance.*` |
| `event_queue` | 3 — Clustering + 5 — RAPTOR | `tasks.clustering.*`, `tasks.agenda.*`, `tasks.raptor.*` |
| `image_vlm_queue` | 4 — Image VLM | `tasks.image_vlm.*` |

### 2) DB approximation: 24h success/fail ([api/admin_queue.py](../../apps/api/app/api/admin_queue.py))

Tam metrik için `worker_task_log` tablosu gerekir (gelecekte). Şu an her kuyruk ilgili tablo transition'ından sayar:

| Queue | 24h Success approximation | 24h Fail (uniform) |
|---|---|---|
| crawl_queue | `articles.status='cleaned' AND updated_at >= 24h` | `failed_jobs job_type LIKE 'article.%'\|'source.%'\|'media.%'` |
| event_queue | `agenda_cards.created_at >= 24h` | `failed_jobs LIKE 'clustering.%'\|'agenda.%'\|'raptor.%'\|'event.%'` |
| image_vlm_queue | `article_images.status='processed' AND processed_at >= 24h` | `failed_jobs LIKE 'image.%'\|'image_vlm.%'\|'media.image.%'` |
| embedding_queue | (TODO — chunk transition pahalı, worker_task_log ile netleşir) | `failed_jobs LIKE 'embedding.%'\|'embed.%'\|'chunk.%'` |

### 3) DLQ severity classification ([models/job.py](../../apps/api/app/models/job.py))

`failed_jobs` tablosuna `severity VARCHAR(20) DEFAULT 'error'` kolonu eklendi. CHECK constraint:

```sql
severity IN ('error', 'warning', 'permanent_info')
```

| Severity | Anlam | Auto-resolve | UI |
|---|---|---|---|
| `error` (default) | Gerçek hata, alarm sayımına dahil | hayır | "Hata" kırmızı badge |
| `warning` | Geçici/öngörülen, manuel müdahale gerekir | hayır | "Uyarı" amber badge |
| `permanent_info` | RSS re-emit gibi info-level — log kaydı | **evet** (`resolved_at=now()`) | "Bilgi" mavi badge |

Default sorgu (`/admin/queue/failed`) `permanent_info` kayıtları hariç tutar — alarm yorgunluğu önlenir. `?include_info=true` veya `?severity=permanent_info` ile dahil edilebilir.

## Admin retry akışı

```
1. Admin tıklar [Tekrar dene] (severity != permanent_info ise)
2. POST /admin/queue/jobs/{failed_id}/retry
3. Backend:
   a. failed_jobs.job_type → JOB_TYPE_TO_TASK registry
   b. payload_json'dan article_id veya article_image_id çek
   c. celery_app.send_task(task_name, args=[arg], priority=7)
   d. failed_jobs.resolved_at = now()
   e. failed_jobs.resolution_note = "admin retry by X (celery_task_id=...)"
4. Celery worker pickup → article fetch_detail / image_vlm process
```

Hata kodları:
- `503 BROKER_UNAVAILABLE` — Redis/Celery erişilemez
- `422 JOB_TYPE_NOT_DISPATCHABLE` — bilinmeyen job_type (registry'de yok)
- `422 PAYLOAD_MISSING_TARGET_ID` — article_id veya article_image_id yok
- `409 ALREADY_RESOLVED` — failed_job zaten resolved

## Production baseline (Epic #443 + follow-up: önce → sonra)

| Metrik | Önce (2026-05-08 17:30 UTC) | Epic kapandı (19:30 UTC) | Follow-up sonra (21:30 UTC) | Δ kümülatif |
|---|---|---|---|---|
| `failed_jobs` unresolved | **396** | 305 | **30** | **−366 (%92)** |
| `article.duplicate_content` unresolved | 74 | 0 | 0 | auto-resolved |
| `article.discovered_timeout` unresolved | 88 | 88 | **0** | auto-resolved (#463) |
| `article.extract` unresolved (AA) | 187 | 187 | **0** | warning backfill (#460) |
| Alarm sayımına dahil olan info | 74 | 0 | 0 | severity ayrıştı |
| Crawl 24h success kartı | 0 (yapısal hatalı) | **311** | 311+ | gerçek veri |
| Worker count (broker bağlantı) | (gösterilmiyordu) | **5** | 5 | yeni metrik |
| Retry button → Celery dispatch | hayır | **evet** | evet | gerçek `apply_async` |
| UI tüm kayıtlara erişim | sadece ilk 50 | **pagination** | pagination + bulk | sayfa boyutu seçici |
| Auto-refresh | yok | **10s polling** | 10s polling | manuel yenileme yok |
| **Bulk operations** | yok | yok | **bulk-retry + bulk-resolve** | 200 id/req max |

### severity dağılımı (post-follow-up, 30 unresolved)

| severity | count | yorum |
|---|---|---|
| error | 30 | gerçek hatalar (28 fetch_detail + 2 extract evrensel) |
| warning | 187 (resolved) | AA SPA migration tracker — Playwright kararı için |
| permanent_info | 91 (resolved) | RSS re-emit (74) + discovered_timeout legacy (88, ama overlap; net 91) |

## İlişkiler

- **İlgili topics:** [[data-pipelines]] — 8 boru hattı (kuyruk haritası bu sayfanın temeli)
- **İlgili varlıklar:** [[celery-worker]] — worker stack, beat schedule
- **İlgili kararlar:** [[pipeline-observability-location]] — `/admin/queue` mevcut sayfa, refactor (yeni sayfa açılmadı, kararla uyumlu)

## Bakım görevleri (#468 — Epic #443 follow-up)

`/admin/queue` sayfasının altında **Bakım görevleri** kartı 5 backfill/retry maintenance task'ını listeler. Her görev için: insancıl ad + boru hattı + interval + son çalışma (zaman + duration + status) + dispatched count + JSON summary tooltip + **"Şimdi çalıştır" butonu**.

| Task | Pipeline | Beat schedule | Açıklama |
|---|---|---|---|
| `tasks.articles.backfill_discovered` | Kazıyıcı | Her 5 dk | Stuck `discovered` article'ları yakalar (broker dispatch loss recovery) |
| `tasks.articles.retry_failed` | Kazıyıcı | Saatte bir :25 | Failed article'ları `discovered`'a reset + fetch_detail dispatch |
| `tasks.image_vlm.backfill_pending` | Görsel VLM | Her 5 dk | Pending image'ları VLM kuyruğuna alır (NIM 40 RPM kapasitesi) |
| `tasks.image_vlm.retry_failed` | Görsel VLM | Saatte bir :20 | Failed image'ları (geçici hata) tekrar dener |
| `tasks.articles.backfill_missing_chunks` | Vektörleştirici | 2 saatte bir :30 | Cleaned ama chunks olmayan article'ları yakalar |

### Tracking mimarisi

- Celery `task_prerun` signal: `started_at` memory store (worker process içi, task_id keyed)
- Celery `task_postrun` signal: started_at + retval Redis'e yazılır
  - Key: `nodrat:maintenance:last:{task_name}`
  - TTL: 24 saat (eski sonuçlar düşer; UI "—" gösterir)
  - Payload: `{started_at, finished_at, duration_seconds, status, summary, triggered_by, error}`
- Sadece `TRACKED_TASKS` listesi izlenir; diğer Celery task'larına dokunmaz (overhead minimum)

### Endpoint'ler

```text
GET  /admin/queue/maintenance                    → 5 task listesi + son run
POST /admin/queue/maintenance/{task_name}/run-now → admin manuel tetikleme
                                                    (whitelist + Celery send_task
                                                     + audit_log action=
                                                     maintenance.run_now)
```

Hata kodları:
- `404 MAINTENANCE_TASK_NOT_FOUND` — whitelist dışı task adı
- `503 BROKER_UNAVAILABLE` — Celery/Redis erişilemez

## Açık sorular / TODO

- **AA SPA migration kararı (#460):** AA aa.com.tr Tailwind+JS SPA'ya geçti, statik HTML extract imkânsız. Üç seçenek: (1) `sources.is_active=false` geçici disable, (2) Playwright JS-render (#71 LATER cut-list ile düzgün), (3) JSON-LD özet kabul (önerilmez). 187 mevcut failure warning olarak resolve edildi, yeni AA fetch'leri hâlâ fail ediyor.
- **Drill-down panel (#461)** — stack_trace + payload_json + article_url + Celery task_id yan panelde gösterilebilir. Bir sonraki oturuma kaldı (alarm 30'a düştü, aciliyet düştü).
- **`worker_task_log` tablosu** — embedding_queue için 24h success approximation güvenilir hale gelsin (chunk transition pahalı sorgu). Celery `task_postrun` signal hook ile yazılabilir.
- **`crawler_jobs` tablosu** — artık hiç write yok. Tablonun gelecekteki rolü: kaldır vs. admin retry audit ledger olarak yeniden tanımla. Karar verilmeli.
- **Date range filter** — last_attempt_at için (sonraki iterasyon).
- **`tasks.maintenance.detect_stale_discovered`** — şu an gerek yok (discovered orphan article = 0, backfill_discovered + retry_failed yeterli). Tekrar ortaya çıkarsa task eklenir.

## Kaynaklar

- [Epic #443](https://github.com/selmanays/nodrat/issues/443) — Admin queue sayfası overhaul
- [PR #447](https://github.com/selmanays/nodrat/pull/447) — Celery broker depth + retry dispatch
- [PR #449](https://github.com/selmanays/nodrat/pull/449) — `ArticleImage.processed_at` hotfix
- [PR #454](https://github.com/selmanays/nodrat/pull/454) — `failed_jobs.severity` + duplicate_content auto-resolve
- [PR #456](https://github.com/selmanays/nodrat/pull/456) — UI pagination + severity badge + auto-refresh
- [apps/api/app/core/celery_introspect.py](../../apps/api/app/core/celery_introspect.py) — broker introspect helpers
- [apps/api/app/api/admin_queue.py](../../apps/api/app/api/admin_queue.py) — overview + retry endpoints
- [apps/api/alembic/versions/20260508_1900_failed_jobs_severity.py](../../apps/api/alembic/versions/20260508_1900_failed_jobs_severity.py) — migration
- [apps/web/src/app/admin/queue/page.tsx](../../apps/web/src/app/admin/queue/page.tsx) — admin UI
