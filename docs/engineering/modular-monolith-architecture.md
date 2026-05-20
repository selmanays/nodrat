# Modular Monolith Architecture

**Sürüm:** v1.0
**Tarih:** 2026-05-20
**Durum:** Kanonik
**Sahibi:** Engineering lead

> Bu doküman Nodrat'ın **modüler monolit mimari spesifikasyonudur**. Yaşayan kararlar ve gerekçeler `wiki/decisions/*` + `wiki/plans/modular-monolith-transition-master-plan.md` altında; bu doküman **sözleşme** seviyesinde durur.

---

## 0. Yönetici özeti

Nodrat tek-repo, tek-deploy monorepo'dur. Microservice'e bölünmeyecektir. Mevcut `apps/api/` yatay kesim yapısı (api/core/models/workers) **domain-bazlı dikey kesime** dönüştürülür: `apps/api/app/modules/<domain>/` + `apps/api/app/shared/<infra>/`. Modüller 4 katmanda (kernel → orta → üst, paralel + cross-cutting); aralarındaki import yönü `import-linter` ile CI'da zorlanır.

Geçiş **boundary-first evrimsel**: yeni feature'lar modül formatında yazılır, legacy dosyalar sadece dokunuldukça inceltilir. Tek seferlik toptan refactor yoktur.

---

## 1. Mimari prensipler

1. **Tek deploy, tek repo.** Microservice yok, RPC sınırı yok.
2. **Domain-bazlı dikey kesim.** Her modül kendi service + repository + routes + schemas + tasks taşır.
3. **Katman disiplini.** Üst katman alt katmanı import eder; ters yön CI fail.
4. **Behavior-preserving refactor.** Refactor PR'ı davranış değiştirmez; davranış değişimi ayrı PR.
5. **Facade-first god-files.** 800+ satır veya kritik davranış taşıyan dosyalar önce facade + characterization test; sonra kademeli iç parçalama.
6. **Models stay flat.** SQLAlchemy modelleri ana refactor boyunca `app/models/` altında flat kalır; taşıma ayrı Faz N+1.
7. **Internal alias-debt yok.** Eski path'ler taşıma PR'ında silinir; backward-compat yalnız external sözleşmeler için.
8. **Documentation as architecture.** Mimari değişiklik = aynı PR'da docs/wiki sync.
9. **Runtime config respect.** Kod-zamanı yapı ≠ runtime feature aktivasyonu; `app_settings` tablosu source-of-truth.

---

## 2. Klasör topolojisi

### 2.1 Backend (`apps/api/app/`)

```
apps/api/app/
├── main.py                  # FastAPI bootstrap (lifespan, middleware, router include)
├── config.py                # Pydantic Settings
├── modules/
│   ├── sources/             # KERNEL (Source entity)
│   ├── articles/            # KERNEL (Article + ArticleImage)
│   ├── crawler/             # orta (extraction, robots, rss, cleaning)
│   ├── rag/                 # orta (retrieval, embedding, chunking, citation, RAPTOR)
│   ├── clusters/            # orta (article event clustering)
│   ├── entities/            # orta (NER + country backfill)
│   ├── media/               # orta (görsel + VLM)
│   ├── style_profiles/      # orta (kullanıcı yazı tarzı)
│   ├── sft/                 # orta (SLM eğitim ETL)
│   ├── accounts/            # paralel (auth + me + consent + admin_users)
│   ├── billing/             # paralel (plan + quota + webhook + invoice)
│   ├── legal/               # paralel (KVKK/ToS/takedown service)
│   ├── prompts_admin/       # paralel (LLM prompt CRUD admin yüzeyi)
│   ├── settings_admin/      # paralel (runtime config CRUD admin yüzeyi)
│   ├── generations/         # ÜST (research orchestration, SSE, agenda, conversation)
│   ├── ops/                 # cross-cut (dashboard, audit, queue, system, maintenance)
│   └── public/              # cross-cut (search + health + bot.txt)
└── shared/
    ├── db/                  # Base, session, common deps
    ├── providers/           # DeepSeek, Gemini, NIM, LemonSqueezy, local_*, registry
    ├── prompts/             # 13 LLM prompt şablonu (modüller import eder)
    ├── email/               # Email gönderim altyapısı
    ├── http/                # http_client wrapper
    ├── storage/             # S3 / Object Storage
    ├── util/                # json_utils, streaming_json
    ├── observability/       # cost_tracker, maintenance_tracker, warmup_state, celery_introspect, provider_log repo
    ├── runtime_config/      # settings_store + prompts_store (Redis pub/sub)
    └── workers/             # celery_app.py (task discovery)
```

### 2.2 Her modülün iç yapısı

```
modules/<mod>/
├── __init__.py              # public facade — modülün dışa açık API'sı
├── facade.py                # (opsiyonel) — alt-paketlerden re-export merkezi
├── service.py               # iş mantığı (cross-module service'leri burada çağrılır)
├── repository.py            # DB erişimi (model flat path'ten import)
├── schemas.py               # Pydantic DTO (cross-module geçirgen)
├── deps.py                  # FastAPI dependency'ler
├── routes.py                # app-level FastAPI router
├── admin/
│   ├── __init__.py
│   ├── routes.py            # admin yüzeyi (URL prefix /admin/<sub>)
│   └── service.py
├── tasks/
│   ├── __init__.py
│   └── <task>.py            # Celery task — name pattern: tasks.<mod>.<task>
└── internal/                # modül-içi yardımcılar — DIŞARIDAN İMPORT EDİLMEZ
    └── ...
```

### 2.3 Frontend (`apps/web/src/`)

```
apps/web/src/
├── app/                     # Next.js App Router — sadece route shell
│   └── <segment>/page.tsx   # import { ModuleComponent } from '@/modules/<mod>/...'
├── components/              # shadcn ui + brand + cross-cutting (cookie-banner, theme-toggle)
│   ├── ui/                  # shadcn defaults (dokunulmaz)
│   ├── blocks/              # dashboard-area-chart, dashboard-stat-card, page-header
│   ├── brand/               # logo + nav + footer
│   ├── theme-provider.tsx, theme-toggle.tsx, cookie-banner.tsx, ...
├── modules/                 # backend modülünün frontend mirror'ı
│   ├── sources/admin/
│   ├── articles/admin/
│   ├── rag/admin/
│   ├── generations/research/    # eski components/research/* buraya
│   ├── accounts/{auth,me,consent}/
│   ├── billing/
│   ├── legal/
│   ├── ops/{dashboard,audit,queue,system}/
│   ├── style_profiles/, sft/admin/, media/admin/, ...
│   └── public/{landing,search,bot}/
└── lib/
    ├── api.ts               # base client (token refresh, retry, rate limit, error handling)
    ├── auth-context.tsx     # global auth state
    ├── format.ts, utils.ts  # cross-cutting util
```

Domain-spesifik API client'lar `src/modules/<mod>/api/<mod>-api.ts`'a taşınır (api.ts split, Faz 7a).

---

## 3. Modül kataloğu

### 3.1 Domain kernel (seviye 2)

| Modül | Sorumluluk | Sahibi (model) |
|---|---|---|
| `sources` | Source entity yaşam döngüsü, config, healthcheck, robots state, RSS endpoint | `models/source.py` (flat) |
| `articles` | Article + ArticleImage okuma API, status lifecycle (`discovered`/`active`/`quarantine`/`discarded`) | `models/article.py` (flat) |

### 3.2 Orta katman (seviye 3)

| Modül | Sorumluluk | Bağımlılığı |
|---|---|---|
| `crawler` | HTML çekme, extraction cascade, cleaning, structured_data, robots, RSS, site_profiles, content_quality | sources, articles |
| `rag` | Hybrid retrieval (BM25 + vector + RRF), reranking (locked OFF), chunking, embedding, citation, answer_span, RAPTOR | articles, sources, entities |
| `clusters` | Article-level event clustering (RAPTOR hariç) | articles |
| `entities` | NER + country backfill + entity statistics | articles, shared/prompts/ner |
| `media` | Görsel store/suggest + VLM postprocess | articles, shared/storage, shared/providers/nim_vlm |
| `style_profiles` | Kullanıcı yazı tarzı analizi | accounts |
| `sft` | SLM eğitim veri pipeline (training_sample ETL, eligibility, eval_run) | generations, articles, accounts |

### 3.3 Üst katman (seviye 4)

| Modül | Sorumluluk | Bağımlılığı |
|---|---|---|
| `generations` | Research conversation orchestration, SSE streaming, tool-call loop (RAG-as-tool), conversational query rewriting, agenda card generation, followup; `conversation/context.py` burada | rag, articles, sources, accounts, billing, style_profiles, entities |

### 3.4 Paralel modüller (seviye 1)

| Modül | Sorumluluk |
|---|---|
| `accounts` | Authentication (login + 2FA + JWT), user CRUD, me/profile/history, consent (KVKK), admin_users |
| `billing` | Plan tier, subscription, quota enforcement, LemonSqueezy webhook, invoice list, seat management |
| `legal` | KVKK/ToS/takedown route'ları, privacy-request, takedown service/repo (model flat) |
| `prompts_admin` | LLM prompt CRUD/versiyon yöneten admin yüzeyi (Redis store altyapısı `shared/runtime_config/`) |
| `settings_admin` | Runtime app_settings CRUD admin yüzeyi (Redis store altyapısı `shared/runtime_config/`) |

### 3.5 Cross-cutting

| Modül | Sorumluluk | Özel kural |
|---|---|---|
| `ops` | Dashboard (toplu metrics), audit log, Celery queue browser, system health, maintenance tasks | Diğer modüllerin public `service.py` / `repository.py`'sini okur — **TEK İSTİSNA**, yukarı yön |
| `public` | Auth-free arama + bot.txt + health endpoint | Yalnız `rag.facade` + `shared/*` |

### 3.6 Shared infrastructure (seviye 0)

| Alt-modül | İçerik |
|---|---|
| `shared/db/` | SQLAlchemy Base, session factory, common deps |
| `shared/providers/` | DeepSeek, Gemini, NIM (chat + VLM), LemonSqueezy, local_e5, local_embedding, wikipedia, registry, base adapter |
| `shared/prompts/` | 13 LLM prompt şablonu (agenda_card, chunk_keywords, content_generator, country_backfill, hyde, meta_query, ner, query_planner, query_rewrite, research_answer, research_followup, style_analyzer, weekly_summary) |
| `shared/email/` | Email gönderim altyapısı + provider |
| `shared/http/` | http_client wrapper (timeout, retry, user-agent) |
| `shared/storage/` | S3 / Object Storage abstraksiyonu |
| `shared/util/` | json_utils, streaming_json |
| `shared/observability/` | cost_tracker (sahibi), maintenance_tracker, warmup_state, celery_introspect, provider_log repository |
| `shared/runtime_config/` | settings_store + prompts_store (Redis pub/sub state, pickle-safe wire format) |
| `shared/workers/` | celery_app.py — autodiscover ile `modules/<mod>/tasks/*` toplar |

---

## 4. Import yönü kuralları (kanonik)

Bu kuralların yaşayan + örnekli hali: [`wiki/decisions/import-direction-rules.md`](../../wiki/decisions/import-direction-rules.md).

### 4.1 Allowed (özet)

- `generations` → `rag`, `articles`, `sources`, `accounts`, `billing`, `style_profiles`, `entities`, `shared/*`
- `rag` → `articles`, `sources`, `entities`, `shared/*`
- `crawler` → `articles`, `sources`, `shared/*`
- `clusters` → `articles`, `shared/*`
- `entities` → `articles`, `shared/*`, `shared/prompts/ner`
- `media` → `articles`, `shared/storage`, `shared/providers/nim_vlm`, `shared/*`
- `style_profiles` → `accounts`, `shared/*`
- `sft` → `generations`, `articles`, `accounts`, `shared/*`
- `articles` → `sources`, `shared/*`
- `sources` → `shared/*`
- `accounts` → `shared/*`
- `billing` → `accounts`, `shared/providers/lemonsqueezy`, `shared/observability/cost_tracker`, `shared/*`
- `legal` → `accounts`, `shared/*`
- `prompts_admin` → `shared/runtime_config`, `shared/prompts` (read-only), `shared/*`
- `settings_admin` → `shared/runtime_config`, `shared/*`
- `ops` → Her modülün public `service.py`/`repository.py` + `shared/*`
- `public` → `rag.facade`, `shared/*`

### 4.2 Forbidden (CI fail)

- `rag` → `crawler`, `generations`
- `crawler` → `rag`, `generations`
- `articles` → `rag`, `generations`, `crawler`, `clusters`
- `sources` → `articles`, `crawler`, `rag`, `generations`
- `accounts` → `billing`, `generations`, `rag`, `articles`, `sources`
- Tüm modüller → `<other_module>/internal/*`
- Tüm modüller → `ops`
- `shared/*` → `modules/*`

### 4.3 Özel kurallar

- **Auth dependency** — Tüm route'lar `accounts.deps.get_current_user`'ı import eder; bu shared dependency kabulüdür, ihlal değil.
- **Pydantic schemas** — Cross-module DTO geçirgen; `<mod>/schemas.py`'dan import OK.
- **Workers** — `shared/workers/celery_app.py` task autodiscover; task fonksiyonu kendi modülünün service'ini import eder.
- **Models flat (Faz N+1'e kadar)** — `from app.models.<entity> import X` boundary istisnası.

### 4.4 Strict kapsam takvimi

| Faz | Strict | Report-only |
|---|---|---|
| 1 | `modules/*`, `shared/*` | `app.core.*`, `app.api.*` |
| 2-7 | Yukarıdaki + her taşınan modül | Kalan legacy |
| 8 | Genel | — |

---

## 5. URL ve route sözleşmesi

URL prefix'leri **harici sözleşme**; refactor sırasında değişmez.

| Prefix | Modül / amaç |
|---|---|
| `/auth/...` | accounts (login, register, 2FA) |
| `/app/me/...` | accounts (profile, history, settings) |
| `/app/consent/...` | accounts (consent) |
| `/app/billing/...` | billing |
| `/app/research/...` | generations |
| `/app/style-profiles/...` | style_profiles |
| `/admin/<sub>/...` | ilgili modülün `admin/routes.py` veya ops |
| `/api/webhooks/lemonsqueezy` | billing |
| `/public/...` | public (anonim arama) |
| `/legal/...` | legal (form'lar) |
| `/health` | public |

Kod path'i değişir (`modules/<mod>/admin/routes.py`), URL prefix korunur. Detay: [`wiki/decisions/admin-route-domain-ownership.md`](../../wiki/decisions/admin-route-domain-ownership.md).

---

## 6. Worker + queue mimarisi

### 6.1 Queue isimleri (korunur, refactor sırasında değişmez)

- `crawl_queue` — sources + articles tasks
- `media_queue` — media task (legacy)
- `image_vlm_queue` — image VLM processing
- `embedding_queue` — embedding + cluster_assigner + sft_curator + maintenance
- `event_queue` — clustering + agenda + raptor + style_profile + entities

### 6.2 Task name pattern

`tasks.<mod>.<task_name>` — string-bound (Beat schedule + apply_async). **Refactor sırasında değişmez.**

### 6.3 Beat schedule

15 scheduled task `shared/workers/celery_app.py` `beat_schedule` dict'inde. Refactor sırasında task path güncellenir, schedule + kwargs değişmez.

### 6.4 Task discovery

`celery_app.py` `include=[...]` listesi explicit modül yollarını içerir; task taşıma PR'ında bu liste güncellenir.

---

## 7. Model + repository stratejisi

### 7.1 Models flat

Faz 0-8 boyunca: `apps/api/app/models/<entity>.py`. Modül service/repository **import eder**, sahip değildir (Faz N+1'e kadar). Detay: [`wiki/decisions/models-flat-until-conditions.md`](../../wiki/decisions/models-flat-until-conditions.md).

### 7.2 Repository pattern

```
modules/<mod>/repository.py:
    from app.models.<entity> import X
    
    class XRepository:
        async def get_by_id(self, session, id) -> X: ...
        async def list_by_filter(self, session, **filters) -> list[X]: ...
        async def update_status(self, session, id, status): ...
```

### 7.3 Service pattern

```
modules/<mod>/service.py:
    from modules.<mod>.repository import XRepository
    from modules.<other>.service import other_service     # cross-module OK
    
    class XService:
        def __init__(self, repository: XRepository): ...
        async def do_business_thing(self, ...): ...
```

### 7.4 Faz N+1 ön-şartları (model taşımanın açılması)

Hep birlikte sağlanmalı:
1. Tüm `relationship()` çağrıları string-ref formunda.
2. Alembic check CI'da (`alembic check` no-diff + `alembic current == alembic heads`).
3. Boş DB → upgrade head testi green.
4. Mapper resolution testi green (`configure_mappers()` hatasız).
5. Autogenerate diff = sıfır.

---

## 8. API contract stability

Refactor PR'ında URL prefix + endpoint isimleri + request/response schema **değişmez**. API contract değişimi feature PR'ı; ayrı issue + ayrı PR. `docs/engineering/api-contracts.md` güncel kalır.

---

## 9. God-file disiplini

3 ana god-file için ayrı strateji: [`wiki/decisions/god-file-facade-first.md`](../../wiki/decisions/god-file-facade-first.md).

| Dosya | Satır | Faz | Sıra |
|---|---|---|---|
| `core/extractor.py` | 1189 | 4 | facade → strategy sequence snapshot → kademeli parçalama |
| `core/retrieval.py` | 2174 | 5 | facade → 50+ query golden snapshot + eval baseline → 9-adım iç parçalama |
| `api/app_research_stream.py` | 1440 | 6 | facade → 10-senaryo SSE replay + RC3-B regression → orchestrator parçalama |

Frontend ek: `src/app/admin/rag/page.tsx` (2356) Faz 7b; `src/lib/api.ts` (2041) Faz 7a.

---

## 10. Documentation strategy

### 10.1 docs/ kanonik

- Bu doküman + `refactor-playbook.md` + `testing-strategy.md` + mevcut architecture/data-model/api-contracts/prompt-contracts/threat-model.
- İnsan-yazılı, PR-required, version-controlled.
- Çelişkide kanonik (wiki/ değil).

### 10.2 wiki/ yaşayan

- `wiki/decisions/*` — locked architectural decisions.
- `wiki/topics/*` — playbook/checklist/post-mortem.
- `wiki/plans/modular-monolith-transition-master-plan.md` — single source of truth (master plan).
- LLM-yazılı, agent-dostu, hızlı güncellenir.

### 10.3 Sync kuralı

Refactor PR'ı **aynı PR'da** docs/wiki sync yapar — ayrı "docs-only" yığma PR'ı yok. Detay PR template'inde.

---

## 11. CI gates (Faz 1 itibarıyla)

- `ruff` (tek formatter) — Python lint
- `import-linter` — boundary enforcement
- `pytest tests/unit` — unit test
- `pytest tests/integration` — integration test
- `alembic check` — no autogenerate diff
- `alembic current == alembic heads` — schema = head
- Frontend: `tsc --noEmit` + `next build`
- Eval (RAG-touching PR): recall@5/10 baseline diff < 0.5%

---

## 12. Cross-references

### Yaşayan kararlar
- [`wiki/decisions/modular-monolith-boundary.md`](../../wiki/decisions/modular-monolith-boundary.md)
- [`wiki/decisions/import-direction-rules.md`](../../wiki/decisions/import-direction-rules.md)
- [`wiki/decisions/models-flat-until-conditions.md`](../../wiki/decisions/models-flat-until-conditions.md)
- [`wiki/decisions/god-file-facade-first.md`](../../wiki/decisions/god-file-facade-first.md)
- [`wiki/decisions/admin-route-domain-ownership.md`](../../wiki/decisions/admin-route-domain-ownership.md)
- [`wiki/decisions/no-internal-backcompat-aliases.md`](../../wiki/decisions/no-internal-backcompat-aliases.md)

### Playbook
- [`wiki/topics/refactor-anti-patterns-do-not-do.md`](../../wiki/topics/refactor-anti-patterns-do-not-do.md)
- [`wiki/topics/refactor-pr-checklist.md`](../../wiki/topics/refactor-pr-checklist.md)
- [`wiki/topics/new-feature-module-checklist.md`](../../wiki/topics/new-feature-module-checklist.md)
- [`wiki/topics/agent-worktree-playbook.md`](../../wiki/topics/agent-worktree-playbook.md)

### Master plan
- [`wiki/plans/modular-monolith-transition-master-plan.md`](../../wiki/plans/modular-monolith-transition-master-plan.md)

### Diğer kanonik
- [`docs/engineering/refactor-playbook.md`](refactor-playbook.md)
- [`docs/engineering/testing-strategy.md`](testing-strategy.md)
- [`docs/engineering/architecture.md`](architecture.md) (mevcut — ileride §11 güncelleme)
- [`docs/engineering/data-model.md`](data-model.md)
- [`docs/engineering/api-contracts.md`](api-contracts.md)
