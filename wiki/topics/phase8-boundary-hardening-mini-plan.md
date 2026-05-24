---
type: topic
title: "Phase 8 — Boundary Hardening Mini-plan"
slug: "phase8-boundary-hardening-mini-plan"
status: live
created: 2026-05-24
updated: 2026-05-24  # v3 — A 5/5 + B 3/4 (8b-1/8b-1.5/8b-2) + Phase 8.2 ORM Completion sub-phase deferred
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§9"
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
  - "wiki/decisions/models-flat-until-conditions.md"
  - "wiki/decisions/import-direction-rules.md"
  - "wiki/decisions/modular-monolith-boundary.md"
tags: [phase8, refactor, boundary, ci, import-linter, alembic, t8, mini-plan]
aliases: [phase8-mini-plan, boundary-hardening-mini-plan]
---

# Phase 8 — Boundary Hardening Mini-plan

## TL;DR

`#1097` Phase 8 hedefi 4 workstream: **(A)** import-linter contracts genişletme + leak fix, **(B)** Alembic CI hardening + T8 ön-şart 2-5 test infra, **(C)** docs/retrospective, **(D)** code migration (`app/core/` + `app/api/` boşaltma). Reality: core/ 39 file/10450L + api/ 21 file/10416L + 148+15 production+test import site — D workstream T6/Phase 7b'den büyük scope; tek umbrella'ya sığmaz. **Karar:** Phase 8'de A+B+C tamamlanır; D **alternate criteria (ii)** ile kabul (strict contract + docs); full migration **Phase 8.1+** ayrı sub-phase issue olarak açılır. T8 ön-şart 1 (string-form relationship) zaten DONE; 2-5 Phase 8 hedefi. RTL yok; backend testler dahil çalışma davranışına dokunulmaz.

## Tanım / Bağlam

`#1097` Phase 8 — Harden docs, CI, and boundary enforcement.

**Mevcut import-linter:** `pyproject.toml` 13 contract, hepsi strict, `lint-imports` CI'da enforce (`ci.yml:289`). 13 kept / 0 broken muafiyetsiz.

**Reality (2026-05-24):**

| Alan | Durum |
|---|---|
| `app/core/` | 39 file / 10,450 LoC; 115 prod + 33 test = **148 import sitesi** |
| `app/api/` | 21 file / 10,416 LoC; 3 prod + 12 test = **15 import sitesi** |
| `app/modules/` | 18 modül aktif facade |
| `app/shared/` | 12 subdir (extraction 1461L + runtime_config 614L + 10 küçük util) |
| Boundary leak | `shared/extraction/extractor.py:194` `from app.core.site_profiles` (Seviye 0 → core leak) |
| T8 ön-şart 1 (string-form) | ✅ DONE (0 class-form, 14 total relationship) |
| T8 ön-şart 2 (Alembic CI) | 🟡 partial (`alembic-check` offline; real upgrade head yok) |
| T8 ön-şart 3/4 (tests/migration) | ❌ YOK |
| T8 ön-şart 5 (autogenerate diff = 0) | ❌ Manuel; CI yok |

**T6 #1085 closed 2026-05-23**, **Phase 7b #1096 closed 2026-05-24** — Phase 8 sırada.

## Karar / Kabul kapsamı

### 4 Workstream

**A — Boundary enforcement (import-linter genişletme + leak fix)**

1. Mevcut tek leak (`shared/extraction → core/site_profiles`) izole + fix
2. Yeni contract: `shared/* must not import app.core/app.api/app.models` (Seviye 0 saflık)
3. Yeni contract: `core/* must not import modules/*` (legacy isolation; ters yön normaldir, bu yön YASAK)
4. Yeni contract: `core/* must not import api/*` (core API'yi tüketmez)
5. (api → modules kuralı KONULMAZ — API doğal olarak modules'ı tüketir, bu yön doğru)
6. Frontend boundary (TypeScript) — Python linter kapsamı dışı; docs-only convention

**B — Alembic CI + T8 ön-şart 2-5 hardening**

1. Disposable Postgres container CI job (alembic upgrade head + alembic check)
2. `tests/migration/test_fresh_upgrade.py` — yeni
3. `tests/migration/test_mapper_resolution.py` — yeni
4. (Opsiyonel) `scripts/lint_relationship_pattern.py` + CI step (T8 ön-şart 1 otomasyonu; class-form geri gelmesini önler)

**C — Docs / retrospective**

1. `wiki/topics/refactor-retrospective-2026.md` — Phase 0..7b özet + dersler (LLM yazma yetkisi açık)
2. `docs/engineering/refactor-playbook.md` retrospective append — **kullanıcı yetki gerek** (`docs/` LLM default kapalı)
3. `docs/engineering/observability-runbook.md` — yeni — **kullanıcı yetki gerek**
4. `docs/engineering/modular-monolith-architecture.md` final state refresh — **kullanıcı yetki gerek**

**D — Code migration (`app/core/` + `app/api/` empty hedefi) — DEFERRED → Phase 8.1+**

- 60+ file migration + 148+15 import path update
- T6 + Phase 7b kümülatif scope'undan büyük
- **Alternate criteria (ii) kabul:** strict import-linter contracts (A workstream) + docs (C) yeterli safety-net; full migration ayrı initiative
- Phase 8 closure'da #1097 kapatılır; **Phase 8.1+ yeni issue** açılır (core → modules, api → modules taşıma alt-fazları)

### Hard kurallar (her PR için)

- Pre-flight: backend `ruff check` + `ruff format --check` + `pytest -q` (apps/api); import-linter; gerekli yerde apps/web `npm run type-check` + `lint` + Vitest 107 + build
- **Backend code/test PR → FULL deploy** beklenir; smoke 4-route + container health + log scan
- **Docs-only PR → deploy SKIP dogfooding**
- **Hiçbir state-changing endpoint / DB/Redis/migration/backfill production'da ASLA manuel tetiklenmez** (alembic upgrade hardening CI içinde disposable container'da yapılır)
- Backend `app.core.*` ve `app.api.*` mevcut import path'leri **dokunulmaz** (Phase 8 hedefi yeni boundary değil; mevcut sınırların korunması)
- T8 testleri import-only / mapper-only / fresh-upgrade — production veriye dokunmaz

### Risk matrisi (öncelikli)

| PR | Risk | Mitigasyon |
|---|---|---|
| 8a-1 leak fix | Düşük — site_profiles tek consumer (shared/extraction), `find_profile` pure function | Önce import chain audit, sonra fix |
| 8a-2 shared/* strict contract | Orta — diğer gizli shared→core sızıntıları çıkabilir | Tüm shared/* dosyaları audit; tek tek leak'ler ayrı PR'larla |
| 8a-3 core/* + api/* contracts | Yüksek — false-positive olasılığı; mevcut core/api iç bağımlılığı bilinmiyor | İlk dene; broken bulgu varsa muafiyet eklenmez; gerçek leak fix |
| 8b-1 disposable Postgres | Orta — CI runtime artar (~30-60 saniye); Postgres image cache stratejisi gerek | Cache + service container; eski offline job'u tutmak |
| 8b-2/3 tests/migration | Düşük — pytest fixtures pattern bilinen | conftest.py + isolated test DB |
| 8c-1 wiki retrospective | Düşük — saf docs | LLM yetki açık |
| 8c-2/3/4 docs/* | Hard blocker — LLM `docs/` yazamaz | Kullanıcı yetki gelene kadar TODO |

## PR sırası (planlanan)

### Workstream A — Boundary enforcement (5 PR, **DONE** 2026-05-24)

| PR | İçerik | Status |
|---|---|---|
| **8a-0** [#1246](https://github.com/selmanays/nodrat/pull/1246) | Bu mini-plan docs-only | ✅ MERGED |
| **8a-1** [#1247](https://github.com/selmanays/nodrat/pull/1247) | `shared/extraction → core/site_profiles` leak fix: `site_profiles` → `shared/extraction/site_profiles.py` (git mv) + 11 test caller flip + production caller flip + docstring güncelleme | ✅ MERGED |
| **8a-2** [#1248](https://github.com/selmanays/nodrat/pull/1248) | Yeni contract `shared/* must not import legacy core/api/models` (strict; 0 broken post-PR-8a-1 audit) | ✅ MERGED |
| **8a-3** [#1249](https://github.com/selmanays/nodrat/pull/1249) | `ner_stats.py` (54 LoC pure Counter+Lock) `app/modules/entities/` → `app/shared/observability/` (git mv) + 2 caller flip (`core/retrieval.py:287` + `api/admin_rag.py:651`) — bu **`core/* → modules/*` wrong-direction leak**'i kapattı (core kernel modules import etmiyor olmalı) | ✅ MERGED |
| **8a-4** [#1250](https://github.com/selmanays/nodrat/pull/1250) | Yeni 2 contract: `core/* must not import modules/*` + `core/* must not import api/*` (strict; 0 broken post-PR-8a-3 audit). 14 → **16 contract**. | ✅ MERGED |

**Workstream A NET:** 16/16 contract strict (CI enforce). 2 boundary leak (shared→core/site_profiles + core→modules/ner_stats) **kalıcı fix** (relocation + kural lock). Tüm pre-PR-8a-1 importlinter contract'ları korundu (13 kept / 0 broken).

### Workstream B — Alembic CI + T8 hardening (3-5 PR + follow-up + Phase 8.2)

| PR | İçerik | Status |
|---|---|---|
| **8b-1** [#1251](https://github.com/selmanays/nodrat/pull/1251) | `.github/workflows/ci.yml` Alembic job: disposable `pgvector/pgvector:pg16` service + `alembic upgrade head` step + 3 model `__init__` registration bug fix (EvalRun, ResearchCluster, MessageCluster) | ✅ MERGED |
| **8b-1.5** [#1253](https://github.com/selmanays/nodrat/pull/1253) | `apps/api/alembic/env.py` `include_object` filter + `RAW_SQL_ONLY_TABLES` frozenset (4 tablo: article_chunks, chat_cache_telemetry, entities, pmf_survey_responses); **alembic check step EKLENMEDİ** — Phase 8.2 deferred (50+ baseline ORM drift) | ✅ MERGED |
| **8b-2** [#1254](https://github.com/selmanays/nodrat/pull/1254) | `tests/migration/test_fresh_upgrade.py` 3 integration test (upgrade head OK + pgvector ext loaded + alembic_version single row); `pg_container` + `test_db_engine` session-scope fixture reuse | ✅ MERGED (CI wiring gap → 8b-2.5) |
| **8b-2.5** (yeni follow-up) | `tests/migration/` CI wiring — mevcut `api-unit-tests` sadece `tests/unit/` alır + integration auto-skip eder; lokal-only ⇒ CI'da koşmuyor. Ya yeni "API migration tests" job (docker + testcontainers), ya `alembic-check` job'a `pytest` step ekle | — |
| **8b-3** (planned) | `tests/migration/test_mapper_resolution.py` — SQLAlchemy `configure_mappers()` hata vermez; relationship'lar tam çözülür | — |
| **8b-4** (opsiyonel) | `scripts/lint_relationship_pattern.py` + CI step — T8 ön-şart 1 (string-form) otomasyon | — |
| **Phase 8.2** (yeni deferred sub-phase, ayrı issue) | ORM Completion: 3 pgvector VECTOR(1024) kolonu (agenda_cards/articles/event_clusters) + 30+ `__table_args__` Index deklarasyonu + 5+ UniqueConstraint + 6+ comment alignment + 1 nullable mismatch fix → tamamlanınca `alembic check` strict gate açılır | — |

### Workstream B dersleri

**PR-8b-1 journey (3 iterasyon):**

1. **Pgvector image gerekli.** Plain `postgres:16` yetmez — init migration `CREATE EXTENSION vector` çalıştırır → `pgvector/pgvector:pg16` zorunlu.
2. **alembic check 3 ORM registration bug catch etti.** `app/models/__init__.py` 3 model atlanmış (EvalRun, ResearchCluster, MessageCluster). Pre-flight checklist'e ekle: yeni model file → mutlaka __init__.py import + __all__.
3. **alembic check scope.** İlk denemede 4 raw-SQL only table için "remove_table" suggestion → scope-shrunk PR-8b-1.5'a bırakıldı.

**PR-8b-1.5 derin keşif:** `include_object` filter ile 4-tablo allowlist kurulup `alembic check` step'i denenince **çok daha geniş drift** ortaya çıktı:
- **3 pgvector VECTOR(1024) kolonu** ORM'de yok (agenda_cards.embedding, articles.summary_embedding, event_clusters.embedding)
- **30+ index** `__table_args__`'da deklare değil (idx_articles_*, idx_messages_*, idx_agenda_cards_*, ...)
- **5+ unique/check constraint** missing
- **modify_comment** ops: conversations.summary + 5× messages columns
- **modify_nullable**: takedown_requests.evidence_urls

ORM modelleri migration-uygulanmış schema'nın **eksik temsili**. Bunu kapatmak multi-PR iş → **Phase 8.2 ORM Completion** yeni sub-phase olarak deferred. PR-8b-1.5 scope-shrunk: sadece `include_object` infra bırakıldı; `alembic check` step açılmadı.

**PR-8b-2 gap:** Test eklendi ama CI'da koşmuyor — `api-unit-tests` sadece `tests/unit/` alır, `tests/migration/` collect edilmiyor + integration marker docker yoksa auto-skip eder. Lokal dev-runnable. CI wiring **PR-8b-2.5** follow-up.

### Workstream C — Docs / retrospective (1-4 PR)

| PR | İçerik | Yetki | Risk |
|---|---|---|---|
| **8c-1** | `wiki/topics/refactor-retrospective-2026.md` (Phase 0..7b özet + dersler) | LLM açık | düşük |
| **8c-2** | `docs/engineering/refactor-playbook.md` retrospective append | **kullanıcı** | hard blocker (yetki) |
| **8c-3** | `docs/engineering/observability-runbook.md` (yeni) | **kullanıcı** | hard blocker (yetki) |
| **8c-4** | `docs/engineering/modular-monolith-architecture.md` final state refresh | **kullanıcı** | hard blocker (yetki) |

### Workstream D — Code migration (DEFERRED)

- **Phase 8.1+ yeni issue** olarak açılır.
- Sub-phase önerisi:
  - 8.1 `core/db` + `core/deps` + `core/security` → `shared/db` (mevcut) genişletme
  - 8.2 `core/retrieval*` (5 file) + `core/research_*` + `core/planner_cache` → `modules/rag/` veya `shared/retrieval/`
  - 8.3 `core/chunker` + `core/semantic_chunker` + `core/embedding_binary` → `modules/embedding/internal/`
  - 8.4 `core/cleaning` + `core/content_quality` → `modules/articles/internal/`
  - 8.5 `core/cost_tracker` → T7 #1086 ile birlikte
  - 8.6 `api/admin_*` (7 file) → `modules/*/admin/routes.py` (Phase 3 pattern devam)
  - 8.7 `api/app_*` + `api/auth*` → `modules/accounts/` veya `modules/public/`
- Her sub-phase mini-plan + kendi PR sırası.

### Toplam Phase 8

- **A: 5 PR ✅ DONE** — 14→16 contract strict.
- **B: 3/4 ✅ DONE** (8b-1 #1251 + 8b-1.5 #1253 + 8b-2 #1254); 8b-3 planned; 8b-4 opsiyonel; 8b-2.5 (CI wiring) yeni follow-up
- **Phase 8.2** (deferred sub-phase, ayrı issue) — ORM Completion → `alembic check` strict gate enable
- **C: 1-4 PR** (8c-1 wiki retrospective LLM açık; 8c-2/3/4 docs kullanıcı yetki gerek)
- **D: DEFERRED** → Phase 8.1+ ayrı issue
- **Closure: 1 PR** (Phase 8 closure docs + #1097 alternate criteria + close)

## Smoke disiplin

### Backend code/test PR (8a-1, 8b-*, opsiyonel 8a-2/3 broken fix)
- FULL deploy
- Smoke: `/` 200, `/admin` 200, `/api/health` 200
- VPS container health 13/13 + log scan 6 dk ZERO ERROR/Traceback/ImportError

### Docs-only PR (8a-0 docs, 8a-2/3 wiki-only, 8c-1 wiki)
- Deploy SKIP dogfooding (Detect job skip_deploy=true)

### CI YAML PR (8b-1)
- CI'nın kendi değişikliği: workflow_dispatch + push trigger; new Alembic job ilk koşumda doğrulanır
- FULL deploy değil (CI-only changes); deploy.yml dokunulmaz

## T8 #1087 etkileşimi

- Phase 8 T8 ön-şart 2-5'i tamamlar → T8 5 ön-şartın tümü ✅ sonrası `wiki/decisions/models-flat-until-conditions.md` status → `ready-for-migration`
- T8 model relocation **kendi başına Phase N+1** initiative; Phase 8'in scope'u DEĞİL
- Phase 8 closure'da T8 ön-şart 2-5 status update + T8 issue yorum

## Stop conditions

1. CI YAML değişiminde mevcut jobs bozulursa (8b-1)
2. import-linter yeni contract'ın 1+ broken sonucu için fix kararı gerekirse (8a-2/3)
3. Disposable Postgres container CI'da kararsızsa (timing/networking)
4. Docs PR'larında `docs/` yetki açılmadıysa (8c-2/3/4) — bunlar bloklar; A+B+8c-1 ile devam
5. `core/api` directory empty criteria için kullanıcı alternate criteria onayı vermiyorsa → Phase 8 OPEN kalır; alternative path tartışmaya açılır

## İlişkiler

- [[modular-monolith-transition-master-plan]] §9 / §13 — Phase 8 ana planı
- [[models-flat-until-conditions]] — T8 5 ön-şart kaynak
- [[import-direction-rules]] — boundary rules referans
- [[modular-monolith-boundary]] — extraction boundary kararı (PR-D1)
- [[phase7b-admin-rag-mini-plan]] / [[phase7b-admin-queue-mini-plan]] / [[phase7b-admin-sft-mini-plan]] — Phase 7b precedent

## Kaynaklar

- [`pyproject.toml`](../../apps/api/pyproject.toml) `[tool.importlinter]` (13 contract)
- [`.github/workflows/ci.yml:289`](../../.github/workflows/ci.yml) lint-imports job
- [`app/shared/extraction/extractor.py:194`](../../apps/api/app/shared/extraction/extractor.py) — leak target
- [`wiki/decisions/models-flat-until-conditions.md`](../decisions/models-flat-until-conditions.md) — T8 5 ön-şart

## Açık sorular / TODO

- (8a-1 öncesi) `core/site_profiles` `shared/site_profiles/` taşıması mı, yoksa shared/extraction'da inline kopya mı? Kullanıcı kararı veya küçük POC ile test edilir.
- (8c-2/3/4 öncesi) `docs/` yetki açılır mı? Yetki gelmezse Phase 8 closure'da 8c-2/3/4 DEFERRED olarak işaretlenir.
- (D workstream öncesi) Alternate criteria (ii) kabul edilir mi? Kullanıcı onayı; aksi takdirde Phase 8 closure ertelenir.
- (Frontend boundary) TypeScript için `eslint-plugin-boundaries` POC açılır mı? Mini-plan kapsamı dışı; future initiative.
