---
type: topic
title: "Modular Monolith Transition — Refactor Retrospective (2026)"
slug: "refactor-retrospective-2026"
status: live
created: 2026-05-24
updated: 2026-05-24
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md"
  - "wiki/topics/phase8-boundary-hardening-mini-plan.md"
  - "wiki/topics/phase7a-frontend-mini-plan.md"
  - "wiki/topics/phase6-sse-prc-plus-mini-plan.md"
  - "wiki/topics/refactor-pr-checklist.md"
  - "wiki/log.md"
tags: [retrospective, refactor, modular-monolith, t6, t8, phase8, autonomous-mode, dogfooding]
aliases: [refactor-retro-2026, phase0-8-retro, modular-monolith-retro]
---

# Modular Monolith Transition — Refactor Retrospective (2026)

## TL;DR

Nodrat `apps/api` ve `apps/web` 2026-04 → 2026-05 boyunca Phase 0..8 ardışıklığıyla **modular monolith** mimari hedefine taşındı. Toplam **~80 PR** (T6/Phase 7b umbrella + Phase 8 dahil) küçük, davranış-koruyucu, scope-disiplinli adımlarla merge edildi. Temel kazanımlar: 13 → **16 import-linter contract strict** (CI-enforce), 4 frontend god-page %56 küçülme, `api.ts` 2041 → 580 LoC (core + facade), backend god-file 4'er karakterizasyon test seti (toplam **251 safety-net test**), Alembic CI hardening (disposable pgvector + upgrade head + mapper resolution + relationship-pattern AST lint). **Production data invariant** her PR'da KORUNDU; **51 docs-only deploy SKIP dogfooding** doğrulandı; otonom mod stabil çalışma için bounded foreground polling + pgvector image vb. operasyonel dersler yerleşti. **Phase 8.1+** (core/api code migration), **Phase 8.2** (ORM completion → alembic check strict gate), **PR-8b-2.5** (tests/migration/ CI wiring) ayrı sub-phase/follow-up olarak deferred. T7 cost_tracker (#1086), T8 model relocation (#1087) ön-şartlar tamamlanırsa aktif.

## Tanım / Bağlam

Bu sayfa, **2026-04 başlangıçlı Modular Monolith Transition** inisiyatifinin Phase 0'dan Phase 8b kapanışına kadar olan sürecini geriye dönük sentezler. Amacı:

- Geriye bakış: hangi kararlar tutarlıydı, hangi varsayımlar revize edildi?
- Süreç dersleri: küçük güvenli PR + scope-disciplined refactor pattern'ı nasıl şekillendi?
- Operasyonel dersler: dogfooding cycle, autonomous mode, CI/deploy operations.
- Sonraki bekleyen iş: deferred sub-phase'ler + follow-up'lar.

Kanonik kaynak [[modular-monolith-transition-master-plan]] (master plan); bu sayfa onun **özet + ders** katmanıdır. Mini-plan dosyaları ([[phase8-boundary-hardening-mini-plan]], [[phase7a-frontend-mini-plan]], [[phase6-sse-prc-plus-mini-plan]]) phase-specific detay verir.

## 1. Phase-by-phase özet

### Phase 0 — kuruluş + import-linter iskelet

Modular monolith hedefi karara bağlandı. `apps/api/pyproject.toml`'a ilk import-linter contract'ları konuldu (boş iskelet, henüz module dolmamış). Wiki katmanı kuruldu ([[modular-monolith-boundary]], [[import-direction-rules]] decision'ları). Master plan #1080 takip issue ile yazıldı.

**Karar:** [[modular-monolith-boundary]] — `app/modules/*` domain modülleri; `app/shared/*` Seviye 0 saflık; `app/core/*` ve `app/api/*` legacy katman (Phase 8 ile boşaltma kararı sonra deferred).

### Phase 1 — module iskeleti (skeleton)

`app/modules/{articles, embedding, agenda, clusters, rag, research, sft, accounts, billing, legal, prompts_admin, settings_admin, generations, public, ops}` 18 alt-paket iskelet olarak yaratıldı. Henüz facade boş; kod taşıma sonraki phase'lere ertelendi.

**Ders:** Boş iskelet bile import-linter graph'ı tutarlı kıldı; sonraki migration'larda sürpriz çıkmadı.

### Phase 2 — facade pattern + ilk migration

İlk gerçek code move: small modüllerin facade pattern'i ile aktivasyonu. `__init__.py` re-export + `README.md` her modülde.

### Phase 3 — articles + embedding + raptor + agenda migration (PR #1131-#1142)

Major file relocations:
- `admin_articles.py` → `modules/articles/admin/routes.py`
- `workers/tasks/articles.py` → `modules/articles/tasks/articles.py`
- `workers/tasks/embedding.py` → `modules/embedding/tasks/embedding.py`
- `cluster_assigner.py` safe-prep
- `raptor` → `modules/rag/tasks/raptor.py`
- `agenda` migration

Her PR ayrı + closure docs ayrı. 13 → 14 import-linter contract (embedding kurali eklendi).

**Ders ([[refactor-pr-checklist]] §1):** "Yeni ignore_imports EKLENMEZ" — migration yapılırken contract'ı zayıflatmak yerine code move ile çöz.

### Phase 4 — extractor refactor (PR #1144-#1175 trail)

Extractor primitives:
- PR-A characterization tests (`extract_body_images`)
- PR-B `modules/crawler/extractor` facade + 3 caller flip
- PR-C internal split (characterization-supported)
- **PR-D1 boundary decision (docs-only locked)** — extraction `app/shared/extraction/` Seviye 0
- **PR-D2 code move + caller flip** — `core/{extractor,_extractor_filters,structured_data}.py` → `shared/extraction/` (3 `git mv` history-preserving + 5 prod caller + 3 test flip)

**Ders:** Decision PR (D1) + Implementation PR (D2) ayrılması karmaşık boundary kararlarında netlik sağladı.

### Phase 5 — core/retrieval characterization (god-file 2174 LoC)

`core/retrieval.py` 2174 → 1911 LoC. Karakterizasyon tabanlı approach: önce 89 test (sonradan 101'e çıktı), sonra split. **Alternate criteria (ii) sign-off**: full extraction/delete yerine "characterization + helper extraction yeterli safety-net" kararı.

**Ders ([[refactor-pr-checklist]] §5):** Full extraction her zaman gerekmez; karakterizasyon + partial extraction da geçerli kapanış kriteri.

### Phase 6 — SSE refactor + PR-C+ döngüsü

`app_research_stream.py` 1416 → 1274 LoC. SSE replay coverage 10/10 senaryo + 1 bonus. PR-C+ döngüsü:
- C+1 [#1213] first-yield matrix
- C+2 [#1215] context/condense extraction → `_research_stream_context.py` 234 LoC
- C+3 [#1217] 2nd-yield positive-path char
- C+4 [#1219] RC3-B reframe-decision extraction → `_maybe_reframe_for_faithfulness`

**Phase 6 PR-C+ DONE** (closure docs v32) — alternate criteria (ii) ile **`_research_stream_body` bilinçli TAŞINMADI**; full TestClient SSE integration + tool-loop timeout + persist + negative path + RC3-B orchestrator-coupling **bilinçli deferred**.

**Ders:** Replay + helper extraction yeterli güvenlik ağı; full integration ROI yüksek değil. Her şeyi extract etme zorunluluğu yok.

### Phase 7a — frontend low-risk domain split (#1095 — 24 PR)

`apps/web/src/lib/api.ts` 2041 → 580 LoC (core + facade re-export). 24 PR ile 17 admin/account/legal/billing/research domain'i ayrı dosyalara taşındı. Her PR'da **3-8 characterization test** eklendi (cumulative ~140+ test).

**Closure ([[phase7a-frontend-mini-plan]]):** Phase 7a "teknik split DONE" — Research SSE dahil tüm domain'ler ayrıldı. #1095 CLOSED (COMPLETED).

**Ders:** Frontend split akışı sürdürülebilir. ESLint unused-import catch + tsc + next build + Vitest 107/107 invariant her PR'da koruyucu net.

### Phase 7b — frontend god-page split (#1096 — 4 alt-track DONE)

- **admin/rag** alt-track ✅ v36: 2356 → 143 LoC thin router (3 tab extract: Raptor + Benchmark + Inspector)
- **admin/queue** alt-track ✅ v39: 1035 → 885 LoC; helpers + 3 presentational subcomponent
- **admin/sft** alt-track ✅ v41: 1026 → 896 LoC; section split deferred
- **research components alternate** — already-split (8 component <400 LoC her biri)

Cumulative god-page LoC: 4417 → 1924 (~%56 küçülme). #1096 CLOSED (COMPLETED).

**Ders:** "auto-split eligible" pattern (A2 complexity gate) ile büyük tab'ler 1-2 PR'da güvenle ayrıldı. _shared.tsx pattern textbook (admin/queue 186 LoC, admin/sft 180 LoC, admin/rag tab'ler).

### Phase 8 — boundary hardening (#1097 — A 5/5 + B 5/5 ✅)

**Workstream A — import-linter contract genişletme (5 PR ✅):**

| PR | İçerik |
|---|---|
| [#1246](https://github.com/selmanays/nodrat/pull/1246) | mini-plan docs |
| [#1247](https://github.com/selmanays/nodrat/pull/1247) | `shared/extraction/site_profiles` relocation (Leak fix: `shared/extraction/extractor.py:194 → core/site_profiles`) |
| [#1248](https://github.com/selmanays/nodrat/pull/1248) | `shared/* must not import legacy core/api/models` contract |
| [#1249](https://github.com/selmanays/nodrat/pull/1249) | `ner_stats.py` → `app/shared/observability/` + 2 caller flip (`core/retrieval.py:287` + `api/admin_rag.py:651`) — **`core/* → modules/*` wrong-direction leak fix** |
| [#1250](https://github.com/selmanays/nodrat/pull/1250) | `core/* must not import modules/*` + `core/* must not import api/*` contracts × 2 |

Net: 14 → **16 import-linter contract strict CI-enforce**, 2 boundary leak relocation + kural lock.

**Workstream B — Alembic CI + T8 preconditions (5 PR ✅):**

| PR | İçerik |
|---|---|
| [#1251](https://github.com/selmanays/nodrat/pull/1251) | `alembic-check` job DB-based: disposable `pgvector/pgvector:pg16` + `alembic upgrade head` + **3 ORM model __init__ registration bug fix** (EvalRun, ResearchCluster, MessageCluster) |
| [#1253](https://github.com/selmanays/nodrat/pull/1253) | `env.py` `include_object` filter + 4 raw-SQL allowlist (article_chunks, chat_cache_telemetry, entities, pmf_survey_responses); **`alembic check` step EKLENMEDİ** — Phase 8.2 deferred |
| [#1254](https://github.com/selmanays/nodrat/pull/1254) | `tests/migration/test_fresh_upgrade.py` 3 integration test (pg_container fixture reuse; CI wiring → 8b-2.5) |
| [#1256](https://github.com/selmanays/nodrat/pull/1256) | `tests/unit/test_mapper_resolution.py` 3 pure-unit test CI'da PASSED (configure_mappers() + __tablename__ + count ≥25) |
| [#1258](https://github.com/selmanays/nodrat/pull/1258) | `scripts/lint_relationship_pattern.py` 113 LoC AST guard + `api-lint` step (T8 ön-şart 1 statik regression guard) |

**Phase 8.2 deferred sub-phase** (yeni ayrı issue önerilir): ORM completion → `alembic check` strict gate enable (3 pgvector VECTOR(1024) kolonu + 30+ `__table_args__` Index + 5+ UniqueConstraint + 6+ comment + 1 nullable mismatch). Detay: [[project-alembic-orm-drift]] (memory referansı; ayrıca PR-8b-1.5 #1253 CI run #26347227886 dump).

**Workstream C** (docs/retrospective) — bu PR (8c-1) ile retrospective yayınlanıyor. 8c-2/3/4 kullanıcı `docs/` yetki gerek.

**Workstream D** (code migration: `core/*` + `api/*` boşaltma) — **DEFERRED → Phase 8.1+ ayrı issue** (148+15 import sitesi T6+P7b'den büyük scope; alternate criteria (ii) ile #1097 kapanışı önerilir).

## 2. Kurumsal kararlar (cross-phase pattern'lar)

### 2.1 Alternate criteria (ii) acceptance pattern

Phase 5 (retrieval) + Phase 6 (PR-C+) + Phase 8 (D workstream code migration) — üçünde de "tam silme/taşıma" yerine "characterization + helper extraction + strict contract + docs" yeterli safety-net olarak kabul edildi. **Sebep:** ROI eğrisinin tepe noktası: %80 değer ilk %20 işle, kalan %80 iş %20 marjinal değer üretir. Alternate criteria (ii) bu noktada DUR + ayrı initiative aç.

### 2.2 Decision PR + Implementation PR ayrımı

Phase 4 PR-D1 (decision) + PR-D2 (implementation) örnek. Karmaşık boundary kararlarında **karar docs-only** (rollback ucuz) + **implementation behavior-preserving** ayrımı netlik sağladı.

### 2.3 Mini-plan + Closure docs disiplini

Her phase başlangıcında **mini-plan docs PR** (scope + PR sırası + risk matrisi + smoke disiplin), her büyük PR sonrası **closure docs PR** (log + master plan §13 + mini-plan progress + index istatistik). Bu meta-overhead her phase'in zorunlu bir parçası — wiki katmanı her zaman güncel kalıyor + paralel worktree agent'ları için tek doğruluk kaynağı.

### 2.4 Behavior-preserving invariant

Refactor PR'ları **davranış değiştirmez** kuralı sıkı korundu. Production data invariant ([[feedback_embedding_rag_index_safety]]) hiçbir PR'da ihlal edilmedi: embedding/chunk/RAG index/vector kayıtları silinmedi, truncate edilmedi, toplu reprocess/rechunk/reembed yapılmadı.

### 2.5 Dogfooding cycle (docs-only deploy SKIP)

Her closure docs PR'ında deploy.yml davranışı gözlemlendi: `Detect job` `skip_deploy=true` → `Deploy to VPS` job **skipped** → production state untouched. **51 docs-only deploy SKIP dogfooding** doğrulandı. Bu mekanizma feature PR'ı bloklasa bile docs sync hızlı + güvenli iterasyon imkânı verdi.

## 3. Süreç dersleri ([[refactor-pr-checklist]] sentez)

`refactor-pr-checklist.md` 80+ Phase 3..8 dersi içeriyor. Buradaki en kritik 10:

1. **Transitive caller chain audit** — A → B move yapılırken B'yi çağıran C, D, ... grep edilmeli; aksi takdirde import path bozulur.
2. **File-path string** — string-form module path'ler (örn. `"app.modules.articles"`) `celery_app.py include`'da kullanılır; grep+update zorunlu.
3. **Namespace import** — `from x import *` kullanan dosyalar audit edilmeli (`models/__init__.py` PR-8b-1 örneği: 3 model atlanmış → `alembic check` catch etti).
4. **Smoke dili** — "production state untouched" ifadesi smoke read-only'se kullanılır; create-then-delete varsa "restored" derken FK + transaction discipline dikkat.
5. **Backward-compat argümanı** — sadece **external sözleşmeler** (API/URL/istemci/KVKK) için. Internal registry/enum string'leri için "backward-compat amaçlı koru" yanlış ([[feedback_backward_compat_argument]]).
6. **TypeScript same-file type-ref** — extract sonrası `import { Type } from "./X"` (X aynı dosyada değil) → tsc kırılır; type-ref'ler de takip edilmeli.
7. **CI auto-trigger anomaly** — ci.yml workflow_dispatch eklenmesi gerekti (PR #1134), aksi takdirde main'e bazı push'lar CI tetiklemiyor.
8. **Backend code/test deploy** — `apps/api/` (test-only DAHİL) PR FULL 17-step deploy tetikler; docs-only gibi SKIP DEĞİL. Detect gate `apps/api/` genelini yakalıyor.
9. **Worktree git disiplini** — kod fix branch'i dosyaları worktree path'inden düzenle + git worktree cwd'de; `cd /primary` YAPMA → commit yanlış branch'e düşer ([[feedback_worktree_git_discipline]]).
10. **Backend deploy timing** — `pyproject.toml` değişiyorsa Docker layer cache miss → image rebuild ~15 dk; düşük-touch değişiklik ~5 dk. Plan bunu hesaba kat.

## 4. Otonom mod dersleri (Phase 8 turunda yerleşti)

Phase 8 başlangıcında kullanıcı **otonom mod** talimatı verdi: "Hard blocker, gerçek incident veya boundary karar çatışması dışında durma." Bu süreçte yerleşen operasyonel dersler:

1. **Bounded foreground polling >>> silent background loop.** Initial PR-7b-8'de background `until ... done &` poller silently SIGPIPE ile öldü; CI fail görünmedi. **Çözüm:** foreground `for i in $(seq 1 N); do sleep 30; check; done` + auto-rerun transient flake. Memory: [[feedback_benchmark_artifact_before_restart]] benzeri operasyonel disiplin.
2. **CI image gereksinimi** — pgvector image'ı (PR-8b-1 iteration #2: `postgres:16` → `pgvector/pgvector:pg16`). Genel kural: CI service container'ları prod'da kullanılan `CREATE EXTENSION`'ları desteklemeli.
3. **Test location strategic** — `tests/unit/` mevcut `api-unit-tests` job otomatik collect ediyor; `tests/migration/` ayrı CI wiring gerek (PR-8b-2 gap → PR-8b-2.5 follow-up).
4. **Scope-shrink pattern** — beklenenden büyük drift/iş çıkarsa PR'ı scope-shrunk et + follow-up çıkar (PR-8b-1.5 alembic check → Phase 8.2 deferred). Bütün işi tek PR'a sığdırmaya çalışma.
5. **3-yol soru → kullanıcı seçer.** Mimari karar gerektiren noktada (Phase 8.2 ORM completion stratejisi) **boundary karar çatışması** = DUR + `AskUserQuestion` ile seçenek sun. Otonom mod = adım atma, **karar verme** değil.
6. **Issue/PR sync disiplini.** Closure docs PR'ında log + master plan §13 + mini-plan + index hepsi senkron; ayrıca bidirectional backlink ([[feedback_wiki_sync_completeness]]).
7. **Memory > guess.** Bilinmeyen state'i tahmin etme; `gh pr view --json`, `gh run view --log`, `docker compose ps` ile doğrula. Kullanıcı teknik doğrulama yapamaz ([[feedback_user_cannot_verify_tech]]); kanıtı agent üretir.

## 5. Alembic drift bulgusu (PR-8b-1.5 detay)

Phase 8b'nin en önemli yan-bulgusu: `alembic check` (autogenerate diff guard) Nodrat'ta **mevcut haliyle enable edilemez** — ORM modelleri migration-applied schema'nın **eksik temsili**. PR-8b-1.5 CI run #26347227886'da 50+ baseline drift item ortaya çıktı:

- **3 pgvector VECTOR(1024) kolonu** ORM'de yok: `agenda_cards.embedding`, `articles.summary_embedding`, `event_clusters.embedding`
- **30+ index** `__table_args__`'da deklare değil
- **5+ UniqueConstraint** missing
- **6+ modify_comment** ops
- **1 modify_nullable** mismatch

Bu, multi-PR **Phase 8.2 ORM Completion** sub-phase'i — tek PR'a sığmaz, ayrı issue önerilir. Detay memory: `project_alembic_orm_drift.md`.

**Pozitif yan:** PR-8b-1 alembic-check job 3 ORM `__init__.py` registration bug catch etti (EvalRun, ResearchCluster, MessageCluster); bu drift detection gate'in CI'da gerçekten değer ürettiğinin ilk kanıtı. Phase 8.2'de strict alembic check enable edildiğinde benzer regression net'ler yakalanacak.

## 6. Deferred + follow-up tablosu (Phase 8 sonrası)

| Item | Kapsam | Tetik | Status |
|---|---|---|---|
| **Phase 8.1+** | `core/*` + `api/*` code migration (148+15 import sitesi) → sub-phase'lere bölünmüş | Phase 8 closure sonrası yeni issue | DEFERRED |
| **Phase 8.2 ORM Completion** | 3 pgvector cols + 30+ Index + 5+ constraint + comments + nullable → alembic check strict gate enable | Ayrı issue | DEFERRED |
| **PR-8b-2.5** | `tests/migration/` CI wiring (api-unit-tests sadece tests/unit/ alır) | Workstream B follow-up | OPEN |
| **8c-2/3/4** | `docs/engineering/{refactor-playbook,observability-runbook,modular-monolith-architecture}` refresh | Kullanıcı `docs/` yetki gerek | BLOCKED-on-permission |
| **T7 cost_tracker** | [#1086](https://github.com/selmanays/nodrat/issues/1086) | Kullanıcı önceliği | OPEN |
| **T8 model relocation** | [#1087](https://github.com/selmanays/nodrat/issues/1087) — 5 ön-şart | Phase 8 + 8.2 sonrası | OPEN/BLOCKED |
| **Full TestClient SSE integration** | Phase 6 bilinçli deferred | Future initiative | DEFERRED |
| **Section split (admin/queue + admin/sft)** | Phase 7b _shared.tsx pattern devamı | Future | DEFERRED |

## 7. Sayısal sonuç

| Metric | Önce | Sonra |
|---|---|---|
| import-linter contract (strict CI-enforce) | 13 | **16** (Phase 8 A: +3) |
| `api.ts` (frontend) | 2041 LoC | 580 LoC (core + facade re-export) |
| 3 admin god-page (cumulative) | 4417 LoC | 1924 LoC (~%56 küçülme) |
| `app_research_stream.py` (SSE) | 1416 LoC | 1274 LoC |
| `core/retrieval.py` | 2174 LoC | 1911 LoC |
| `core/extractor.py` | 1189 LoC | 1019 LoC + relocated to `shared/extraction/` |
| Backend characterization test | ~0 | **141** (4 god-file char) |
| Frontend characterization test | 0 | **110** |
| Toplam safety-net test | 0 | **251** (backend 141 + frontend 110) |
| Alembic CI hardening | offline-only | DB-based pgvector + upgrade head + 3 model fix |
| New unit tests (PR-8b-3 mapper_resolution) | — | 3 |
| Lint guards (PR-8b-4 relationship-pattern) | — | scan 19 model file |
| Docs-only deploy SKIP dogfooding | 0 | **51 ✅** |
| Production data invariant | KORUNDU | KORUNDU |
| 80+ PR cumulative | — | merge + deploy + smoke 100% green |
| Wiki sayfa | (önceki snapshot) | 180 (16 entity + 30 concept + 21 topic + 75 decision + 35 source + 1 plan + 3 hub) |

## 8. Açık sorular / TODO

- **Phase 8 closure kararı:** alternate criteria (ii) ile #1097 close mı, yoksa Workstream C tamamlanana kadar açık mı kalsın? — kullanıcı tercihi (closure assessment'ta belgelenecek).
- **Phase 8.2 ORM Completion** zamanlaması — T8'in **ön-şartı**; T8 önceliği geldiğinde başlatılır.
- **PR-8b-2.5 CI wiring** — alembic-check job'a `pytest tests/migration/` step ekle veya yeni "API migration tests" job (docker + testcontainers).
- **Docs/engineering refresh** (8c-2/3/4) — kullanıcı `docs/` yetki açar açmaz başlatılabilir.

## İlişkiler

- [[modular-monolith-transition-master-plan]] (kanonik plan — bu sayfa özet+ders katmanı)
- [[phase8-boundary-hardening-mini-plan]] (Phase 8 detay)
- [[phase7a-frontend-mini-plan]] (Phase 7a 24 PR detay)
- [[phase6-sse-prc-plus-mini-plan]] (Phase 6 PR-C+ detay)
- [[refactor-pr-checklist]] (80+ cross-phase ders)
- [[modular-monolith-boundary]] (Phase 0 decision)
- [[import-direction-rules]] (Phase 0 decision)
- [[models-flat-until-conditions]] (T8 ön-şart kararı)

## Kaynaklar

- [`wiki/plans/modular-monolith-transition-master-plan.md`](../plans/modular-monolith-transition-master-plan.md) — §8.1 phase tablosu, §12.3 decision changelog, §13 status board, §14 phase retrospectives
- [`wiki/log.md`](../log.md) — v1..v47 closure entries (kronolojik)
- 80+ merged PR closure entries (#1131-#1259)
