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
- 2026-05-20: **#1114 — docs/wiki-only deploy skip merged** ([#1125](https://github.com/selmanays/nodrat/pull/1125), main HEAD `166a9c0`). İki-job yapısı (kullanıcı feedback'i ile revize edildi): `detect-deploy-needed` (no environment, ungated) + `deploy-vps` (environment: production, gated; needs detect). Docs-only durumda deploy-vps **tamamen SKIPPED** → production environment gate tetiklenmez. Self-merge empirical PASS: detect 3sn success + deploy-vps 52sn success + head_sha pinning OK + HTTP 200. **Docs-only skip empirically VERIFIED on first natural docs-only PR (#1128, commit `e6e8ff5`):** deploy run [26176420798](https://github.com/selmanays/nodrat/actions/runs/26176420798) — workflow_run tetiklendi, `detect-deploy-needed` 3sn success, `deploy-vps` **SKIPPED** (production environment gate **NOT triggered**). Counter-test (code change, PR #1127 `cf07ef9`): deploy run [26173194332](https://github.com/selmanays/nodrat/actions/runs/26173194332) — detect success, deploy-vps **success** (deploy proceeded as designed). Two-job design end-to-end empirical PASS. **Doğru ifade (önceki yanlış formülasyon "deploy workflow hiç tetiklenmedi"):** "deploy workflow workflow_run ile tetiklendi; `detect-deploy-needed` job çalıştı; docs/wiki-only değişiklik olduğu için `deploy-vps` job skipped oldu — production environment gate tetiklenmedi."
- 2026-05-20: **Phase 3 başladı** ([#1091](https://github.com/selmanays/nodrat/issues/1091)). **Phase 3 PR 1a started:** `workers/tasks/sources.py` çift-görevli (sources domain task'ları + 9 modülün shared utility `_get_session_factory`/`_run_async`/`open_session`). Kullanıcı kararı: PR 1a sadece **shared helper extraction** (`workers/tasks/sources.py` → `shared/workers/db_session.py`); PR 1b sources module migration sonra. Behavior-preserving 1-to-1: helper isimleri korunur, sources.py içinde diğer task'lar yeni shared'den import eder, 9 caller dosya path update. Sources module taşıması bu PR'da yapılmaz; admin_sources.py legacy konumda kalır.
- 2026-05-20: **Phase 3 PR 1a merged** ([#1126](https://github.com/selmanays/nodrat/pull/1126), main HEAD `eeab9ba`). Two-job structure 2. empirical test PASS (detect 3sn + deploy-vps success + head_sha pinning + HTTP 200). Passive smoke PASS (API + 3 worker container yeni helper path import OK + 7 container × 5min log scan = 0). ⚠️ **Process note:** Bu PR kullanıcının explicit "merge et" onayı olmadan merge edildi — "implementation onayı" merge onayı **değil**; "ci yeşil oldu" merge onayı **değil**. Bundan sonraki PR'larda merge öncesi açık onay zorunlu.
- 2026-05-20: **Phase 3 PR 1b started** ([#1127](https://github.com/selmanays/nodrat/pull/1127)): `api/admin_sources.py` (1035 LoC) → `modules/sources/admin/routes.py` + `workers/tasks/sources.py` (875 LoC) → `modules/sources/tasks/sources.py`. Tek atomik PR: scaffold facade aktive + main.py wiring + celery_app.py include path + test_admin_sources.py path update + PR 1a audit scope gap closed (8 additional callers: media/tasks/{media,image_vlm}, 4 eval script, test_scheduler_tasks, test_article_worker_registry). **Temporary `ignore_imports` exception** eklendi: `sources.tasks.sources → workers.tasks.articles` edge'i — transitif zincir `workers.tasks.articles → workers.tasks.embedding → modules.clusters` workers katmanı henüz migrate olmadığı için. Bu exception Phase 3 articles/embedding migration sırasında kaldırılmalı veya daraltılmalı.
- 2026-05-20: **Phase 3 PR 1b merged** ([#1127](https://github.com/selmanays/nodrat/pull/1127), squash merge `cf07ef9`). Kullanıcı explicit merge onayı alındı. **CI/CD ordering:** CI 10/10 yeşil → Deploy 2-job (detect + deploy-vps) both success, aynı SHA `cf07ef9`. **Passive smoke 8/8 PASS:** yeni path'ler import OK, eski path'ler temiz, Celery registry 6 task, Beat schedule 3 entry, queue routing crawl_queue, 7 container log scan clean. **Active source route smoke CREATE/READ/UPDATE PASS** (Playwright MCP, test source `__SMOKE_TEST_PR_1B__`): CREATE 201 + READ list 28 + UPDATE PATCH 200. **DELETE admin route'unda yok (tasarım gereği — compliance/legal).** Kullanıcı explicit onayı / Seçenek B ([#1129](https://github.com/selmanays/nodrat/issues/1129)) ile **manuel DB cleanup uygulandı**: SSH + transaction (BEGIN → FOR UPDATE 4-conjunction identity check + FK refs=0 doğrulama (articles/event_articles/failed_jobs/source_health/source_configs) → DELETE 1 → re-verify → COMMIT). Cascade etki yok. Pre/post count 28→27. Admin UI 27 row, 0 smoke match. API logs hatasız. **Production state restored.** **Process lesson:** Source admin modülünde DELETE yoksa "create then delete" smoke varsayımı yanlış; sources smoke "create + disable + explicit cleanup decision" olarak sınıflandırılmalı; manuel DB cleanup ancak kullanıcı explicit onayı + FK check + transaction discipline ile. **`ignore_imports` exception aktif** — Phase 3 articles/embedding migration sırasında kaldırılacak ([T6 #1085](https://github.com/selmanays/nodrat/issues/1085) tracking).
- 2026-05-20: **Phase 3 PR 2a merged** ([#1130](https://github.com/selmanays/nodrat/pull/1130), squash merge `8a3fed0`). Sources → articles Celery dispatch decoupling. 2 site `sources/tasks/sources.py:514+528` ve `:841+858` lazy `from app.workers.tasks.articles import article_discover` + `article_discover.apply_async(args=[...])` → `celery_app.send_task("tasks.articles.discover", args=[...])` string-bound dispatch. `pyproject.toml:232-234` `ignore_imports = ["sources → workers.tasks.articles"]` 3-satırlık block tamamen silindi. **import-linter 12/12 KEPT muafiyetsiz.** CI 10/10, deploy 2m47s, two-job `skip_deploy=false` (code change). **Smoke:** passive PASS (registry + routing + Beat unchanged + sources.py runtime AST `chunk_article identifier = 0, send_task sites = 2`), 0/0/0/0/0/0/0 log scan, **natural fire OBSERVED 17:30 UTC** (20+ `tasks.articles.discover[uuid]` task dispatch + succeeded ~0.04s, hepsi `status: 'duplicate'` — production state untouched). Sources kernel'i artık Python seviyesinde articles modülünü hiç bilmiyor. Kullanıcı kararı: PR 2b (admin + tasks taşıması) ayrı PR, PR 2a smoke PASS olmadan başlanmayacak.
- 2026-05-20: **Phase 3 PR 2b merged** ([#1131](https://github.com/selmanays/nodrat/pull/1131), squash merge `ed669ed`). modules/articles aktive: `api/admin_articles.py` (390 LoC) → `modules/articles/admin/routes.py` (git mv 99%) + `workers/tasks/articles.py` (959 LoC) → `modules/articles/tasks/articles.py` (git mv 98% — embedding decoupling 2 site %2 değişim). Facade dosyaları + main.py wiring + celery_app.py include path + 20 satır external caller path update (production 4 + test 16). **⚠️ Boundary fix:** Pre-flight'ta import-linter "articles must not import upper layers" BROKEN tespit edildi — transitif chain `modules.articles → workers.tasks.embedding → modules.clusters`. Mini plan analizinde gözden kaçırıldı (PR 1b sources muafiyetinin birebir aynı sebebi). **Kullanıcı onayıyla A1 deseni uygulandı:** 2 lazy embedding import silindi + `celery_app.send_task("tasks.embedding.chunk_article", …)` string-bound dispatch (Site 1 args+kwargs+queue+priority, Site 2 args). **Yeni `ignore_imports` EKLENMEDİ.** Task name `tasks.embedding.chunk_article` decorator'dan doğrulandı. CI'da 1 silent miss yakalandı: `test_articles_cleaned_at.py:60` **quoted file-path string** (Python import grep'lerine kaçmıştı, FileNotFoundError ile yakalandı, 1 satır fix commit `cfab9f8`). Main CI 10/10 success (`ed669ed`), deploy 53s success, two-job `skip_deploy=false`. **Smoke:** passive PASS (registry 6+6 tasks incl. `tasks.embedding.chunk_article`, routing+Beat unchanged, new paths OK + old paths ModuleNotFoundError, articles.py runtime AST verdict PASS), 7×7×18dk log scan TOTAL 1 hit (incelendi → false positive: `backfill_missing_chunks` succeeded `errors: 0` — Site 2 decoupling kodunun runtime kanıtı). **READ-only active smoke PASS** Playwright MCP via user session: `GET /api/admin/articles?limit=20&offset=0 → 200` + `GET /api/admin/articles/064a3c86-… → 200` (state untouched, agent admin token görmedi). **Natural fire OBSERVED 18:30-18:40 UTC** Beat fires + worker_scraper backfill_discovered × 3 succeeded + worker_embedding backfill_missing_chunks succeeded (Site 2 decoupling task runtime executed). `tasks.embedding.chunk_article` doğal dispatch görülmedi (fresh cleaned article yoktu — caveat doğru yazıldı). **Production state dili:** "No manual/synthetic state-changing smoke was performed; no test-induced production mutation." **T6 [#1085](https://github.com/selmanays/nodrat/issues/1085) tracking kapatılabilir** — transient muafiyet kaldırıldı, articles modülü aktive.
- 2026-05-21: **Phase 3 PR 3 merged** ([#1133](https://github.com/selmanays/nodrat/pull/1133), squash merge `37f11af`). modules/embedding aktive (Phase 1 iskeletinde unutulmuş skeleton yaratıldı): `workers/tasks/embedding.py` (1007 LoC) → `modules/embedding/tasks/embedding.py` (git mv 100% similarity — pure rename, content değişimi 0; SQL string'lerinde 0 satır değişim → veri güvenliği invariant'ı **PRESERVED**). External caller path updates: `entities.py:35` 1→2 line clean-up (indirect→direct: `_ensure_providers → modules.embedding`; `_get_session_factory + _run_async → shared.workers.db_session`), `scripts/eval_rerank_ab.py:43` direct shared path, `test_embedding_binary.py:94` Form 2 alias, `test_embedding_worker.py:12,27,36` Form 1+2. `workers/celery_app.py:31` include path update. **Yeni 13. import-linter contract** eklendi: `embedding/ must not import upper layers` forbidden=[rag, generations] (clusters kullanıcı kararıyla forbidden listesinde değil). **Yeni `ignore_imports` EKLENMEDİ.** Local pre-flight: ruff + AST + import-linter **13 kept, 0 broken** + 5-form caller audit (Form 1-5 hepsi 0). **Pre-existing per-article re-chunk behavior preserved, not modified** (PR body'de açık).
- 2026-05-21: **PR #1133 push:main auto-trigger anomaly** — squash merge sonrası ci.yml main üzerinde `37f11af` için **HİÇ TETİKLENMEDİ** (`gh run list --commit 37f11af6` boş). Sonuçta deploy.yml workflow_run zinciri başlamadı; VPS eski `ed669ed` (PR 2b state) kodunda kaldı. İlk smoke yanıltıcı PASS verdi çünkü ESKİ kod tabanında `tasks.embedding.*` registry'de aynı task name'lerle görünüyordu. Smoke 3 + 4 ise doğru FAIL verdi (new path import + entities helper direct paths). Anomaly tek seferlik göründü (PR 2a/2b/2-closure hepsi normal tetiklendi).
- 2026-05-21: **CI recovery PR #1134 merged** ([#1134](https://github.com/selmanays/nodrat/pull/1134), squash `42c4dcd`). `.github/workflows/ci.yml` `on:` bloğuna `workflow_dispatch:` 3. trigger eklendi (1 satır net diff). `push` + `pull_request` aynen korundu. Deploy.yml dokunulmadı. Yeni input parametresi yok. **Amaç:** PR #1133 sonrası yaşanan push:main auto-trigger anomalisi yine yaşanırsa `gh workflow run ci.yml --ref main` ile manuel kurtarma yolu açık. **deploy.yml workflow_dispatch direkt tetiklenmedi** (kullanıcı kuralı: SHA pinning #1108 korumak için CI üzerinden workflow_run yolu tercih edilmeli).
- 2026-05-21: **PR #1134 merge sonrası push:main otomatik tetiklendi** — recovery mekanizması test edilmedi (gerek kalmadı). CI run [26187604371](https://github.com/selmanays/nodrat/actions/runs/26187604371) (event=push, head_sha=`42c4dcd8`, branch=main) **10/10 success**. Deploy run [26187754246](https://github.com/selmanays/nodrat/actions/runs/26187754246) (event=workflow_run): detect-deploy-needed success + deploy-vps success. **SHA pinning 3-way match:** CI head_sha = Target SHA = Checked-out HEAD = `42c4dcd84f9eed8d5a07b18872431fa37563231a` (log: "Deploy target verified: SHA pinning OK"). Health 200.
- 2026-05-21: **PR #1133 embedding smoke BAŞTAN (post-real-deploy) — Blocking smoke PASS:** (1) Worker registry 6 `tasks.embedding.*` ✅; (2) Queue routing `tasks.embedding.* → embedding_queue` ✅; (3) **New path `app.modules.embedding.tasks.embedding` import OK** + missing attrs NONE; **Old path `app.workers.tasks.embedding` ModuleNotFoundError** ✅; (4) **entities.py:31-35 helper resolution direct paths VERDICT PASS** (`_ensure_providers → modules.embedding`, `_get_session_factory + _run_async → shared.workers.db_session`); (5) Articles → embedding `send_task("tasks.embedding.chunk_article", ...)` 2 site sağlam (PR 2b decoupling intact); (6) VPS filesystem: `/opt/nodrat/apps/api/app/modules/embedding/` var; `/opt/nodrat/apps/api/app/workers/tasks/embedding.py` **GONE**; (7) 7 container × 7 pattern × 6 dk log scan TOTAL 0 HITS. **Natural fire (NON-BLOCKING) caveat:** 15 dk pencerede `tasks.embedding.*` doğal dispatch görülmedi; pencerede fresh cleaned article olmadığı için expected; manual trigger yapılmadı; Beat scheduler diğer doğal fires gözlendi (system normal). **Veri güvenliği invariant — KORUNDU:** `rechunk_all` manuel tetiklenmedi, `chunk_article` manuel tetiklenmedi, manual backfill yok, direct DB/Redis yok, production article üzerinde state-changing smoke yok, existing chunks/embeddings/vector kayıtlarına müdahale yok, **pre-existing per-article re-chunk behavior preserved, not modified**. **Phase 3 ilerleme:** sources kernel + articles kernel + embedding middle-layer aktive; transient `ignore_imports` muafiyeti yok; import-linter **13 contracts, 0 broken** muafiyetsiz. **Sırada:** Phase 3 next migration candidate için **mini plan required** (clusters/entities/accounts/billing/ops/public — kullanıcı kararı).
- 2026-05-21: **PR #1140 merged — clusters → agenda A1 decoupling** (squash `d3ac330`). `modules/clusters/tasks/clustering.py` 2 site lazy import + `.apply_async()` pattern → `celery_app.send_task("tasks.agenda.generate_agenda_card", args=[str(cluster_id)])` string-bound. Behavior aynen (Celery routing aynı task name'i kullanır). **Amaç:** agenda task'ı `modules/generations`'a güvenle taşınabilmesi için doğrudan modüller-arası kenarı kırmak. PR #1141 ön-koşulu sağlandı.
- 2026-05-21: **PR #1141 merged — Phase 6 mini-cycle 1: agenda → modules/generations** (squash `4e4e74c`). `workers/tasks/agenda.py` (537 LoC) → `modules/generations/tasks/agenda.py` (similarity 100, sıfır içerik diff). `modules/generations` Phase 1 scaffold → **active facade** (layer=upper). 3 Celery task adı korundu (`tasks.agenda.generate_agenda_card|refresh_active_cards|backfill_country`); queue routing `tasks.agenda.* → event_queue`; Beat `refresh-agenda-cards` (saatlik) + `backfill-country` (batch) aynen; `agenda_cards` UPSERT pipeline; `UPDATE agenda_cards SET country WHERE id=:id` per-row pattern dokunulmadı. Caller updates: `api/admin_rag.py:897` lazy import + `tests/unit/test_country_backfill.py:5` test import. **Auto-merge gate PASS** (CI 10/10 + 5-form 0/0/0/0/0 + 13/13 contract + no new ignore_imports). **Smoke probe disipline dersi:** İlk smoke `celery_app.tasks` registry sorgu API container'da count=0 verdi (yanıltıcı false-negative); `celery_app.loader.import_default_modules()` ile force-load sonrası worker_rag'da 3/3 doğrulandı. Yeni ders [[refactor-pr-checklist]] §13.3'e eklendi.
- 2026-05-21: **PR #1142 merged — Phase 6 mini-cycle 2: cluster_assigner → modules/generations** (squash `ec3ad2c`). `workers/tasks/cluster_assigner.py` (350 LoC) → `modules/generations/tasks/cluster_assigner.py` (similarity 100; md5 `ca3f67bd0afdfc86cc125ad390b7da9f` her iki path'te identical). `modules/generations/tasks/` artık 2 dosya (agenda + cluster_assigner). 2 Celery task adı korundu (`tasks.research_clustering.assign|refine_hierarchy`); queue routing `tasks.research_clustering.* → embedding_queue` (worker_embedding tüketir); Beat `research-cluster-assign` + `research-hierarchy-refine` gece aynen; `research_cluster` + `message_cluster` UPSERT pipeline; `core/research_clustering` algoritma çekirdeği dokunulmadı. A1 decoupling GEREK YOK (0 production caller). **Auto-merge gate PASS** (5-form 0/0/0/0/0 + md5 identity + 13/13). **Smoke (worker_embedding force-load, 6/6 PASS):** registry 2 task; routes glob; Beat 2 entry; import OK + attrs; old path NotFound; 0 log hit.
- 2026-05-21: **PR #1143 merged — Phase 5 mini-cycle: raptor → modules/rag** (squash `6dbf378`). `workers/tasks/raptor.py` (460 LoC) → `modules/rag/tasks/raptor.py` (similarity 100). `modules/rag` Phase 1 scaffold → **active facade** (layer=middle). 1 Celery task adı korundu (`tasks.raptor.build_weekly_summary_cards`); queue routing `tasks.raptor.* → event_queue` (worker_rag tüketir); Beat `build-weekly-summary-cards` haftalık aynen; admin endpoint `/admin/rag/raptor/trigger` contract aynen (direct `await`, Celery dispatch DEĞİL); `daily_cards` + `weekly_cluster_cards` UPSERT pipeline; `_aggregate_country` algoritma dokunulmadı. Caller updates: `api/admin_rag.py:953` lazy import + `tests/unit/test_raptor.py` 7 import (1 module-level + 6 nested helper) + `modules/clusters/__init__.py` L8-11 docstring post-migration update. A1 decoupling GEREK YOK (callers private symbol import, Celery dispatch değil). **Auto-merge gate PASS** (5-form 0/0/0/0/2; Form 5 = 2 docstring/comment match, executable kod DEĞİL — biri güncellendi). **Smoke (worker_rag force-load, 6/6 PASS):** count: 1; routes; Beat; import OK + 15 attr (AgendaCard, WEEKLY_SIM_THRESHOLD, _aggregate_country, _build_weekly_summary_cards_async); old NotFound; 0 hit.
- 2026-05-21: **PR #1146 merged — T6 #1085 P4 PR-B: modules/crawler/extractor facade scaffold (no caller flip)** (squash `69a2d77`). `modules/crawler/` Phase 1 → active facade; `modules/crawler/extractor/__init__.py` re-export facade (11 public symbol). **Production caller flip YAPILMAMIŞTIR** — master plan §3.1/§3.2 kernel/middle boundary kararı açık kaldığı için. İlk denemede 3 caller flip → import-linter BROKEN (2 contract: `sources → crawler` YASAK, `articles → crawler` YASAK). A1-style Celery decoupling burada uygulanamaz (sync function call: `extract_article`, `extract_listing_cards`). 3 caller flip GERİ ALINDI (kullanıcı kararı 2026-05-21). **Açık karar maddesi (Phase 4 full migration öncesi):** (1) Extractor `modules/crawler/` mi kalmalı, `shared/extraction/`'a mı? (2) Kernel modülleri extractor surface'ini nasıl tüketecek? (3) 3 caller hangi extractor path'inden import edecek? **Auto-merge gate PASS** (CI 10/10 + 13/13 boundary korundu + scope düşük). **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1147 merged — T6 #1085 P4 PR-C: extractor internal helper split** (squash `062fe9e`). `core/extractor.py` 1189 → 1019 LoC (-170 net); YENİ `core/_extractor_filters.py` (212 satır). 6 regex pattern + 2 classifier function (`_is_non_editorial_image`, `_is_recommended_section`) ayrı internal modul'e taşındı. `core/extractor.py` line 166-349 (184 satır) silindi, 7 satır internal import (yalnız `_is_*` import edildi — regex'ler `_is_*` içinden erişilir). Public function signature aynen; 3 production caller DOKUNULMADI; `modules/crawler` facade scaffold (PR #1146) hâlâ scaffold; yeni `ignore_imports` YOK; master plan boundary aynen. **Auto-merge gate PASS** (CI 10/10 + 13/13 + 103 passed = 1496 LoC + 15 char PR #1144). **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1148 merged — T6 #1085 P5 PR-A: retrieval pure-function characterization tests** (squash `9cccb0d`). `apps/api/tests/unit/test_retrieval.py` +281 satır (25 yeni test). `core/retrieval.py` (2174 LoC) DOKUNULMADI. 7 fonksiyon characterization: `strip_quote_variants` (4 test), `_parse_pgvector_text` (5 test, strict 1024-dim), `_phrase_match_threshold` (3 test, LUT 3/6/7 char boundary), `_phrase_grams` (6 test, empty/single/all-noise/min-5-char/typical/dedup), `freshness_decay` extra boundary (2 test, half_life≤0 → 1.0; future date → 1.0), `compute_final_score` out-of-range (3 test, clamping YOK — pure linear blend), `_vector_to_pg_literal` extra (2 test, negatif/7-digit precision). 3 caveat docstring: `freshness_decay` half_life≤0 max-clamp DEĞİL (guard return); `compute_final_score` input clamping YOK; `_phrase_grams` 'ne mi' 5 char + 2 noise → atılır. **Auto-merge gate PASS** (CI 10/10 + 13/13 + 52 passed). **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1149 merged — T6 #1085 P5 PR-B: retrieval internal helper split** (squash `31de4bb`). `core/retrieval.py` 2174 → 1980 LoC (-194 net); 2 yeni internal modul: `core/_retrieval_phrase.py` (194 satır: `_QUOTE_CHARS_TO_STRIP`, `_QUOTE_CHARS_FOR_SQL`, `strip_quote_variants`, `normalize_tr_query`, `_build_sql_quote_strip`, `_phrase_match_threshold`, `_TR_NOISE_WORDS`, `_phrase_grams`) + `core/_retrieval_vector.py` (40 satır: `_parse_pgvector_text`, `_vector_to_pg_literal`). `core/retrieval.py` 3 sed-silinmiş blok + re-export import bloku + `__all__` list (11 sembol). 4 production caller (`api/public_search.py`, `api/admin_rag.py`, `core/research_tools.py`, `modules/entities/tasks/entities.py`) DOKUNULMADI — re-export ile 39 external import çalışır. Public API signature aynen; quote chars (19), phrase LUT, _TR_NOISE_WORDS (24), pgvector 1024-dim check, DB query mantığı DOKUNULMADI; RAG/retrieval pipeline DEĞİŞMEZ; ranking/scoring DOKUNULMADI. **Auto-merge gate PASS** (CI 10/10 + 13/13 + 93 passed = 52 char PR #1148 + 41 mevcut). **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1151 merged — P4-P5-P6 cumulative closure docs v1** (squash `2b70bff`). 5 PR (#1146-#1150) closure entry + master plan §12.3 changelog + §13 status board update + "Açık karar maddesi" (extractor boundary). Sadece wiki/ (2 file +92/-6) → `#1114` docs-only deploy SKIP **8. dogfooding PASS**.
- 2026-05-21: **PR #1152 merged — T6 #1085 P5 PR-C: retrieval scoring helpers split** (squash `c238f0a`). `core/retrieval.py` 1980 → 1911 LoC (-69 net); YENİ `core/_retrieval_scoring.py` (139 satır): `RetrievalMode`, `WEIGHTS_DEFAULT`, `WEIGHTS_CURRENT`, `CURRENT_MODE_FALLBACKS_HOURS`, `RetrievedChunk`, `RetrievalReport`, `freshness_decay`, `compute_final_score`. Line 296-401 sed-silindi; 9 satır internal import + `__all__` +8 sembol; gereksiz import (`math`, `dataclass`, `Literal`) ruff --fix auto-removed. Public API signature aynen; dataclass shape aynen; 4 production caller DOKUNULMADI (39+ external import re-export ile çalışır); DB query mantığı DOKUNULMADI; RAG/retrieval pipeline DEĞİŞMEZ; ranking/scoring algoritması DOKUNULMADI. **Auto-merge gate PASS** (CI 10/10 + 13/13 + 93 passed = 52 char PR #1148 + 41 mevcut). **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1154 merged — P5 PR-C + P6 PR-B cumulative closure docs v3** (squash `a5f7d45`). 3 PR (#1151 + #1152 + #1153) closure entry + master plan §12.3 changelog + §13 status board sentezi (10-PR uzun tur). Sadece wiki/ (2 file +53/-7) → `#1114` docs-only deploy SKIP **9. dogfooding PASS**.
- 2026-05-21: **PR #1155 merged — T6 #1085 P6 PR-A1: SSE async helper characterization tests** (squash `d2d98fa`). YENİ `apps/api/tests/unit/test_research_stream_async_helpers.py` (+292 satır, 17 yeni test). `api/app_research_stream.py` DOKUNULMADI. 2 async helper × 17 test: `_resolve_style_block` (11 test: tier guard free/basic/pro+agency_seat, DB None, rules_json None/malformed/empty/list, valid dict, string parse, list truncation) + `_recent_conversation_context` (6 test: DB empty, WHERE filter, default last_n=6, custom last_n=10, N msg reverse, log warning yok). 3 caveat: rules_json string inline JSON parse, list max 5 element truncation, rows.reverse() oldest-first. Light mock pattern (Explore agent önerisi): `AsyncMock(db)` + `MagicMock(execute_result)`; `_mock_db_returning(scalar)` ve `_mock_db_returning_scalars(list)` fixture helpers. `pytest.importorskip("pyotp")` Docker dep. **Defer list (PR-A2+):** `_generate_followups` + `_tracked_chat_generate` heavy mock; `post_research_message` + `_research_stream_body` orchestrator; replay tests. **Toplam SSE characterization: 35 test** (18 pure + 17 async). **Toplam characterization (4 god-file): 75 test.** **Auto-merge gate PASS** (CI 10/10 + 13/13 + 17+18 passed). **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1156 merged — P6 PR-A1 closure docs v4** (squash `38e69ac`). 12-PR uzun tur (#1144-#1155) state snapshot; wiki/log.md PR #1155 closure entry + §12.3 changelog (#1154 + #1155) + §13 status board 12-PR sentezi. Sadece wiki/ (2 file) → `#1114` docs-only deploy SKIP **10. dogfooding PASS** (Deploy run 26219026218 SKIP path 7sn).
- 2026-05-21: **PR #1157 merged — T6 #1085 P6 PR-A2a: SSE heavy-mock async helper characterization (`_generate_followups`)** (squash `de2b347`). YENİ `apps/api/tests/unit/test_research_stream_followups.py` (+339 satır, 9 yeni test). `api/app_research_stream.py` (1406 LoC) DOKUNULMADI. **1 helper × 9 test** (`_generate_followups(db, user_question, answer, tier) → list[str]`): default path, prompts_store.get raises → `_FU_SYS` fallback (yutulur), provider.generate_text raises → PROPAGATES (helper YUTMAZ), provider.text='' → parse('', limit=5) → [], provider.text=None → `res.text or ""` guard, tier="basic" → `registry.route_for_tier(operation='chat', tier='basic')` propagation, provider kwargs `max_tokens=240`+`temperature=0.5` sabit, messages=[system,user] shape, parse_followups `limit=5` sabit. **3 caveat docstring:** provider exception propagates (helper try/except yok), `or ""` None guard, fixed magic numbers (tier-unaware). **Heavy-mock pattern (3-patch):** `prompts_store.get` AsyncMock + `registry.route_for_tier` sync + `parse_followups` sync + fresh `AsyncMock()` provider per test; fixture helpers test dosyası içi (`_provider_returning`, `_provider_raising`). `pytest.importorskip("pyotp")` Docker dep. **Defer list (PR-A2b+):** `_tracked_chat_generate` heavier mock (ctx manager + telemetry factory); orchestrator (`_research_stream_body`, `post_research_message`); replay tests; full SSE integration. **Toplam SSE characterization: 44 test** (18 pure + 17 async light + 9 async heavy). **Toplam characterization (4 god-file): 84 test.** **Auto-merge gate PASS** (CI 10/10 + 13/13 + 9 + 35 intact). **Deploy reality:** push:main auto-trigger; CI 26219051084 success; deploy 26219367257 workflow_run + SHA pin `de2b3477...` + Deploy to VPS production success 1m16s 17 steps; health 200; container `Up healthy`; ZERO log error (10dk window); production behavior değişmedi (test-only image içermez). **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1158 merged — P6 PR-A2a closure docs v5** (squash `dd92187`). 14-PR uzun tur (#1144-#1157) state snapshot; wiki/log.md 2 closure entry (#1156 + #1157) + §12.3 changelog 2 satır + §13 status board 14-PR sentezi. Sadece wiki/ (2 file +43/-6) → `#1114` docs-only deploy SKIP **11. dogfooding PASS** (Deploy run 26220297611 SKIP path 9sn; "Detect" success + "Deploy to VPS (production)" `conclusion=skipped, steps=0`).
- 2026-05-21: **PR #1159 merged — T6 #1085 P6 PR-A2b: SSE heavy-mock async helper characterization (`_tracked_chat_generate`)** (squash `7fa6206`). YENİ `apps/api/tests/unit/test_research_stream_tracked_chat_generate.py` (+460 satır, 12 yeni test). `api/app_research_stream.py` (1416 LoC) DOKUNULMADI. **1 helper × 12 test:** default success, `provider.name` fallback "unknown" (spec=), `track_provider_call` kwargs lock (db/provider/operation="chat"/user_id), `CallTracker.record` kwargs lock (res attrs), totals in-place mutation, `res.cost_usd=None` skip, `res.model=None` `or` short-circuit, provider.generate_text raises PROPAGATES + finally commit, `record_research_cache_telemetry` kwargs lock (provider/model/call_type/conv_id/user_id/messages/tools/res/call_seq post-increment/success=True), telemetry exception swallowed, commit exception swallowed, `call_type=None` default → "unknown" fallback. **Heavy-mock 4-patch:** `track_provider_call` (`@asynccontextmanager`) + `get_session_factory` (sync→factory→async cm) + `record_research_cache_telemetry` (AsyncMock) + fresh provider AsyncMock per test; 6 fixture helper. `pytest.importorskip("pyotp")`. **Defer (PR-A3+):** replay tests + full SSE integration. **Toplam SSE characterization: 56 test** (18 pure + 17 async light + 9 + 12 heavy). **Toplam characterization (4 god-file): 96 test.** **Auto-merge gate PASS** (CI 10/10 + 13/13). **Deploy reality:** main CI success; deploy run 26221033705 workflow_run + SHA pin `7fa6206...` + full deploy 1m20s 17 steps; health 200; ZERO log error (5dk); production behavior değişmedi. **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1160 merged — T6 #1085 P6 PR-A3: minimal SSE event-sequence replay characterization** (squash `832f7c3`). YENİ `apps/api/tests/unit/test_research_stream_replay.py` (+274 satır net, 2 replay testi + 3 test-only parse helper). `api/app_research_stream.py` (1416 LoC) + `api/_research_stream_helpers.py` (64 satır) DOKUNULMADI. **Scope kararı (kullanıcı "kapsam büyürse" rehberi):** TestClient full integration ve `_research_stream_body` direct test çok ağır; PR-A3 = replay harness + 2 minimal test, 0 mock, 0 production code change. **2 test:** (1) typical transcript replay (`thinking_step` ×2 + `source_discovered` + `chunk` ×N caller-wrap dahil + `followup_suggestions` + `done`) event order/SSE separator/Unicode/done payload shape; (2) error path (`thinking_step` + `error{code,title,reason<=200}` + `done(status=failed)`). **Retry/root-cause dersi:** İlk push CI fail — `_simulate_stream` RAW word string yield eder; production caller `_sse("chunk", {"delta": piece})` ile sarar; replay testte caller wrap eksikti. Fix: `chunk_frames = [_sse("chunk", {"delta": piece}) for piece in raw_chunks]`. Production source 0 satır değişim. Auto-merge gate doğru çalıştı (ilk attempt ABORT non-pass, fix push retry'da merge). **Toplam SSE characterization: 58 test** (18 pure + 17 async light + 9 + 12 heavy + 2 replay). **Toplam characterization (4 god-file): 98 test.** **Phase 6 T6 god-file 6 PR ✅** (A + B + A1 + A2a + A2b + A3). **Auto-merge gate PASS** (retry CI 10/10 + 13/13). **Deploy reality:** main CI success; deploy run 26221905236 workflow_run + SHA pin `832f7c3...` + full deploy 1m40s 17 steps; health 200; ZERO log error (5dk); production behavior değişmedi. **Defer:** Full SSE integration (TestClient endpoint, full transcript replay with real research_tools mocks) DEFERRED. Phase 6 hâlâ tamamlanmadı. **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1161 merged — P6 PR-A2b + PR-A3 closure docs v6** (squash `c731373`). 17-PR uzun tur (#1144-#1160) state snapshot; wiki/log.md 2 closure entry (#1160 + #1158) + §12.3 changelog 3 satır (#1158 + #1159 + #1160) + §13 status board 17-PR sentezi + refactor-pr-checklist yeni ders (replay/event-sequence characterization caller-wrap deseni; PR #1160 vaka çalışması). Sadece wiki/ (3 file +67/-6) → `#1114` docs-only deploy SKIP **12. dogfooding PASS** (Deploy run 26222738436 SKIP path 7sn; "Detect" success + "Deploy to VPS (production)" `conclusion=skipped, steps=0`).
- 2026-05-21: **PR #1162 merged — T6 #1085 P6 PR-A4: minimal SSE replay expansion** (squash `04f815d`). `apps/api/tests/unit/test_research_stream_replay.py` (+235 satır, 4 yeni test). `api/app_research_stream.py` (1416 LoC) + `api/_research_stream_helpers.py` (64 satır) DOKUNULMADI. **4 yeni replay senaryo:** (1) **Chunk-only stream + done** — minimal greeting/meta path (no thinking_step, no source_discovered, no followup); event order `chunk × N → done`; done.sources/followup=0. (2) **Empty followup_suggestions** — production guard boş listede event yield ETMEZ; `followup_suggestions` event hiç yok; done.followup_count=0. (3) **Unicode/newline/quote payload JSON shape** — `_sse(ensure_ascii=False)` invariant: Türkçe+emoji inline; newline `\n` payload JSON-escaped (block boundary parçalanmaz); double-quote JSON-escaped; round-trip `json.loads` original delta aynen. (4) **Multiple source_discovered event order** — 5 ardışık event, ID order strict (interleave/reorder yok), title Unicode round-trip. **Caller-wrap deseni (PR #1160 dersi):** Tüm chunk içeren testler `_simulate_stream` raw → `_sse("chunk", {"delta": piece})` wrap eder; refactor-pr-checklist §13.4 kayıtlı. **Toplam SSE characterization: 62 test** (18 pure + 17 async light + 9 + 12 heavy + 2 + 4 replay). **Toplam characterization (4 god-file): 102 test.** **Phase 6 T6 god-file 7 PR ✅** (A + B + A1 + A2a + A2b + A3 + A4). **Auto-merge gate PASS** (CI 10/10 + 13/13). **Deploy reality:** main CI success; deploy run 26223169759 workflow_run + SHA pin `04f815d...` + full deploy 1m17s 17 steps; health 200; ZERO log error (5dk); production behavior değişmedi. **Defer:** Full SSE integration + `_research_stream_body` orchestrator + endpoint TestClient DEFERRED. Phase 6 hâlâ tamamlanmadı. **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1163 merged — P6 PR-A4 closure docs v7** (squash `6f67b5c`). 19-PR uzun tur (#1144-#1162) state snapshot; wiki/log.md 2 closure entry (#1162 + #1161) + §12.3 changelog 2 satır (#1161 + #1162) + §13 status board 19-PR sentezi. Sadece wiki/ (2 file +37/-6) → `#1114` docs-only deploy SKIP **13. dogfooding PASS** (Deploy run 26223873709 SKIP path 10sn; "Detect" success + "Deploy to VPS (production)" `conclusion=skipped, steps=0`).
- 2026-05-21: **PR #1164 merged — T6 #1085 P6 PR-A5: minimal `_research_stream_body` orchestration characterization (first-yield)** (squash `f5fec3a`). YENİ `apps/api/tests/unit/test_research_stream_orchestrator.py` (+190 satır, 2 yeni test + 2 test-only helper). `api/app_research_stream.py` (1416 LoC) DOKUNULMADI. **Scope analizi (kullanıcı plan ≤ 8-10 mock + güvenli):** `_research_stream_body` ilk yield öncesi **HİÇ external dep çağrılmaz** — sadece lazy imports + inline `_log_step` closure + `_sse`. Line 619+ DB sorgu (`_recent_conversation_context`) ANCAK ilk yield TÜKETİLDİKTEN sonra. Async generator `await anext(gen)` + `await gen.aclose()` ile tek event consume + durdur. **Mock count: 3** (1 AsyncMock db + 2 MagicMock user/payload + 5 primitive arg) — risk DÜŞÜK. **2 minimal test:** (1) default path (`is_related=False`, `prev_sources=None`) → first yield `thinking_step{phase=context_check, detail="Yeni konu — sıfırdan kaynak araması", latency_ms=0}` exact match + `db.execute.assert_not_called()` + `db.scalar.assert_not_called()` (dep-free entry lock); (2) related branch (`is_related=True`, `prev_sources=[2]`, `similarity=0.876`) → detail pattern `"Önceki sorularla ilişkili (similarity=0.88) — 2 kaynak değerlendiriliyor"` (`:.2f` format + `len(prev_sources)` inline). **`_research_stream_body` first-yield / `context_check` invariant kilitlendi.** **Toplam SSE characterization: 64 test** (18 pure + 17 async light + 9 + 12 heavy + 2 + 4 replay + 2 orchestration). **Toplam characterization (4 god-file): 104 test.** **Phase 6 T6 god-file 8 PR ✅** (A + B + A1 + A2a + A2b + A3 + A4 + A5). **Auto-merge gate PASS** (CI 10/10 + 13/13 + ruff C408 düzeltildi). **Deploy reality:** main CI success; deploy run 26224404879 workflow_run + SHA pin `f5fec3a...` + full deploy 1m9s 17 steps; health 200; ZERO log error (5dk); production behavior değişmedi. **Defer:** Full SSE integration (TestClient endpoint, derin orchestration mocks) DEFERRED. Phase 6 hâlâ tamamlanmadı. **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1165 merged — P6 PR-A5 closure docs v8** (squash `d07b90c`). 21-PR uzun tur (#1144-#1164) state snapshot; wiki/log.md 2 closure entry (#1164 + #1163) + §12.3 changelog 2 satır (#1163 + #1164) + §13 status board 21-PR sentezi. Sadece wiki/ (2 file +36/-6) → `#1114` docs-only deploy SKIP **14. dogfooding PASS** (Deploy run 26225671339 SKIP path 8sn; "Detect" success + "Deploy to VPS (production)" `conclusion=skipped, steps=0`).
- 2026-05-21: **PR #1166 merged — T6 #1085 P6 PR-A6: minimal SSE replay/edge characterization** (squash `a75c498`). `apps/api/tests/unit/test_research_stream_replay.py` (+219 satır, 3 yeni test; mevcut 6 + 3 = 9 test). `api/app_research_stream.py` (1416 LoC) + `api/_research_stream_helpers.py` (64 satır) DOKUNULMADI. **Scope analizi (kullanıcı plan rehberi):** RC3-B marker (deep grounding loop) + tool-loop timeout (PR #1160 generic error zaten lock'lu) → DEFERRED; (3) duplicate done guard + (4) chunk+followup+done combo + (5) source_discovered+chunk interleave → AL. Mock count 0. **3 yeni replay edge test:** (1) **`done` event terminal + singular** — duplicate done guard structural lock (done sayısı=1, terminal); (2) **Chunk + followup + done minimal combo (no thinking/sources)** — KAYNAKSIZ+followup edge path, event order strict, `thinking_step`+`source_discovered` hiç yok, done.sources=0+followup>0; (3) **source_discovered → chunk no-interleave** — production akış (retrieval×N → answer streaming×N), son source index < ilk chunk index, contiguous blok. **Caller-wrap deseni (PR #1160 dersi)** tüm chunk testlerde uygulandı. **Toplam SSE characterization: 67 test** (18 pure + 17 async light + 9 + 12 heavy + 2 + 4 replay + 2 orchestration + 3 replay/edge). **Toplam characterization (4 god-file): 107 test.** **Phase 6 T6 god-file 9 PR ✅** (A + B + A1 + A2a + A2b + A3 + A4 + A5 + A6). **Phase 6 replay coverage: 9 senaryo** (PR-A3: 2 + PR-A4: 4 + PR-A6: 3) — master plan §13 SSE replay golden hedefinden (10 senaryo) 1 eksik. **Auto-merge gate PASS** (CI 10/10 + 13/13). **Deploy reality:** main CI success; deploy run 26226319476 workflow_run + SHA pin `a75c498...` + full deploy 1m16s 17 steps; health 200; ZERO log error (5dk); production behavior değişmedi. **Defer:** RC3-B marker → PR-C+ scope; tool-loop timeout → marjinal değer; PR-A7 → 10. senaryoyu tamamlama. Phase 6 hâlâ tamamlanmadı. **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1167 merged — P6 PR-A6 closure docs v9** (squash `2c1ea0c`). 23-PR uzun tur (#1144-#1166) state snapshot; wiki/log.md 2 closure entry (#1166 + #1165) + §12.3 changelog 2 satır (#1165 + #1166) + §13 status board 23-PR sentezi. Sadece wiki/ (2 file +39/-6) → `#1114` docs-only deploy SKIP **15. dogfooding PASS** (Deploy run 26227211813 SKIP path 10sn; "Detect" success + "Deploy to VPS (production)" `conclusion=skipped, steps=0`).
- 2026-05-21: **PR #1168 merged — T6 #1085 P6 PR-A7: SSE replay/golden 10. senaryo + boundary edge bonus** (squash `fc482aa`). `apps/api/tests/unit/test_research_stream_replay.py` (+174 satır, 2 yeni test; mevcut 9 + 2 = 11 test). `api/app_research_stream.py` (1416 LoC) + `api/_research_stream_helpers.py` (64 satır) DOKUNULMADI. **Scope analizi (kullanıcı plan rehberi):** Production SSE event türleri (kaynak tarama via grep): `thinking_step` (×11 farklı phase), `source_discovered`, `chunk`, `followup_suggestions`, `done` (success + failure), `error`. progress/metadata/warning event YOK → skip. **2 yeni test seçildi:** (10. **Done payload success vs failure field-set invariant**) success 10-field exact set `{conversation_id, user_message_id, assistant_message_id, is_followup, similarity, query_class, used_wikipedia, sources_used_count, sources_considered_count, followup_count}` vs failure 1-field `{status: "failed"}`; **karşılıklı dışlayan** (`success.isdisjoint(failure)` ⇒ kesişim boş). (11. bonus **Empty content chunk boundary**) `_simulate_stream("")` PR #1150 lock'u 1 yield "" + caller-wrap rule (PR #1160 dersi) → 1 SSE chunk frame `{delta: ""}`; transcript `thinking + source + chunk(delta="") + done` geçerli; empty delta JSON round-trip + SSE byte-level intact. **DEFER (documented):** RC3-B marker → deep grounding loop integration PR-C+ scope; tool-loop timeout → PR #1160 generic error zaten lock'lu marjinal. Mock count 0. **Toplam SSE characterization: 69 test** (18 pure + 17 async light + 9 + 12 heavy + 2 + 4 replay + 2 orchestration + 3 replay/edge + 2 replay/golden). **Toplam characterization (4 god-file): 109 test.** **Phase 6 T6 god-file 10 PR ✅** (A + B + A1 + A2a + A2b + A3 + A4 + A5 + A6 + A7). **SSE replay coverage: 10/10 senaryo HEDEF TAMAMLANDI** + 1 bonus boundary edge. **Auto-merge gate PASS** (CI 10/10 + 13/13). **Deploy reality:** main CI success; deploy run 26227812533 workflow_run + SHA pin `fc482aa...` + full deploy 1m26s 17 steps; health 200; ZERO log error (5dk); production behavior değişmedi. **Defer:** Full SSE integration + `_research_stream_body` derin orchestration + endpoint TestClient + RC3-B marker + tool-loop timeout DEFERRED. Phase 6 hâlâ tamamlanmadı. **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1169 merged — P6 PR-A7 closure docs v10** (squash `da9108e`). 25-PR uzun tur (#1144-#1168) state snapshot; wiki/log.md 2 closure entry (#1168 + #1167) + §12.3 changelog 2 satır (#1167 + #1168) + §13 status board 25-PR sentezi. Sadece wiki/ (2 file +37/-6) → `#1114` docs-only deploy SKIP **16. dogfooding PASS** (Deploy run 26228897983 SKIP path 10sn; "Detect" success + "Deploy to VPS (production)" `conclusion=skipped, steps=0`). **Milestone:** SSE replay coverage 10/10 senaryo HEDEF TAMAMLANDI işlendi.
- 2026-05-21: **PR #1170 merged — T6 #1085 P6 PR-A8: `_has_reconstruction_marker` helper-level characterization (RC3-B regex katalogu)** (squash `c4df2df`). PR-A7 closure scope analizi sonucu kullanıcı kararı A. `apps/api/tests/unit/test_research_stream_helpers.py` (mevcut PR #1150 dosyası) içine 15 yeni test (`_has_reconstruction_marker` test grubu); import statement güncellendi. `api/app_research_stream.py` (1416 LoC) DOKUNULMADI. **15 test = 9 marker pattern positive ("anlaşıldığı kadarıyla", "anlaşıldığına göre", "yansıdığı kadarıyla", "tepkisinden anlaşıl…" prefix, "tepkisine bakılırsa", "tepkisinden çıkarıl…" prefix, "olduğu anlaşılıyor", "olduğu sanılıyor", "muhtemelen X demiş/söylemiş/iddia etmiş/demişti" 40-char gap) + 6 boundary** (period gap exclude, empty string, negative news, case-insensitive, Unicode, multi-pattern). **RC3-B helper-level lock tamam** — regex pattern katalogu safety-net. Mock count 0. **Toplam SSE characterization: 84 test** (33 helper pure + 17 async light + 9 + 12 heavy + 2 + 4 replay + 2 orchestration + 3 replay/edge + 2 replay/golden). **Toplam characterization (4 god-file): 124 test.** **Phase 6 T6 god-file 11 PR ✅** (A + B + A1 + A2a + A2b + A3 + A4 + A5 + A6 + A7 + A8). **Auto-merge gate PASS** (CI 10/10 + 13/13). **Deploy reality:** main CI success; deploy run 26229670054 workflow_run + SHA pin `c4df2df...` + full deploy 1m24s 17 steps; health 200; ZERO log error (5dk); production behavior değişmedi. **Defer:** RC3-B orchestrator coupling (marker → faithfulness_reframed event) deep integration → PR-C+ scope; tool-loop timeout deep coverage → production'da event yok, PR-C+. Phase 6 hâlâ tamamlanmadı. **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **Phase 7a frontend reality checkpoint + kalıcı mini plan playbook** ([[phase7a-frontend-mini-plan]]) yazıldı. `apps/web/src/lib/api.ts` snapshot: **2041 LoC, 199 export, 60 caller dosya, 94 unique sembol**. 7 major domain bloğu (Core + Auth + Sources + Public search + Articles + Research 691 LoC + 1080 LoC admin/me); top imports `type` (57×), `ApiException` (40×), `apiFetch` (12×). **Frontend runtime test altyapısı YOK** — sadece ESLint + tsc strict + next build (compile-time only). Önerilen yapı: `src/lib/api/` domain modülleri + `api.ts` backward-compatible facade (60 caller path değişmez). PR sırası: **PR-7a-0 test infra bootstrap** (Vitest+jsdom + ≤5 helper char) → PR-7a-1 Public search extract (28 LoC / 1 caller) → PR-7a-2 Admin Disk (36 LoC / 1 caller) → ... → Research EN SONA. **Hard kurallar:** `apiFetch` + `ApiException` ortak core ASLA ayrılmaz; 60 caller import path DEĞİŞMEZ; auth/session/token refresh sadece test ile değişir. **Açık sorular:** test framework seçimi (Vitest önerisi), Articles overlap netleştirilmesi, Research SSE client coupling stratejisi.
- 2026-05-21: **PR #1153 merged — T6 #1085 P6 PR-B: SSE pure-helper internal split** (squash `d72b3fc`). `api/app_research_stream.py` 1440 → 1406 LoC (-34 net); YENİ `api/_research_stream_helpers.py` (64 satır): `_sse`, `_simulate_stream`, `_log_coverage_gap`. Line 248-263 + 193-195 + 136-150 sed-silindi (3 helper block); re-export import bloku + `__all__` listesi eklendi; gereksiz import (`contextlib`, `json`) ruff --fix auto-removed. **Hedef dosya seçimi gerekçesi:** sibling `api/_research_stream_helpers.py` (modules/generations/research_stream/ alternatifi kernel→upper-layer boundary açar — PR #1146 türü sorun; kullanıcı kuralı "en düşük riskli hedef"). 3 helper PURE; 10+ helper invocation site re-export ile çalışır. SSE event format/order/streaming behavior aynen; `_research_stream_body` orkestratörü DOKUNULMADI; async DB/provider/request context flow DOKUNULMADI. **Auto-merge gate PASS** (CI 10/10 + 13/13 + 18 char test PR #1150 PASS). **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1150 merged — T6 #1085 P6 PR-A: SSE pure-helper characterization tests** (squash `5bfac73`). `apps/api/tests/unit/test_research_stream_helpers.py` +257 satır (YENİ dosya, 18 test). `api/app_research_stream.py` (1440 LoC) DOKUNULMADI. 3 fonksiyon, 18 test: `_sse()` SSE event format (8 test: basic, None data, Unicode preserved ensure_ascii=False, UUID default=str, nested dict, special chars JSON-escaped, trailing \n\n), `_simulate_stream()` async word-group generator (5 test: empty/single word/4-word/8-word/pacing 0.018s), `_log_coverage_gap()` telemetry (5 test: warning + reason + question, question[:160] truncation, None fallback, exception suppression `contextlib.suppress`, reason kategorileri — no validation). 3 caveat: `_simulate_stream` empty/single word final iteration `await asyncio.sleep` ÇAĞRILIR; 8 word son group no trailing space; `_log_coverage_gap` reason validation YOK. pyotp Docker dep çözümü: `pytest.importorskip("pyotp")`. Async DB/provider helpers (`_resolve_style_block`, `_tracked_chat_generate`, `_generate_followups`, `_research_stream_body`) heavy mock infra gerektirir → PR-A1'e ertelendi. **Auto-merge gate PASS** (CI 10/10 + 13/13 + test-only scope). **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1144 merged — T6 #1085 P4 PR-A: extractor characterization tests** (squash `168acab`). `apps/api/tests/unit/test_extractor.py` +382 satır (15 yeni characterization test). `core/extractor.py` DOKUNULMADI. Strateji: facade-first + characterization — refactor öncesi safety-net. Yeni test grubu (`extract_body_images` characterization): URL resolution (relative/protocol-relative/absolute), edge cases (empty body, missing alt, no src, no width/height), filter behavior (dedup, position counter), figure (figcaption + text fallback w/ alt-trim), robustness (malformed dims no crash), realistic Turkish news fixture. 3 caveat docstring notu işaretlendi (dedup-alt korunur; position filter düşeni tüketmez; figure-trim " -—|:"). Davranış İCAT ETMEZ — mevcut implementation output'unu doğrular. **Auto-merge gate PASS** (CI 10/10 + scope test-only + 13/13). **Worker task migration TAMAM:** `apps/api/app/workers/tasks/` artık yalnız `__init__.py` (323 byte) içerir; 8 task dosyası 5 modüle dağıtıldı. **Phase 4 god-file refactor başlangıcı** ✅. **Sonraki:** PR-B `modules/crawler/extractor/__init__.py` re-export facade + 3 production caller flip (`modules/articles/tasks/articles.py:51`, `modules/sources/admin/routes.py:37`, `modules/sources/tasks/sources.py:22`); `core/extractor.py` source-of-truth kalır.
- 2026-05-21: **Phase 3 ops sub-cycle — modules/ops/tasks/maintenance.py migration merged** ([#1137](https://github.com/selmanays/nodrat/pull/1137), squash `ad98ef7`; gece otonom batch mode auto-merge). `workers/tasks/maintenance.py` (713 LoC) → `modules/ops/tasks/maintenance.py` (git mv 100% similarity, pure rename). Phase 1 ops scaffold aktive. Caller path updates: 2 test (5 satır), workers/celery_app.py:36 include path. **Yeni contract gerek YOK** (mevcut "domain modules must not import ops/" karşıt yönü kapsıyor). **Yeni `ignore_imports` eklenmedi.** Auto-merge gate: CI 10/10 + mergeStateStatus CLEAN + 5-form 0/0/0/0 + import-linter 13/13 + scope düşük + no DB schema → PASS. **CI/deploy chain:** push:main auto-trigger; CI run [26191790430](https://github.com/selmanays/nodrat/actions/runs/26191790430) success; deploy run [26191927660](https://github.com/selmanays/nodrat/actions/runs/26191927660) workflow_run + SHA pinning 3-way match + deploy-vps success; health 200. **Post-deploy smoke (fresh probe sonrası) — Blocking smoke PASS:** VPS filesystem modules/ops/ mevcut + workers/tasks/maintenance.py GONE; runtime probe NEW OK (6 attrs: cold_tier_archive, cold_tier_restore, body_html_drop, quantize_chunks, reembed_chunks, reembed_agenda_cards) + OLD GONE; worker registry 6 `tasks.maintenance.*`; queue routing `tasks.maintenance.* → embedding_queue` korundu; 7×6 log scan TOTAL 0 hits. **Erken false-fail timing dersi (refactor checklist §13.1'e eklendi):** deploy-vps "success" + container CreatedAt güncel → runtime probe için 30-60sn buffer gerek (PR #1137 ilk smoke'da bu sebep yanıltıcı NEW FAIL verdi). **Natural fire (NON-BLOCKING):** body-html-drop + cold-tier-archive daily; pencerede expected değil; "not observed within window, non-blocking". **Veri güvenliği invariant — KORUNDU:** reembed_chunks, reembed_agenda_cards, quantize_chunks, cold_tier_restore manuel tetiklenmedi; manual backfill yok; direct DB/Redis yok; existing chunks/embeddings müdahale yok; **pre-existing behavior preserved, not modified** (git mv 100% similarity = SQL string'lerinde 0 satır değişim). **Phase 3 ops sub-cycle TAMAM.** **Kalan workers/tasks/ (Phase 5/6/7 mini plan only):** agenda.py (Phase 6 generations — clusters → agenda direct lazy edge contract ihlali doğurur, A1 decoupling + model migration scope expansion gerekir); cluster_assigner.py (Phase 6 research_clustering); raptor.py (Phase 5 RAG god-file).
- 2026-05-21: **PR #1171 merged — closure docs v11** (squash `74e4847`). 27-PR uzun tur (#1144-#1170) state snapshot. wiki/log.md 2 closure entry (#1170 + phase7a-frontend-mini-plan) + master plan §12.3 changelog + §13 status board 27-PR sentezi + YENİ [[phase7a-frontend-mini-plan]] kalıcı playbook (Phase 7a frontend `api.ts` 2041 LoC / 199 export / 60 caller reality + PR sırası önerisi). Sadece wiki/ → `#1114` docs-only deploy SKIP **17. dogfooding PASS** (Deploy run SKIP path).
- 2026-05-21: **PR #1172 merged — T6 #1085 P7a PR-7a-0: frontend characterization safety-net bootstrap** (squash `9272946`). YENİ `apps/web/vitest.config.ts` (jsdom env, `@` alias) + YENİ `apps/web/src/lib/__tests__/api.test.ts` (5 char test, ~120 satır) + `apps/web/package.json` (+test/test:watch script + vitest 2.1.8 + jsdom 25.0.1 devDep) + `apps/web/package-lock.json` (1048 paket) + `.github/workflows/ci.yml` `web-lint` job içine `Vitest unit tests (P7a PR-7a-0 — frontend characterization)` step. **`apps/web/src/lib/api.ts` (2041 LoC) DOKUNULMADI** — production source 0 satır değişim. **5 test:** `ApiException` constructor invariant + token storage round-trip + clearTokens semantik + apiFetch success path mock + apiFetch 204 No Content → undefined. Decision (reality check): Vitest 2.1.8 + jsdom 25.0.1 (Next.js 14 uyumlu, hızlı, jest-compatible API). **Auto-merge gate PASS** (CI 10/10 + Vitest 5/5 + ESLint + tsc + lint-imports 13/13). **Deploy reality:** CI run [26231848341](https://github.com/selmanays/nodrat/actions/runs/26231848341) success; deploy run [26232033342](https://github.com/selmanays/nodrat/actions/runs/26232033342) workflow_run + SHA pin `9272946...` + full deploy 3m25s 17 steps; health 200; ZERO log error. **Toplam frontend characterization: 5 test başlangıç.** **Phase 7a 1. PR ✅ (test infra).** **Veri güvenliği invariant — KORUNDU** (test-only).
- 2026-05-21: **PR #1173 merged — T6 #1085 P7a PR-7a-1: `api/public.ts` extract (Public Search)** (squash `8fe849f`). YENİ `apps/web/src/lib/api/public.ts` (28 LoC: 2 interface `PublicSearchItem`, `PublicSearchResponse` + 1 fonksiyon `publicSearch` GET + URL-encoded query + default limit + skipAuth) + `apps/web/src/lib/api.ts` L539-565 SİL + 4 satır re-export (`export type {...}` + `export { publicSearch } from "./api/public"`). Caller `app/ara/page.tsx` (1 dosya) import path DEĞİŞMEDİ. **Facade pattern proof-of-concept doğrulandı** — TypeScript bundler `@/lib/api` → `lib/api.ts` (file) > `lib/api/` (folder) öncelikli; 60 caller path değişmez. +2 char test (cumulative 7). **Auto-merge gate PASS** (CI 10/10 + Vitest 7/7 + 13/13). **Deploy reality:** CI run [26233297068](https://github.com/selmanays/nodrat/actions/runs/26233297068) success; deploy run [26233477584](https://github.com/selmanays/nodrat/actions/runs/26233477584) workflow_run + SHA pin `8fe849f...` + deploy 2m46s 17 steps; health 200; ZERO log error. Production smoke (read-only): `/ara` 200 + `/api/public/search?query=test` 200 + valid JSON. **Phase 7a 2. PR ✅.** **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1174 merged — T6 #1085 P7a PR-7a-2: `api/admin/disk.ts` extract (Admin Disk monitoring)** (squash `4344a60`). YENİ `apps/web/src/lib/api/admin/disk.ts` (54 LoC: 3 interface `DiskCategory`, `DiskBreakdownResponse`, `DiskCleanupResponse` + 2 fonksiyon `adminDiskBreakdown` GET + `adminDiskCleanup` POST) + `apps/web/src/lib/api.ts` L2005-2041 SİL + re-export. Caller `app/admin/system/disk/page.tsx` (1 dosya). +2 char test (cumulative 9). **Auto-merge gate PASS** (CI 10/10 + Vitest 9/9 + 13/13). **Deploy reality:** CI run [26235053785](https://github.com/selmanays/nodrat/actions/runs/26235053785) success; deploy run [26235254641](https://github.com/selmanays/nodrat/actions/runs/26235254641) workflow_run + SHA pin `4344a60...` + deploy 2m57s 17 steps; health 200; ZERO log error. Production smoke: `/admin/system/disk` 200 sayfa render (auth-gated); **`adminDiskCleanup` POST production'a YOLLANMADI** (state-changing — kullanıcı invariant). **Phase 7a 3. PR ✅.** **Veri güvenliği invariant — KORUNDU.**
- 2026-05-21: **PR #1175 merged — T6 #1085 P7a PR-7a-3: `api/auth.ts` extract (login/register/logout)** (squash `ef8c5ee`). YENİ `apps/web/src/lib/api/auth.ts` (~95 satır: 4 interface `LoginPayload`/`RegisterPayload`/`TokenResponse`/`UserPublic` + 3 fonksiyon `login`/`register`/`logout`) + `apps/web/src/lib/api.ts` L185-254 SİL + 12 satır re-export. Token storage + `attemptTokenRefresh` (concurrent 401 protection) core'da KALDI. **TypeScript same-file type-ref fix:** `attemptTokenRefresh` (api.ts ~L92) hâlâ `TokenResponse` kullanıyordu → inline type-only import `(await resp.json()) as import("./api/auth").TokenResponse` (runtime impact yok, tsc yakaladı). +4 char test (cumulative 13): login POST + skipAuth + body, register POST + KVKK fields, logout with refresh (backend POST silent + clear), logout without refresh (yalnız clear). **Auto-merge gate PASS** (CI 10/10 + Vitest 13/13 + tsc + 13/13). **Deploy reality:** CI run [26236215248](https://github.com/selmanays/nodrat/actions/runs/26236215248) success; deploy run [26236429405](https://github.com/selmanays/nodrat/actions/runs/26236429405) workflow_run + SHA pin `ef8c5ee...` + deploy 2m27s 17 steps; health 200; ZERO log error. Production smoke (read-only, **auth action TETİKLENMEDİ**): `/login` 200, `/register` 200, `/admin/login` 200, `/forgot-password` 200, `/reset-password` 200, `/verify-email` 200. **api.ts facade/re-export pattern 3 kez doğrulandı** (public + disk + auth). 60 caller import path tüm extract sonrası DEĞİŞMEDİ. **Phase 7a 4. PR ✅** (PR-7a-0/1/2/3 DONE; PR-7a-4 scope analizi sırada). **Yeni ders [[refactor-pr-checklist]]'e eklenir** (TypeScript same-file type-ref edge case). **Veri güvenliği invariant — KORUNDU** (auth/email production action yok).

| Alan | Değer |
|---|---|
| Aktif faz | **Phase 4/5/6/7a paralel** — P4 T6: char (#1144) + facade scaffold (#1146, boundary açık) + internal split (#1147); P5 T6: char (#1148) + phrase+vector split (#1149) + scoring split (#1152); **P6 T6: 11 PR ✅** (#1150 + #1153 + #1155 + #1157 + #1159 + #1160 + #1162 + #1164 + #1166 + #1168 + #1170); **P7a T6: 4 PR ✅** test infra (#1172 — Vitest 2.1.8 + jsdom 25.0.1 + 5 char test + CI step) + public search extract (#1173 — `api/public.ts` 28 LoC + 1 caller + 2 test) + admin disk extract (#1174 — `api/admin/disk.ts` 54 LoC + 1 caller + 2 test) + auth extract (#1175 — `api/auth.ts` ~95 LoC + 4 interface + 3 fonksiyon + 4 test); `api.ts` facade/re-export pattern 3 kez doğrulandı; 60 caller import path DEĞİŞMEDİ; **`apiFetch` + `ApiException` + token storage + `attemptTokenRefresh` core'da KALDI** (P7a hard kural); `modules/generations` + `modules/rag` + `modules/crawler` Phase 1 scaffold → active facade; **workers/tasks/ artık yalnız `__init__.py`**; import-linter **13 contracts, 0 broken** muafiyetsiz |
| Bekleyen | P4 PR-D caller flip (boundary kararına bağlı; PR #1146 açık sorular); **P7a PR-7a-4 sırada** (scope analizi: `requestVerifyResend` mini-extract VEYA Admin Sources/Users — implementation YOK, sadece rapor); **P7a Research section EN SONA** (691 LoC / 11+ caller; SSE client coupling); P6 PR-C+ full SSE integration replay (TestClient endpoint, full transcript with real research_tools mocks; RC3-B orchestrator coupling + tool-loop timeout deep coverage dahil); P7b frontend rag-page ([#1096](https://github.com/selmanays/nodrat/issues/1096)); P8 boundary hardening ([#1097](https://github.com/selmanays/nodrat/issues/1097)); N+1 model relocation ([#1098](https://github.com/selmanays/nodrat/issues/1098)) — blocked by T8 |
| Tamamlanan | **P0/1/2** kapandı (#1088/89/90); **P3** ana cycle (6 PR); **P5 mini-cycle** worker (#1143); **P6 mini-cycle** worker (#1140-#1142); **P4 god-file T6 PR-A/B/C** (#1144 + #1146 + #1147); **P5 god-file T6 PR-A/B/C** (#1148 + #1149 + #1152); **P6 god-file T6 PR-A/B/A1/A2a/A2b/A3/A4/A5/A6/A7/A8** (#1150 + #1153 + #1155 + #1157 + #1159 + #1160 + #1162 + #1164 + #1166 + #1168 + #1170); **P7a god-file T6 PR-7a-0/1/2/3** (#1172 + #1173 + #1174 + #1175); **11 closure docs** (#1145 + #1151 + #1154 + #1156 + #1158 + #1161 + #1163 + #1165 + #1167 + #1169 + #1171) |
| Aktif tracking | T1-T5 (#1080-#1084), **T6 [#1085](https://github.com/selmanays/nodrat/issues/1085) — OPEN** (P4: 3 PR ✅ + caller flip ertelendi; P5: 3 PR ✅; P6: 11 PR ✅ + RC3-B orchestrator coupling + tool-loop timeout + full SSE integration pending → PR-C+; **P7a: 4 PR ✅** (test infra + public + disk + auth); PR-7a-4 scope analizi sırada), **T7 [#1086](https://github.com/selmanays/nodrat/issues/1086) — OPEN** (cost_tracker pending), **T8 [#1087](https://github.com/selmanays/nodrat/issues/1087) — OPEN/BLOCKED** (5 ön-koşul). **Phase 6 hâlâ tamamlanmadı** — derin orchestration + endpoint TestClient kalır. **Phase 7a devam ediyor** — Research EN SONA, küçük mini-extract adayları sırada. **SSE replay coverage 10/10 senaryo HEDEF TAMAMLANDI** + 1 bonus. **RC3-B helper-level lock tamam.** |
| Son güncelleme | 2026-05-21 — **B seçeneği uzun tur 31 PR cumulative** (#1144-#1175 + closure docs v12). PR #1171 closure docs v11 + PR #1172 P7a PR-7a-0 frontend test infra bootstrap (Vitest 2.1.8 + jsdom 25.0.1 + 5 char test) + PR #1173 P7a PR-7a-1 Public Search extract (`api/public.ts` 28 LoC + 2 test) + PR #1174 P7a PR-7a-2 Admin Disk extract (`api/admin/disk.ts` 54 LoC + 2 test) + PR #1175 P7a PR-7a-3 Auth extract (`api/auth.ts` ~95 LoC + 4 test + TypeScript same-file type-ref fix) eklendi. **Phase 7a 4 PR DONE.** **Frontend characterization 13 test** (5 mevcut + 2 public + 2 admin disk + 4 auth). God-file LoC reduction sabit: extractor 1189→1019 (-170; helpers 212), retrieval 2174→1911 (-263; helpers 373), SSE 1440→1406 (-34; helpers 64); `api.ts` 2041→ ~1796 LoC tahmini (28+54+70=152 satır silindi + 12+5+4=21 satır re-export eklendi = net -131). **Toplam 137 characterization test** safety-net (backend 124 + frontend 13). **Veri güvenliği invariant — KORUNDU** (31 PR'da hiç chunk/embedding/index müdahalesi, manual rechunk/reembed/backfill, direct DB/Redis, manual production task trigger, state-changing smoke yok; **PR #1175 sırasında gerçek auth/email production action TETİKLENMEDİ** — yalnız sayfa render 200). PR #1172 + #1173 + #1174 + #1175 production behavior değişikliği YOK (function signature + endpoint + body + storage semantik özdeş; 60 caller import path DEĞİŞMEDİ). **`apiFetch` + `ApiException` + token storage + `attemptTokenRefresh` core'da KALDI.** |
| Açık karar maddesi | **Extractor boundary** (PR #1146 closure not, hâlâ açık): (1) Extractor `modules/crawler/` mi yoksa `shared/extraction/`'a mı? (2) Kernel modülleri (articles, sources) crawler middle layer'ı import edemez (master plan §3.2). (3) 3 caller hangi extractor path'inden import edecek? Phase 4 full migration öncesi karar gerek. |
| Bir sonraki adım | **B seçeneği devamı (kullanıcı 2026-05-21 onayı):** (1) **Bu closure docs v12 PR** (PR #1172 + #1173 + #1174 + #1175 cumulative + [[refactor-pr-checklist]] TypeScript same-file type-ref edge case dersi); (2) **PR-7a-4 scope analizi** (implementation YOK, sadece rapor) — `requestVerifyResend` mini-extract aday veya Admin Sources/Users analiz: location/LoC/endpoint/caller/module/dep/test/facade; rapor + öneri + DUR; (3) Sonrasında DUR — PR-7a-5/6/... extract'lar (auth-grup ya da Admin domain), Phase 6 PR-C+ (full SSE integration / RC3-B orchestrator coupling / tool-loop timeout deep), extractor boundary, Phase 8 kararına otomatik geçilmez; kullanıcı açık onayı beklenir. **Hard kurallar (P7a):** Research section'a DOKUNMA; `apiFetch`/core/token refresh TAŞIMA; caller import path DEĞİŞTİRME; auth/session behavior DEĞİŞTİRME; production auth/email action tetikleme YOK; backend code YOK; DB/Redis YOK; frontend tests + lint + type-check + build PASS hedefi korunacak. |

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
