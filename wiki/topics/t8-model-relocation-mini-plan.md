---
type: topic
title: "T8 Model Relocation Mini-plan"
slug: "t8-model-relocation-mini-plan"
category: "playbook"
status: "live"
created: "2026-05-26"
updated: "2026-05-26"
# v68 update: T8-PRE-1 zorunlu pre-step + 11. hard-stop kuralı + collect-only pre-flight
github_issue: "https://github.com/selmanays/nodrat/issues/1087"
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§2.4"
  - "wiki/plans/modular-monolith-transition-master-plan.md§4.2"
  - "wiki/topics/phase8-2-orm-completion-mini-plan.md"
  - "wiki/topics/phase8-boundary-hardening-mini-plan.md"
  - "wiki/topics/refactor-retrospective-2026.md"
  - "wiki/decisions/models-flat-until-conditions.md"
tags: [t8, refactor, orm, model-relocation, mini-plan, phase-n-plus-1, modular-monolith]
aliases: [t8-mini-plan, model-relocation-mini-plan, phase-n-plus-1-mini-plan]
---

# T8 Model Relocation Mini-plan

> 🟡 **T8 [#1087](https://github.com/selmanays/nodrat/issues/1087) — T8-PRE-1 bekliyor.** 5/5 ön-şart fully GREEN, ancak v68'de PR-T8-1 (#1298) collect-time circular import nedeniyle revert edildi (#1299). **T8-PRE-1 zorunlu pre-step:** 8 A grubu modülün `__init__.py`'lerinde lazy routes refactor. Detay: §5 ve 11. hard-stop kuralı. T8-PRE-1 yeşilliği sonrası T8-1 yeniden denenir.

## TL;DR

T8 = **Phase N+1 model relocation**: 20 dosya / 36 ORM sınıfı (3,117 satır) `apps/api/app/models/` flat layout'undan `apps/api/app/modules/<x>/models.py` modüler düzene taşınır. Tüm PR'lar **behavior-preserving** — yalnız (a) dosya konumu, (b) `from app.modules.<x>.models import` güncellemesi, (c) `app/models/__init__.py` re-export değişikliği. **No migration write, no DB schema change.** Wave A (3 PR, 0-caller ısınma) → Wave B (6 PR, düşük risk) → Wave C (7 PR, FK aileleri + yeni modüller `agenda` + `conversations`) → Wave D (6 PR, vector + identity + facade cleanup). Hard kural: facade `app/models/__init__.py` korunur (Alembic `from app.models import *` çalışmaya devam eder). T8 ön-şart 5/5 fully GREEN; data invariant 22 PR boyunca KORUNUR; `alembic check` strict gate her PR'da drift = 0.

## Tanım / Bağlam

### Niye T8?

Master plan [[modular-monolith-transition-master-plan|§2.4]] modüler monolith vizyonunda her domain'in `modules/<x>/` altında **kendi `models.py`**'sine sahip olmasını öngörür. Şu an `apps/api/app/models/` altında **flat 20-dosya layout** var (Phase 0'dan beri kasıtlı: `models-flat-until-conditions` decision) — bu T6/T7 tamamlanana ve Alembic CI hardening'i bitene kadar bilinçli ertelendi.

Phase 8 (#1097 KAPALI 2026-05-24) + Phase 8.2 ORM Completion (#1288 KAPALI 2026-05-24) + #1292 fixture fix (v66, 2026-05-26) ile **5/5 T8 ön-şart fully GREEN** — model taşımanın tüm güvenlik ağları yerinde.

### T8 ön-şart matrisi (5/5 fully GREEN — 2026-05-26)

| Ön-şart | Test | Status | Kaynak |
|---|---|---|---|
| 1. Import boundary contracts strict (relationship-pattern AST lint) | `ruff` + `pytest tests/static/test_relationship_form_strict.py` | ✅ GREEN | Phase 8 Workstream B PR-8b-4 #1258 |
| 2. Alembic CI hardening (disposable pgvector + upgrade head + `include_object` infra) | `alembic upgrade head` CI step (DB-based check) | ✅ GREEN | Phase 8 Workstream B PR-8b-1 #1251 + PR-8b-1.5 #1253 |
| 3. Fresh DB upgrade test CI guard | `api-migration-tests` job (`tests/migration/test_fresh_upgrade.py`, testcontainers pgvector:pg16) | ✅ **GREEN (v66)** | PR #1294 subprocess fix + PR #1295 NullPool fix (#1292 closed) |
| 4. mapper_resolution unit tests + AST lint | `pytest tests/unit/test_mapper_resolution.py -v` (3 test) | ✅ GREEN | Phase 8 Workstream B PR-8b-3 #1256 |
| 5. `alembic check` autogenerate diff = 0 strict gate | `alembic check` CI step (Phase 8.2 ACTIVE) | ✅ GREEN | Phase 8.2 PR-8.2-13 #1285 + PR-8.2-13a #1286 |

> T8 üzerinde değişen her PR bu 5 gate'in tümünden geçmek zorundadır (yeniden green CI). Drift veya regression = hard-stop.

### Phase 8.2 ORM Completion neden ön-şart 5'i unlock etti?

Phase 8.2 (53 drift item, 15 PR) **migration yazmadan** ORM modellerini DB state'in tam temsili haline getirdi. Bu sayede:
- `alembic check` autogenerate diff = 0 (strict gate ACTIVE)
- Gelecekte model değişiklikleri (T8 dahil) autogenerate ile yakalanır → silent regression yok
- pgvector `Vector(1024)` SQLAlchemy type'ı 3 embedding column'a resmi olarak bağlandı

T8 her PR'ında bu strict gate'i şarta bağlı olarak kullanır — model dosyası TAŞININCA autogenerate diff = 0 olmak zorunda (sadece konum değişti, schema/index/constraint/comment değişmedi).

## 1. Locked module kararları (kullanıcı tarafından 2026-05-26)

Master plan §2.4'te `agenda` ve `conversation` modelleri `generations/` altında listeleniyordu (görece eski karar). Kullanıcı tarafından T8-0'da bilinçli olarak override edildi:

| Karar | Detay |
|---|---|
| **`AgendaCard` → YENİ `modules/agenda/`** | `modules/agenda/__init__.py` + `modules/agenda/models.py`. RAPTOR sonrası ajanda kart özet düğümleri (vector(1024) embedding). |
| **`Conversation` + `Message` → YENİ `modules/conversations/`** | `modules/conversations/__init__.py` + `modules/conversations/models.py`. Perplexity-style research UX domain (#793 S1). `relationship()` back_populates aynı dosyada. |
| **Facade `app/models/__init__.py` KORUNUR** | `from app.models import *` çalışmaya devam eder (alembic/env.py:40, test fixtures). T8-22 finalde re-export'a dönüşür (içerik: `from app.modules.<x>.models import X as X`). |
| **Master plan §2.4 satırı düzeltme** | T8 closure docs PR'ında §2.4 `agenda` + `conversation` row'ları güncellenir (ayrı modül olarak). Bu mini-plan kararı kayıt altına alır; uygulama T8 sequence içinde. |

> Bu mini-plan ÇELİŞKİYİ (master plan §2.4 vs kullanıcı kararı) **bilinçli ve kayıt altında** olarak çözer. Çelişki bloğu: master plan satırı T8 closure docs PR'ında güncellenecek.

## 2. 22-PR sequence (Wave A → D)

Sıralama kriterleri:
1. **0-caller modeller önce** (Wave A): caller bütçesi sıfır; ısınma + sequence pattern kalıplaşır.
2. **FK aileleri TEK PR** (`Conversation`+`Message`, `Source`+`SourceConfig`+`SourceHealth`, vb.) — `relationship()` back_populates tutarlılığı için.
3. **Caller bütçesi ≤ 8 dosya / PR** (hard kural; aşılırsa alt-PR'lara böl).
4. **Vector kolonu (HIGH RISK) sona** — `Article.summary_embedding`, `AgendaCard.embedding`, `EventCluster.embedding` Wave D'de.
5. **`User`/`Session` 28-caller EN SON** — T8-21 zorunlu alt-PR sequence (a/b/c).

### Wave A — Isınma (3 PR, 0 caller)

| PR | Başlık | Model(ler) | Kaynak → Hedef | Risk | FK | Caller bütçesi |
|---|---|---|---|---|---|---|
| T8-1 | `settings_admin/models.py` (AppSetting) | `AppSetting` | `app/models/app_setting.py` → `app/modules/settings_admin/models.py` | LOW | users (nullable updated_by) | **0** (raw SQL only) |
| T8-2 | `prompts_admin/models.py` (AppPrompt + AppPromptHistory) | `AppPrompt`, `AppPromptHistory` | `app/models/app_prompt.py` → `app/modules/prompts_admin/models.py` | LOW | users (nullable) | **0** (raw SQL only) |
| T8-3 | `rag/models.py` (EvalRun) | `EvalRun` | `app/models/eval_run.py` → `app/modules/rag/models.py` | LOW | YOK | **0** (raw SQL only) |

### Wave B — Düşük risk, mevcut modüller (6 PR)

| PR | Başlık | Model(ler) | Hedef modül | Risk | Caller bütçesi |
|---|---|---|---|---|---|
| T8-4 | `legal/models.py` | `TakedownRequest` | `legal` | LOW | 2 |
| T8-5 | `sft/models.py` | `TrainingSample` | `sft` | LOW | 2 |
| T8-6 | `style_profiles/models.py` | `StyleProfile`, `StyleSample` | `style_profiles` | LOW | 5 (3+2 ortak dosyalar) |
| T8-7 | `ops/models.py` (jobs + audit) | `FailedJob`, `AdminAuditLog` | `ops` | LOW-MED | 8 (5+11 unique → bütçe sınırında, dikkat) |
| T8-8 | `shared/observability/models.py` (YENİ paket) | `ProviderCallLog` | `shared/observability` (YENİ) | LOW | 1 (+ infra) |
| T8-9 | `shared/email/models.py` (YENİ paket) | `EmailLog`, `EmailVerificationToken`, `PasswordResetToken` | `shared/email` (YENİ) | LOW | 3 |

### Wave C — Orta risk, FK aileleri + yeni modüller (7 PR)

| PR | Başlık | Model(ler) | Hedef modül | Risk | FK | Caller bütçesi |
|---|---|---|---|---|---|---|
| T8-10 | **`conversations/__init__` + `models.py`** | `Conversation`, `Message` | **conversations (YENİ)** | MED | users; relationship() back_populates | 8 (7+8 hot; bütçe sınırında — gerekirse 10a/10b'ye böl) |
| T8-11 | `sources/models.py` | `Source`, `SourceConfig`, `SourceHealth` | `sources` | MED | users (Source) | 8 (7+2+1, ortak dosyalar) |
| T8-12 | `articles/models.py` | `Article`, `ArticleImage` | `articles` | MED | sources | 8 (11+9 unique → çoğunluğu aynı modül, dikkat) |
| T8-13 | `clusters/models.py` (event family) | `EventCluster`, `EventArticle` | `clusters` | MED | articles, sources | 2 (EventCluster) + 0 (EventArticle) |
| T8-14 | `clusters/models.py` (research/message family) | `ResearchCluster`, `MessageCluster` | `clusters` | MED | messages, users | 6 (3+3) |
| T8-15 | `generations/models.py` (telemetry) | `ResearchCacheTelemetry` | `generations` | LOW-MED | users | 1 |
| T8-16 | `billing/models.py` (core 5) | `Plan`, `Subscription`, `Invoice`, `AgencySeat`, `WebhookEvent` | `billing` | MED | users (Subscription) | 8 (1+2+1+0+3 = 7, ortak dosyalar) |

### Wave D — Yüksek risk (6 PR — vector + identity + cleanup)

| PR | Başlık | Model(ler) | Hedef modül | Risk | Notlar |
|---|---|---|---|---|---|
| T8-17 | `billing/models.py` (usage_event) | `UsageEvent` | `billing` | MED-HIGH | 2 caller; generations'tan yazılır ama billing sahiplenir |
| T8-18 | **`agenda/__init__` + `models.py`** (HIGH: vector(1024)) | `AgendaCard` | **agenda (YENİ)** | HIGH | event_clusters FK; embedding column; T8-13 sonrası |
| T8-19 | `articles/models.py` (vector hardening) | `Article.summary_embedding` ORM idempotent re-verify | `articles` | HIGH | 0-2 caller; Phase 8.2-12'de zaten ORM'e eklendi; T8-12 sonrası mapper resolution doğrulaması |
| T8-20 | `clusters/models.py` (event vector hardening) | `EventCluster.embedding` ORM idempotent re-verify | `clusters` | HIGH | 0-2; Phase 8.2-11; T8-13 sonrası |
| T8-21 | **`accounts/models.py`** (User + Session, 28-caller) | `User`, `Session` | `accounts` | HIGH | 28 caller; **ZORUNLU alt-PR sequence** (T8-21a Session-only + T8-21b User alias re-export + T8-21c caller migration final) |
| T8-22 | **Facade cleanup + closure** | `app/models/__init__.py` `from app.modules.<x>.models import ...` re-export; eski flat `app/models/*.py` dosyaları silinir | — | LOW | EN SON; facade public sembol listesi aynı kalır; benchmark `from app.models import *` import time ölçülür |

**Toplam:** 3 (Wave A) + 6 (Wave B) + 7 (Wave C) + 6 (Wave D) = **22 PR**. T8-21'in alt-PR'ları (a/b/c) ihtiyaca göre +2-3 ekleyebilir.

## 3. Hard-stop kuralları (T8 boyunca)

T8 **mekanik** bir refactor — davranış sapması = bug. Aşağıdaki kuralların **herhangi biri** ihlal olursa hardstop, kullanıcıya raporla, devam etme:

1. **No migration write.** T8 ASLA `apps/api/alembic/versions/*` altına yeni migration dosyası eklemez veya geçmiş migration düzenlemez. Yalnız ORM **dosya konumu** değiştirilir.
2. **No DB schema change.** Hiçbir column, index, constraint, default, server_default, comment, type, nullable, FK rule, unique key değişmez. `alembic check` her PR'da 0 drift.
3. **Data invariant.** Hiçbir embedding/chunk/RAG index/vector kaydı silinmez, truncate edilmez, manuel rechunk/reembed/backfill yapılmaz (MEMORY `feedback_embedding_rag_index_safety`).
4. **`alembic check` strict gate her PR'da PASS.** Drift çıkıyorsa **hardstop** — sebebi araştır (ORM declaration kaybı? Re-export hatası?). Phase 8.2 PR-8.2-13'ten beri 0-drift garantisi.
5. **mapper_resolution unit tests her PR'da PASS.** 3 test (back_populates / relationship() / forward-ref) bozulursa hardstop.
6. **import-linter 16 contract korunur.** `boundary-rules.toml` her PR sonrası 0 ihlal. Özellikle `shared/* must not import legacy core/api` ve `modules/<x> must not import modules/<y>` (model FK ilişkileri OLSA bile — model `User`'ı `accounts`'tan import etmek yerine ilgili modülün `models.py`'sinde forward-ref string kullanılır).
7. **Behavior-preserving (no logic change).** PR diff yalnız (a) `git mv` dosya konumu, (b) `from app.modules.<x>.models import` güncellemesi, (c) `app/models/__init__.py` re-export değişikliği. Hiçbir logic, validation, kolon tanımı değişmez.
8. **Caller update bütçesi ≤ 8 dosya / PR.** Aşılırsa hardstop → PR alt-PR'lara bölünür (T8-21 zorunlu alt-PR sequence).
9. **Facade `app/models/__init__.py` korunur.** `from app.models import *` ve `from app.models import User, Conversation, ...` HER ZAMAN çalışır. T8-22'ye kadar geçici olarak (a) eski flat dosya + (b) yeni modüler dosya AYNI ANDA olabilir (facade her ikisini de re-export eder); T8-22'de eski dosyalar silinir.
10. **`relationship()` resolution string-form.** `Conversation` ↔ `Message` back_populates STRING olarak ifade edilir (`relationship("Message", back_populates="conversation")`). Class-form yasak (Phase 8 PR-8b-4 AST lint yakalar). Cross-module FK'ler `relationship("OtherModel", primaryjoin="...")` string ile çözülür.
11. **Module `__init__.py` yalnız docstring + `__all__` içerir** (v68 dersi — PR #1298 reverted). Routes/tasks/models alt-modüllerden **lazy** çekilir; `from .routes import router` üst düzeyde yasak. `main.py` ve `celery_app.py` doğrudan submodule path'inden import etmeli (`from app.modules.X.routes import router as X_router`). Aksi halde `app.models.__init__.py`'dan paketi import etmek collect-time circular tetikler (`app.core.deps` partially initialized → ImportError). Bu kural T8-PRE-1 ile 8 A grubu modülde uygulandı, gelecek modüller için norm.

### Ek operasyonel disiplin

- **Wiki güncellemesi T8 PR'larında YOK** (CLAUDE.md §1.3 paralel worktree disiplini). T8 closure docs ayrı PR.
- **Her PR self-contained**: caller listesi PR description'da declare, reviewer 8-dosya bütçesini kontrol eder.
- **Local pre-flight her PR'da:** `ruff` + `import-linter` 16/16 + `pytest tests/unit/test_mapper_resolution.py -v` + **`pytest tests/unit/test_admin_*.py --collect-only` (yeni — v68 dersi, collect-time circular import yakalar)** + 5-form caller grep (`from app.models import X`, `from app.models.<file> import X`, `app.models.<file>.X`, `models.<file>.X`, `models.X`).
- **Post-merge smoke her PR'da:** `/health` HTTPS 200 + container 13/13 + log scan ZERO (ImportError/Traceback/CRITICAL).
- **PR title prefix:** `refactor(models): T8-<N> <model_name> → modules/<x>/models.py` (örn. `refactor(models): T8-1 app_setting → modules/settings_admin/models.py`).

## 4. Açık sorular / decision matrix

T8 sequence içinde her PR başlamadan **bu cevaplara bakılır**. Belirsizlik halinde hardstop + kullanıcı kararı.

| # | Soru | Karar (bu mini-plan) | PR | Risk |
|---|---|---|---|---|
| 1 | `agenda` modülü `generations` altında mı, ayrı modül mü? | **AYRI modül** (kullanıcı locked 2026-05-26); master plan §2.4 satırı T8 closure docs PR'ında güncellenir | T8-18 + T8-22 | Çelişki kaydı zorunlu |
| 2 | `conversations` modülü `generations` altında mı, ayrı modül mü? | **AYRI modül** (kullanıcı locked 2026-05-26); master plan §2.4 satırı T8 closure docs PR'ında güncellenir | T8-10 + T8-22 | Çelişki kaydı zorunlu |
| 3 | `EmailLog`, `EmailVerificationToken`, `PasswordResetToken` nereye? | **`shared/email/models.py` YENİ paket** (master plan §2.4 ile uyumlu) | T8-9 | shared paket infra (init + boundary rule) |
| 4 | `ProviderCallLog` nereye? | **`shared/observability/models.py` YENİ paket** (master plan §2.4 ile uyumlu) | T8-8 | shared paket infra |
| 5 | `UsageEvent` billing'e mi, generations'a mı? | **`billing/models.py`** (cost ledger pattern; `Subscription`/`Invoice` akrabası); generations yazar ama billing sahiplenir | T8-17 | Caller risk: generations.tasks |
| 6 | `ResearchCacheTelemetry` generations'a mı, rag'a mı? | **`generations/models.py`** (master plan §2.4 ile uyumlu; generate-hattı prompt-cache) | T8-15 | — |
| 7 | `User`/`Session` 28-caller stratejisi? | **Alt-PR sequence ZORUNLU**: T8-21a `Session` only (4 caller); T8-21b `User` `from app.modules.accounts.models import User as _User` alias facade'da (0 caller); T8-21c caller migration final (24 caller, 3-4 PR'a yayılır 21c-1/c-2/c-3) | T8-21a/b/c | EN YÜKSEK risk PR'ı |
| 8 | `relationship()` resolution form? | **String-form** (`relationship("Message", back_populates="conversation")`); class-form yasak (PR-8b-4 AST lint) | T8-10 (ana), T8-14 (cluster), T8-21 (user-session) | — |
| 9 | Facade migration yöntemi (T8-22)? | (a) `app/models/__init__.py` re-export yapısı: `from app.modules.<x>.models import X as X` her sınıf için; (b) eski flat `app/models/<x>.py` dosyaları **silinir** (`git rm`); (c) public sembol listesi (`__all__`) AYNI kalır; (d) Alembic env.py:40 `from app.models import *` davranışı doğrulanır (fresh upgrade testleri ile) | T8-22 | LOW (mekanik cleanup) |
| 10 | `from app.models import *` import time performance T8 sonrası? | Document, blocker DEĞİL. T8-22 closure'da baseline ölçüm (`python -X importtime -c "from app.models import *"`); 22 modülden re-export bir-kez başlangıç maliyetini ekler (≈1-3ms tahmini) | T8-22 closure | — |

## 5. Pre-T8 doğrulama checklist (T8-1 öncesi)

### ⚠️ T8-PRE-1 zorunlu pre-step (v68 dersi — PR #1298 reverted 2026-05-26)

**Önce şu yapılmalı, T8-1'e ASIL gitmeden:** 8 A grubu modülün (`settings_admin`, `prompts_admin`, `legal`, `sft`, `sources`, `articles`, `style_profiles`, `media`) `__init__.py`'sinden `from .routes import router` (veya varyant) satırlarını kaldır → `main.py` doğrudan `from app.modules.X.routes import router as X_router` formuyla import etsin.

**Niye:** Bu modüllerin `__init__.py`'si eager `routes` import ediyor; routes da `app.core.deps` import ediyor. `app.models.__init__.py`'dan o paketi import etmek collect-time'da `app.core.deps` partially initialized iken zincire dönerek `ImportError: cannot import name 'get_client_ip' from partially initialized module 'app.core.deps'` veriyor. Local pre-flight entry-point farklı olduğu için yakalamıyor — pytest collect bunu yakalar.

**T8-PRE-1 PR scope:**
- 8 A grubu `__init__.py` lazy refactor (route export kaldır)
- `apps/api/app/main.py` adapt (~10 satır)
- Regression test: `tests/unit/test_module_init_lazy.py` — paket import sonrası `app.core.deps not in sys.modules`
- README/docstring "Public API: router" → "Public API: routes.router" güncellemesi
- Caller bütçesi ~10 dosya, hard-stop yok (FastAPI startup + router discovery + test fixture + Celery worker etkilenmez)

T8-PRE-1 main'de yeşil + regression guard çalışırken → T8-1 yeniden denenir.

### Standart pre-T8-1 checklist

Bu mini-plan PR'ı merge edildikten ve T8-PRE-1 tamamlandıktan sonra T8-1'e başlamadan önce:

- [ ] **Main HEAD doğrula:** `git log origin/main -1` → T8-PRE-1 PR commit'i.
- [ ] **5/5 ön-şart son CI run'ında GREEN.** `gh run list --branch main --workflow ci.yml --limit 1` → conclusion=success; `api-migration-tests` + `alembic check` + `Import boundary check` + `Migrations syntax (ast.parse)` + `API unit tests` JOB'LARI hepsi yeşil.
- [ ] **Local pre-flight:** `cd apps/api && ruff check . && alembic check && pytest tests/unit/test_mapper_resolution.py -v && pytest tests/static/test_relationship_form_strict.py -v` — hepsi PASS.
- [ ] **GitHub issue #1087** state=OPEN, başlık T8 model relocation içermeli; bu mini-plan link'i comment olarak eklenir (kullanıcı tarafından).

## 6. Wave A → Wave D geçiş kapısı

Her wave'in son PR'ı merge edildikten sonra **mini-checkpoint** (manuel — bu mini-plan PR'ından sonra ayrı wave checkpoint docs PR'ları açılabilir):

| Wave geçişi | Checkpoint kriteri |
|---|---|
| A → B | Wave A 3 PR yeşil; pattern (`git mv` + `__init__.py` ekle + `__all__` korunur + caller=0 + smoke OK) kalıplaşmış; herhangi bir PR'da sürpriz çıkmamış |
| B → C | Wave B 6 PR yeşil; `shared/email` + `shared/observability` paketleri kurulmuş + import-linter contract'a eklenmiş; ops/legal/sft/style_profiles caller pattern'ları doğrulanmış |
| C → D | Wave C 7 PR yeşil; `conversations` + `clusters` + `sources` + `articles` + `billing` taşınmış; `relationship()` string-form doğrulamaları PASS; vector kolonu olmayan tüm modeller modüler düzende |
| D sonrası | Wave D 6 PR yeşil; `agenda` yaratılmış (vector); `User`/`Session` 28-caller migration TAM; facade re-export aktif; eski flat `app/models/*.py` SİLİNMİŞ; T8 #1087 KAPATILABİLİR |

## 7. Çıkarımlar (peşinen)

1. **Hiç migration yazılmayacak.** Phase 8.2 dersi: ORM metadata değişikliği migration tetiklemez (autogenerate diff = 0 sürdükçe). T8 saf konum değişikliği.
2. **Pattern kalıplaşması Wave A'ya bağlı.** Wave A'da 3 PR sürpriz çıkarmamalı (hepsi 0-caller); kalıp oturursa Wave B+ hızlanır.
3. **`User` (28 caller) wave'ın stress testi.** T8-21 alt-PR sequence başarı/başarısızlık çıktısı T8'in toplam süresini belirler. Beklenen: 3-4 alt-PR + 2-3 closure docs.
4. **`models/__init__.py` facade kalıcı.** T8-22 sonrası bile re-export pattern korunur (Alembic + test fixtures için zorunlu). Bu Nodrat-spesifik bir "facade preservation" pattern'i — kayıt altına alınmalı.
5. **Wave D (vector + identity) bilinçli sona.** HIGH RISK PR'lar yeterli warm-up + safety net (Phase 8 strict gate + mapper resolution) sonrası çalışır.

## İlişkiler

- **Beslediği plan:** [[modular-monolith-transition-master-plan]] §2.4 + §4.2 (T8 = Phase N+1 model relocation)
- **Önceki sub-phase:** [[phase8-2-orm-completion-mini-plan]] (T8 ön-şart 5 unlock) + [[phase8-boundary-hardening-mini-plan]] (T8 ön-şart 1-2 + 4)
- **İlgili decisions:** [[models-flat-until-conditions]] (T8 başlangıcı bu kararın "conditions met" kapısı)
- **İlgili retrospective:** [[refactor-retrospective-2026]]
- **GitHub:** [#1087 T8 model relocation](https://github.com/selmanays/nodrat/issues/1087) (unblocked + tam-tedarikli 2026-05-26 v66)

## Açık sorular / TODO

- (4'üncü madde §4'te ele alındı: master plan §2.4 satırı T8 closure docs PR'ında düzeltilir. Çelişki bloğu BU mini-plan'a değil, master plan'a eklenir.)
- T8-21 alt-PR sequence detay tasarımı (T8-21a/b/c) T8-20 merge sonrası ayrı mini-plan-update PR'ında somutlaşır.
- **Deploy paths-filter incident (v68 dersi):** PR-T8-1 #1298 forward (flat→modüler rename) → deploy SKIP; revert PR #1299 reverse direction → deploy FULL. Aynı 3 dosyada paths-filter asymmetric davrandı. Ayrı incident PR (deploy.yml workflow düzeltmesi) açılacak; T8 sequence bunu beklemez ama her PR sonrası deploy davranışı doğrulanır.

## Kaynaklar

- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md) §2.4 + §4.2 + §13
- [[phase8-2-orm-completion-mini-plan]]
- [[phase8-boundary-hardening-mini-plan]]
- [[refactor-retrospective-2026]]
- [[models-flat-until-conditions]]
- GitHub Issue [#1087](https://github.com/selmanays/nodrat/issues/1087) (T8 model relocation umbrella)
- GitHub Issue [#1288](https://github.com/selmanays/nodrat/issues/1288) (Phase 8.2 — KAPALI 2026-05-24)
- GitHub Issue [#1097](https://github.com/selmanays/nodrat/issues/1097) (Phase 8 — KAPALI 2026-05-24)
- GitHub Issue [#1292](https://github.com/selmanays/nodrat/issues/1292) (fixture fix — KAPALI 2026-05-26)
