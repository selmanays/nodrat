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
     │  articles INSERT (status=discovered)
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

- **HTTP 4xx/5xx 3 kez retry** → `failed_jobs` insert → manual admin retry
- **Selector kırılması** → source_health.status='broken', alarm + admin notify (R-OPS-01 mitigation)
- **Robots.txt disallow** → ZORUNLU skip; alarm yok (silent)

### İlişkiler

- **Tablolar:** `sources`, `source_configs`, `source_health`, `articles`, `article_images`, `crawler_jobs`, `failed_jobs`
- **Risk:** [[risk-source-fragility]] (R-OPS-01)

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

Embedding **tek provider:** local `BAAI/bge-m3` (sentence-transformers, ~2.3 GB FP32, CPU on VPS). #350 ile DB re-embed migration tamamlandı (2026-05-06); #420 ile NIM `nv-embedqa-e5-v5` adapter sistemden tamamen kaldırıldı (sürekli .env.example/.env karışıklığını gidermek için).

**Production telemetry (provider_call_logs son 7 gün, 2026-05-08):** Tüm embedding çağrıları `local_bge_m3` provider'ında. Eski `nim_bge_m3` provider name son çağrı 2026-05-06 18:46'da (#350 öncesi); #420 sonrası registry'de kayıtlı değil.

> ℹ️ **Embedding uzayı tek model:** Mevcut DB chunks + agenda_cards (`vector(1024)`) tamamı `BAAI/bge-m3` ile üretilmiş. Eski NIM `nv-embedqa-e5-v5` ile orthogonal cosine sorunu vardı (#345); DB re-embed task ile çözüldü.

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

### İlişkiler

- **Tablo:** `article_images` (sadece metadata)
- **Risk:** R-OPS-05 (storage runaway) — ÇÖZÜLDÜ (#300 MVP-1.4)

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
│   1. Cold archived raw_html (30+ gün article'lar)           │
│      → tasks.maintenance.cold_tier_archive (daily)          │
│      → articles.body_html=NULL, body_compressed → S3 key   │
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
| **NIM bge-m3** (nv-embedqa-e5-v5) | Embedding fallback (local factory fail durumunda) | $0 (NIM free tier) | 🟡 FALLBACK (son kullanım 2026-05-06) |
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
