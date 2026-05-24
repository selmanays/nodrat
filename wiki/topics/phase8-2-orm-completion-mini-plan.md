---
type: topic
title: "Phase 8.2 — ORM Completion Mini-plan"
slug: "phase8-2-orm-completion-mini-plan"
status: completed
created: 2026-05-24
updated: 2026-05-24
completed: 2026-05-24
github_issue: "https://github.com/selmanays/nodrat/issues/1288"
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
  - "wiki/topics/phase8-boundary-hardening-mini-plan.md"
  - "wiki/topics/refactor-retrospective-2026.md"
  - "wiki/decisions/models-flat-until-conditions.md"
tags: [phase8-2, refactor, orm, alembic, drift, mini-plan, deferred-sub-phase, t8-precondition]
aliases: [phase8-2-mini-plan, orm-completion-mini-plan]
---

# Phase 8.2 — ORM Completion Mini-plan

> 🏁 **TAMAMLANDI 2026-05-24.** Umbrella issue [#1288](https://github.com/selmanays/nodrat/issues/1288) **KAPATILDI (reason=COMPLETED)**. T8 ön-şart 5 (autogenerate diff = 0) **GREEN** → T8 model relocation [#1087] **unblocked**. 15 PR + 1 follow-up merged; 53 baseline drift item kapatıldı; `alembic check` strict gate ACTIVE in CI.

## TL;DR

Phase 8 (#1097 KAPALI) `alembic check` strict gate'i enable etmek üzere Workstream B'de **`include_object` infra**'sını [PR-8b-1.5 #1253] hazırladı; ancak ilk CI denemesinde (run #26347227886) **53 drift item** ortaya çıktı — `alembic check` strict gate **enable EDİLEMEDİ** (Phase 8.2'ye ertelendi). Phase 8.2 ORM Completion bu drift'i kapattı: 6 drift sınıfı (37 missing index + 6 modify_comment + 3 pgvector VECTOR cols + 2 missing UniqueConstraint + 1 modify_nullable + 1 add_index expression mismatch), **15 PR + 1 follow-up** (1 mini-plan docs + 13 implementation + 1 fix-forward + 1 closure), tüm PR'lar **migration YAZMADI** (sadece ORM metadata hizalama; DB schema değişmedi). **T8 ön-şart 5** (autogenerate diff = 0) GREEN → T8 model relocation [#1087] unblocked. **Production data invariant KORUNDU**; rechunk/reembed/vector backfill/manual trigger HİÇ YAPILMADI.

## Tanım / Bağlam

### Niye ayrı sub-phase?

Phase 8 closure değerlendirmesinde (#1097 [[refactor-retrospective-2026]]) belirtildiği gibi: PR-8b-1.5'in `alembic check` denemesi ORM modellerinin migration-uygulanmış schema'nın **eksik temsili** olduğunu ortaya çıkardı. 53 drift item'ın tek PR'a sığması mümkün değil (multi-week iş; pgvector dependency add + 3 farklı model'de VECTOR column + 37 index deklarasyonu + 7 unique/comment/nullable hizalama).

Phase 8 boundary enforcement birincil hedefti — alternate criteria (ii) ile kapatıldı (16 contract strict + safety-net). **Phase 8.2 ORM Completion** ayrı **deferred sub-phase issue** olarak yedek bırakıldı; T8 ön-şart 5 için ön gereksinim.

### Phase 8.2 sonrası kazanım

- ✅ `alembic check` strict CI gate enable
- ✅ T8 ön-şart 5 (autogenerate diff = 0) yeşil
- ✅ ORM modelleri DB state'inin **tam temsili** — gelecek model değişiklikleri autogenerate ile yakalanır
- ✅ pgvector `Vector(1024)` SQLAlchemy type'ı resmi olarak modele bağlandı (3 embedding column)
- ✅ Gelecek schema drift `alembic check` ile **lint-zamanı** yakalanır (silent regression yok)

## 1. Drift sınıfları (kaynak: CI run #26347227886)

`alembic check` autogenerate çıktısında **6 farklı op tipi** + **53 ayrı drift item**:

| Op tipi | Adet | Anlam | Düzeltme tarzı |
|---|---|---|---|
| `remove_index` | **37** | DB'de var, ORM `__table_args__`'da yok | `Index(...)` deklarasyonu ekle |
| `modify_comment` | **6** | DB column.comment ≠ ORM `mapped_column(comment=...)` | ORM'e `comment="..."` ekle |
| `remove_column` | **3** | DB'de var, ORM'de tanımlı değil — **hepsi pgvector VECTOR(dim=1024)** | `from pgvector.sqlalchemy import Vector` + `Mapped[...] = mapped_column(Vector(1024))` |
| `remove_constraint` | **2** | DB UniqueConstraint, ORM'de eksik | `__table_args__`'a `UniqueConstraint(...)` ekle |
| `modify_nullable` | **1** | ORM `nullable` default ≠ DB (takedown_requests.evidence_urls) | `mapped_column(..., nullable=False)` ekle + insert path audit |
| `add_index` | **1** | ORM'de var ama DB'de farklı tanım (idx_agenda_cards_level) | model side index expression DB'ye uydur |

**Toplam:** **50 ayrı düzeltme aksiyonu** + 4 raw-SQL only tablo allowlist'te (zaten muaf).

## 2. Etkilenen model/tablo listesi

### 2.1 pgvector VECTOR kolonları (3 column / 3 model)

| Model dosya | Tablo | Kolon | Tip | Mevcut ORM |
|---|---|---|---|---|
| `apps/api/app/models/agenda.py` | `agenda_cards` | `embedding` | `VECTOR(1024)` | ❌ YOK |
| `apps/api/app/models/article.py` | `articles` | `summary_embedding` | `VECTOR(1024)` | ❌ YOK |
| `apps/api/app/models/event.py` | `event_clusters` | `embedding` | `VECTOR(1024)` | ❌ YOK |

~~`pgvector` Python paketi henüz `pyproject.toml`'da YOK → bootstrap PR (PR-8.2-10) ile eklenecek.~~

> **2026-05-24 reality check (PR-8.2-10 closure v60):** Bu satır YANLIŞTI. `pgvector>=0.3.6` `apps/api/pyproject.toml` L22'de **day-1'den beri** var (commit `30d02bb` Foundation Faz 0 PR [#81] 2026-05-01). `grep -rn "from pgvector" apps/api/app/` → 0 production import; tek site `apps/api/alembic/versions/20260511_0100_article_summary_embedding.py:21` (migration env). PR-8.2-10 NO-OP olarak işaretlendi; ilk production model-level `from pgvector.sqlalchemy import Vector` PR-8.2-11/12 ile gelecek (dolayısıyla import chain risk **ortadan kalkmadı**, sadece dep install adımı yapılmış sayıldı).

### 2.2 Index drift (37 unique index; 15 tablo)

| Tablo | Eksik index sayısı |
|---|---|
| `articles` | 10 |
| `agenda_cards` | 5 |
| `messages` | 2 |
| `failed_jobs` | 3 |
| `subscriptions` | 3 |
| `training_samples` | 2 |
| `email_verification_tokens` | 2 |
| `password_reset_tokens` | 2 |
| `plans` | 1 |
| `style_profiles` | 1 |
| `style_samples` | 1 |
| `agency_seats` | 1 |
| `event_clusters` | 1 |
| `invoices` | 1 |
| `webhook_events` | 1 |

ORM tarafında **mevcut 25 index** var; drift'le birlikte tam set ~62.

### 2.3 UniqueConstraint drift (2 named + 5 unique=True index)

- `agency_seats(subscription_id, invited_email)` — unnamed
- `webhook_events(provider, ls_event_id)` — unnamed
- `subscriptions` `uniq_subscriptions_active_per_user` — partial UQ
- `training_samples` `idx_training_samples_gen_task` — unique
- `training_samples` `uq_training_samples_message_task_sample` — unique
- `articles` `uq_articles_source_external_id` — unique
- `subscriptions` `idx_subscriptions_ls_subscription_id` — unique

### 2.4 modify_comment drift (6 column / 2 model)

| Tablo | Kolon |
|---|---|
| `conversations` | `summary` |
| `messages` | `role` |
| `messages` | `sources_used` |
| `messages` | `sources_considered` |
| `messages` | `query_embedding` |
| `messages` | `thinking_steps` |

### 2.5 modify_nullable drift (1)

`takedown_requests.evidence_urls`: ORM nullable=True (default), DB NOT NULL.

### 2.6 add_index drift (1)

`idx_agenda_cards_level` — ORM tarafı var ama expression DB'den farklı.

### 2.7 Raw-SQL only tablolar (allowlist — Phase 8.2 KAPSAMI DIŞINDA)

- `article_chunks`, `chat_cache_telemetry`, `entities`, `pmf_survey_responses` — `env.py` `RAW_SQL_ONLY_TABLES` frozenset bu 4'ünü `include_object` ile exclude eder; ORM model yazılmaz.

## 3. PR sırası (15 PR plan)

| PR | Kapsam | Drift azalması | Risk | Migration? | Durum |
|---|---|---|---|---|---|
| **PR-8.2-0** (docs) | Mini-plan docs + wiki sync | 0 | düşük | hayır | ✅ DONE 2026-05-24 ([#1262](https://github.com/selmanays/nodrat/pull/1262)) |
| **PR-8.2-1** (modify_comment) | `conversation.py` 6 `mapped_column(..., comment="...")` (Conversation.summary + Message.role/sources_used/sources_considered/query_embedding/thinking_steps) | 6 → 0 | sıfır | hayır | ✅ DONE 2026-05-24 ([#1263](https://github.com/selmanays/nodrat/pull/1263)) |
| **PR-8.2-2** (UniqueConstraint) | 7 UQ (2 named `UniqueConstraint`: agency_seats + webhook_events; 5 `Index(unique=True)`: articles partial + subscriptions ×2 partial + training_samples ×2 — `billing.py` + `article.py` + `training_sample.py`) | 7 → 0 | düşük | hayır | ✅ DONE 2026-05-24 ([#1265](https://github.com/selmanays/nodrat/pull/1265)) |
| **PR-8.2-3** (Index batch: articles) | `article.py` 8 in-scope index (4 plain + 2 partial + 2 GIN trgm); `idx_articles_summary_emb` PR-8.2-12'ye deferred (`summary_embedding` Vector(1024) ORM'de yok); `uq_articles_source_external_id` 8.2-2'de eklendi | 8 → 0 | düşük | hayır | ✅ DONE 2026-05-24 ([#1267](https://github.com/selmanays/nodrat/pull/1267)) |
| **PR-8.2-4** (Index batch: agenda_cards + add_index fix) | `agenda.py` 4 missing (title_trgm, summary_trgm, parent partial, country partial) + 1 add_index expression fix (level plain columns); idx_agenda_cards_embedding PR-8.2-11'e deferred | 5 → 0 | düşük | hayır | ✅ DONE 2026-05-24 ([#1269](https://github.com/selmanays/nodrat/pull/1269)) |
| **PR-8.2-5** (Index batch: messages + style) | `conversation.py` 2 partial (sft_eligible, dpo_rejected — assistant only) + `style_profile.py` 2 (StyleProfile user+created_at DESC, StyleSample profile FK) | 4 → 0 | düşük | hayır | ✅ DONE 2026-05-24 ([#1271](https://github.com/selmanays/nodrat/pull/1271)) |
| **PR-8.2-6** (Index batch: auth) | `email.py` 2 (verify user partial + expires) + 2 (reset user partial + expires); her iki sınıfa yeni __table_args__ | 4 → 0 | düşük | hayır | ✅ DONE 2026-05-24 ([#1273](https://github.com/selmanays/nodrat/pull/1273)) |
| **PR-8.2-7** (Index batch: ops) | `job.py` failed_jobs 3 partial (unresolved + source + severity_unresolved) + `billing.py` 4 (plans active_order, invoices user_created, agency_seats subscription, webhook_events unprocessed partial) | 7 → 0 | düşük | hayır | ✅ DONE 2026-05-24 ([#1275](https://github.com/selmanays/nodrat/pull/1275)) |
| **PR-8.2-8** (event/training residual) | **NO-OP** — reality check: event_clusters'ın 1 drift item'ı pgvector ivfflat → PR-8.2-11; training_samples'ın 2 item'ı UQ → PR-8.2-2'de eklendi. event/training residual = 0 | 0 (zaten) | sıfır | hayır | ✅ DONE 2026-05-24 (no-op, docs-only PR) |
| **PR-8.2-9** (takedown nullable audit + fix) | `takedown.py` evidence_urls — DB nullable=True (migration sa.Column default), ORM `Mapped[list[str]]` nullable=False çıkarımı → modify_nullable drift. Insert path audit 4 site, hiç None geçmiyor; ORM'i DB'ye hizala `Mapped[list[str] \| None]` | 1 → 0 | orta | hayır | ✅ DONE 2026-05-24 ([#1278](https://github.com/selmanays/nodrat/pull/1278)) |
| **PR-8.2-10** (pgvector dep + bootstrap) | **NO-OP** — reality check: `pgvector>=0.3.6` ZATEN `apps/api/pyproject.toml` L22'de (commit `30d02bb` Faz 0 PR [#81] 2026-05-01); `grep -rn "from pgvector" apps/api/app/` → 0; tek import `apps/api/alembic/versions/20260511_0100_article_summary_embedding.py:21` (migration). Dep day-1'den beri kurulu — bootstrap gereksiz | 0 (zaten) | sıfır | hayır | ✅ DONE 2026-05-24 (no-op, docs-only PR) |
| **PR-8.2-11** (pgvector cols batch 1: agenda + event) | `agenda.py` embedding `Vector(1024)` + `idx_agenda_cards_embedding` ivfflat (PR-8.2-4 deferred) + `event.py` embedding `Vector(1024)` + `idx_event_clusters_embedding` ivfflat — first production model-level `from pgvector.sqlalchemy import Vector` | 4 → 0 | **yüksek** (embedding pipeline regression riski; first import chain entry) | hayır | ✅ DONE 2026-05-24 ([#1281](https://github.com/selmanays/nodrat/pull/1281)) — behavior-preserving; writer/reader raw SQL; ORM accessor 0; FULL deploy + 9/9 smoke PASS (pgvector import OK + AgendaCard/EventCluster `.embedding.type` = VECTOR(1024)); data invariant KORUNDU |
| **PR-8.2-12** (pgvector col: articles) | `article.py` summary_embedding `Vector(1024)` + `idx_articles_summary_emb` ivfflat (PR-8.2-3 deferred; lists=100 NOT 50) | 2 → 0 | **yüksek** (embedding pipeline regression riski; mirror 8.2-11 deseni) | hayır | ✅ DONE 2026-05-24 ([#1283](https://github.com/selmanays/nodrat/pull/1283)) — behavior-preserving; writer raw SQL (embedding/tasks/embedding.py:532); reader raw SQL (retrieval.py:1148-1153 `<=>` cosine); ORM accessor 0; FULL deploy + 7/7 smoke PASS (pgvector import OK + Article.summary_embedding VECTOR(1024)); data invariant KORUNDU |
| **PR-8.2-13** (alembic check enable) | `.github/workflows/ci.yml` `alembic-check` job'a `alembic check` step ekle (strict gate) | 0 op (gate aktif) | düşük (geri kalan drift sıfır olmalı — beklendiği gibi DUR tetiklenirse 1 follow-up PR) | hayır | ✅ DONE 2026-05-24 ([#1285](https://github.com/selmanays/nodrat/pull/1285)) — ilk run #26364214021 1 drift surfaced (idx_subscriptions_status_period); DUR + PR-8.2-13a fix-forward |
| **PR-8.2-13a** (follow-up: subscriptions plain Index) | `billing.py` Subscription `__table_args__`'a `Index("idx_subscriptions_status_period", "status", "current_period_end")` ekle (PR-8.2-2 UQ-only scope + PR-8.2-7 Subscription'a dokunmama gap) | 1 → 0 | düşük (mekanik mirror PR-8.2-2/7) | hayır | ✅ DONE 2026-05-24 ([#1286](https://github.com/selmanays/nodrat/pull/1286)) — main CI 10/10 (#26364481486) + **alembic check step SUCCESS** + FULL deploy (#26364544598) + /health 200 + container 13/13 + log scan ZERO. **T8 ön-şart 5 GREEN.** |
| **PR-8.2-closure** (docs) | Phase 8.2 closure: log v64 + master plan §13 P8.2 'done' + mini-plan status `completed` + index istatistik + umbrella issue [#1288] create + KAPAT | 0 | düşük | hayır | ✅ DONE 2026-05-24 (umbrella [#1288](https://github.com/selmanays/nodrat/issues/1288) KAPATILDI reason=COMPLETED; v64 closure docs PR) |

**Toplam:** 15 PR + 1 fix-forward (PR-8.2-13a) — tamamı merged 2026-05-24.

## 4. Hard kurallar (her PR için)

- Pre-flight: backend `ruff check` + `ruff format --check` + `pytest -q` (apps/api); import-linter 16/16; AST parse
- **Backend code PR → FULL 17-step deploy** beklenir; smoke `/health` + read-only endpoint + container 13/13 + log scan ZERO
- **Docs-only PR → deploy SKIP dogfooding** doğrulanır
- **Hiçbir state-changing endpoint / DB/Redis/migration/backfill production'da ASLA manuel tetiklenmez**
- **Migration YAZILMAZ** — Phase 8.2'nin amacı ORM model dosyalarını DB state'ine hizalamak; DB schema değişmez
- **Tarihsel migration edit edilmez** — alembic versions/* dokunulmaz
- **Production DB'ye dokunulmaz** — sadece disposable CI Postgres container'da `alembic upgrade head` + `alembic check`
- **Rechunk/reembed/vector backfill YASAK** ([[feedback_embedding_rag_index_safety]] invariant)
- **Wiki sync aksatılmaz** — her anlamlı PR grubundan sonra closure docs update

## 5. Risk matrisi

| PR | Kapsam | İmpl | Migration | Test | Rollback |
|---|---|---|---|---|---|
| 8.2-0 | docs | düşük | sıfır | sıfır | trivial |
| 8.2-1..8 | metadata (comment, UQ, Index) | düşük | sıfır | sıfır (runtime path değişmez) | trivial |
| 8.2-9 | nullable (takedown) | **orta** | sıfır | **orta** (insert path audit) | trivial revert + insert pattern revert |
| 8.2-10 | pgvector dep (NO-OP — zaten kurulu) | sıfır | sıfır | sıfır | trivial (revert yok) |
| 8.2-11/12 | pgvector cols | **yüksek** | sıfır | **yüksek** (embedding lifecycle regression) | revert + worker-embedding restart |
| 8.2-13 | alembic check enable | düşük | sıfır | düşük | revert ci.yml |
| 8.2-closure | docs | düşük | sıfır | sıfır | trivial |

## 6. Smoke disiplin

### Backend code PR (8.2-1..12) post-merge
- FULL 17-step deploy
- Smoke: `/health` 200, `/admin/rag/ner-stats` 401 (PR-8a-3 sanity), 13/13 container healthy, last 5m log scan ZERO ImportError/Traceback/ERROR/CRITICAL
- 8.2-9 ek: takedown_requests insert path testleri (varsa) yeşil — production state untouched
- 8.2-10 ek: pgvector import test (`python -c "from pgvector.sqlalchemy import Vector"` in container) yeşil
- 8.2-11/12 ek: embedding worker container restart sonrası natural Beat backfill (idempotent, mevcut chunk queue ile etkileşim doğal pattern); manual trigger YOK

### CI/CD step PR (8.2-13)
- alembic-check job 10/10 (offline + DB-based + check 0 drift)
- Tüm import-linter contract 16 kept / 0 broken
- Mevcut testler PASS

### Docs-only PR (8.2-0, 8.2-closure)
- Deploy SKIP dogfooding: Detect job success + Deploy to VPS job skipped

## 7. Phase 8.2 kapsamında / sonrasında

### Phase 8.2 kapsamında (yukarıdaki 15 PR)
- 50 drift item'ın tamamı (6 comment + 1 nullable + 7 unique + 36 index + 3 vector + 1 add_index)
- pgvector dependency formal olarak `pyproject.toml`'da (PR-8.2-10 NO-OP — zaten Faz 0'dan beri kurulu)
- `alembic check` strict CI gate enable
- Phase 8.2 closure docs + yeni umbrella issue close
- **T8 ön-şart 5** (autogenerate diff = 0) yeşil → T8 [#1087] unblocked

### Phase 8.2 sonrasına ertelenir (DEFERRED)
- **Raw-SQL only tablo → ORM stub** (article_chunks, entities, chat_cache_telemetry, pmf_survey_responses) — `RAW_SQL_ONLY_TABLES` allowlist'te kalır; ayrı sub-phase (Phase 8.3?). En kritik `article_chunks` retrieval-tabanlı raw SQL pattern'i değiştirir (multi-PR; embedding/RAG critical path).
- **`tests/migration/` CI wiring** (PR-8b-2.5) — bağımsız Phase 8 follow-up; Phase 8.2 ile koşullu değil.
- **Phase 8.1+ core/api code migration** — tamamen ayrı initiative.
- **T8 model relocation** [#1087] — Phase 8.2 başarıyla tamamlanırsa T8 ön-şart 5 yeşil → T8 unblocked; ayrı issue/initiative.

## 8. Data-safety stop condition'ları (HARD STOP)

Phase 8.2 boyunca aşağıdakilerden **biri** ortaya çıkarsa → DUR + kullanıcı bildir + bekle:

1. **Production DB schema değişikliği gerekir** → DUR. Migration YAZILMAZ; DB değişmez. Eksik column/type mismatch/FK farkı çıkarsa Phase 8.2 kapsamı DIŞINDA — ayrı PR/onay gerek.
2. **Mevcut migration'ı revert/edit gerekmiş gibi görünür** → DUR.
3. **Embedding/chunk/RAG/vector verisine dokunma sinyali** ([[feedback_embedding_rag_index_safety]]): bulk reprocess, rechunk, reembed, truncate → DUR.
4. **pgvector dependency add (8.2-10) production import chain'ini bozar** (worker-embedding container ImportError, alembic env import fail) → DUR + revert.
5. **pgvector column ekleme (8.2-11/12) embedding writer pattern'ini değiştirir** (mevcut `INSERT INTO ... (embedding) VALUES (?)` raw SQL kırılır) → DUR + writer kod path'i audit.
6. **`alembic check` enable edildiğinde (8.2-13) beklenenden fazla drift** kalırsa → DUR + scope analizi tekrarla (main son 14 PR'da yeni drift eklenmiş olabilir).
7. **Backend code/test PR sonrası ImportError/Traceback/ERROR log scan'de** → DUR + rollback.
8. **CI/deploy/smoke failure** (10/10 değil, 13/13 değil, /health 200 değil) → DUR + raporla.
9. **Bu mini-plan'da belgelenmeyen yeni drift sınıfı** ortaya çıkarsa (örn. `add_column`, `drop_column`, `alter_column_type`) → DUR + scope analizi tekrarla.
10. **Yeni model file** (Phase 8.2 boyunca) → `models/__init__.py` import + `__all__` zorunlu ([[refactor-pr-checklist]] PR-8b-1 ders); aksi takdirde `alembic check` skip eder.

## İlişkiler

- [[phase8-boundary-hardening-mini-plan]] — Phase 8 (kapanmış); 8.2'nin parent kapsamı
- [[refactor-retrospective-2026]] — Phase 0..8 retrospective; Alembic drift bulgusu §5
- [[modular-monolith-transition-master-plan]] §13 P8 row
- [[models-flat-until-conditions]] — T8 ön-şart decision (5 ön-şart; bu plan ön-şart 5'i kapatır)
- [[refactor-pr-checklist]] — 80+ ders (özellikle PR-8b-1 model __init__ omission)
- [[feedback_embedding_rag_index_safety]] (memory) — embedding/vector data safety invariant

## Kaynaklar

- [`wiki/plans/modular-monolith-transition-master-plan.md`](../plans/modular-monolith-transition-master-plan.md) §13
- [`wiki/topics/phase8-boundary-hardening-mini-plan.md`](phase8-boundary-hardening-mini-plan.md)
- PR-8b-1.5 CI run [#26347227886](https://github.com/selmanays/nodrat/actions/runs/26347227886) — drift snapshot kaynağı
