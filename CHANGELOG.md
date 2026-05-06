# Changelog

Tüm önemli değişiklikler bu dosyada belgelenir.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

### Eklendi
- (TBD) MVP-1.5 storage migration (Epic #215 — Contabo VPS 40 + Object Storage)
- (TBD) MVP-2 başlangıç issue'ları (#51, #70, #71, #72, #73, #74, #75)

### Beklemede (blocked-external)
- #68 Resend transactional email (Resend API key gerekli)

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
- **0.3.x** = MVP-3 (paid launch, Iyzico, e-Arşiv, style profiles)
- **1.0.0** = General Availability (multi-seat agency, full API, white-label option)

[Unreleased]: https://github.com/selmanays/nodrat/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/selmanays/nodrat/releases/tag/v0.1.0
