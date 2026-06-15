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
| `warning` | Geçici/öngörülen + **#904 extraction-miss DAHİL** (GÖRÜNÜR) | hayır | "Uyarı" amber badge |
| `permanent_info` | legacy (RSS re-emit info — #445) | **evet** | "Bilgi" mavi badge |
| `discarded_info` | **#904** — yalnız GERÇEK kalıcı (true soft_404/duplicate/invalid_url); article `discarded` | **evet** (`resolved_at=now()`) | "Bilgi" mavi badge |

Default sorgu (`/admin/queue/failed`) `permanent_info` **VE `discarded_info`** kayıtlarını hariç tutar (#904) — alarm yorgunluğu önlenir; `warning` (extraction-miss dahil) GÖRÜNÜR kalır (görünürlük ilkesi). `?include_info=true` ile dahil edilebilir.

> **#904 güncelleme:** Eski model `thin_content`'i `permanent_info`+terminal `archived` yapıp **sessizce gizliyordu** (1182 kayıp kök nedeni). Yeni model: extraction-miss → `warning`+`quarantine` (GÖRÜNÜR+retryable); yalnız gerçek-kalıcı → `discarded_info`+`discarded`. Bkz. [[generic-extractor-cascade]].

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
| warning | 187 (resolved, 2026-05-09) | AA SPA migration tracker — `extractor multi-mode (#529)` ile çözüldü; Playwright gerekmedi |
| permanent_info | 91 (resolved) | RSS re-emit (74) + discovered_timeout legacy (88, ama overlap; net 91) |

## İlişkiler

- **İlgili topics:** [[data-pipelines]] — 8 boru hattı (kuyruk haritası bu sayfanın temeli)
- **İlgili varlıklar:** [[celery-worker]] — worker stack, beat schedule
- **İlgili kararlar:** [[pipeline-observability-location]] — `/admin/queue` mevcut sayfa, refactor (yeni sayfa açılmadı, kararla uyumlu)
- [[generic-extractor-cascade]] — #904 severity modeli (`discarded_info`) + `archived` semantik karmaşasını çözen karar
- [[extraction-confidence-telemetry]] — `warning` DLQ alarmını besleyen per-domain metrik
- [[adaptive-polling-tier]]
- [[realtime-rss-polling]]
- [[robots-transient-vs-genuine-deactivation]] — kaynak auto-deactivation izini `FailedJob(job_type='source.auto_deactivated', severity='warning')` ile bu DLQ'ya yazar (admin_audit_log.actor_id NOT NULL → sistem-aktör FailedJob kullanır)
- [[source-silent-deactivation-incident-2026-06]] — sessiz-deactivation incident retrospektifi

## Performans (#475 — Epic #443 follow-up)

`/admin/queue/overview` endpoint'i ilk implementasyonda **~4.3 saniye** sürüyordu. Profile sonucu:

| Adım | Önce |
|---|---|
| `inspect.active()` (timeout 2.0s) | 2123 ms |
| `inspect.ping()` (timeout 2.0s) | 2014 ms |
| 4 LLEN | 10 ms |
| 9 DB count sorgusu sıralı | 120 ms |
| **Toplam** | **~4300 ms** |

%95'i Celery `inspect()` zaman aşımıydı; worker'lar localhost broker'da 50-150ms cevap veriyordu, 2sn timeout aşırı güvenli marjdı.

### Yeni mimari

1. **Tek `inspect.active()` çağrısı** (eskiden 2 ayrı call): worker_name keys = worker_count, task listesi = active_counts. `inspect.ping()` artık çağrılmaz.
2. **Inspect timeout 2.0s → 0.5s**.
3. **Redis pipeline** ile 4 LLEN tek round-trip.
4. **5 saniye Redis snapshot cache** (`nodrat:broker:overview`): auto-refresh 10s + cache TTL 5s → her 2 yenilemenin 1'i cache hit.
5. Endpoint'te broker snapshot **`asyncio.create_task` ile arka planda async başlar**; DB sorguları sıralı çalışır (AsyncSession concurrent ops desteklemez, `asyncio.gather` çağırılmaz).

### Production ölçümler (canlı)

| Senaryo | Süre | Hızlanma |
|---|---|---|
| İlk yükleme (cache miss) | 510-684 ms | 6-8x |
| Sonraki yenileme (cache hit) | 11-50 ms | **86-390x** |

UI HTTPS round-trip:
- `/admin` (özet sayfası, `getQueueOverview` çağırır): **152 ms**
- `/admin/queue`: **276 ms**

### Frontend ek optimizasyon

- **Bakım görevleri (`/admin/queue/maintenance`) ayrı 30 saniye interval** ile yenilenir (beat schedule en kısa interval 5 dk olduğu için 30s yeterli)
- Ana refresh (10s) sadece queue overview + failed_jobs çağırır → daha az iş, daha hızlı render

## Image VLM fail sayım pattern (#479 — Epic #443 stabilizasyon)

Image VLM kuyruğu için fail sayımı **diğer kuyruklardan farklı** çalışır:

```
crawl_queue / event_queue / embedding_queue:
  failed_jobs WHERE created_at >= 24h AND job_type LIKE prefix
                 (uniform — task tarafı _record_failure helper ile yazar)

image_vlm_queue:
  article_images WHERE status='failed' AND processed_at >= 24h
                  (özel — process_article_image_vlm task failed_jobs'a YAZMAZ,
                   sadece article_images.status='failed' set eder)
```

**Sebep:** image_vlm task'ı tasarımdan beri her image için ayrı `failed_jobs`
kaydı yazmıyor (storage tasarrufu — bir article 5+ image içerebilir, hepsi
aynı kaynaktan fail ederse DLQ şişer). Status + error_message + processed_at
tek satırda yeterli teşhis.

**`processed_at` semantiği genişletildi (#479):**
- Eskiden sadece SUCCESS path'te set ediliyordu
- Yeni: 3 fail path de (`ImageRejected`, `NIM_API_KEY missing`, `VLMError`)
  `processed_at = NOW()` — "VLM call yapıldı, sonuç başarısız" anlamı

**Kod referansı:** [admin_queue.py `_image_vlm_failed_count_24h`](../../apps/api/app/api/admin_queue.py).

## Error tracking (#477 — fail nedeni UI'da görünür)

Eskiden image_vlm fail mesajı sadece **Celery result backend**'inde tutuluyordu;
UI'dan erişilemiyor, "VLM çıktısı yok" jenerik mesajı gösteriliyordu. NIM 403
incident'ında bu eksikliğin maliyeti netleşti.

**Düzeltme:**
- Migration `20260508_2200` — `article_images.error_message TEXT NULL` kolonu
- Task 3 fail path'ine yazılır:
  ```
  rejected: HTTP 404 (gone) at HEAD     ← ImageRejected (kaynak silmiş)
  NIM_API_KEY missing                    ← settings hatası
  vlm: NIM error: status=403 body={...}  ← VLMError (auth/parse/4xx)
  ```
- `MediaImageDTO.error_message` field, list + reprocess endpoints döner
- UI [media/page.tsx](../../apps/web/src/app/admin/media/page.tsx): `status='failed'
  && error_message` varsa kırmızı renkte render (title attr ile full detay)

**Sonuç:** her fail için neden tek bakışta görünür. NIM auth issue, kaynak silmiş, parse fail birbirinden ayırt edilebilir.

## JSON parser robustness (#480 — VLM tolerant parser)

NIM Llama 4 Maverick bazen Türkçe karakterleri **bozuk Unicode escape ile**
yazıyor (4 hex digit yerine 3 — örn. `\u00b` yerine `ç`). `json.loads`
reddediyor → eski parser fallback'a düşüp raw JSON'u `vlm_caption` alanına
döküyordu. Production'da %0.2 oran (4/2002 kayıt) ama UI'da çirkin sızıntı.

**`_safe_json_parse` 3 katmanlı parser:**

| Katman | Mantık |
|---|---|
| L1 | `json.loads(text)` — sağlıklı %99.8 response |
| L2 | `\u(1-3 hex)` invalid escape → literal'e çevir → tekrar `json.loads` |
| L3 | Regex ile manuel `caption` + `ocr_text` + `depicts` extraction |

**Ek koruma:** prompt'a UTF-8 hint — modeli baştan caydırır.

**`vlm_caption` (özet) + `ocr_text` (kayıpsız OCR) ayrı alanlar:** Hukuki belge
gibi uzun OCR içeren görsellerde caption **kısa akıllı yorum**, ocr_text **ham
metin** olarak ayrılır. Limit: caption 5000 char, ocr_text 10000 char.

**Repair migration `20260509_0000`:** Mevcut 4 bozuk kaydı `_safe_parse` ile
doğru alanlara dağıttı. Test coverage: 7 unit test (gerçek production sample
dahil — Turkish Airlines `u\u00bçak` örneği).

## `archived` semantik karmaşası (#483 — UI label fix)

> **⚠️ ÇÖZÜLDÜ (#904, 2026-05-16):** Bu bölümün anlattığı `archived` status DEĞERİ **tamamen kaldırıldı**. `status='archived'` → `quarantine` (extraction-miss, retryable) + `discarded` (gerçek kalıcı, terminal) olarak ayrıştırıldı; `#478` 72h+ backfill mantığı yaş-tabanlı değil deneme-tabanlı (`extract_attempts`) oldu. Cold-tier `archived_at`/`cold_storage_key` (aşağıdaki ilk satır) AYRI kalır, etkilenmedi. Kanonik: [[generic-extractor-cascade]]. Aşağısı tarihsel bağlam içindir.

Kod tabanında `archived` kelimesi **iki farklı amaçla** kullanılıyor:

| Kavram | Field/Value | Anlam | Article kullanılır mı? | UI |
|---|---|---|---|---|
| **Cold tier archive** | `archived_at` (timestamp) + `cold_storage_key` (S3 path) | 30+ gün eski article'ın `raw_html`'i Contabo OS'a taşındı. `cleaning.py` state machine'de geçiş yok; `cold_tier_archive` task sadece bu iki field'ı set eder. | **EVET** — `status='cleaned'` kalır, RAG'da kullanılır, audit/legal için raw HTML cold storage'dan saniyeler içinde fetch edilir | yok (görünmez) |
| **Terminal failed status** (#478) | `status='archived'` value | 72h+ `status='failed'` article'lar `retry_failed` task'ı tarafından bypass ediliyordu, ama `failed` olarak alarm yaratıyorlardı. PR #478 backfill ile bu kayıtları `archived`'a çekti — terminal state, retry yok, content yok | **HAYIR** — terminal | "**İşlenemiyor**" (#483 label fix; eskiden "Arşiv") |

**İki kavram aynı kelimeyi paylaşıyor ama farklı:** cold tier `archived_at` set edilirken **status DEĞİŞMEZ** (article aktif kalır); status='archived' ise terminal kapanış. Maintenance task `cold_tier_archive` ([maintenance.py:139](../../apps/api/app/workers/tasks/maintenance.py#L139)) sadece `archived_at = now, cold_storage_key = ...` UPDATE yapar.

Cold tier detayı: [[hot-cold-tier]]. Status state machine: [cleaning.py:67-69](../../apps/api/app/core/cleaning.py#L67) (`STATUS_CLEANED → {STATUS_ARCHIVED, STATUS_FAILED}`, `STATUS_ARCHIVED: set()` terminal).

**Future cleanup (out of scope):** Status için yeni isim (`abandoned` / `permanent_failed`) — schema check constraint + migration + state machine update gerek. Şu an UI label fix yeterli.

## Operasyonel olaylar / öğrenimler (Epic #443 stabilizasyon)

### `celery_app` import bug (503 BROKER_UNAVAILABLE)

Tüm retry/run-now endpoint'leri canlıdan beri 503 dönüyordu. Kök neden:
`admin_queue.py` imports'ında `from app.workers.celery_app import celery_app`
satırı eksikti. `send_task` çağrılarında her seferinde `NameError` fırlıyordu,
generic `except Exception` bunu 503'e çeviriyordu.

**Niçin gözden kaçtı:**
- Manuel `docker exec ... python -c "..."` test'inde ben ayrıca import etmiştim
- pytest router-registered smoke test sadece import-time çalışır, request-time `NameError`'u yakalamaz
- Frontend'den deneme yapan kullanıcı 503 alıyordu ama log incelenmemişti

**Lesson:** Endpoint testleri **gerçek body döndürmeli**, sadece status code yetmiyor. MVP-3 cut-over'da load test (#388) bu tip NameError'ları yakalar.

### NIM API key sessiz 403

NIM API key revoked/expired olunca **hiçbir alarm tetiklenmedi**. Worker log'unda her image task fail oluyordu ama operasyonel monitoring yoktu. Kullanıcı UI'da fail birikimi görünce fark etti.

**Lesson:** External provider key'ler için **sağlık check task'ı** gerek (R-OPS-07 candidate). Provider × günde bir lightweight call → 401/403 dönerse alarm.

### `failed_jobs` impedance mismatch

image_vlm task tarafı failed_jobs'a yazmıyordu, admin queue tarafı saymaya çalışıyordu → her zaman 0. **Lesson:** Yeni task eklerken DLQ yazım policy'si + sayım pattern aynı PR'da düşünülmeli; "yeniden iyi olur" diye bırakılırsa sayfaya 0 olarak yansır.

### Sonsuz dispatch loop tehlikesi (#488)

`_record_failure` helper severity='permanent_info' iken article.status'u değiştirmiyordu (eski yorum: *"article zaten cleaned veya pipeline devam ediyor"*). Gerçekte duplicate_content path'inde article **DISCOVERED**'da kalıyordu → backfill_discovered her 5 dk yeniden dispatch → fetch_detail tekrar duplicate → **sonsuz loop**. Production'da saatte 180 yeni DLQ kaydı + 14 article'lık takılı havuz oluştu.

**Düzeltme:**
1. State machine `core/cleaning.py`: `DISCOVERED → ARCHIVED` + `FETCHED → ARCHIVED` + `FAILED → ARCHIVED` geçişleri eklendi (terminal exit)
2. `_record_failure` helper'a `article_status_override` parametresi
3. `duplicate_content` call-site: `STATUS_ARCHIVED` ile terminal'e taşındı

**Lesson:** Beat schedule × terminal-olmayan state = sonsuz loop riski. Yeni `permanent_info` path eklerken her zaman state machine'de **terminal exit**'i düşünmek gerekir. Helper'ın "dokunmama" varsayımı (cleaned senaryosu için doğru) discovered/fetched senaryolarında loop yaratıyor — caller'ın kasıtlı override ile state'i kapatması zorunlu.

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

- ~~**AA SPA migration kararı (#460):** AA aa.com.tr Tailwind+JS SPA'ya geçti, statik HTML extract imkânsız. Üç seçenek: (1) `sources.is_active=false` geçici disable, (2) Playwright JS-render (#71 LATER cut-list ile düzgün), (3) JSON-LD özet kabul (önerilmez). 187 mevcut failure warning olarak resolve edildi, yeni AA fetch'leri hâlâ fail ediyor.~~ **ÇÖZÜLDÜ 2026-05-09 ([#529](https://github.com/selmanays/nodrat/issues/529) [PR #533](https://github.com/selmanays/nodrat/pull/533)):** Extractor multi-mode cascade (precision → default → recall) + extract_fallback boş `<main>` guard. Playwright gerekmedi — SSR HTML üzerinde çalışıyor. 167 stuck article.extract DLQ → 0, 45h cleaned blackout sonlandı. Detay: [[data-pipelines]] §1 Kural A6.
- **Drill-down panel (#461)** — stack_trace + payload_json + article_url + Celery task_id yan panelde gösterilebilir. Sonraki oturuma kaldı (alarm temiz, aciliyet düşük).
- **`worker_task_log` tablosu** — embedding_queue için 24h success approximation güvenilir hale gelsin (chunk transition pahalı sorgu). Celery `task_postrun` signal hook ile yazılabilir.
- **`crawler_jobs` tablosu** — artık hiç write yok. Tablonun gelecekteki rolü: kaldır vs. admin retry audit ledger olarak yeniden tanımla. Karar verilmeli.
- **Date range filter** — last_attempt_at için (sonraki iterasyon).
- **`tasks.maintenance.detect_stale_discovered`** — şu an gerek yok (discovered orphan article = 0, backfill_discovered + retry_failed yeterli). Tekrar ortaya çıkarsa task eklenir.
- **Provider key validity check (#R-OPS-07 candidate)** — NIM 403 gibi sessiz expire'lar için günlük lightweight call + alarm. Bu oturumun ana öğrenimi.
- **`triggered_by` admin/beat ayrımı** — `record_run_sync` her zaman `'beat'` yazıyor; admin manuel tetiklemede `'admin'` ayırt edilmeli (Celery task headers ile).

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
