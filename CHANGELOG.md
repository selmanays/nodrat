# Changelog

Tüm önemli değişiklikler bu dosyada belgelenir.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

### Beklemede
- **Dalga 6 hardening** — load test (50→200 RPS), eval suite full koşum, D7 retention raporu, 25 persona görüşmesi
- **#55** PMF survey scaffold — 30g aktif user gerek, scaffold MVP-3 öncesi

### Beklemede (blocked-external)
- #68 Resend production verify (yapıldı 2026-05-07 smoke, kalibre edildi)

---

## [0.1.6] — 2026-05-07 — MVP-2 Dalga 0-5 Bulk Delivery

> 🎯 **Milestone:** MVP-2 (Dalga 0 stabilizasyon → Dalga 5 search hub UI) tek günde
> 📦 **13 PR merged** (#368-380), **11 issue closed** + 1 partial (#261 Phase C → MVP-3'e)
> 🚀 **Production stable**, tüm container healthy

### Dalga 0 — Stabilizasyon
- **#294** fix(infra): web healthcheck localhost → 127.0.0.1 (IPv4 force) — PR #368
- **#273** feat(providers): HTTP timeout runtime tunable (5 setting, lifespan async bootstrap) — PR #369
- **#331** fix(infra): Cloudflare Origin CA cert (15 yıl, Full strict aktif) — PR #370
- **#256** fix(db): asyncpg pool tune + postgres max_connections=300 — PR #371
- **#243** test: production email pipeline smoke (Resend e2e verify + reset flow doğrulandı)

### Dalga 1 — Admin operasyon (R-OPS-01 mitigation)
- **#70** feat(admin): selector test UI — listing + detail canlı test — PR #372
- **#71** feat(scraper): category page source type + 3 pagination — PR #373
- **#75** feat(admin): source config versioning UI + rollback — PR #374

### Dalga 2 — Üretim genişlemesi
- **#73 #74** feat: 8 tone + 3 length + 4 output type (x_post / thread / summary / headline) — PR #375
- LENGTH_COUNTS mapping: output_type × length → max_posts/items

### Dalga 3 — Search-as-a-Service Phase A (TOFU backend)
- **#261 Phase A** feat: anonim public search backend, IP rate limit (10/min), telemetry — PR #375 (combined)

### Dalga 4 — Comparison mode + Landing
- **#51** feat(rag): comparison.enabled feature flag + telemetry (R-PRD-03 mitigation) — PR #377
- **#299** feat(web): landing redesign — hero/features/how-it-works/pricing/CTA/footer — PR #380

### Dalga 5 — Search hub UI Phase B
- **#261 Phase B** feat(web): public anonim search UI /ara — PR #376

### Hotfix
- **DeepSeek v4-flash thinking-disabled** (PR #378, PR #379) — root cause: default thinking mode response.content boş, payload'a `{"thinking": {"type": "disabled"}}` eklenerek non-thinking force
- **shadcn Select migrate** (admin/sources/new + app/generate dropdown'ları)
- **Login redirect** super_admin auto-redirect kaldırıldı (admin için ayrı /admin/login)

### Bilinçli ertelenmiş
- **#261 Phase C** publisher widget + advanced SEO → **MVP-3**

---

## [0.1.5] — 2026-05-06 — MVP-1.5 Infrastructure Migration & Storage Optimization

> 🎯 **Milestone:** Epic #215 — VPS dedicated + Contabo Object Storage migration, cold tier retention, binary quantization scaffold, local model scaffold
> 📦 **6 PR merged** (#341, #342, #343 PR-fix + #344 PR-6 + #346 PR-8 + #348 PR-9): scaffold + 1 deferred (PR-7) + 2 spawn issue (#345, #347)
> 💾 **Storage**: 31x sıkışma scaffold (binary quantization), Contabo OS cold tier aktif

### Eklendi — Migration (A. group)
- **PR-1 #216 — Cloud VPS 40 NVMe** (12 vCPU / 47 GB / 484 GB) — VPS 30 → 40 plan upgrade (reranker + local embed footprint)
- **PR-2 #217 — Contabo Object Storage + restic backend swap** — B2 → S3-compat eu2.contabostorage.com (3 snapshot migrate, restic init OK)
- **PR-3 #218 — Production migration** — pg_dump 34 MB + MinIO + apps/ rsync, DNS Cloudflare A record cutover

### Eklendi — Storage optimizasyonları (B. group)
- **PR-4 #219 — Cold tier retention task** — 30+ gün eski raw_html gzip + Contabo OS PUT, gece 03:30 UTC, idempotent batch=100
- **PR-5 #220 — body_html drop policy** — 24h sonrası body_html NULL (clean_text korunur), gece 03:00 UTC, settings flag
- **PR-6 #221 — pgvector binary quantization scaffold** — `embedding_binary BIT(1024)` + HNSW Hamming index, build-time backfill task, embedding worker dual-write, **2167 chunk backfilled (8.5 MB → 270 KB = 31x)**

### Eklendi — Local model scaffold (C. group)
- **PR-8 #223 — Local bge-m3 scaffold** — sentence-transformers + torch CPU, Dockerfile builder bge-m3 (~2.3 GB) build-time HF cache preload, default `USE_LOCAL_EMBEDDING=false`. Smoke: warm 106ms, batch 19ms/text. **Bulgu:** NIM nim_bge_m3 endpoint, BAAI/bge-m3'ten farklı bir model serve ediyor (cosine ≈ 0); flag flip için re-embed migration gerek (#345 spawn).
- **PR-9 #224 — Local bge-reranker-v2-m3 scaffold** — sentence-transformers CrossEncoder, Dockerfile preload (~568 MB), default `USE_LOCAL_RERANK=false`. Smoke: warm 184ms; quality 2/3 sorgu mükemmel, 1 regression → eval gate (#347 spawn). Tour 5 reranker kalite sorunlarının (#251, #252, #254, #259, #260) kalıcı çözüm yolu.

### Doc senkron — PR-10 #225
- `architecture.md` §5.5 (binary quantization) + §5.6 (local model providers)
- `unit-economics.md` v1.2 actuals — VPS 40 NVMe $41.70/ay = ~€488/yıl, Contabo OS €2.49
- `ropa.md` Contabo Object Storage + Cloud VPS 40 NVMe provider entry'leri (DE/AB içi, KVKK envanter)
- `risk-register.md` §5.1b MVP-1.5 ✅ DELIVERED işareti + spawn issue takibi
- `INDEX.md` v1.3 — MVP-1.5 delivered

### Skip / Deferred
- **PR-7 #222 — Chunk dedup**: canonical_url üzerinde 0 dup (1888/1888 unique). Content-similarity yaklaşımı ayrı epic gerek.

### Cleanup
- #340 — Eski VPS (173.212.238.104) bağımlılıkları temizlendi: `infra/deploy.sh` + `infra/sops-setup.md` + `.github/workflows/deploy.yml` + `docs/operations/deployment-manual-steps.md` + `docs/engineering/architecture.md` + skill memory yeni VPS (164.68.107.205:22) bilgileriyle güncellendi. GitHub secrets (`VPS_HOST/PORT/KNOWN_HOSTS`) yenilendi.
- #334 — `hybrid_search_agenda_cards` SELECT'ine `country` + `level` field eklendi (UI hydration fix)
- #337 — RAPTOR weekly card'lar daily children'dan dominant country aggregate ediyor (≥%60 majority threshold)

### Spawn issues (MVP-2'ye taşındı)
- #345 — NIM → local bge-m3 embedding re-embed migration
- #347 — Local rerank eval gate (NDCG@10 ≥ 0.90 hedefi)

### Mali durum (gerçekleşen)
- VPS 40 NVMe + extension: $41.70/ay = ~€488/yıl
- Contabo Object Storage 250 GB: €2.49/ay = ~€30/yıl
- DeepSeek (tahmini): ~€60/yıl
- **Toplam: ~€578/yıl** (target €350; VPS 30 → 40 upgrade yüzünden +€140 üstünde, MVP-3'e kadar yetiyor)

---

## [0.1.4] — 2026-05-06 — MVP-1.4 Image Pipeline (Process & Discard)

> 🎯 **Milestone:** Image VLM Pipeline (Epic #300) — kaynak haberlerden DOM görsellerini NIM Llama 4 Maverick VLM ile işleme; bytes saklanmıyor, sadece textual metadata.
> 📦 **16 PR merged** (#311–#326): 6 atomic milestone PR'ı + 10 fix iterasyonu
> 💾 **Storage**: 5 TB/yıl → 90 GB/yıl (%98 azalma)

### Eklendi — Pipeline çekirdeği
- **DB schema migration** — `article_images` storage kolonları kaldırıldı (storage_url, sha256_hash, perceptual_hash, mime_type, width, height, file_size); `vlm_caption`, `ocr_text`, `depicts` (JSONB), `processed_at`, `position` eklendi
- **DOM extraction** — RSS thumbnail kapatıldı; `<article>/<main>/<figure>` içindeki gerçek görseller (multi-image desteği)
- **NIM VLM provider** — `meta/llama-4-maverick-17b-128e-instruct` (Türkçe + multilingual + ücretsiz, 40 RPM, 1.5-2.5s latency ortalama)
- **`worker_image_vlm`** — concurrency 2, autoretry on transient errors (rate limit/timeout/network), max_retries 3 with exponential backoff
- **Admin /media UI** — paginated tablo + 4'lü stat + filter row + Dialog modal (büyük önizleme + tüm metadata + kebab actions: yeniden işle / haberi-kaynakta-aç / görseli-kaynakta-aç)
- **Suggest_image** — `app/core/media_suggest.py` Türkçe Jaccard helper + `/app/generate` UI kartı (FSEK uyarılı)

### Eklendi — Pipeline iyileştirmeleri (#312–#326)
- **`backfill_pending_images`** — beat */5dk batch=300, manuel one-shot dispatch
- **`retry_failed_images`** — saatte bir batch=100, max_age_hours=72, failed→pending dönüştür
- **Site profile sistemi** (`app/core/site_profiles.py`) — domain → SiteProfile dataclass. 6 production source için profile (BBC `figure img` whitelist + `<li>` exclude; Habertürk `article.it-main` + `.widget-image img`; Evrensel/AA/Habertürk/TRT/Yeşil Gazete generic + minor exclude). `_RECOMMENDATION_RE`'dan "widget" kaldırıldı (Habertürk widget-image false positive)
- **Reklam / logo / dekoratif filter** — domain blacklist + URL path + alt text + 5 ata level class/id check
- **Lazyload placeholder** fallback — `src` placeholder ise `data-src`/`data-original`/`data-lazy-src`/`data-srcset` (ilk URL)
- **Öneri/ilgili haber section filter** — semantic skip (`<li>`, `<aside>`, `<nav>`) + class regex (`related|recommend|suggest|sidebar|...`)
- **Generic figure caption** — `<figcaption>` → fallback `figure.get_text()` (Evrensel `<span class="small-title">` ve diğer non-figcaption pattern'leri kapsar)
- **Cross-reference güvenliği** — `vlm_postprocess.enrich_caption_with_depicts()`. alt_text validation: depicts ismi alt'ta yoksa replacement skip (yanlış kişi atıfı koruması)
- **VLM prompt iyileştirme** — kişi tanıma cross-reference (sen tanı + alt doğrula), `figure_caption` EN GÜVENİLİR context (görsel altı editör yazımı)
- **Bulk reprocess pipeline** — tüm 1870 article'ı discovered'a çek + fetch_detail dispatch; ~30-45 dk'da temiz baştan extraction

### Değişti
- **Settings reorganize**: `media.vlm_provider`, `media.vlm_model`, `media.vlm_rate_limit_rpm` → `llm` grubu (LLM Modelleri sayfası)
- **`/admin/settings/media` label**: "Görsel İndirme" → "Görsel İşleme"
- **`media.suggestion_enabled`** = true (production'da aktif edildi)

### Vendor consolidation
- Backblaze B2 + (planlanan) Anthropic Vision iptal — NIM ücretsiz tier yeterli (rate limit + Türkçe support)
- Vendor sayısı: 7 → 5

### Doc senkron (#306 + post-MVP-1.4 polish)
- `docs/engineering/architecture.md` §0 stack, §3.1 image_vlm_queue, §3 site_profiles
- `docs/engineering/data-model.md` §3.5 article_images yeni şema
- `docs/engineering/prompt-contracts.md` §5.2 NIM VLM (cross-reference), §5.3 suggest_image
- `docs/engineering/threat-model.md` §2.3.1 STRIDE matrix
- `docs/legal/ropa.md` Aktivite #07 process & discard
- `docs/strategy/risk-register.md` R-OPS-05 ÇÖZÜLDÜ
- `docs/strategy/unit-economics.md` §2.3 storage projeksiyonu

---

## [0.1.0] — 2026-05-02 — MVP-1 alpha-ready

> 🎯 **Milestone:** MVP-1 Çalışan minimum (Faz 0+1+2+3) — 97% (55/57 issue closed)
> 🌐 **Production:** https://nodrat.com (live)
> 📦 **42 PR merged** (Faz 0 foundation → Faz 3 generation pipeline)

### Eklendi — Faz 0 (Altyapı)

- **Monorepo + Docker Compose** — apps/api, apps/web, infra/, packages/ ([#81](https://github.com/selmanays/nodrat/pull/81))
- **NIM embedding adapter** — bge-m3 + local fallback + noindex koruması ([#82](https://github.com/selmanays/nodrat/pull/82))
- **CI/CD workflows** — .github/workflows/ci.yml + deploy.yml ([#118](https://github.com/selmanays/nodrat/pull/118))
- **Sentry monitoring SDK** — defensive init, invalid DSN startup'i kırmıyor ([#118](https://github.com/selmanays/nodrat/pull/118), [#122](https://github.com/selmanays/nodrat/pull/122))
- **sops + age secrets** — .env.encrypted şifreli secret yönetimi ([#118](https://github.com/selmanays/nodrat/pull/118))

### Eklendi — Faz 1 (Source pipeline)

- **Source + article schema** — NodratBot UA, robots.txt zero-tolerance, /bot landing ([#83](https://github.com/selmanays/nodrat/pull/83))
- **RSS parser** — admin /sources endpoints + 5-item compliance checklist ([#85](https://github.com/selmanays/nodrat/pull/85))
- **3-kademeli detail page extractor** — selectors > trafilatura > fallback ([#86](https://github.com/selmanays/nodrat/pull/86))
- **Article cleaning + dedupe + state machine** — PRD §1.6 + §1.7 ([#87](https://github.com/selmanays/nodrat/pull/87))
- **Celery Beat scheduler** — source crawl/healthcheck ([#88](https://github.com/selmanays/nodrat/pull/88))
- **Article images downloader** — MinIO upload pipeline ([#90](https://github.com/selmanays/nodrat/pull/90))
- **Article worker pipeline** — RSS → DB → fetch_detail → clean → persist ([#95](https://github.com/selmanays/nodrat/pull/95))
- **Admin queue + DLQ endpoints** — failed jobs retry/resolve ([#91](https://github.com/selmanays/nodrat/pull/91))

### Eklendi — Faz 2 (RAG)

- **Türkçe haber chunker** — token-aware splitting ([#101](https://github.com/selmanays/nodrat/pull/101))
- **Embedding worker** — chunk + embed + pgvector persist ([#102](https://github.com/selmanays/nodrat/pull/102))
- **Vector search + retrieval mode** — current/historical ([#103](https://github.com/selmanays/nodrat/pull/103))
- **provider_call_logs + cost tracker** — token + cost telemetry ([#104](https://github.com/selmanays/nodrat/pull/104))
- **Event clustering** — semantic + temporal ([#107](https://github.com/selmanays/nodrat/pull/107))
- **Agenda card generator** — LLM (DeepSeek V3) ([#108](https://github.com/selmanays/nodrat/pull/108))

### Eklendi — Faz 3 (User generation)

- **DeepSeek V3 chat provider adapter** — NIM endpoint üzerinden ([#106](https://github.com/selmanays/nodrat/pull/106))
- **DB tabloları** — generations + usage_events + saved_generations ([#112](https://github.com/selmanays/nodrat/pull/112))
- **Generation pipeline** — query planner + content gen + sufficiency + quota ([#113](https://github.com/selmanays/nodrat/pull/113))
- **Faz 3 user UI** — register/login/dashboard/generate/history ([#114](https://github.com/selmanays/nodrat/pull/114))
- **Brand identity** — logo, favicon, insufficient_data UX ([#120](https://github.com/selmanays/nodrat/pull/120))

### Eklendi — Cross-cutting (Legal, Admin)

- **4 takedown endpoints** — abuse / takedown (5651) / copyright (FSEK) / privacy_request (KVKK md.11) ([#116](https://github.com/selmanays/nodrat/pull/116))
- **8 legal pages** — privacy / tos / kvkk-aydinlatma / cookies / scraping + 4 talep formu ([#116](https://github.com/selmanays/nodrat/pull/116))
- **Cookie banner** — localStorage consent ([#116](https://github.com/selmanays/nodrat/pull/116))
- **Admin source management UI** — login + list + create + activate ([#98](https://github.com/selmanays/nodrat/pull/98))
- **Admin article management UI** — backend endpoints + frontend ([#100](https://github.com/selmanays/nodrat/pull/100))
- **Admin legal triage UI** — 4 form ticketing ([#116](https://github.com/selmanays/nodrat/pull/116))
- **Admin queue UI** — DLQ overview + retry/resolve ([#125](https://github.com/selmanays/nodrat/pull/125))
- **Admin users UI** — list + detail + role/tier/active management ([#123](https://github.com/selmanays/nodrat/pull/123))
- **KVKK self-service `/app/me`** — view/update/delete + admin user CRUD ([#121](https://github.com/selmanays/nodrat/pull/121))

### Eklendi — Test & Eval

- **pytest fixtures + testcontainers** — golden-set eval framework ([#92](https://github.com/selmanays/nodrat/pull/92))
- **PII golden set ≥%99 effectiveness** — phone dash separator dahil ([#97](https://github.com/selmanays/nodrat/pull/97))
- **60-case prompt golden sets** — Query Planner + Agenda + Content + Halu trap ([#119](https://github.com/selmanays/nodrat/pull/119))
- **Alpha invite docs** — kullanıcı davet süreci ([#119](https://github.com/selmanays/nodrat/pull/119))

### Değiştirildi

- **DeepSeek V3 NIM endpoint** — ek API key gerekmez (NIM_API_KEY ile birleşik) ([#110](https://github.com/selmanays/nodrat/pull/110), [#111](https://github.com/selmanays/nodrat/pull/111))

### Düzeltildi

- IBAN regex spaced format desteği ([#93](https://github.com/selmanays/nodrat/pull/93))
- admin_audit_log.metadata SQLAlchemy reserved name uyumu ([#84](https://github.com/selmanays/nodrat/pull/84))
- celerybeat-schedule writable path ([#89](https://github.com/selmanays/nodrat/pull/89))
- worker_scraper + embedding + rag nodrat_edge'e ek ([#96](https://github.com/selmanays/nodrat/pull/96))
- Admin UI unused imports ([#99](https://github.com/selmanays/nodrat/pull/99), [#115](https://github.com/selmanays/nodrat/pull/115))
- ticket_id server_default ORM model'de eksik ([#117](https://github.com/selmanays/nodrat/pull/117))
- Sentry init defensive — invalid DSN startup'i kırmaz ([#122](https://github.com/selmanays/nodrat/pull/122))

### Doküman

- INDEX.md v1.1 — MVP-1 status reflect ([#123](https://github.com/selmanays/nodrat/pull/123))
- docs/operations/deployment-manual-steps.md — kullanıcının çalıştıracağı manuel adımlar ([#123](https://github.com/selmanays/nodrat/pull/123), [#126](https://github.com/selmanays/nodrat/pull/126))
- GH Actions secrets onarım rehberi ([#126](https://github.com/selmanays/nodrat/pull/126))

### Güvenlik

- Robots.txt zero-tolerance — admin override yok
- PII redaction LLM çağrısı öncesi şart (Argon2id, Luhn TC, IBAN, email, IP, UUID)
- 18+ yaş gate — register flow'unda zorunlu
- 4 KVKK checkbox — kayıt başlangıcı
- Auth-walled admin endpoints — JWT + role check
- Cookie banner — opt-in (default decline)

---

## Sürüm anlamı

- **0.1.0** = MVP-1 alpha (3 RSS kaynağı, current mode, X post output, kayıtlı kullanıcı)
- **0.2.x** = MVP-2 (trial flow, tone/length, X thread, comparison mode)
- **0.3.x** = MVP-3 (paid launch, Lemon Squeezy MoR, style profiles)
- **1.0.0** = General Availability (multi-seat agency, full API, white-label option)

[Unreleased]: https://github.com/selmanays/nodrat/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/selmanays/nodrat/releases/tag/v0.1.0
