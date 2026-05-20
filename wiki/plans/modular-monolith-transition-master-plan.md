---
type: plan
title: Modular Monolith Transition — Master Plan
slug: modular-monolith-transition-master-plan
status: live
created: 2026-05-20
updated: 2026-05-20
github_milestone: Nodrat Modular Monolith v1
github_milestone_number: 18
github_milestone_url: https://github.com/selmanays/nodrat/milestone/18
sources:
  - wiki/decisions/modular-monolith-boundary.md
  - wiki/decisions/import-direction-rules.md
  - wiki/decisions/models-flat-until-conditions.md
  - wiki/decisions/god-file-facade-first.md
  - wiki/decisions/admin-route-domain-ownership.md
  - wiki/decisions/no-internal-backcompat-aliases.md
  - docs/engineering/modular-monolith-architecture.md
  - docs/engineering/refactor-playbook.md
  - docs/engineering/testing-strategy.md
tags:
  - architecture
  - modular-monolith
  - refactor
  - master-plan
aliases:
  - modular-monolith-master
  - mm-master-plan
---

# Modular Monolith Transition — Master Plan

> **TL;DR:** Nodrat'ı domain-bazlı modüler monolite dönüştüren tek-doğruluk-kaynağı plan. Microservice değil, big-bang refactor değil — boundary-first evrimsel geçiş. 8 ana faz + ayrı Faz N+1 (model taşıma). 2-3 ay'a yayılır, MVP/RC temposunu engellemez. Bu dosya planın kanonik halidir; GitHub milestone 18 ve issue ağacı buraya link verir.

> **Bu dosya geçici not değildir.** Her phase başlangıcı + bitişinde güncellenir; karar değişimi superseded işaretiyle korunur. Agent veya insan ileride takıldığında bu dosyayı okuyup bağlamı geri kazanır.

---

## 1. Final Architecture Direction

| Karar | Detay |
|---|---|
| Microservice'e geçilmeyecek | Tek repo, tek deploy, tek Docker Compose |
| Monorepo devam | `apps/api/` (FastAPI + Celery), `apps/web/` (Next.js), `infra/`, `docs/`, `wiki/` |
| Big-bang refactor yasak | Hiçbir PR 5+ modülü dokunmaz; hiçbir faz 5 günden uzun değil |
| Boundary-first evrimsel | Önce sınırı tanımla (import yönü, modül sorumluluğu); dosyaları kararı zorlamak için zorla |
| Modeller flat (Faz N+1'e kadar) | `app/models/` flat kalır; modül taşıma 5 ön-şart sonrası |
| God-file = facade + characterization önce | retrieval.py / app_research_stream.py / extractor.py için direkt parçalama yasak |
| Domain admin route'ları kendi modülünde | `modules/<mod>/admin/`; merkezi `ops/` dar tutulur |
| Documentation as architecture | Her refactor PR'ı kendi docs/wiki sync'ini taşır (ayrı PR yok) |

İlgili kanonik belgeler:
- [docs/engineering/modular-monolith-architecture.md](../../docs/engineering/modular-monolith-architecture.md)
- [docs/engineering/refactor-playbook.md](../../docs/engineering/refactor-playbook.md)
- [docs/engineering/testing-strategy.md](../../docs/engineering/testing-strategy.md)

İlgili locked decision sayfaları:
- [[modular-monolith-boundary]]
- [[import-direction-rules]]
- [[models-flat-until-conditions]]
- [[god-file-facade-first]]
- [[admin-route-domain-ownership]]
- [[no-internal-backcompat-aliases]]

---

## 2. Module Map

### 2.1 Katman seviyeleri

```
Seviye 4 (üst):      generations
Seviye 3 (orta):     crawler, rag, clusters, entities, media, style_profiles, sft
Seviye 2 (kernel):   sources, articles
Seviye 1 (paralel):  accounts, billing, legal, prompts_admin, settings_admin
Seviye 0 (alt):      shared/* (db, providers, prompts, util, http, storage,
                                email, observability, runtime_config, workers)

Cross-cutting:       ops    — modüllerin public API'larını okur (özel istisna)
Cross-cutting:       public — yalnız rag.search facade + health
```

### 2.2 Modüller ve sorumlulukları

| Modül | Seviye | Sorumluluk |
|---|---|---|
| `sources/` | kernel | Source entity yaşam döngüsü, config, healthcheck, robots state, RSS endpoint |
| `articles/` | kernel | Article + ArticleImage okuma API, status lifecycle (`discovered`→`active`/`quarantine`/`discarded`) |
| `crawler/` | orta | HTML çekme, extraction cascade, cleaning, structured_data, site_profiles, content_quality |
| `rag/` | orta | Hybrid retrieval (BM25+vector+RRF), reranking, chunking, embedding, citation, RAPTOR |
| `clusters/` | orta | Article-level event clustering (RAPTOR HARİÇ — rag içinde) |
| `entities/` | orta | NER + country backfill + entity stats |
| `media/` | orta | Görsel store/suggest + VLM postprocess |
| `style_profiles/` | orta | Kullanıcı yazı tarzı analizi |
| `sft/` | orta | SLM eğitim veri pipeline (training_sample ETL, eligibility) |
| `accounts/` | paralel | Auth (login + 2FA), user CRUD, me/profile/history, consent, takedown model sahibi (model flat) |
| `billing/` | paralel | Plan tier, subscription, quota, LemonSqueezy webhook, invoice, seat |
| `legal/` | paralel | KVKK/ToS/takedown form route'ları, privacy-request, takedown service/repo |
| `prompts_admin/` | paralel | LLM prompt CRUD/versiyon admin yüzeyi (store altyapısı `shared/runtime_config/`) |
| `settings_admin/` | paralel | Runtime app_settings CRUD admin yüzeyi (store altyapısı `shared/runtime_config/`) |
| `generations/` | üst | Research conversation orchestration, SSE streaming, tool-call loop, agenda card generation; `conversation/context.py` burada |
| `ops/` | cross-cut | Dashboard, audit, queue, system, maintenance — domain admin DAHİL DEĞİL |
| `public/` | cross-cut | `/public/*` arama + `/health` + `/bot.txt` (auth-free) |

### 2.3 Shared infrastructure

| Alt-modül | İçerik |
|---|---|
| `shared/db/` | Base, session, common deps |
| `shared/providers/` | DeepSeek, Gemini, NIM, LemonSqueezy, local_*, registry, wikipedia |
| `shared/prompts/` | 13 LLM prompt şablonu — modüller import eder |
| `shared/email/` | Email gönderim altyapısı |
| `shared/http/` | http_client wrapper |
| `shared/storage/` | S3 / Object Storage |
| `shared/util/` | json_utils, streaming_json |
| `shared/observability/` | cost_tracker (sahibi), maintenance_tracker, warmup_state, celery_introspect, provider_log repository |
| `shared/runtime_config/` | settings_store + prompts_store (Redis pub/sub state) |
| `shared/workers/` | celery_app.py — task discovery |

### 2.4 Flat model sahiplikleri (Faz N+1'e kadar — model kendisi `app/models/` altında durur)

| Model dosyası | Service/repository sahibi |
|---|---|
| `models/source.py` | `modules/sources/` |
| `models/article.py` (Article, ArticleImage) | `modules/articles/` |
| `models/event.py` | flat, geleceğin `ops/observability/` adayı |
| `models/user.py` | `modules/accounts/` |
| `models/takedown.py` | `modules/legal/` (legal domain sahibi; kanca accounts'a değil) |
| `models/conversation.py` (Conversation, Message) | `modules/generations/` |
| `models/agenda.py` | `modules/generations/` |
| `models/research_cluster.py` | `modules/clusters/` |
| `models/research_cache_telemetry.py` | `modules/generations/` |
| `models/style_profile.py` | `modules/style_profiles/` |
| `models/training_sample.py` | `modules/sft/` |
| `models/eval_run.py` | `modules/sft/` |
| `models/billing.py` (Plan, Subscription, AgencySeat, Invoice, WebhookEvent) | `modules/billing/` |
| `models/app_setting.py` | `modules/settings_admin/` + read'ler shared/runtime_config |
| `models/app_prompt.py` | `modules/prompts_admin/` + read'ler shared/runtime_config |
| `models/job.py` | `modules/ops/` (queue admin) |
| `models/provider_log.py` | `shared/observability/` (sahibi); ops görüntüler |
| `models/email.py` | `shared/email/` |
| Diğer | İlgili modüle göre |

---

## 3. Import Boundary Rules

### 3.1 Allowed imports (özet)

| From | Allowed to |
|---|---|
| `generations` | `rag`, `articles`, `sources`, `accounts`, `billing`, `style_profiles`, `entities`, `shared/*` |
| `rag` | `articles`, `sources`, `entities`, `shared/*` |
| `crawler` | `articles`, `sources`, `shared/*` |
| `clusters` | `articles`, `shared/*` |
| `entities` | `articles`, `shared/*`, `shared/prompts/ner` |
| `media` | `articles`, `shared/storage`, `shared/providers/nim_vlm`, `shared/*` |
| `style_profiles` | `accounts`, `shared/*` |
| `sft` | `generations`, `articles`, `accounts`, `shared/*` |
| `articles` | `sources`, `shared/*` |
| `sources` | `shared/*` |
| `accounts` | `shared/*` |
| `billing` | `accounts`, `shared/providers/lemonsqueezy`, `shared/*` |
| `legal` | `accounts`, `shared/*` |
| `prompts_admin` | `shared/runtime_config`, `shared/prompts`, `shared/*` |
| `settings_admin` | `shared/runtime_config`, `shared/*` |
| `ops` | Her modülün **public service.py / repository.py** + `shared/*` |
| `public` | `rag.facade`, `shared/*` |

### 3.2 Forbidden imports (CI fail tetikleyici)

| From | Forbidden to | Neden? |
|---|---|---|
| `rag` | `crawler`, `generations` | RAG, çekme detayını veya orkestrasyonu bilmez |
| `crawler` | `rag`, `generations` | Aşağıdan yukarı |
| `articles` | `rag`, `generations`, `crawler`, `clusters` | Kernel yukarı bakmaz |
| `sources` | `articles`, `crawler`, `rag`, `generations` | Kernel'in kerneli |
| `accounts` | `billing`, `generations`, `rag`, `articles`, `sources` | Bağımsız identity |
| Tüm modüller | `<other_module>/internal/*` | Yalnız public API |
| Tüm modüller | `ops` | Ops yukarı; modüller ops'u import etmez |
| `shared/*` | Herhangi bir `modules/*` | Shared yukarı bakmaz |

Detay ve özel durumlar: [[import-direction-rules]]

### 3.3 Strict kapsam takvimi

| Faz | Strict kapsamı | Report-only kapsamı |
|---|---|---|
| 1 | `modules/*`, `shared/*` (yeni iskelet) | `app.core.*`, `app.api.*` (legacy) |
| 2-7 | Yukarıdaki + her taşınan modül | Kalan legacy |
| 8 | Genel (legacy boş veya silinmiş) | — |

---

## 4. Model Strategy

### 4.1 Flat-until-conditions

Modeller `app/models/<entity>.py` altında flat kalır. Modüller `from app.models.<entity> import X` ile erişir. Repository/service modülün içindedir.

### 4.2 Faz N+1 ön-şartları (model taşımanın açılması için)

5 koşul **hep birlikte** sağlanmadan model PR'ı açılmaz:

1. **Relationship string-ref**: Tüm `relationship()` çağrıları string formunda — `relationship("Article", back_populates="source")`.
2. **Alembic check CI'da**: `alembic check` no-diff + `alembic current == alembic heads` jobs CI'da yeşil.
3. **Boş DB → upgrade head testi**: Yeni Postgres → tüm migration uygulanır + tüm modeller import-resolve.
4. **Mapper resolution testi**: SQLAlchemy mapper init order'ında hata yok; eager init testi yeşil.
5. **Autogenerate diff sıfır**: `alembic revision --autogenerate` çıktısı boş — schema = code state.

Detay: [[models-flat-until-conditions]]

### 4.3 Repository/service pattern

```
modules/<mod>/
├── __init__.py
├── repository.py       (model import: from app.models.<entity> import X)
├── service.py
├── schemas.py          (Pydantic DTO)
├── deps.py             (FastAPI dependency)
├── routes.py
├── admin/
│   ├── routes.py
│   └── service.py
├── tasks/              (Celery)
└── internal/           (modül-içi yardımcı — dışarıdan import edilmez)
```

---

## 5. Admin / Ops Strategy

| Tür | Konum | URL |
|---|---|---|
| Domain admin | `modules/<mod>/admin/routes.py` | `/admin/<sub>/...` |
| Cross-cutting ops | `modules/ops/{dashboard,audit,queue,system}/` | `/admin/<sub>/...` |
| Operasyonel altyapı | `shared/observability/` | (modüllerden okunur) |

Kod path'i `ops/`, **URL prefix `/admin/` korunur** (harici sözleşme). Detay: [[admin-route-domain-ownership]]

---

## 6. God-file Strategy

| Dosya | Satır | Faz | Sıra |
|---|---|---|---|
| `core/extractor.py` | 1189 | 4 | facade → strategy_used sequence snapshot → kademeli parçalama |
| `core/retrieval.py` | 2174 | 5 | facade → retrieval golden snapshot (50+ query) + niche_007/009 + RC3-B + eval baseline diff → 9-adım iç parçalama |
| `api/app_research_stream.py` | 1440 | 6 | facade → SSE replay golden (10 senaryo) + RC3-B v2 marker regression + tool-loop timeout → orchestrator parçalama |
| `api/admin_rag.py` (frontend `admin/rag/page.tsx` 2356) | 1819 / 2356 | 5 (BE) / 7b (FE) | facade ile çağrı yerleri yönlendirilir |
| `src/lib/api.ts` | 2041 | 7a/7b | base + domain ayrımı; god-page split'inden önce |

Hiçbir god-file characterization test paketi olmadan parçalanmaz. Detay: [[god-file-facade-first]]

---

## 7. Documentation Strategy

| Katman | Sahibi | Karakter |
|---|---|---|
| `docs/` | İnsan-yazılı, version-controlled, PR-required | Kanonik mimari/sözleşme/runbook |
| `wiki/` | LLM-yazılı, hızlı güncelleme, agent-dostu | Yaşayan karar/gerekçe/playbook/checklist |

**Senkron kuralları:**
- docs/ kanoniktir; çelişkide docs/ kazanır.
- Her refactor PR'ı **aynı PR'da** docs/wiki sync yapar — ayrı "docs-only" yığma PR'ı yok.
- Karar değişimi: eski sayfa `status: superseded` + yeni sayfa link; decision changelog tarihli.
- **Gereksiz sayfa yasak**: Her wiki sayfası bir karar/kural/playbook/checklist taşır. "Bilgi dökme" sayfası kabul edilmez.

İlgili kanonik:
- [docs/engineering/modular-monolith-architecture.md](../../docs/engineering/modular-monolith-architecture.md)
- [docs/engineering/refactor-playbook.md](../../docs/engineering/refactor-playbook.md)
- [docs/engineering/testing-strategy.md](../../docs/engineering/testing-strategy.md)

---

## 8. GitHub Milestone / Issue Map

**Milestone:** [Nodrat Modular Monolith v1 (#18)](https://github.com/selmanays/nodrat/milestone/18)

### 8.1 Phase Issues

| ID | Başlık | Issue # | Status |
|---|---|---|---|
| P0 | Phase 0 — Finalize modular monolith decision and documentation | [#1088](https://github.com/selmanays/nodrat/issues/1088) | **in-progress** |
| P1 | Phase 1 — Create modules/shared skeleton and boundary checks | [#1089](https://github.com/selmanays/nodrat/issues/1089) | blocked |
| P2 | Phase 2 — Move low-risk modules | [#1090](https://github.com/selmanays/nodrat/issues/1090) | blocked |
| P3 | Phase 3 — Introduce sources/articles repository-service layer | [#1091](https://github.com/selmanays/nodrat/issues/1091) | blocked |
| P4 | Phase 4 — Add crawler facade and extraction characterization tests | [#1092](https://github.com/selmanays/nodrat/issues/1092) | blocked |
| P5 | Phase 5 — Add RAG facade and retrieval characterization tests | [#1093](https://github.com/selmanays/nodrat/issues/1093) | blocked |
| P6 | Phase 6 — Add generations facade and SSE replay tests | [#1094](https://github.com/selmanays/nodrat/issues/1094) | blocked |
| P7a | Phase 7a — Modularize frontend low-risk domains | [#1095](https://github.com/selmanays/nodrat/issues/1095) | blocked |
| P7b | Phase 7b — Modularize frontend god-pages and research UI | [#1096](https://github.com/selmanays/nodrat/issues/1096) | blocked |
| P8 | Phase 8 — Harden docs, CI, and boundary enforcement | [#1097](https://github.com/selmanays/nodrat/issues/1097) | blocked |
| N+1 | Phase N+1 — Prepare and execute SQLAlchemy model relocation | [#1098](https://github.com/selmanays/nodrat/issues/1098) | blocked (5 preconditions) |

### 8.2 Tracking Issues

| ID | Başlık | Issue # | Status |
|---|---|---|---|
| T1 | Master plan: maintain wiki/plans/modular-monolith-transition-master-plan.md | [#1080](https://github.com/selmanays/nodrat/issues/1080) | live |
| T2 | Boundary enforcement: import-linter rules and CI gates | [#1082](https://github.com/selmanays/nodrat/issues/1082) | live |
| T3 | Documentation sync checklist (per-PR enforcement) | [#1081](https://github.com/selmanays/nodrat/issues/1081) | live |
| T4 | Refactor PR checklist (template + review discipline) | [#1083](https://github.com/selmanays/nodrat/issues/1083) | live |
| T5 | Characterization test requirements (retrieval, SSE, extraction) | [#1084](https://github.com/selmanays/nodrat/issues/1084) | live |
| T6 | God-file facade strategy (retrieval / SSE / extraction) | [#1085](https://github.com/selmanays/nodrat/issues/1085) | live |
| T7 | Runtime-sensitive modules (settings_store, prompts_store, cost_tracker) | [#1086](https://github.com/selmanays/nodrat/issues/1086) | live |
| T8 | Model relocation prerequisites (5 conditions) | [#1087](https://github.com/selmanays/nodrat/issues/1087) | live |

---

## 9. Phase Plan

### Phase 0 — Documentation + boundary decision (≈5-7 gün)
- **Amaç:** Mimari yön kararı + master plan + 6 decision + 4 topic + 3 docs/engineering belgesi. Hiçbir kod taşınmaz.
- **Bu PR ile (Transition PR 1) yapılır.** Bu fazın çıktısı bu master plan dosyasının kendisi + ilgili decisions/topics + docs/engineering yeni 3 belge.
- **Acceptance:** Kullanıcı Transition PR 1'i review + onay.

### Phase 1 — Module/shared skeleton + import-linter (≈2-3 gün)
- **Amaç:** Boş iskelet + import-linter CI. Tek bir Python dosyası taşınmaz.
- **Yapılacak:** `apps/api/app/modules/<mod>/__init__.py` + `README.md`; `apps/api/app/shared/<sub>/`; `pyproject.toml`'da `[tool.importlinter]` config; CI'a alembic check + import-linter step.
- **Strict kapsam:** Yeni `modules/*` ve `shared/*` baştan strict; legacy `app.core.*` + `app.api.*` report-only.
- **Risk:** Düşük. CI yeşil olmalı — boş iskelet ihlal yaratmaz.

### Phase 2 — Low-risk modules (≈1.5-2 hafta)
- **Modüller:** style_profiles, sft, entities, media, clusters, legal (takedown service/repo dahil), prompts_admin + shared/runtime_config/prompts_store, settings_admin + shared/runtime_config/settings_store.
- **Yapılmayacak:** Modeller taşınmaz; god-file dokunulmaz; sources/articles dokunulmaz.
- **Risk:** Düşük-Orta. settings_store + prompts_store Redis pub/sub davranışı staging'de doğrulanır.

### Phase 3 — Sources/articles repository/service + accounts + billing (≈1.5-2 hafta)
- **Modüller:** sources, articles, accounts (auth + 2FA + me + consent + admin_users), billing (routes + service + webhook + admin).
- **`app_me.py` (1091)** profile/history/settings dosyalarına bölünür (god-file değil, semantik ayrım net).
- **Risk:** Orta. Auth import path değişimi koordinasyonu gerek.

### Phase 4 — Crawler facade + extraction characterization + ops + public (≈2 hafta)
- **Modüller:** crawler (facade ile re-export + workers/tasks + cleaning/robots/rss/site_profiles/content_quality/structured_data taşıma); ops (admin_dashboard/audit/queue/system + shared/observability/*); public (public_search + health).
- **`cost_tracker`** → `shared/observability/cost_tracker.py`.
- **Risk:** Orta. Crawler workers Beat schedule production'da kritik; task name değişmez.

### Phase 5 — RAG facade + retrieval characterization (≈3 hafta)
- **Modüller:** rag (facade → retrieval golden snapshot → tüm çağrı yerleri facade'a → workers/tasks/embedding + raptor → admin_rag routes → retrieval iç parçalama 9 adımda → chunking + citation + embedding/binary).
- **Yapılmayacak:** Cross-encoder rerank açma (locked-permanent); confidence routing geri getirme; sub-chunking.
- **Risk:** Yüksek. Retrieval Nodrat'ın kalbi; sessiz regresyon riski en yüksek.

### Phase 6 — Generations facade + SSE replay tests (≈3 hafta)
- **Modüller:** generations (facade → SSE replay golden → citation/conversation_context/tracked_chat/streaming_orchestrator/agenda task/research_tools + RC3-B v2 marker regression).
- **Yapılmayacak:** DeepSeek tool_choice değişikliği (cache invariant); LLM-verifier geri getirme.
- **Risk:** Çok yüksek. SSE state machine + tool-loop davranışı.

### Phase 7a — Frontend low-risk (≈1-1.5 hafta, P3 ile paralel olabilir)
- **Modüller:** legal, billing, accounts, style_profiles, settings_admin, prompts_admin, sft (frontend).
- **`src/lib/api.ts` split** burada: base infrastructure (token refresh, retry, rate limit) kalır; domain api'ler `src/modules/<mod>/api/`'a taşınır.

### Phase 7b — Frontend god-pages + research UI (≈1.5-2 hafta, P6 sonrası)
- **Modüller:** generations/research (eski `src/components/research/*` 8 dosya); admin/rag (2356 sat) 4 bileşene böl; admin/queue (1035) 3 bileşene böl; admin/sft (1026) 3 bileşene böl.

### Phase 8 — Documentation hardening + CI enforcement (≈1 hafta)
- **Yapılacak:** docs/engineering/modular-monolith-architecture.md final; refactor-playbook retrospective; observability-runbook final; import-linter genel strict; alembic CI sertleştir (relationship pattern denetim script'i).
- **Faz N+1 hazırlık:** Master plan §4.2 5 ön-şartını sağlayan kontroller `wiki/decisions/models-flat-until-conditions.md` `status: ready-for-migration`'a yükselir.

### Phase N+1 — Model relocation (ayrı milestone)
- **Bloklayıcı:** §4.2'deki 5 ön-şart.
- **Modül sırası:** sources → articles → orta katman → üst katman.
- **Her modül için ayrı PR**, deprecation period 1 release.

---

## 10. First PR Sequence

| # | Kapsam | Risk | Bağımlılık |
|---|---|---|---|
| Transition PR 1 | Master plan + 6 decision + 4 topic + 3 docs/engineering + CLAUDE.md / INDEX.md update + GitHub milestone/labels/templates/issues. **No application code changed.** | Çok düşük | — |
| Transition PR 2 | `modules/` + `shared/` boş iskelet + import-linter config + CI step + `apps/web/src/modules/` iskelet | Düşük | Transition PR 1 onay |
| Transition PR 3 | `modules/style_profiles/` tam taşıma | Düşük | Transition PR 2 merge |
| Transition PR 4 | `modules/settings_admin/` + `shared/runtime_config/settings_store` | Orta | Transition PR 2 merge (Transition PR 3 paralel olabilir) |
| Transition PR 5 | `modules/prompts_admin/` + `shared/runtime_config/prompts_store` | Orta | Transition PR 4 merge (Redis pub/sub pattern doğrulandıktan sonra) |

Sonraki PR'lar (Phase 2 devam): entities, media, clusters, legal, sft (her biri ayrı PR).

---

## 11. Do-Not-Do List

Detaylı tarihsel kanıt: [[refactor-anti-patterns-do-not-do]]

| # | Anti-pattern | Kaynak |
|---|---|---|
| 1 | Big-bang refactor (5+ modülü tek PR'da) | (proaktif) |
| 2 | Model taşımayı erken yapma (Faz N+1 ön-şartları sağlanmadan) | %93 class-ref relationship — circular import garantili |
| 3 | God-file facade ve characterization öncesi parçalama | RC3-B v1 prod 4/8 yanlış-pozitif (log #1076) |
| 4 | Characterization test olmadan retrieval/SSE değişikliği | niche_007/009 6 ay kör (#939); RC3-B v1 |
| 5 | Merkezi `admin/` god-modülü | (proaktif — domain boundary yok eder) |
| 6 | `core/` içine yeni domain logic ekleme | 47 dosya legacy — yeni dosya **modüle** |
| 7 | Import boundary ihlali | §3.2 forbidden tablosu |
| 8 | Docs/wiki güncellemesi atlama | feedback_wiki_sync_completeness |
| 9 | Internal alias-debt biriktirme (eski path'leri "backward-compat" tutma) | feedback_backward_compat_argument |
| 10 | Cross-encoder rerank açma | cross-encoder-rerank-disabled locked-permanent |
| 11 | Confidence-based routing geri getirme | confidence-based-routing superseded |
| 12 | Sub-chunking / micro-chunking | failed-experiments #769 |
| 13 | Rerank-only niş entity çözüm | failed-experiments #758/783/791 |
| 14 | LLM-judgment faithfulness verifier geri getirme | log #1076 RC3-B v1 |
| 15 | DeepSeek tool_choice cache-breaking değişiklik | feedback_deepseek_toolchoice_cache |
| 16 | Spike deploy'u clean-main restore etmeden bırakma | feedback_spike_deploy_restore_clean_main |
| 17 | Queue/task name değişikliği | (proaktif — string-bound) |
| 18 | Paralel SSH ile deploy | feedback_deploy_lessons |
| 19 | Eski path'ten yeni path'e re-export köprü (legacy alias) | (mimari prensip — no-internal-backcompat) |
| 20 | Refactor PR'ında davranış değişikliği (feature/fix karıştırma) | feedback_spike_deploy_restore + behavior-preserving |

---

## 12. Open Questions and Decisions

### 12.1 Kararlaştırılmış (kullanıcı 2026-05-20)

1. ~~Modül adı `ops/` mi `admin/` mi?~~ → **`ops/` kod path, `/admin/*` URL** (karar 2026-05-20).
2. ~~Settings/prompts store yeri?~~ → **`shared/runtime_config/`**; admin modülleri yalnız CRUD yüzeyi.
3. ~~`conversation_context` shared mi?~~ → **`modules/generations/conversation/context.py`** — generations'a ait.
4. ~~`cost_tracker` billing'e mi?~~ → **`shared/observability/cost_tracker.py`**; billing read-only consumer.
5. ~~Model taşıma ana faza dahil mi?~~ → **Ayrı Faz N+1**, 5 ön-şart.
6. ~~Frontend tamamen Faz 7'de mi?~~ → **Faz 7a (low-risk paralel) + Faz 7b (god-pages, backend sonrası)**.
7. ~~api.ts split nezaman?~~ → **God-page parçalamadan önce** (Faz 7a).
8. ~~`core/` ne zaman silinir?~~ → **Import-bazlı**: `app.core.*` import kalmadığında.
9. ~~`api/` ne zaman silinir?~~ → **Faz 6 sonu** — son route (app_research) taşındıktan sonra. URL değişmez.
10. ~~State management değişir mi?~~ → **Hayır**, refactor scope dışı.
11. ~~`event.py` model sahibi?~~ → **Flat kalır**; ileride ops/observability adayı.
12. ~~`takedown.py` sahibi?~~ → **legal/** service/repo; model flat.
13. ~~`provider_log.py` sahibi?~~ → **shared/observability/**; ops görüntüler.
14. ~~`job.py` sahibi?~~ → **ops/queue/**; model flat.
15. ~~Frontend modül + alt feature adı?~~ → **`src/modules/generations/research/`**.
16. ~~Import-linter strict ne zaman?~~ → **Faz 1: modules/shared strict + legacy report-only; kademeli; Faz 8 genel strict**.

### 12.2 Açık (Faz başlangıcında cevaplanır)

- (Faz 1) `apps/api/pyproject.toml`'da `[tool.importlinter]` mi yoksa ayrı `.importlinter.cfg` mi?
- (Faz 4) `apps/api/app/workers/celery_app.py` `modules/`'a mı taşınır yoksa `shared/workers/`'da mı kalır? (Önerim: `shared/workers/`.)
- (Faz 5) `cross-encoder` rerank kodu silinsin mi yoksa pluggable interface arkasında kapalı mı kalsın? (Önerim: kapalı kalır; locked-permanent decision'a göre.)
- (Faz 6) **`generations → sft` import yönü kararı.** Phase 2 PR 2 sırasında `app/api/app_research.py` (generations modülü, Phase 6'da taşınacak) lazy `from app.modules.sft.eligibility import recompute_sft_eligibility` import'u yapıyor. Phase 6'da `generations` taşınırken iki seçenek arasında karar verilmeli:
  - **Seçenek 1**: `generations → sft` allowed direction olarak [[import-direction-rules]] tablosuna eklenir; eligibility public API.
  - **Seçenek 2**: SFT recompute/eligibility davranışı `modules/sft` public service/admin surface altında izole edilir; generations doğrudan SFT internallerini bilmez (örn. message tablosunda `sft_recompute_pending` flag → curator task yapar).
  - Karar Phase 6 başlamadan önce verilir; T2 [#1082](https://github.com/selmanays/nodrat/issues/1082) ve T6 [#1085](https://github.com/selmanays/nodrat/issues/1085) tracking'lerde takip edilir.
- (Faz 8) Faz N+1 ön-şart denetim script'i nasıl yazılır (relationship pattern grep, alembic env hook)?

### 12.3 Decision changelog

- 2026-05-20: Plan v2 → final v3 (kullanıcı 16 karar entegrasyonu).
- 2026-05-20: Master plan + 6 decision + 4 topic oluşturuldu (Transition PR 1).
- 2026-05-20: Transition PR 1 merged ([#1099](https://github.com/selmanays/nodrat/pull/1099), main HEAD `72b68c3`). Phase 0 closed ([#1088](https://github.com/selmanays/nodrat/issues/1088)). Phase 1 started.
- 2026-05-20: Phase 1 PR merged ([#1100](https://github.com/selmanays/nodrat/pull/1100), main HEAD `5a67e06`). Phase 1 closed ([#1089](https://github.com/selmanays/nodrat/issues/1089)). modules/shared skeleton + 12 import-linter contracts + lint-imports + alembic-check CI active. Phase 2 started.
- 2026-05-20: Phase 2 PR 1 merged ([#1101](https://github.com/selmanays/nodrat/pull/1101), main HEAD `66d224a`). First modular migration: `modules/style_profiles/` (1-to-1 from `app.api.style_profiles` + `app.core.text_metrics` + `app.workers.tasks.style_profile`). Behavior-preserving (URL + Celery name + DB schema unchanged). Phase 2 PR 2 started: `modules/sft/`.
- 2026-05-20: Phase 2 PR 2 merged ([#1102](https://github.com/selmanays/nodrat/pull/1102), main HEAD `6c22f14`). Second modular migration: `modules/sft/` (1-to-1 from `app.api.admin_sft` + `app.core.sft_eligibility` + `app.workers.tasks.sft_curator`). Behavior-preserving. CI lesson: broader grep pattern (`from X import Y` ve `from X.Y import Z` her ikisi) standart hale geldi — `refactor-pr-checklist` §6 güncel. Boundary follow-up: `generations → sft` import yönü Phase 6'da karara bağlanacak (§12.2 yeni madde). Phase 2 PR 3 started: `modules/entities/`.
- 2026-05-20: Phase 2 PR 3 merged ([#1103](https://github.com/selmanays/nodrat/pull/1103), main HEAD `8338249`). Third modular migration: `modules/entities/` (1-to-1 from `app.core.ner_stats` + `app.workers.tasks.entities`). Behavior-preserving. 2 follow-up not bu PR'da uygulandı: `refactor-pr-checklist` §6 broader grep pattern + master plan §12.2 generations→sft Phase 6 open question + T2/T6 tracking comments. Phase 2 PR 4 started: `modules/legal/` (kullanıcı tercihiyle media/clusters'tan önce).

---

## 13. Current Status Tracker

| Alan | Değer |
|---|---|
| Aktif faz | **Phase 2** ([#1090](https://github.com/selmanays/nodrat/issues/1090)) — in-progress |
| Bekleyen | P3 [#1091](https://github.com/selmanays/nodrat/issues/1091), P4 [#1092](https://github.com/selmanays/nodrat/issues/1092), P5 [#1093](https://github.com/selmanays/nodrat/issues/1093), P6 [#1094](https://github.com/selmanays/nodrat/issues/1094), P7a [#1095](https://github.com/selmanays/nodrat/issues/1095), P7b [#1096](https://github.com/selmanays/nodrat/issues/1096), P8 [#1097](https://github.com/selmanays/nodrat/issues/1097), N+1 [#1098](https://github.com/selmanays/nodrat/issues/1098) |
| Tamamlanan | **P0** [#1088](https://github.com/selmanays/nodrat/issues/1088) (merged `72b68c3`), **P1** [#1089](https://github.com/selmanays/nodrat/issues/1089) (merged `5a67e06`) |
| Aktif tracking | T1 [#1080](https://github.com/selmanays/nodrat/issues/1080), T2 [#1082](https://github.com/selmanays/nodrat/issues/1082), T3 [#1081](https://github.com/selmanays/nodrat/issues/1081), T4 [#1083](https://github.com/selmanays/nodrat/issues/1083), T5 [#1084](https://github.com/selmanays/nodrat/issues/1084), T6 [#1085](https://github.com/selmanays/nodrat/issues/1085), T7 [#1086](https://github.com/selmanays/nodrat/issues/1086), T8 [#1087](https://github.com/selmanays/nodrat/issues/1087) |
| Son güncelleme | 2026-05-20 — Phase 2 PR 4 açılıyor: `modules/legal/` dördüncü modül taşıma (1-to-1, kullanıcı tercihiyle media/clusters'tan önce — domain çeşitliliği için); Phase 2 PR 3 ([#1103](https://github.com/selmanays/nodrat/pull/1103)) merged → main HEAD `8338249` |
| Bir sonraki adım | Phase 2 PR 4 review + merge → Phase 2 PR 5 (media), sonra PR 6 (clusters), sonra runtime-sensitive PR 7-8 (settings_admin, prompts_admin) |

---

## 14. Phase Retrospectives

Her phase kapanışında 5-10 satır eklenir. Format:

```
### Phase X — <başlık> (kapandı YYYY-MM-DD)
- **Ne iyi gitti:** ...
- **Ne yapılmazdı:** ...
- **Beklenmeyen:** ...
- **Sonraki faz için ders:** ...
- **PR'lar:** #X, #Y, #Z
```

### Phase 1 — Module/shared skeleton + import-linter (kapandı 2026-05-20)

- **Ne iyi gitti:** Boş iskelet + 12 import-linter contract + 2 yeni CI job (lint-imports + offline alembic-check) tek atomic PR'da teslim. CI 10/10 yeşil ilk koşumda; ihlal yok. 17 backend modülü + 10 shared sub + 16 frontend modül skeleton kuruldu. PR review feedback'i 0 düzeltme gerektirdi (Phase 0 dersleri uygulandı: format/auto-link/label sayısı önceden temiz).
- **Ne yapılmazdı:** Worktree branch'ini main'e geçirirken local `--delete-branch` gh komutunun fail etmesi (ana repo'da main checked out olduğu için). Etki yok — remote branch silindi, local stale branch manuel silindi. Yine de bir uyarı: paralel worktree senaryolarında `gh pr merge --delete-branch` her zaman remote'ta çalışır ama local cleanup ekstra adım gerektirir.
- **Beklenmeyen:** `import-linter>=2.1` install + ilk lint-imports koşumu hızlı (1m53s) — boş iskelet sayesinde graph parse trivial. Phase 8'de strict scope büyüdükçe süre artacak (boş değil binlerce import edilen kod).
- **Sonraki faz için ders:** Boş iskelet üzerine modül-by-modül taşıma yapısı Phase 2'ye temiz başlangıç verir. Her low-risk modül için 1 PR + atomic delete-old-paths disiplini ([[no-internal-backcompat-aliases]]) test edilecek. İlk modül `style_profiles` (449 + 197 + 68 satır, low-coupling — sadece kendi route + task + util).
- **PR'lar:** [#1100](https://github.com/selmanays/nodrat/pull/1100) (merged commit `5a67e06`).

### Phase 0 — Documentation + boundary decision (kapandı 2026-05-20)

- **Ne iyi gitti:** 16 kullanıcı kararı tek oturumda entegre edildi; 11 wiki sayfası + 3 docs/engineering belgesi + 19 GitHub issue + milestone tek atomic PR'da teslim. Hiçbir uygulama kodu dokunulmadı.
- **Ne yapılmazdı:** PR description'da HEREDOC backslash-escape (`\``) artefakt'leri ilk açılışta düzeltilmemişti; review v1'de temizlendi. PR title'ında `PR #1` yazılıyordu; GitHub auto-link mevcut PR #1'e linkliyordu; review v1'de düzeltildi.
- **Beklenmeyen:** YAML frontmatter flow-style (`tags: ["x", "y"]`) vs block-style (`tags:\n  - x`) ayrımı kullanıcı tarafından raw render kalitesi sebebiyle istendi; v2'de PyYAML ile re-dump yapıldı. Bazı kullanıcı görüntüleme katmanları (cache/PR diff render) raw'dan farklı görünüm verebiliyor — kanıt için raw URL ve `wc -l` çıktıları paylaşılması gerekti.
- **Sonraki faz için ders:** Refactor PR'larında "atomic" niyetiyle başlasak da review feedback'i atom-altı düzeltme gerektirebilir; **format/cosmetic review** ile **content review** ayrı çıkarımlar getirebilir. PR description'ı ilk açılışta `--body-file` ile temiz vermek HEREDOC escape sorununu önler. GitHub auto-link tehlikesini (`#N` küçük sayılar, `PR #N`, `milestone #N`) ilk yazımdan itibaren markdown link veya tam URL ile geçmek standart.
- **PR'lar:** [#1099](https://github.com/selmanays/nodrat/pull/1099) (merged commit `72b68c3`). 3 commit: `dd971e9` initial, `7c3c9ae` review v1 (auto-link + INDEX.md + label count), `21c80f0` review v2 (block-style YAML).

---

## 15. Cross-references

### docs/
- [INDEX.md](../../INDEX.md) — kanonik doküman indeksi
- [docs/engineering/modular-monolith-architecture.md](../../docs/engineering/modular-monolith-architecture.md)
- [docs/engineering/refactor-playbook.md](../../docs/engineering/refactor-playbook.md)
- [docs/engineering/testing-strategy.md](../../docs/engineering/testing-strategy.md)
- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) (mevcut, ileride §11 güncelleme)

### wiki/
- [[modular-monolith-boundary]] — locked
- [[import-direction-rules]] — locked
- [[models-flat-until-conditions]] — locked
- [[god-file-facade-first]] — locked
- [[admin-route-domain-ownership]] — locked
- [[no-internal-backcompat-aliases]] — locked
- [[refactor-anti-patterns-do-not-do]] — topic
- [[refactor-pr-checklist]] — topic
- [[new-feature-module-checklist]] — topic
- [[agent-worktree-playbook]] — topic

### GitHub
- Milestone: https://github.com/selmanays/nodrat/milestone/18
- Phase + tracking issue'ları §8'de listelenir.
