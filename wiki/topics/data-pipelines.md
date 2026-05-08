---
type: topic
title: "Data Pipelines — Tüm Boru Hatları (8 pipeline overview)"
slug: "data-pipelines"
category: "architecture"
status: "live"
created: "2026-05-08"
updated: "2026-05-08"
sources:
  - "apps/api/app/workers/tasks/*.py"
  - "apps/api/app/api/app_generate.py"
  - "apps/api/app/api/public_search.py"
  - "apps/api/app/core/storage.py"
  - "apps/api/app/core/retrieval.py"
  - "apps/api/app/core/citation.py"
  - "infra/backup.sh"
  - "docs/engineering/architecture.md"
  - "docs/engineering/data-model.md"
tags: ["pipelines", "architecture", "workers", "rag", "vlm", "storage", "synthesis"]
aliases: ["all-pipelines", "boru-hatlari", "veri-akislari"]
---

# Data Pipelines — Tüm Boru Hatları

> **TL;DR:** Nodrat 8 pipeline'dan oluşur. **Veri içeri:** (1) source crawl, (4) image VLM. **Veri işleme:** (2) embedding, (3) clustering+agenda, (5) RAPTOR weekly. **Veri çıkışı:** (6) /app/generate (içerik üretim), (7) /ara (public search). **Altyapı:** (8) object storage + cold tier + backup. Her pipeline ayrı Celery task veya endpoint olarak çalışır; ortak provider abstraction üzerinden ([[provider-abstraction]]).

## Bağlam

Nodrat backend'i **stateless API + Celery worker'lar + Postgres + Redis + MinIO** mimarisi. Her pipeline kendi triggering mekanizmasıyla çalışır:

- **Scheduled** (Celery Beat): periodic crawl + maintenance + RAPTOR weekly
- **Event-driven** (queue): article cleaned → embed → cluster
- **API-triggered** (sync): /app/generate (auth'lı), /ara (public)

Pipeline diyagramları bu sayfada özet veriliyor; detay kod referansları her bölümde.

## Mimari kuş bakışı

```
                      KAYNAKLAR (RSS/Web)
                              │
                              ▼
   ┌──────────────────────────────────────────────┐
   │  PIPELINE 1: SOURCE CRAWL                    │
   │  RSS poll → discover → fetch detail → clean  │
   └─────────────────┬────────────────────────────┘
                     │ articles row + body_text
                     ▼
   ┌──────────────────────────────────────────────┐
   │  PIPELINE 4: IMAGE VLM (process & discard)   │
   │  Image URL → NIM Llama 4 → caption+OCR       │
   │  → article_images metadata (bytes drop)      │
   └─────────────────┬────────────────────────────┘
                     │ article cleaned event
                     ▼
   ┌──────────────────────────────────────────────┐
   │  PIPELINE 2: EMBEDDING                       │
   │  body_text → chunks → LOCAL bge-m3 (VPS CPU) │
   │  → article_chunks.embedding (1024-dim)       │
   └─────────────────┬────────────────────────────┘
                     │
                     ▼
   ┌──────────────────────────────────────────────┐
   │  PIPELINE 3: CLUSTERING + AGENDA             │
   │  cosine similarity → event_clusters          │
   │  → DeepSeek synthesis → agenda_cards         │
   └─────────────────┬────────────────────────────┘
                     │ daily cards
                     ▼
   ┌──────────────────────────────────────────────┐
   │  PIPELINE 5: RAPTOR-LITE (weekly summary)    │
   │  daily cards → cluster → weekly cards        │
   │  → agenda_cards.level=weekly/monthly         │
   └────────┬──────────────────────────┬──────────┘
            │                          │
            ▼                          ▼
   ┌─────────────────────┐    ┌─────────────────────┐
   │ PIPELINE 6:         │    │ PIPELINE 7:         │
   │ /app/generate       │    │ /ara public search  │
   │ (auth, X content    │    │ (anon, semantic     │
   │  üretim)            │    │  agenda search)     │
   └─────────────────────┘    └─────────────────────┘
            │
            ▼
   KULLANICI içerik (X post / summary / thread / headline)

   ───── Altyapı katmanı ───────────────────────────
   ┌──────────────────────────────────────────────┐
   │  PIPELINE 8: OBJECT STORAGE + COLD TIER      │
   │  - MinIO (image bytes — Faz 4 öncesi only)   │
   │  - Contabo Object Storage (cold tier 30+gün) │
   │  - restic backup (daily 04:00 → S3)          │
   └──────────────────────────────────────────────┘
```

---

## 1️⃣ Source Crawl Pipeline

> **Amaç:** RSS / category page poll → article discovery → detail fetch → trafilatura clean → DB write.
> **Trigger:** Celery Beat scheduler (her source'un `crawl_interval_minutes`'ı).
> **Kod:** [tasks/sources.py](../../apps/api/app/workers/tasks/sources.py), [tasks/articles.py](../../apps/api/app/workers/tasks/articles.py)

### Akış

```
[Celery Beat (her N dk)]
     │
     ▼
[tasks.sources.healthcheck_source]
     │  feedparser RSS / Playwright category page
     ▼
[Yeni RSS item / link bulundu]
     │
     ▼
[tasks.articles.discover]              ← yeni article queue'ya
     │  Dedupe katman 1: canonical_url exact match → varsa skip
     │  Dedupe katman 2 (#496): external_article_id (URL'den regex extract)
     │    same source + same ext_id → skip (slug değişimi yakalama)
     │  articles INSERT (status=discovered, ext_id doldurulur)
     │  RSS metadata: title, summary, published_at
     ▼
[tasks.articles.fetch_detail]
     │  HTTP GET (NodratBot/1.0 UA)
     │  HTML → trafilatura.extract → body_text
     │  Image URLs → article_images (placeholder rows)
     ▼
[articles.status = cleaned]
     │  body_html → 24h sonra NULL drop (#220)
     ▼
[Yayınlanır embedding queue + clustering queue]
```

### Ana servisler

| Bileşen | Rol |
|---|---|
| `feedparser` | RSS XML → item list |
| `Playwright` | Category page paginate (3 type: load-more, page-nav, infinite-scroll) |
| `httpx` | Detail page fetch |
| `trafilatura` | HTML → temiz body_text |
| Postgres | `articles`, `article_images`, `failed_jobs`, `crawler_jobs` |

### Hata akışı

- **HTTP 4xx/5xx** → `failed_jobs` insert (DLQ); 4xx vs 5xx ayrımı şu an yok (Faz B sonrası genel ImageDownloadError pattern'i article'a uyarlanabilir)
- **Selector kırılması** → source_health.status='broken', alarm + admin notify (R-OPS-01 mitigation)
- **Robots.txt disallow** → ZORUNLU skip; alarm yok (silent)
- **Duplicate content (RSS re-emit / republish)** → `IntegrityError` on `uq_articles_source_content_hash` → **article.status='archived'** (#488 terminal — eskiden 'failed' ile sonsuz dispatch loop) + DLQ `job_type='article.duplicate_content'` severity='permanent_info' ([#433](https://github.com/selmanays/nodrat/issues/433), [#488](https://github.com/selmanays/nodrat/issues/488))
- **Slug değişimi (#496 — Evrensel kalıbı)** → discover'da ext_id check, mevcut article varsa **skip + log** (yeni satır INSERT'lenmez); fetch_detail aşamasına ulaşmaz. Race-safe: `(source_id, external_article_id)` partial UNIQUE index DB-level garanti.

### Kuyruk discipline + freshness kuralları (#433/#436 dersi)

> Bu boru hattı **eventually consistent** — hiçbir article kuyrukta sonsuz beklemez, başarısız olanlar otomatik tekrar denenir, ama 72 saatten eski takılı kayıtlar (kaynak haber muhtemelen artık erişilemez veya freshness kayıp) bypass edilir. Kurallar image pipeline §4 ile birebir paralel; aynı self-healing pattern.

#### Kural A1 — Backfill discovered (idempotent, 5 dk beat)

- **Trigger:** Celery Beat `backfill-discovered-articles` (her 5 dk).
- **İş:** `articles WHERE status='discovered' AND created_at >= NOW() - 72h ORDER BY created_at ASC LIMIT 100` → her biri için `article_fetch_detail.apply_async`.
- **Idempotent:** Sadece `status='discovered'` seçer; cleaned/failed olanlar değişmez. Çoklu beat tetiklemesi zarar vermez.
- **Stale (>72h) bypass:** Kaynak haber muhtemelen artık erişilemez (yayıncı silmiş, URL değişmiş) veya freshness kayıp. Sonsuz retry NIM kotası ve worker yükü harcar.
- **Kullanım senaryosu:** Discovery sırasında dispatch edilen `fetch_detail` Redis broker'da kaybolursa (worker crash, OOM, restart) bu backfill yakalar.
- **Kod:** [tasks.articles.backfill_discovered_articles](../../apps/api/app/workers/tasks/articles.py)

#### Kural A2 — Retry-failed (saatlik beat, 72h freshness window)

- **Trigger:** Celery Beat `retry-failed-articles` (saatte bir, dakika 25 — image retry_failed dakika 20'den farklı).
- **İş:** En eski 50 `status='failed'` VE `created_at >= NOW() - 72h` kaydı → `status='discovered'` UPDATE + dispatch.
- **Sentinel:** Permanent fail (duplicate_content, fetch HTTP 4xx, extraction conf<0.6) tekrar denendiğinde yine fail olur ama:
  - Faz B sayesinde autoretry yok (transient list dışı exception'lar hızlı reject)
  - max 72h penceresi sonsuz retry'ı önler
- **Geçici hatalar (DNS outage, 5xx, timeout) bu retry ile recover olur.**
- **Kod:** [tasks.articles.retry_failed_articles](../../apps/api/app/workers/tasks/articles.py)

#### Kural A3 — Transient vs permanent fail sınıflandırması ([#433](https://github.com/selmanays/nodrat/issues/433))

| Sınıf | Exception örnekleri | Davranış |
|---|---|---|
| **Transient** (autoretry 2x, exp backoff max=300s) | `httpx.TimeoutException`, `httpx.RequestError` (DNS/conn reset), `OperationalError` (DB pool timeout), `ConnectionError`, `TimeoutError` | Re-raise → Celery autoretry. Son retry'da tükenirse exception loglanır; retry-failed beat 72h içinde tekrar dener. |
| **Permanent** (DB terminal status, no autoretry) | `IntegrityError` on `uq_articles_source_content_hash` (duplicate_content) → **`status='archived'`** (#488 terminal, eskiden 'failed' ile sonsuz dispatch loop); HTTP 4xx/5xx fetch fail (`status_code >= 400`), extraction conf<0.6 (`extract_failed`), cleaning fail → **`status='failed'`** (retry-failed beat 72h dener). 72h+ failed → archived (PR #478 backfill semantiği). |
| **Bug sentinel** (autoretry tetiklemez — `_TRANSIENT_EXCEPTIONS` dışı) | `ValueError`, `KeyError`, `AttributeError` (kod bug'ı), diğer `IntegrityError` türleri | ⚠️ Autoretry yapılmaz, exception yüzeye çıkar (alarm tetikleyici). Eski `autoretry_for=Exception` davranışında IntegrityError 2× retry'a girip article 'discovered' state'inde takılıyordu (#433 kök neden). |

#### Kural A4 — Duplicate content (RSS re-emit pattern)

##### Tespit mekanizması

- **Hash fonksiyonu** ([cleaning.py:270](../../apps/api/app/core/cleaning.py:270)): `compute_content_hash(text) = SHA-256(re.sub(r"\s+", " ", text.lower().strip()))`. Whitespace tek boşluğa, lowercase, sonra SHA-256.
- **UNIQUE constraint:** `uq_articles_source_content_hash` UNIQUE `(source_id, content_hash)` — aynı kaynaktan aynı normalize body iki kere yazılamaz.
- **İki aşamalı hash:**
  - Discover'da: `provisional_hash = compute_content_hash(summary OR title)` — body henüz fetch edilmediği için provisional
  - Fetch_detail'de: `real_hash = compute_content_hash(cleaned.clean_text)` — UPDATE sırasında UNIQUE check tetiklenir; provisional'dan farklıysa ve aynı kaynakta zaten varsa → IntegrityError.

##### Neden oluyor (kök neden)

Yayıncı RSS feed'i aynı haberi **slug varyasyonlarıyla** veya farklı GUID'lerle re-emit ediyor. `canonicalize_url` UTM/tracking parametrelerini (`utm_*`, `fbclid`, `gclid` vb. — [cleaning.py:94-119](../../apps/api/app/core/cleaning.py:94)) düzgün strip ediyor, ama path/slug değişikliklerini değiştirmez.

> ✅ **#496 ile çözüldü:** `extract_external_article_id(url)` helper URL pattern'inden haber ID çıkarır (`/haber/(\d+)/` Evrensel, suffix `(\d{6,})` AA). discover task'ı **dedup katman 2** ile aynı `(source_id, ext_id)` varsa skip eder; `(source_id, external_article_id)` partial UNIQUE index DB-level garanti. Aşağıdaki Evrensel "chpyi" vs "chp-yi" örneği artık discover aşamasında yakalanır, fetch_detail'e dahi ulaşmaz. Migration `20260509_0500` ile mevcut 97 dup set consolidate edildi.

**Production örneği** (Evrensel, 2026-05-08):

| Article ID | canonical_url (slug) | status | content_hash | created |
|---|---|---|---|---|
| `1bea9f7a` | `.../5983186/baris-anneleri-heyeti-`**`chpyi`**`-ziyaret-etti` | cleaned | `c4ebfc9d...` (real) | 12:00 |
| `867f5f6f` | `.../5983186/baris-anneleri-heyeti-`**`chp-yi`**`-ziyaret-etti` | failed | `ffde4273...` (provisional) | 13:30 |

`chpyi` (yapışık) vs `chp-yi` (tireli) — aynı haber, aynı body, ama RSS feed iki ayrı URL emit etti. canonicalize iki farklı sonuç üretti → discover dedup'tan kaçtı → ikisi de DB'ye girdi → fetch_detail'in ikincisi commit aşamasında `(source_id, real_content_hash)` çakışmasına çarptı.

> **Kayıt için:** Ne UTM tracking ne de query parametre farkı duplicate'a sebep oluyor — bunlar zaten strip ediliyor. Asıl tetikleyici **path/slug varyasyonları** (yayıncı feed'inin tutarsızlığı).

##### Diğer olası nedenler (production'da nadir)

- **Republish (URL aynı, GUID farklı):** RSS GUID değişiyor ama canonical aynı kalıyor → discover'da `canonical_url` UNIQUE handler bunu yakalıyor (article.duplicate, fetch'e gitmiyor). DLQ'ya **A4 girmez**.
- **Crawler race condition:** Aynı article kısa sürede iki kez discover ediliyor (paralel poll), iki row da 'discovered' olarak yazılıyor → fetch_detail'in ikincisi A4'e düşer. Önemsiz, doğal akış.

##### Faz B çözümü

[#434](https://github.com/selmanays/nodrat/pull/434) + [#488](https://github.com/selmanays/nodrat/issues/488): `db.commit()` öncesi explicit handler. #488 ile `_record_failure` çağrısına `article_status_override=STATUS_ARCHIVED` eklendi — eskiden permanent_info article'ı discovered'da bırakıyor sonsuz loop yaratıyordu.

```python
try:
    await db.commit()
except IntegrityError as exc:
    await db.rollback()
    if _is_duplicate_content_hash_error(exc):
        # Same session reuse — yeni factory() açmak MissingGreenlet tetikler (#435)
        article_reload = await db.get(Article, article_id)
        if article_reload and article_reload.status != STATUS_CLEANED:
            await _record_failure(
                db, article=article_reload,
                job_type="article.duplicate_content",
                severity="permanent_info",          # auto-resolve DLQ
                article_status_override=STATUS_ARCHIVED,  # #488 terminal
                ...,
            )
            await db.commit()
        return summary  # status='duplicate_content'
    raise  # diğer IntegrityError → bug, yüzeye
```

**#496 sonrası:** discover dedup katman 2 (ext_id) bu yola **çoğunlukla ulaşmaz** — slug varyasyonu zaten discover aşamasında yakalanır. Bu fallback handler sadece nadir race condition (paralel poll aynı article'ı discover'a alır) için kalır.

#### Kural A5 — Drenaj sağlığı izleme

Production'da kuyruk sağlıklı mı? Hızlı kontroller:

```sql
-- discovered count düşüyor mu? (yeni gelenle dengeli olmalı, 5 dk başına ≥-20)
SELECT status, COUNT(*) FROM articles GROUP BY status ORDER BY 2 DESC;

-- Stale ratio: discovered'ın kaçı >72h?
SELECT
  COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '72 hours') AS within_72h,
  COUNT(*) FILTER (WHERE created_at <  NOW() - INTERVAL '72 hours') AS stale
FROM articles WHERE status='discovered';

-- Son 15 dk DLQ entries — duplicate_content oranı ne kadar?
SELECT job_type, COUNT(*) FROM failed_jobs
  WHERE created_at > NOW() - INTERVAL '15 minutes'
  GROUP BY job_type ORDER BY 2 DESC;
```

Worker logu:

```bash
docker compose logs --tail=200 worker_scraper |
  grep -E "duplicate_content|IntegrityError|MissingGreenlet|fetch_detail.*succeeded|cleaned"
```

**Alarm tetikleyicisi:**
- `MissingGreenlet` → handler regression (rollback sonrası yeni factory() açma — #435 ders)
- `IntegrityError` autoretry pattern'i (3+ retry hep aynı article) → handler bypass edildi, yeniden bug
- discovered count düşmüyorsa → backfill beat çalışmıyor veya worker crash; `docker compose ps scheduler worker_scraper` kontrol

### İlişkiler

- **Tablolar:** `sources`, `source_configs`, `source_health`, `articles`, `article_images`, `crawler_jobs`, `failed_jobs`
- **Risk:** [[risk-source-fragility]] (R-OPS-01)
- **Image pipeline parite:** §4 Kural 1-3+8 ile birebir paralel pattern'ler ([#425](https://github.com/selmanays/nodrat/pull/425) image, [#436](https://github.com/selmanays/nodrat/issues/436) article)
- **Regression örnekleri:** [#433](https://github.com/selmanays/nodrat/issues/433) IntegrityError → 124 stuck discovered, [#434](https://github.com/selmanays/nodrat/pull/434) handler + transient classification, [#435](https://github.com/selmanays/nodrat/pull/435) MissingGreenlet hotfix, [#436](https://github.com/selmanays/nodrat/issues/436) [#437](https://github.com/selmanays/nodrat/pull/437) backfill+retry beat tasks

---

## 2️⃣ Embedding Pipeline

> **Amaç:** Article body_text → chunks → 1024-dim vector → pgvector storage.
> **Trigger:** Article cleaned event → `embedding_queue`.
> **Kod:** [tasks/embedding.py](../../apps/api/app/workers/tasks/embedding.py)

### Akış

```
[article.status = cleaned]
     │  embedding_queue'ya enqueue
     ▼
[tasks.embedding.chunk_article]
     │  body_text → ~500 token chunks (overlap 50)
     │  article_chunks INSERT (chunk_text, chunk_index)
     ▼
[tasks.embedding.embed_chunks]
     │  batch_size=16 chunks
     │  routing: registry.route_for_tier(operation="embedding", tier="free")
     │           → _fallback("local_bge_m3")  # tek provider, #420
     ▼
[Local BAAI/bge-m3 provider]           ← VPS CPU (~50-150ms/batch)
     │  sentence-transformers SentenceTransformer.encode (batched)
     │  1024-dim numpy → list[float]
     ▼
[article_chunks.embedding = vector(1024)]
     │  pgvector ivfflat / HNSW index
     │  Binary quantization opsiyonel: bit(1024) (#221)
```

### Provider durumu (production)

Embedding **tek provider:** local `BAAI/bge-m3` (sentence-transformers, ~2.3 GB FP32, CPU on VPS).



### Ana servisler

| Bileşen | Rol |
|---|---|
| `LangChain RecursiveCharacterTextSplitter` | Chunking |
| **`sentence-transformers` SentenceTransformer (BAAI/bge-m3)** | Embedding (CPU on VPS, ~50-150ms/batch) — tek provider |
| pgvector | Vector storage + cosine search |

### İlişkiler

- **Tablolar:** `article_chunks`, `provider_call_logs`
- **Index:** `article_chunks_embedding_ivfflat_idx` (cosine)
- **Concept:** [[binary-quantization]] (1024 float32 → bit(1024) opsiyonel)
- **Decision:** [[deepseek-default-llm]] §provider-abstraction'ın bir parçası

---

## 3️⃣ Clustering + Agenda Card Pipeline

> **Amaç:** Benzer article'ları event_cluster'a sok, cluster'dan sentez agenda_card üret.
> **Trigger:** Article embedded → `clustering_queue`. Refresh: 6 saat.
> **Kod:** [tasks/clustering.py](../../apps/api/app/workers/tasks/clustering.py), [tasks/agenda.py](../../apps/api/app/workers/tasks/agenda.py)

### Akış

```
[article_chunks.embedding READY]
     │
     ▼
[tasks.clustering.cluster_article]
     │  pgvector cosine similarity → existing clusters
     │  threshold > 0.85 → merge into cluster
     │  threshold < 0.85 → new cluster (ec.id INSERT)
     ▼
[event_clusters + event_articles updated]
     │  status='developing' / 'active' / 'cooling'
     │  refresh_clusters task her 6h re-evaluate
     ▼
[tasks.agenda.generate_agenda_card]
     │  cluster article'ları topla (top N)
     │  DeepSeek v4-flash sentez prompt
     │  → title, summary, key_points, source_refs
     ▼
[agenda_cards INSERT (level='daily')]
     │  embedding üretilir + pgvector'a yazılır
     │  importance_score + freshness_score hesaplanır
```

### Sentez kalitesi

- **Citation %100 hedef** — agenda_card.source_refs zorunlu, halü filtreleme
- **FSEK 25 kelime cap** — direct quote prompt-level enforced
- **Importance scoring** — article count + cross-source coverage + freshness

### Ana servisler

| Bileşen | Rol |
|---|---|
| pgvector cosine | Cluster matching |
| DeepSeek v4-flash | Cluster → agenda card sentezi |
| Citation validator (cosine) | Halü guard |

### İlişkiler

- **Tablolar:** `event_clusters`, `event_articles`, `agenda_cards`
- **Risk:** [[risk-source-fragility]] (R-OPS-01 cluster freshness)

---

## 4️⃣ Image VLM Pipeline (Process & Discard)

> **Amaç:** Article image URL → NIM Llama 4 Maverick → caption + OCR + depicts → metadata only (bytes saklanmaz).
> **Trigger:** article_images.status='pending' → `image_vlm_queue`.
> **Kod:** [tasks/image_vlm.py](../../apps/api/app/workers/tasks/image_vlm.py), [tasks/media.py](../../apps/api/app/workers/tasks/media.py)

### Akış

```
[Article fetch_detail → article_images placeholder INSERT]
     │  status='pending', original_url + metadata
     ▼
[tasks.media.download_article_image]
     │  HTTP GET image (max 10 MB)
     │  MIME whitelist check (jpeg/png/webp/avif/gif)
     │  In-memory bytes (geçici)
     ▼
[tasks.image_vlm.process_article_image_vlm]
     │  Bytes → base64 → NIM Llama 4 Maverick
     │  Prompt: caption + OCR text + depicts list (max 5 entity)
     ▼
[Site profile filter]
     │  Reklam/logo/öneri haber detection (BBC/Habertürk/Evrensel/AA/TRT/Yeşil Gazete)
     │  filter_decision: 'keep' | 'discard'
     ▼
[article_images UPDATE]
     │  status='processed', vlm_caption, ocr_text, depicts[],
     │  alt_text, score, filter_reason
     │  ⚠️ BYTES SAKLANMAZ — sadece metadata + original_url
```

### Storage etkisi (R-OPS-05 çözümü)

Eski mimari: 5 TB/yıl image bytes MinIO'da. Yeni mimari (#300 MVP-1.4): **process & discard** — orijinal URL ve VLM metadata DB'de, bytes processing sonrası silinir. **5 TB/yıl → 90 GB/yıl (-%98)**.

### Ana servisler

| Bileşen | Rol |
|---|---|
| `httpx` | Image download (max 10 MB) |
| MIME whitelist | jpeg, png, webp, avif, gif (security) |
| NIM Llama 4 Maverick | Vision-language model — caption + OCR + depicts |
| Site profile classifier | 6 site profili (reklam/logo filter) |

### Kuyruk discipline + freshness kuralları

> Bu boru hattı **eventually consistent** çalışır: hiçbir image kuyrukta sonsuz beklemez, başarısız olanlar otomatik tekrar denenir, ama 72 saatten eski failed kayıtlar (kaynak haber silinmiş olabilir) bypass edilir. Kurallar kod referanslarıyla:

#### Kural 1 — Backfill (idempotent, 5 dk beat)

- **Trigger:** Celery Beat `backfill-pending-images` (her 5 dk).
- **İş:** `article_images WHERE status='pending' ORDER BY created_at ASC LIMIT 300` → her biri için `process_article_image_vlm.apply_async(args=[id])`.
- **Idempotent:** Sadece `status='pending'` seçer; processed/failed/skipped olanlar değişmez. Çoklu beat tetiklemesi zarar vermez.
- **Hız:** NIM 40 RPM × worker concurrency 2 → 5 dk'da pratikte 300-400 image işlenir.
- **Kod:** [tasks.image_vlm.backfill_pending_images](../../apps/api/app/workers/tasks/image_vlm.py)

#### Kural 2 — Retry-failed (saatlik beat, 72h freshness window)

- **Trigger:** Celery Beat `retry-failed-images` (saatte bir, dakika 20).
- **İş:** En eski 100 `status='failed'` VE `created_at >= NOW() - 72h` kaydı → `status='pending'` UPDATE + dispatch.
- **Freshness window (`max_age_hours=72`):** 3 günden eski failed kayıtlar bypass. Gerekçe: kaynak haber muhtemelen artık erişilemez (yayıncı silmiş, URL değişmiş) ya da yapısal nedenler (selector kırılması) — sonsuz retry NIM kotasını boşa harcar.
- **Sentinel:** Permanent fail (mime/parse) tekrar denendiğinde yine fail olur ama bir sonraki saatte tekrar denenir; 72h penceresi out olunca durur.
- **Kod:** [tasks.image_vlm.retry_failed_images](../../apps/api/app/workers/tasks/image_vlm.py)

#### Kural 3 — Transient vs permanent fail sınıflandırması

| Sınıf | Exception örnekleri | Davranış |
|---|---|---|
| **Transient** (autoretry 3x, exp backoff max=300s) | `VLMRateLimitError` (NIM 429), `VLMTimeoutError`, `ImageDownloadError` (5xx + diğer 4xx network — 404/410 hariç), `httpx.TimeoutException`, `httpx.RequestError` | Re-raise → Celery autoretry. Son retry'da tükenirse DB `status='failed'` ve bir sonraki saatlik retry beat'i dener. |
| **Permanent** (DB `status='failed'`, no autoretry) | `ImageRejected` — MIME/size whitelist fail, **HTTP 404/410 (Gone)** [#427](https://github.com/selmanays/nodrat/issues/427), magic bytes sniff fail; `VLMError` (JSON parse fail, model error) | Anında DB'ye yaz. Saatlik retry beat 72h pencerede yeniden tetikler ama her seferinde hızlı (1 HEAD req/image, no GET, no autoretry); kaynak hâlâ yokken yine 'failed' kalır, 72h sonra freshness window dışına düşer. |
| **Bug sentinel** (autoretry tetiklemez — `_TRANSIENT_EXCEPTIONS` dışı) | `TypeError`, `AttributeError`, `KeyError` (kod bug'ı) | ⚠️ Image **stuck pending** kalır — DB status değişmez, backfill her 5 dk yeniden dispatch eder, hep aynı hata patlar. Tespit: `pending` count düşmüyor. Örn: [#424](https://github.com/selmanays/nodrat/issues/424) — `tracker.record()` kwargs regression. |

#### Kural 4 — Cost tracker contract (deploy öncesi mecbur)

`tracker.record()` valid kwargs: `input_tokens, output_tokens, cached_tokens, model, cost_usd`. Yanlış kwargs (`cost_per_1m_*` — bu `estimate_cost_usd()` helper'ına ait) `TypeError` fırlatır → kural 3'teki "Bug sentinel" pattern'ine düşer.

Regression koruması: [test_image_vlm_retry.py::test_tracker_record_accepts_image_vlm_kwargs](../../apps/api/tests/unit/test_image_vlm_retry.py).

#### Kural 5 — Runtime kill-switch (settings flag)

| Setting | Default | Etki |
|---|---|---|
| `media.processing_enabled` | `false` | `false` ise `_process_image_async` "skipped" döner; image pending kalır ama hiçbir VLM call yapılmaz. Cost runaway / NIM outage durumunda acil durdurma. |
| `media.vlm_model` | `meta/llama-4-maverick-17b-128e-instruct` | Alternative: `google/paligemma`. |
| `media.max_image_bytes` | `5_242_880` (5 MB) | Permanent fail tetikleyicisi (`ImageRejected`). |
| `media.download_timeout` | `10.0` (s) | Transient fail tetikleyicisi. |

Tümü admin panel `/admin/settings` runtime tunable, restart gerektirmez ([[risk-cost-runaway]] mitigation).

#### Kural 6 — Worker concurrency

`worker_image_vlm` container'ı concurrency=2 (NIM 40 RPM rate limit'e güvenli pay). Pratik throughput: 4-5 image/dakika (P50 ~25-45 saniye/image). Concurrency artırmak için NIM tier upgrade veya ikinci VLM provider gerek (R-FIN-01 monitor + circuit breaker).

#### Kural 7 — Drenaj sağlığı izleme

Production'da kuyruk sağlıklı mı? Hızlı kontroller:

```sql
-- pending sayısı düşüyor mu? (yeni gelenle dengeli olmalı, +5 dk başına -250±)
SELECT status, COUNT(*) FROM article_images GROUP BY status ORDER BY 2 DESC;

-- Son saatte kaç tane processed? (beklenen: ~250-300)
SELECT COUNT(*) FROM article_images WHERE processed_at > NOW() - INTERVAL '1 hour';

-- Stuck mı? En eski pending kayıt kaç saat önce gelmiş?
SELECT MIN(NOW() - created_at) AS oldest_pending_age FROM article_images WHERE status='pending';
```

Worker logu:

```bash
docker compose logs --tail=200 worker_image_vlm | grep -E "succeeded|TypeError|backfill|retry_failed"
```

**Alarm tetikleyicisi:** `TypeError` görünüyorsa kural 3'teki "Bug sentinel" pattern aktif → kuyruk donar, hemen kod fix gerek.

#### Kural 8 — Permanent fail edge case'leri ([#427](https://github.com/selmanays/nodrat/issues/427) dersi)

[#424](https://github.com/selmanays/nodrat/issues/424) sonrası kalan 7 failed image teşhisinden çıkan iki bug + 1 design notu:

##### A) HTTP 404 / 410 (Gone) → permanent

Yayıncı haberi sildiğinde image URL'si 404 dönüyor. Eski davranış: tüm 4xx/5xx `ImageDownloadError` (transient) → autoretry 3x + saatlik retry beat 72h boyunca = ~864 wasted HTTP req per article-removal.

Yeni davranış (#427): `head_check` ve GET stream'inde HTTP 404/410 → `ImageRejected` (permanent). Her saatlik retry'da 1 HEAD req/image (GET'e gitmez, autoretry yok). 6 ölü URL için 6 HEAD/saat × 72h = 432 req — eski 5184'ten 12× daha az.

```python
# apps/api/app/core/media.py
if resp.status_code in (404, 410):
    raise ImageRejected(f"HTTP {resp.status_code} (gone)")
if resp.status_code >= 400:
    raise ImageDownloadError(...)  # diğer 4xx/5xx hala transient
```

##### B) Boş Content-Type → magic bytes fallback

Bazı CDN'ler (örn: WhatsApp Manifold storage `mmg.whatsapp.net`, yanlış konfigüre S3 bucket'lar) Content-Type header göndermiyor. Eski davranış: `ImageRejected: 'mime not allowed: '` (boş MIME). Image aslında geçerli bir JPEG/PNG ama header eksik diye reddediliyordu.

Yeni davranış (#427): Header eksik/boş → streaming sonrası ilk 16 byte'tan magic bytes ile MIME detect edilir. Sadece `ALLOWED_IMAGE_MIME` whitelist'i (JPEG, PNG, WebP, AVIF, GIF). Detect başarısız → `ImageRejected` (sniff fail).

```python
# Magic bytes signature'ları (apps/api/app/core/media.py:_sniff_image_mime)
b"\xff\xd8\xff" → image/jpeg
b"\x89PNG\r\n\x1a\n" → image/png
b"GIF8" → image/gif
b"RIFF...WEBP" → image/webp (WAV/AVI brand check ile ayrıştırılır)
b"...ftypavif" / b"...ftypavis" → image/avif
```

##### C) Duplicate dispatch — design notu (bug değil)

[#424](https://github.com/selmanays/nodrat/issues/424) öncesi 26 saat boyunca backfill her 5 dk × 300 task = ~93k task dispatch'i Redis broker'da birikti (her biri TypeError ile patladı). Worker recreate sonrası queue drenajı sırasında aynı `image_id` saniyeler içinde 4-6 kez dispatch görüldü. Kabul edilebilir çünkü `process_article_image_vlm`:

- `status='processed'` ise idempotent ('already_processed' döner) ✅
- `status='failed'` için idempotent **değil** — yeniden işliyor (ama HEAD 404 fix'i artık 0.13s'de bitiriyor, dolayısıyla maliyet düşük)

Eski queue drenajı ~30 dk içinde sönümleniyor; kalıcı bir bug değil. Eğer pattern sürekli görünürse (yeni ingest'lerde de) — broker queue size izle, idempotency için `status='failed'` da skip edilmeli.

**Açık follow-up:** 404 image'lar 72h boyunca her saat 1 HEAD'le retry edilecek. Tamamen durdurmak için `retry_count` veya ayrı `'gone'` status gerek (data-model değişikliği). MVP-1.x'te scope dışı; gerekirse [#427](https://github.com/selmanays/nodrat/issues/427) follow-up issue'da işlenir.

### İlişkiler

- **Tablo:** `article_images` (sadece metadata)
- **Risk:** R-OPS-05 (storage runaway) — ÇÖZÜLDÜ (#300 MVP-1.4); R-FIN-01 (cost runaway) — kural 5 + 6 + 8A ile mitigate
- **Regression örneği:** [#424](https://github.com/selmanays/nodrat/issues/424) (TypeError → 320 stuck pending, [#425](https://github.com/selmanays/nodrat/pull/425) ile düzeltildi)
- **Edge case fix:** [#427](https://github.com/selmanays/nodrat/issues/427) (boş Content-Type + 404/410, [#428](https://github.com/selmanays/nodrat/pull/428) ile düzeltildi)

---

## 5️⃣ RAPTOR-Lite Pipeline (Weekly/Monthly Aggregation)

> **Amaç:** Daily agenda_cards → weekly cluster summary cards → monthly aggregations. Hierarchical retrieval için (PRD §2.7 weekly mode).
> **Trigger:** Celery Beat scheduled (haftalık).
> **Kod:** [tasks/raptor.py](../../apps/api/app/workers/tasks/raptor.py)

### Akış

```
[Cron: haftalık (Pazar 23:00 TR)]
     │
     ▼
[tasks.raptor.build_weekly_summary_cards]
     │  fetch agenda_cards WHERE level='daily' AND updated_at >= now()-7d
     │  her 'daily' card için embedding parse (vector(1024)::text)
     ▼
[Hierarchical clustering]
     │  cosine similarity > 0.70 → grup
     │  her grup için aggregate stats (article_count, importance avg)
     ▼
[Per-group LLM synthesis]
     │  DeepSeek v4-flash: gruba ait daily card'lardan weekly title+summary
     ▼
[agenda_cards INSERT (level='weekly')]
     │  parent_card_ids → daily cards reference
     │  embedding hesaplanır + pgvector'a yazılır
```

### Faydası

- **Time-aware retrieval:** "bu hafta" sorgularında weekly card kullanılır (daha az ama daha geniş bağlam)
- **Storage tasarrufu:** weekly cards retrieval'da daily card'lar yerine seçilebilir
- Detay: [[mvp-roadmap]] §MVP-1.1

### İlişkiler

- **Tablo:** `agenda_cards.level` enum: daily | weekly | monthly
- **Provider:** [[deepseek-v3]] (sentez)

---

## 6️⃣ Content Generation Pipeline (`/app/generate`)

> **Amaç:** Kullanıcı doğal dil talebi → 6-adım RAG → X post / summary / thread / headline.
> **Trigger:** Authenticated POST `/api/app/generate`.
> **Kod:** [app_generate.py](../../apps/api/app/api/app_generate.py)
> **Detay:** [[pipeline-performance-baseline]] (token/latency/maliyet snapshot + tracking)

### 6-adım akış

```
KULLANICI: "İsrail-Filistin bu hafta sert tonlu 3 tweet"
     │
     ▼
[1] Query Planner          DeepSeek v4-flash       ~800→~300 token
     │  doğal dil → JSON plan (intent, keywords, tone, max_posts...)
     ▼
[2] Query Embedding        Local bge-m3            ~50 token → 1024-dim
     │  enriched_query (topic + keywords)
     ▼
[3] Hybrid Search          pgvector + trigram      DB only
     │  RRF fusion, candidate_pool=30 (short query=10), top_k=5 (#393)
     ▼
[4] Reranker               NIM nv-rerankqa         query+10 passage
     │  cross-encoder relevance scoring
     │  short query (≤2 word) → skip
     ▼
[5] Content Generator      DeepSeek v4-flash       ~3,200→~1,500 token
     │  static system prompt v1.1.0 (cache hit ≥40%)
     │  user payload: plan + 5 cards + output_constraints
     ▼
[6] Citation Validation    bge-m3 (reuse)          tek mega-batch
     │  source.embedding agenda_cards'tan reuse → embed_fn sadece post text
     │  cosine ≥ 0.55 → supported
     ▼
KULLANICIYA SUN  (P50 toplam ~3-4s, P95 3-6s, MVP-2.1 sonrası)
```

### MVP-2.1 optimizasyon özeti (3 PR ile)

- **PR #411:** citation 6→1 batch + settings 5→1 paralel + normalize 1×
- **PR #416:** citation embedding reuse + short query candidate_pool 30→10
- **PR #418:** prompt v1.1.0 STATIC (cache hit ≥40% hedef) + content top_k 10→5

Detaylı tracking: [[pipeline-performance-baseline]].

---

## 7️⃣ Public Search Pipeline (`/ara`)

> **Amaç:** Anonim haber arama (Search-as-a-Service Phase B [#261](https://github.com/selmanays/nodrat/issues/261)). TOFU funnel.
> **Trigger:** Public GET `/api/public/search?q=...&limit=10`.
> **Kod:** [public_search.py](../../apps/api/app/api/public_search.py)

### Akış

```
[Anonim ziyaretçi → nodrat.com/ara]
     │  Frontend (Next.js) → POST /api/public/search
     ▼
[Rate limit check (Redis)]
     │  Sliding window: 10 req/min/IP
     │  429 → block (KVKK: IP+timestamp 30g retention)
     ▼
[Query embedding]                  Local bge-m3 (VPS CPU)
     │  q → 1024-dim vector (sentence-transformers)
     │  Embed fail → sparse-only (degraded)
     ▼
[Vector + sparse search]           pgvector + trigram
     │  agenda_cards üzerinde
     │  status IN ('active', 'developing', 'cooling')
     │  son 30 gün filtresi
     ▼
[RRF fusion + top_k=10]
     │  agenda_card title + summary + source_refs döner
     ▼
[Public response (no PII)]
     │  No telemetry user-bound; sadece daily total counter
```

### Önemli notlar

- **Auth: Yok** — anonim, tüm cluster'lar erişilebilir (son 30 gün arşivi)
- **Üretim erişimi: YOK** — sadece arama. Register wall ile /app/generate'e yönlendirir
- **CTA:** "Bu konuda X paylaşımı üreteyim mi?" → register/login flow
- **KVKK:** PII redaction yok ama query log only IP + timestamp; 30g auto-purge
- **Robots.txt:** `/api/public/*` ALLOW (SEO için)

### İlişkiler

- **Tablo:** `agenda_cards` (read-only)
- **Detay:** [[mvp-roadmap]] §MVP-2 (Phase A backend + Phase B /ara UI)
- **Topic:** [[llm-provider-strategy]] (embedding [[local-bge-m3]] paylaşımlı — pipeline 2 + 6 + 7 hepsi aynı modeli kullanır)

---

## 8️⃣ Object Storage + Cold Tier + Backup Pipeline

> **Amaç:** Image bytes (Faz 4 öncesi), 30+ gün eski article'lar (cold tier), production daily backup.
> **Trigger:** Çoklu — VLM pipeline + cold tier maintenance + cron daily 04:00.
> **Kod:** [storage.py](../../apps/api/app/core/storage.py), [tasks/maintenance.py](../../apps/api/app/workers/tasks/maintenance.py), [infra/backup.sh](../../infra/backup.sh)

### Üç katman

```
┌─ KATMAN A: MinIO (Hot, üretim altyapı) ────────────────────┐
│ Bucket: nodrat-images-hot                                   │
│ Key: images/{source_slug}/{yyyy}/{mm}/{dd}/{image_id}.{ext} │
│ Kullanım: Image VLM PR-3 öncesi byte saklama (deprecated)   │
│ Yeni: process & discard mimarisi → metadata only            │
└─────────────────────────────────────────────────────────────┘

┌─ KATMAN B: Contabo Object Storage (Cold tier) ──────────────┐
│ Endpoint: eu2.contabostorage.com                            │
│ Bucket: nodrat-prod                                         │
│ İçerik:                                                     │
│   1. Cold tier raw_html (30+ gün, articles.archived_at set) │
│      → tasks.maintenance.cold_tier_archive (daily)          │
│      → articles.body_html=NULL, body_compressed → S3 key   │
│      ⚠️ status='cleaned' kalır; status='archived' farklı     │
│         kavram (#483 — terminal failed, [[queue-management]])│
│   2. restic backup repository                              │
│      → infra/backup.sh (daily 04:00 cron)                  │
│      → pg_dump + minio mirror + config files               │
│      → restic encrypted snapshot                           │
└─────────────────────────────────────────────────────────────┘

┌─ KATMAN C: Backup retention (restic) ──────────────────────┐
│ keep-daily 7 + keep-weekly 4 + keep-monthly 6              │
│ Auto prune sonrası snapshot history                         │
│ Restore drill: AYLIK (architecture.md §9)                   │
└────────────────────────────────────────────────────────────┘
```

### Cold tier akışı

```
[Cron daily 03:00]
     │
     ▼
[tasks.maintenance.cold_tier_archive (batch=100, max_age=30d)]
     │  articles WHERE created_at < now()-30d AND body_html IS NOT NULL
     │  body_html → gzip compress → S3 PUT (Contabo)
     │  articles.body_html = NULL
     │  articles.cold_tier_key = 's3://nodrat-prod/cold/{article_id}.html.gz'
     ▼
[Read access]
     │  /admin/articles/{id} → cold tier ise restore_one
     │  S3 GET → decompress → cache (10 dk Redis) → response
```

### Backup akışı

```
[Cron 04:00 Europe/Istanbul]
     │
     ▼
[infra/backup.sh]
     │  1. pg_dump → /tmp/nodrat-backup/postgres.dump
     │  2. mc mirror minio → /tmp/nodrat-backup/minio/
     │  3. .env + docker-compose.yml + Caddyfile → /tmp/.../config/
     │  4. restic backup --tag auto --tag YYYY-MM-DD
     │  5. restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6
     ▼
[Contabo Object Storage repository]
     │  restic encrypted snapshot
     │  S3 path: s3://nodrat-prod/restic
```

### Ana servisler

| Bileşen | Rol |
|---|---|
| MinIO | Hot tier image bytes (deprecated, process & discard sonrası) |
| Contabo Object Storage (S3-compat) | Cold tier + backup |
| `boto3` | S3 client |
| `restic` | Encrypted backup tool |
| `mc` (MinIO client) | MinIO mirror |

### İlişkiler

- **Decision:** [[contabo-vps-hosting]] (storage backend de Contabo)
- **Concept:** [[hot-cold-tier]] (storage tier abstraction)
- **Tablo:** `articles.cold_tier_key`, `articles.body_html` (NULL after archive)

---

## Pipeline durumu özeti (2026-05-08 itibarıyla)

| # | Pipeline | Durum | MVP fazı | Optimizasyon |
|---|---|---|---|---|
| 1 | Source Crawl | ✅ Production | MVP-1 | Selector test UI (#70 MVP-2) |
| 2 | Embedding | ✅ Production (**LOCAL**, post-#345 migration) | MVP-1 → MVP-1.5 PR-8 (local preload) → 2026-05-07 flag flip | NIM fallback, eval gate geçildi |
| 3 | Clustering + Agenda | ✅ Production | MVP-1 | Importance scoring (MVP-1.1 #182) |
| 4 | Image VLM | ✅ Production | MVP-1.4 | Process & discard (#300, -%98 storage) |
| 5 | RAPTOR-Lite | ✅ Production | MVP-1.1 #182 | — |
| 6 | /app/generate | ✅ Production (MVP-2.1 optimizes) | MVP-1 | 3 PR closed: #411, #416, #418 |
| 7 | /ara public search | ✅ Production | MVP-2 #261 | Phase C planned (MVP-3 #384) |
| 8 | Object Storage + Cold Tier + Backup | ✅ Production (Contabo MVP-1.5) | MVP-1.5 | restic monthly drill |

## Provider envanteri (8 pipeline boyunca)

| Provider | Hangi pipeline'da kullanılır | Maliyet | Production durumu |
|---|---|---|---|
| **DeepSeek v4-flash** (native API) | 3 (agenda card sentez), 5 (raptor weekly), 6 (planner + content gen) | $0.27/$1.10 per 1M; %75 kampanya 2026-05-31'e kadar | ✅ AKTİF |
| **Local BAAI/bge-m3** (sentence-transformers, VPS CPU) | 2 (chunk embed), 3 (cluster matching), 6 (citation), 7 (search query) | $0 (CPU compute, hosting'in bir parçası) | ✅ AKTİF (USE_LOCAL_EMBEDDING=true) |
| **NIM nv-rerankqa-mistral-4b-v3** | 6 (rerank stage) | $0 | ✅ AKTİF (USE_LOCAL_RERANK=false) |
| **NIM Llama 4 Maverick (VLM)** | 4 (image caption + OCR) | $0 | ✅ AKTİF |
| **Anthropic Haiku 4.5** | 6 (Pro+ tier) | ~$0.80/$4 — Faz 2 aktivasyon | ⏳ Faz 2'de (MVP-3) |
| **Anthropic Sonnet 4.6** | 6 (Agency comparison_generation) | ~$3/$15 | ⏳ Faz 2'de (MVP-3) |

## İlişkiler

- **İlgili topics:** [[pipeline-performance-baseline]] (#6 detay tracking), [[llm-provider-strategy]] (provider routing), [[mvp-roadmap]] (her pipeline'ın MVP teslim tarihi)
- **İlgili kavramlar:** [[provider-abstraction]], [[hot-cold-tier]], [[binary-quantization]]
- **İlgili varlıklar:** [[deepseek-v3]], [[local-bge-m3]], [[contabo-vps]], [[celery-worker]]
- **İlgili kararlar:** [[deepseek-default-llm]], [[contabo-vps-hosting]]

## Açık sorular / TODO

- **Pipeline-level latency dashboard:** Her pipeline'ın P50/P95 latency'si tek panel'de izlenmeli (provider_call_logs query'si). Şu an her pipeline ayrı log'da.
- **Cold tier restore drill:** Aylık restore prosedürü çalıştırıldı mı? Son drill tarihi belirsiz.
- **Image VLM eval:** Llama 4 Maverick "filter reklam/logo" doğruluğu eval edilmedi (R-OPS-06).
- **Public search Phase C:** Publisher widget + advanced SEO (#384 MVP-3 cut-over).
- **Local provider flip:** USE_LOCAL_EMBEDDING + USE_LOCAL_RERANK flag flip için #345 + #347 eval gate'leri açık.
- **RAPTOR monthly:** Şu an sadece weekly. Monthly aggregation için trigger plan'ı yok.

## Kaynaklar

- [apps/api/app/workers/tasks/](../../apps/api/app/workers/tasks/) — tüm Celery task'lar
- [apps/api/app/api/app_generate.py](../../apps/api/app/api/app_generate.py) — pipeline 6
- [apps/api/app/api/public_search.py](../../apps/api/app/api/public_search.py) — pipeline 7
- [apps/api/app/core/storage.py](../../apps/api/app/core/storage.py) — pipeline 8
- [infra/backup.sh](../../infra/backup.sh) — pipeline 8 backup
- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §3 (worker stack), §9 (backup)
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) §3 (Faz 1 tables), §4 (Faz 2 RAG)
