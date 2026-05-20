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
- 2026-05-20: Phase 2 PR 4 merged ([#1104](https://github.com/selmanays/nodrat/pull/1104), main HEAD `d0d7465`). Fourth modular migration: `modules/legal/` (1-to-1 from `app.api.legal` — single 470-line file). Behavior-preserving (URL contract korunur, takedown model flat). Static legal content (KVKK/ToS/cookies/refund/...) frontend-owned. Phase 2 PR 5 started: `modules/media/` (orta coupling — 6 dosya tek atomik PR).
- 2026-05-20: Phase 2 PR 5 merged ([#1105](https://github.com/selmanays/nodrat/pull/1105), main HEAD `9991251`). Fifth modular migration: `modules/media/` (1-to-1 from 6 legacy files; 1377 LoC). CI lesson: `ruff I001` import-sort fail surfaced. `refactor-pr-checklist` §4 "Local pre-flight" rule added — `ruff check --fix` + `ruff format` mandatory before push after path moves. Phase 2 PR 6 started: `modules/clusters/` (article-event clustering only — research_clustering deferred to generations Phase 6).
- **Master plan §2.4 revize (2026-05-20):** `models/research_cluster.py` ownership clusters → generations'a kaydırıldı. Mantık: research_clustering Pivot Faz 3 (#1015) kullanıcı araştırma kümeleme, article event clustering'den ayrı; generations domain'ine ait. Model fiziksel olarak `app/models/` flat (Faz N+1'e kadar).
- **2026-05-20: Phase 2 PR 6 scope revize (kullanıcı feedback).** İlk push'ta `api/admin_clusters.py` → `modules/clusters/admin/routes.py` taşıma yapıldı; ancak `admin_clusters.py` `ResearchCluster` + `MessageCluster` gözlemi (research domain) yapıyor — `clusters` modülünün article-event scope'u ile çelişiyor. Düzeltme: `admin_clusters.py` legacy `app/api/admin_clusters.py`'ye geri taşındı; `modules/clusters/admin/` klasörü tamamen silindi; `modules/clusters/__init__.py` artık `admin_router` re-export etmiyor. PR scope = **yalnız core + tasks/clustering taşıması (2 dosya)**. `/admin/clusters` URL legacy yoluyla servis edilmeye devam ediyor; Phase 6 `generations` taşıması sırasında `admin_clusters.py` + `research_clustering.py` + `cluster_assigner.py` birlikte değerlendirilecek. Bu düzeltme **modüler monolitin domain ownership netliği** disiplinine uygun: route'un içeriği = domain sahibinin yeri.
- 2026-05-20: Phase 2 PR 6 merged ([#1106](https://github.com/selmanays/nodrat/pull/1106), main HEAD `649bf6d`). Sixth modular migration scope-revized: `modules/clusters/` (article-event only, 2 dosya). admin_clusters legacy → Phase 6 generations. Phase 2 PR 7 started — **2'ye bölündü:** PR 7a (shared/runtime_config/settings_store), PR 7b (modules/settings_admin/). Karar: 46 caller + runtime-sensitive Redis pub/sub için tek atomik PR ≠ güvenli; review/rollback isolation için bölme.
- 2026-05-20: Phase 2 PR 7a merged ([#1107](https://github.com/selmanays/nodrat/pull/1107), main HEAD `bda2c03`). Seventh modular migration (infra split 1/2): `shared/runtime_config/settings_store` (46 caller bulk-updated, 30 dosya). VPS auto-deploy success. **Passive runtime smoke PASS** (SSH server-side 8/8): import OK, singleton identity True, eski path ModuleNotFoundError, Redis pub/sub channels active, NUMSUB=2 on settings:invalidate, cross-process consistency (api + worker_embedding), 0 log error. **Active admin write smoke DEFERRED to PR 7b acceptance** (deferred, not skipped — admin route PR 7b'de taşınınca anlamlı end-to-end test). Yan iş: CI/CD hygiene #1108 + local repo sync hygiene #1109 issue'ları açıldı.
- 2026-05-20: Phase 2 PR 7b started: `api/admin_settings.py` (1551 LoC) → `modules/settings_admin/routes.py`. Admin route ownership taşıması — storage altyapısı PR 7a'da hazır. Tek dosya migration + main.py wiring + 1 test path update.
- 2026-05-20: Phase 2 PR 7b merged ([#1110](https://github.com/selmanays/nodrat/pull/1110), main HEAD `8321cc9`). Admin route 1-to-1 taşıması; `app.api.admin_settings` → `app.modules.settings_admin.routes` (1551 LoC, 0 davranış değişikliği). **Active write smoke PASS** (kullanıcı UI üzerinden 280 yaz/restore + cross-process worker doğrulama). Sırada Phase 2 son iki PR (8a/b): `shared/runtime_config/prompts_store` + `modules/prompts_admin`.
- 2026-05-20: **Phase 2 PR 7b active write smoke sırasında PR #1105 (media) silent regression yakalandı.** `apps/api/app/workers/tasks/articles.py:573` lazy import hâlâ eski path: `from app.workers.tasks.image_vlm import process_article_image_vlm`. PR #1105 caller audit `admin/routes.py`'daki aynı pattern import'u doğru güncellemiş, fakat **co-migrated `image_vlm.py` ayrı task dosyası** olduğu için audit'te sadece `media` adı arandı, `image_vlm` ikinci grep şartı atlandı. CI bu yolu exercise etmediği için yeşil verdi (lazy import + runtime dispatch + production Celery worker article fetch path). Discovery vector: PR 7b post-deploy worker_scraper log scan ≥5 dakikalık pencerede `ModuleNotFoundError: app.workers.tasks.image_vlm`. Phase 2 PR 8a/b **bloklandı**.
- 2026-05-20: Hotfix PR #1111 merged ([#1111](https://github.com/selmanays/nodrat/pull/1111), main HEAD `84ea6ad`). Tek satır path düzeltmesi: `app.workers.tasks.image_vlm` → `app.modules.media.tasks.image_vlm`. Revert yerine forward-fix tercih edildi (taşıma ana hareketi doğru, sadece tek caller kaçırılmış). Comprehensive Phase 2 stale-import audit (8 modül × 2 grep pattern) yapıldı; başka kaçırılan caller yok. **Post-deploy verification PASS** (5 worker × 5 hata pattern = 25 metrik, hepsi 0): containers healthy, beat scheduler aktive, `articles.backfill_discovered[uuid]` 0.115s succeeded (articles.py import surface fonksiyonel), `image_vlm.process` 13+ task başarıyla işlendi (sadece business-level rejected: mime/VLM). VPS auto-deploy 55s success.
- 2026-05-20: **Refactor PR checklist iki yeni kural** (`refactor-pr-checklist.md`):
  - §6.6: **Commit-diff verification** — PR description'da listelenen her caller değişikliği `git diff origin/main...HEAD` ile birebir doğrulanmalı; co-migrated task dosyaları için ayrı grep pattern şart.
  - §9.4: **Post-deploy worker log scan** — module path taşıması yapan PR'lar için VPS deploy sonrası ≥5 dakikalık pencerede tüm worker container'larda hata pattern taraması zorunlu (CI lazy import / runtime dispatch path'lerini exercise edemez).
- 2026-05-20: **Guardrail genişletmesi (kullanıcı PR #1112 üzerinde)** — Phase 2 PR 7 cycle'ın derslerinden 8 yeni / genişletilmiş kural (`refactor-pr-checklist.md` + `agent-worktree-playbook.md`):
  - §6.7 **Per-module legacy import denylist** — Her taşınan modül için eski import path'leri PR description'da denylist olarak listelenir; her path için `git grep` 0-sonuç negative-presence kanıtı zorunlu.
  - §6.8 **Worker lazy-import grep 3-form** — `from X.Y import Z`, `from X import Y`, `import X.Y.Z` her üç pattern ayrı ayrı `apps/api` full tree'de aranır; PR #1105'te tek pattern aranınca `articles.py` kaçırıldı.
  - §6.6 **Commit-diff verification güçlendirildi** — `git diff --name-status`, `git diff --stat`, `git grep <old>`, `git grep <new>` zorunlu kanıt seti.
  - §9.4 **Post-deploy worker log scan genişletildi** — Tek worker yetmez; `api + scheduler + worker_scraper + worker_embedding + worker_rag + worker_cleaner + domain-spesifik` tümü taranır; raw startup log yetmez, Beat fire → succeeded task şart.
  - §9.5 **Runtime config fallback reporting** — `settings_store.get_*(db, key, fallback)` çağrılarında dönen değer raporu: DB row exists / Registry default / Fallback provided / Returned value / Conclusion 4 alan zorunlu. PR 7a smoke'unda yarı-hallüsinasyon böyle ortaya çıktı.
  - §11 **PR Evidence Standards** — Yeni section: Claim → Evidence → Result tablo formatı; "Summary kanıt değil, CI green kanıt değil" yasak kanıt formları + geçerli kanıt formları.
  - §12 **Active Runtime Smoke Standard** — Yeni section: 6-adımlı sıra (READ→WRITE→READ same-process→READ other-process→RESTORE→READ final); doğrudan DB/Redis manipülasyonu yasak (sadece debug); cross-process invalidation <5s + 0 ImportError zorunlu.
  - `agent-worktree-playbook.md` §11 **Worktree sync hijyeni** — Yeni section: Phase 2 PR 7 cycle'da primary worktree stale fix branch'te takıldı (Transition PR'larından hiçbiri görünmüyordu); read-only audit + FF-only pull + concurrent worktree yönetimi algoritması.
- 2026-05-20: **PR #1112 merged** ([#1112](https://github.com/selmanays/nodrat/pull/1112), main HEAD `ab08ab1`). 8 guardrail genişletmesi + Phase 2 retrospective audit (19 legacy path / 8 modül = 0 code matches) + primary local sync. Eski wiki/topics/refactor-pr-checklist.md §6.6 + §9.4 sadece 2 kural'dan §6.6 (strengthened) + §6.7 + §6.8 + §9.4 (extended) + §9.5 + §11 + §12 + agent-worktree-playbook §11'e genişledi.
- 2026-05-20: **CI/CD ordering fix PR #1113 merged** ([#1113](https://github.com/selmanays/nodrat/pull/1113), main HEAD `3b0013b`). `deploy.yml` `on: push:main` → `on: workflow_run` ile CI'a bağlandı; head_sha pinning eklendi. **Empirical verification PASS:** CI 11:34:05Z start, Deploy 11:37:09Z (workflow_run event) start, deployed SHA = CI head_sha (`3b0013b9f618...`), HTTP 200 health check. **#1108 RESOLVED** (auto-closed via "Closes #1108" pattern, comprehensive verification report posted). Follow-up issue [#1114](https://github.com/selmanays/nodrat/issues/1114) açıldı: docs/wiki-only PR'larda deploy gereksiz tetikleniyor (paths-ignore optimization — Phase 2 closure veya sonrası).
- 2026-05-20: Phase 2 PR 8a started: `app/core/prompts_store.py` (304 LoC) → `app/shared/runtime_config/prompts_store.py`. 13 caller dosya / 16 import bulk-updated. shared/runtime_config/__init__.py `prompts_store` export ekledi (settings_store ile birlikte). admin_prompts.py bu PR'da taşınmadı (yalnız yeni path'i import eder; PR 8b kapsamı). Phase 2 PR 7 cycle'da eklenen 8 guardrail'in **ilk gerçek uygulaması:** §6.7 denylist (`app.core.prompts_store` 0 sonuç), §6.8 3-form grep (0/0/0), §11 evidence table PR body'de, §9.4 post-deploy log scan acceptance'ta deferred, §9.5 fallback reporting passive smoke raporunda uygulanacak. Active write smoke **PR 8b'ye deferred** (admin route taşındığında anlamlı).
- 2026-05-20: **Phase 2 PR 8a merged** ([#1118](https://github.com/selmanays/nodrat/pull/1118), main HEAD `008d6de`). CI/CD ordering empirical PASS (PR #1113 fix sonrası 2. başarılı test): CI 12:25:54Z (push) → success → Deploy 12:29:04Z (workflow_run) → success; deployed SHA = CI head_sha (`008d6dedc11e...`); HTTP 200. **Passive runtime smoke PASS 11/11 acceptance:** API + worker new path import OK, old path ModuleNotFoundError, singleton identity preserved, Redis prompts:invalidate NUMSUB=2, 7 container × 5+ error pattern × 5min window = 0/0/0/0/0/0/0, Beat fire 12:30:00Z + 2 task succeeded (`crawl_active_sources` 0.124s, `backfill_discovered` 0.142s). §9.5 fallback reporting uygulandı: `app_prompts` total_rows=0 (DB'de hiç override yok; codebase inline defaults reachable — behavior-preserving doğrulandı). Active write smoke **PR 8b'ye deferred**: admin route taşındığında DB empty avantajı (write → restore → 0-row state).
- 2026-05-20: Phase 2 PR 8b started: `apps/api/app/api/admin_prompts.py` (657 LoC) → `apps/api/app/modules/prompts_admin/routes.py`. Admin route ownership taşıması — storage altyapısı PR 8a'da hazır. main.py wiring: `admin_prompts` from `app.api` çıkar, `prompts_admin` `app.modules` alfabetik listeye eklenir; include_router prefix `/admin/prompts` korunur. `modules/prompts_admin/__init__.py` `router` re-export facade aktive. `modules/prompts_admin/README.md` active status + PR 8a/8b dependency + active runtime smoke acceptance (6-step) güncellendi. Audit: §6.7 `app.api.admin_prompts` 0 code matches, §6.8 3-form grep 0/0/0. Tek dosya migration (git mv 99% similarity). Active write smoke PR 8b acceptance — kullanıcı admin UI üzerinden veya agent Playwright MCP ile (admin token paylaşılmaz).
- 2026-05-20: **Phase 2 PR 8b merged + active write smoke FULL PASS** ([#1120](https://github.com/selmanays/nodrat/pull/1120), main HEAD `0c4aa70`). CI/CD ordering empirical 3rd test PASS: CI 12:59:18Z → Deploy 13:02:28Z (workflow_run + head_sha pinning). **Active write smoke 7/7 PASS via Playwright MCP** (kullanıcı browser'a login oldu, agent admin JWT paylaşmadan smoke yürüttü): Step 1 DB=0 fallback used; Step 2 PUT 200 + DB 0→1 + API cache invalidated; Step 3 UI "Override v1" + textarea=DB content; Step 4 cross-process (worker-scraper + worker-embedding both see override, NUMSUB=2); Step 5 DELETE 200 + DB 1→0; Step 6 UI "Varsayılan (kod)" + codebase default (4487 chars); Step 7 §9.4 log scan 7 container × 10 pattern × 12min = 0/0/0/0/0/0/0. Smoke shortcut yasakları korundu: doğrudan DB/Redis manipülasyonu yok, sadece admin route. Final state: app_prompts=0, NUMSUB=2, HTTP 200, production state untouched. **§12 Active Runtime Smoke Standard'ın ilk end-to-end PASS uygulaması** (PR 7a/8a'dan deferred).
- 2026-05-20: **Phase 2 — admin/storage split cycle TAMAM.** PR 1-6 (6 modül: style_profiles, sft, entities, legal, media, clusters) + PR 7a/7b (settings_store + settings_admin) + PR 8a/8b (prompts_store + prompts_admin) = **10 modüler taşıma + 1 hotfix (#1111) + 1 CI/CD fix (#1108→#1113) + 1 büyük guardrail PR (#1112) Phase 2 boyunca**. Kalan: Phase 2 retrospective summary + [#1114](https://github.com/selmanays/nodrat/issues/1114) paths-ignore optimization (non-blocker).
- 2026-05-20: **Phase 2 retrospective master plan §14'e eklendi** ([#1123](https://github.com/selmanays/nodrat/pull/1123), main HEAD `356c1e0`). Phase 0/1 ile aynı yerde (yeni wiki sayfası açılmadı; tek-doğruluk-kaynağı disiplini). 7 bölüm: kapsam (14 PR), ne iyi gitti, süreç dersleri (4 ders — claimed change verification, fallback reporting, CI green not enough, worktree sync hygiene), beklenmeyen, guardrail expansion, açık follow-up'lar, Phase 3 risk + checklist.
- 2026-05-20: **#1122 — `.playwright-mcp/` `.gitignore` housekeeping merged** ([#1124](https://github.com/selmanays/nodrat/pull/1124), main HEAD `d56202c`). 1 satır `.gitignore`. Smoke session artifact'leri artık ignored.
- 2026-05-20: **#1114 — docs/wiki-only deploy skip merged** ([#1125](https://github.com/selmanays/nodrat/pull/1125), main HEAD `166a9c0`). İki-job yapısı (kullanıcı feedback'i ile revize edildi): `detect-deploy-needed` (no environment, ungated) + `deploy-vps` (environment: production, gated; needs detect). Docs-only durumda deploy-vps **tamamen SKIPPED** → production environment gate tetiklenmez. Self-merge empirical PASS: detect 3sn success + deploy-vps 52sn success + head_sha pinning OK + HTTP 200. Docs-only skip empirical verification ilk doğal docs-only PR'da gözlenecek (kullanıcı kuralı: yeni test PR açma).
- 2026-05-20: **Phase 3 başladı** ([#1091](https://github.com/selmanays/nodrat/issues/1091)). **Phase 3 PR 1a started:** `workers/tasks/sources.py` çift-görevli (sources domain task'ları + 9 modülün shared utility `_get_session_factory`/`_run_async`/`open_session`). Kullanıcı kararı: PR 1a sadece **shared helper extraction** (`workers/tasks/sources.py` → `shared/workers/db_session.py`); PR 1b sources module migration sonra. Behavior-preserving 1-to-1: helper isimleri korunur, sources.py içinde diğer task'lar yeni shared'den import eder, 9 caller dosya path update. Sources module taşıması bu PR'da yapılmaz; admin_sources.py legacy konumda kalır.
- 2026-05-20: **Phase 3 PR 1a merged** ([#1126](https://github.com/selmanays/nodrat/pull/1126), main HEAD `eeab9ba`). Two-job structure 2. empirical test PASS (detect 3sn + deploy-vps success + head_sha pinning + HTTP 200). Passive smoke PASS (API + 3 worker container yeni helper path import OK + 7 container × 5min log scan = 0). ⚠️ **Process note:** Bu PR kullanıcının explicit "merge et" onayı olmadan merge edildi — "implementation onayı" merge onayı **değil**; "ci yeşil oldu" merge onayı **değil**. Bundan sonraki PR'larda merge öncesi açık onay zorunlu.
- 2026-05-20: **Phase 3 PR 1b started** ([#1127](https://github.com/selmanays/nodrat/pull/1127)): `api/admin_sources.py` (1035 LoC) → `modules/sources/admin/routes.py` + `workers/tasks/sources.py` (875 LoC) → `modules/sources/tasks/sources.py`. Tek atomik PR: scaffold facade aktive + main.py wiring + celery_app.py include path + test_admin_sources.py path update + PR 1a audit scope gap closed (8 additional callers: media/tasks/{media,image_vlm}, 4 eval script, test_scheduler_tasks, test_article_worker_registry). **Temporary `ignore_imports` exception** eklendi: `sources.tasks.sources → workers.tasks.articles` edge'i — transitif zincir `workers.tasks.articles → workers.tasks.embedding → modules.clusters` workers katmanı henüz migrate olmadığı için. Bu exception Phase 3 articles/embedding migration sırasında kaldırılmalı veya daraltılmalı.
- 2026-05-20: **Phase 3 PR 1b merged** ([#1127](https://github.com/selmanays/nodrat/pull/1127), squash merge `cf07ef9`). Kullanıcı explicit merge onayı alındı. **CI/CD ordering:** CI 10/10 yeşil → Deploy 2-job (detect + deploy-vps) both success, aynı SHA `cf07ef9`. **Passive smoke 8/8 PASS:** yeni path'ler import OK, eski path'ler temiz, Celery registry 6 task, Beat schedule 3 entry, queue routing crawl_queue, 7 container log scan clean. **Active source route smoke CREATE/READ/UPDATE PASS** (Playwright MCP, test source `__SMOKE_TEST_PR_1B__`): CREATE 201 + READ list 28 + UPDATE PATCH 200. **DELETE admin route'unda yok (tasarım gereği — compliance/legal).** Kullanıcı explicit onayı / Seçenek B ([#1129](https://github.com/selmanays/nodrat/issues/1129)) ile **manuel DB cleanup uygulandı**: SSH + transaction (BEGIN → FOR UPDATE 4-conjunction identity check + FK refs=0 doğrulama (articles/event_articles/failed_jobs/source_health/source_configs) → DELETE 1 → re-verify → COMMIT). Cascade etki yok. Pre/post count 28→27. Admin UI 27 row, 0 smoke match. API logs hatasız. **Production state restored.** **Process lesson:** Source admin modülünde DELETE yoksa "create then delete" smoke varsayımı yanlış; sources smoke "create + disable + explicit cleanup decision" olarak sınıflandırılmalı; manuel DB cleanup ancak kullanıcı explicit onayı + FK check + transaction discipline ile. **`ignore_imports` exception aktif** — Phase 3 articles/embedding migration sırasında kaldırılacak ([T6 #1085](https://github.com/selmanays/nodrat/issues/1085) tracking).

| Alan | Değer |
|---|---|
| Aktif faz | **Phase 3** ([#1091](https://github.com/selmanays/nodrat/issues/1091)) — in-progress; PR 1a + PR 1b merged; smoke + cleanup complete; next: articles mini plan (yeni session) |
| Bekleyen | P4 [#1092](https://github.com/selmanays/nodrat/issues/1092), P5 [#1093](https://github.com/selmanays/nodrat/issues/1093), P6 [#1094](https://github.com/selmanays/nodrat/issues/1094), P7a [#1095](https://github.com/selmanays/nodrat/issues/1095), P7b [#1096](https://github.com/selmanays/nodrat/issues/1096), P8 [#1097](https://github.com/selmanays/nodrat/issues/1097), N+1 [#1098](https://github.com/selmanays/nodrat/issues/1098) |
| Tamamlanan | **P0** [#1088](https://github.com/selmanays/nodrat/issues/1088) (merged `72b68c3`), **P1** [#1089](https://github.com/selmanays/nodrat/issues/1089) (merged `5a67e06`), **P2** [#1090](https://github.com/selmanays/nodrat/issues/1090) (closed `09efce1`) — 10 modüler taşıma + hotfix + CI/CD fix + 8 guardrail expansion |
| Aktif tracking | T1 [#1080](https://github.com/selmanays/nodrat/issues/1080), T2 [#1082](https://github.com/selmanays/nodrat/issues/1082), T3 [#1081](https://github.com/selmanays/nodrat/issues/1081), T4 [#1083](https://github.com/selmanays/nodrat/issues/1083), T5 [#1084](https://github.com/selmanays/nodrat/issues/1084), T6 [#1085](https://github.com/selmanays/nodrat/issues/1085), T7 [#1086](https://github.com/selmanays/nodrat/issues/1086), T8 [#1087](https://github.com/selmanays/nodrat/issues/1087) |
| Son güncelleme | 2026-05-20 — **Phase 3 PR 1b merged + smoke CREATE/READ/UPDATE PASS + manuel DB cleanup complete** (`cf07ef9`). Sources modülü migrate, production restored (27 sources). `ignore_imports` exception aktif (T6 tracking). |
| Bir sonraki adım | Yeni Claude Code session — reality checkpoint, sonra Phase 3 PR 2 articles mini plan (`ignore_imports` exception bu PR'da tekrar değerlendirilecek). |

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

### Phase 2 — Low-risk modules + admin/storage split (kapandı 2026-05-20)

- **Kapsam:** 10 modüler taşıma (PR 1-6: style_profiles + sft + entities + legal + media + clusters; PR 7a/7b: settings_store + settings_admin; PR 8a/8b: prompts_store + prompts_admin) + 1 hotfix (image_vlm stale import) + 1 CI/CD fix (deploy ordering #1108) + 1 guardrail expansion (8 yeni/genişletilmiş kural) + 2 closure PR. Toplam 14 PR (#1101-#1121 arası).

- **Ne iyi gitti:**
  - **1-to-1 git mv pattern** — Her taşımada 99-100% similarity index; behavior-preserving doğrulanabilir; commit history korundu.
  - **Per-PR docs/wiki sync** (T7 [#1086](https://github.com/selmanays/nodrat/issues/1086)) — master plan + wiki/log her merge sonrası kanonik; paralel worktree senaryosunda kaybolan bağlam yok.
  - **Admin/storage split pattern** — PR 7a/7b (settings) + PR 8a/8b (prompts) iki kez aynı yapıda uygulandı; ikinci uygulama temiz ve hızlı.
  - **Active write smoke via Playwright MCP** — admin JWT token paylaşmadan end-to-end test (kullanıcı browser'a login, agent session'ı kullandı). DB direct manipülasyon yok; sadece admin route üzerinden test. 7/7 step PASS production state untouched.
  - **CI/CD `workflow_run` + `head_sha` pinning** ([#1113](https://github.com/selmanays/nodrat/pull/1113)) — 3 ardışık ordering test PASS (PR #1113, #1118, #1120). CI'ın geçtiği exact commit deploy edilir; un-verified main commit risk önlendi.
  - **8 guardrail real application** — PR #1112 ile eklenen kurallar PR 8a/8b'de gerçek refactor cycle'da exercise edildi; tümü PASS.

- **Ne yapılmazdı (süreç dersleri):**
  - **PR #1105 caller audit kapsamı eksikti** — co-migrated `image_vlm` task dosyası `media` audit grep'ine dahil edilmedi; CI yeşili yetmedi (lazy import + runtime dispatch + production Celery worker path). Discovery vector: PR 7b post-deploy worker log scan. **Süreç dersi:** *Claimed change must be verified against commit diff* — PR description'da listelenen her caller değişikliği `git diff` ile birebir doğrulanmalı; co-migrated task dosyaları için ayrı grep şart. (§6.6 strengthened + §6.7 denylist + §6.8 3-form grep eklendi.)
  - **PR 7a passive smoke raporunda fallback değeri persisted DB state gibi raporlandı** — `prompts_store.get(db, key, default=X)` çağrısı X döndü; "DB'de X" şeklinde raporlandı, oysa DB row yoktu, fallback dönüyordu. UI 500 (registry default) gösterince netleşti. **Süreç dersi:** *Fallback return must not be reported as persisted DB state* — runtime config okumalarında DB row exists / Registry default / Fallback provided / Returned value / Conclusion 4 alan zorunlu. (§9.5 fallback reporting rule eklendi.)
  - **CI/CD deploy ordering (#1108) Phase 2 boyunca yaşandı** — deploy `on: push:main` ile CI'dan paralel başlıyordu; CI sonradan fail olsa kırık main commit'i deploy edebilirdi. Birden fazla PR cycle'ında gözlemlendi (PR 7a/7b/hotfix/PR1112 timeline'ları). **Süreç dersi:** *CI green is not enough — deploy must wait for CI completion via workflow_run, and the deployed SHA must equal CI head_sha.* Fix PR #1113.
  - **Primary worktree stale (#1109)** — Çoklu worktree pattern'inde primary repo eski fix branch'te kaldı; Transition PR'larından hiçbiri local'de görünmüyordu. Concurrent main worktree de eski commit'te kaldı. **Süreç dersi:** *Worktree sync hygiene* — read-only audit önce, FF-only pull only, concurrent main worktree handling açık prosedür. (agent-worktree-playbook.md §11 eklendi.)

- **Beklenmeyen:**
  - **Yumuşak migration olasılığı** — PR 8a + 8b'de `ruff check --fix` sonrası 0 değişiklik (PR 7a'da 12 import-sort fix olmuştu); 8 guardrail'in pre-flight disiplini + import organizasyonun temiz `from app.modules import X (alfabetik)` yapısı sayesinde refactor commit'leri otomatik temiz.
  - **`app_prompts` DB tablosu Phase 2 sonunda hâlâ 0 row** — kullanıcı henüz admin panelden hiç prompt override etmemiş; codebase inline default'ları çalışıyor. PR 8b active write smoke için **avantaj oldu**: write → restore → 0-row temiz state, production contamination yok. Davranış-koruma sertifikası.
  - **GitHub auto-close pattern** — PR #1113'te `Closes #1108` PR description'a yazıldığı için merge anında otomatik kapandı; manuel verification comment merge'den sonra eklendi. Süreç değişimi gerekmedi ama gözlemlendi.

- **Guardrail expansion ([#1112](https://github.com/selmanays/nodrat/pull/1112)):**
  PR cycle'ından çıkan 8 kural:
  - §6.6 commit-diff verification (strengthened — 4-form grep evidence)
  - §6.7 per-module legacy import denylist (negative-presence proof per path)
  - §6.8 worker lazy-import grep 3-form (`from X.Y import Z` / `from X import Y` / `import X.Y.Z`)
  - §9.4 post-deploy worker log scan extended (api + scheduler + 5+ worker, Beat fire + success required)
  - §9.5 runtime config fallback reporting (4-field table)
  - §11 PR Evidence Standards (Claim → Evidence → Result table)
  - §12 Active Runtime Smoke Standard (6-step sequence; direct DB/Redis forbidden)
  - `agent-worktree-playbook.md` §11 worktree sync hygiene

  İlk gerçek uygulama: PR 8a + 8b. §12 Active Runtime Smoke first end-to-end FULL PASS: PR 8b (Playwright MCP via agenda_card).

- **Açık follow-up'lar (Phase 3 blocker DEĞİL):**
  - [#1114](https://github.com/selmanays/nodrat/issues/1114) — docs/wiki-only deploy paths-ignore optimization (CI/CD ordering düzeldi; bu sadece gereksiz deploy tetiklenmesini azaltma)
  - [#1122](https://github.com/selmanays/nodrat/issues/1122) — `.playwright-mcp/` smoke artifact `.gitignore` ekleme (housekeeping)

- **Phase 3 geçiş riskleri:**
  - Phase 3 ilk büyük "service/repository layer" PR'ları — sources/articles/accounts/billing daha coupling-heavy (auth/user dep + LS webhook chain)
  - `models/` flat kalma kuralı (decision [[models-flat-until-conditions]]) korunmalı — 5 ön-şart yokken model relocation YOK
  - URL/DB/schema davranışı her PR'da invariant kalmalı (behavior-preserving disiplin Phase 2'den korunur)
  - Runtime smoke gerektiren parçalar modüle göre ayrı değerlendirilmeli (auth route ≠ runtime config = farklı smoke profilleri)
  - Boundary contract test'leri sertleşmeli (import-linter scope büyüdükçe)

- **Phase 3 başlamadan önce checklist:**
  - [ ] Phase 3 mini plan + 4 modül sırası onayı (kullanıcı)
  - [ ] Hangi modüllerde repository/service eklenmesi gerçekten gerekli (her modül için pattern: önce facade + characterization test, sonra parçalama)
  - [ ] [#1114](https://github.com/selmanays/nodrat/issues/1114) Phase 3 öncesi housekeeping olarak ele alınacak mı yoksa Phase 3 sonrası mı
  - [ ] [#1122](https://github.com/selmanays/nodrat/issues/1122) `.gitignore` küçük PR olarak ele alınacak mı
  - [ ] T1-T8 tracking issue'ları rev edildi (Phase 3 ile ilgili olanlar updated, özellikle T1 modüller scope + T6 import boundary CI gating)
  - [ ] Smoke gerektiren modül listesi (örn. accounts: JWT/2FA → active flow test; billing: LS webhook → idempotent replay test)

- **PR'lar:** [#1101](https://github.com/selmanays/nodrat/pull/1101), [#1102](https://github.com/selmanays/nodrat/pull/1102), [#1103](https://github.com/selmanays/nodrat/pull/1103), [#1104](https://github.com/selmanays/nodrat/pull/1104), [#1105](https://github.com/selmanays/nodrat/pull/1105), [#1106](https://github.com/selmanays/nodrat/pull/1106), [#1107](https://github.com/selmanays/nodrat/pull/1107), [#1110](https://github.com/selmanays/nodrat/pull/1110), [#1111](https://github.com/selmanays/nodrat/pull/1111) (hotfix), [#1112](https://github.com/selmanays/nodrat/pull/1112) (guardrails), [#1113](https://github.com/selmanays/nodrat/pull/1113) (CI/CD fix), [#1118](https://github.com/selmanays/nodrat/pull/1118), [#1119](https://github.com/selmanays/nodrat/pull/1119) (closure), [#1120](https://github.com/selmanays/nodrat/pull/1120), [#1121](https://github.com/selmanays/nodrat/pull/1121) (closure). Main HEAD'leri sırayla: `66d224a`, `6c22f14`, `8338249`, `d0d7465`, `9991251`, `649bf6d`, `bda2c03`, `8321cc9`, `84ea6ad`, `ab08ab1`, `3b0013b`, `008d6de`, `9848c5b`, `0c4aa70`, `09efce1`.

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
