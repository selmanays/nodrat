# Changelog

Tüm önemli değişiklikler bu dosyada belgelenir.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

### Eklendi
- (TBD) MVP-2 başlangıç issue'ları (#51, #70, #71, #72, #73, #74, #75)

### Beklemede (blocked-external)
- #41 Backblaze B2 backup (B2 hesabı + API key gerekli)
- #68 Resend transactional email (Resend API key gerekli)

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
