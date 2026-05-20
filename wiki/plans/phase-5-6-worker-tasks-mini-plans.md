---
title: "Phase 5/6 Worker Tasks Mini Plans (mini-plan-only, implementation YOK)"
type: plan
slug: phase-5-6-worker-tasks-mini-plans
status: live
created: 2026-05-21
updated: 2026-05-21
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md §12.3"
  - ".github/ISSUE_TEMPLATE/refactor.md"
tags:
  - modular-monolith
  - phase-3
  - phase-5
  - phase-6
  - mini-plan
aliases:
  - phase-5-6-mini-plans
  - worker-tasks-mini-plans
---

# Phase 5/6 Worker Tasks Mini Plans

> **TL;DR:** Phase 3 modüler migration cycle (sources/articles/embedding + ops/maintenance) tamamlandı. Kalan 3 worker task — `agenda.py`, `cluster_assigner.py`, `raptor.py` — Phase 5/6 god-file/scope-expansion kapsamına girer; kullanıcı kuralı gereği **mini plan only**. Bu sayfa scope analizi + risk değerlendirmesi + önerilen yaklaşımı kayıt altına alır. Implementation kullanıcı talimatı bekler.

## Bağlam

Phase 3 cycle özet (2026-05-21):

| Migration | PR | Status |
|---|---|---|
| Shared worker DB/session helpers | [#1126](https://github.com/selmanays/nodrat/pull/1126) | ✅ merged |
| modules/sources | [#1127](https://github.com/selmanays/nodrat/pull/1127) | ✅ merged |
| sources → articles Celery decoupling | [#1130](https://github.com/selmanays/nodrat/pull/1130) | ✅ merged |
| modules/articles + embedding decoupling | [#1131](https://github.com/selmanays/nodrat/pull/1131) | ✅ merged |
| modules/embedding | [#1133](https://github.com/selmanays/nodrat/pull/1133) | ✅ merged |
| CI recovery (workflow_dispatch) | [#1134](https://github.com/selmanays/nodrat/pull/1134) | ✅ merged |
| modules/ops/tasks/maintenance | [#1137](https://github.com/selmanays/nodrat/pull/1137) | ✅ merged |

**Import-linter:** 13 kept, 0 broken (muafiyetsiz).
**`workers/tasks/` kalan:** `agenda.py`, `cluster_assigner.py`, `raptor.py`.

Her biri **risk profili** veya **scope** sebebiyle Phase 5/6 kapsamına alınır; bu sayfa mini planlarını sunar.

## 1. `agenda.py` → `modules/generations/tasks/agenda.py` (Phase 6)

### Scope

- **Dosya:** `apps/api/app/workers/tasks/agenda.py` (537 LoC)
- **Task names (3):**
  - `tasks.agenda.generate_agenda_card` (line 318)
  - `tasks.agenda.refresh_active_cards` (line 361, bind=True)
  - `tasks.agenda.backfill_country` (line 535, bind=True)
- **Queue:** `tasks.agenda.* → event_queue`
- **Beat:** `refresh-agenda-cards` (saatlik), `backfill-country` schedule var
- **Caller surface:**
  - `app/api/admin_rag.py:897` lazy `_backfill_country_async` (production)
  - `app/modules/clusters/tasks/clustering.py:113, 140` lazy `generate_agenda_card` (production, **cross-domain chain**)
  - `tests/unit/test_country_backfill.py:5` module-level
- **Module-level imports:**
  - `app.models.agenda.AgendaCard`, `app.models.event.EventCluster` (flat models)
  - `app.prompts.{agenda_card, country_backfill}` (legacy)
  - `app.providers.{base, registry}` (provider layer)
  - `app.core.cost_tracker` (legacy)

### Risk

**🔴 YÜKSEK — boundary contract ihlali doğurur:**

- `modules.clusters → workers.tasks.agenda` direct lazy edge mevcut (`clusters/tasks/clustering.py:113, 140`)
- agenda **generations** modülüne taşınırsa: `modules.clusters → modules.generations` edge oluşur
- **Clusters contract:** `forbidden=[rag, generations]` (pyproject.toml) — **BROKEN olur**

### Önerilen yaklaşım

**A1 deseni: send_task decoupling kaynak Python import'unu kaldırır:**

1. **Pre-step (agenda migration ÖNCE):** clusters/tasks/clustering.py:113, 140 lazy `from app.workers.tasks.agenda import generate_agenda_card` → `celery_app.send_task("tasks.agenda.generate_agenda_card", args=[...])`
2. **Pre-step:** admin_rag.py:897 lazy `_backfill_country_async` direct call'i de evaluate; bu *async helper*, decoupling karmaşık olabilir (lokal function call gibi davranır, Celery send_task'a göndermek yapısal değişim)
3. **Step:** agenda.py → `modules/generations/tasks/agenda.py` git mv
4. **Step:** test caller update
5. **Yeni contract:** `generations/ must not import upper layers` veya benzer (forbidden listede ne olmalı?)

### Caveat

- `app.models.agenda.AgendaCard` model: agenda generations'a taşınırsa model dosyası nerede kalır? Master plan kuralı: **models flat (Faz N+1'e kadar)** → modeller `app/models/` altında kalır (sources/articles/embedding deseni).
- `admin_rag.py:897 _backfill_country_async` direct call — async helper, send_task ile decouple etmek async signature uyumsuzluğu yaratır (send_task fire-and-forget; helper ise Future bekler). **Ek tasarım kararı gerek.**

### Boundary ek pre-flight

- Master plan §12.2 "(Faz 6) generations → sft import yönü kararı" zaten açık; agenda Phase 6'da generations'a girince benzer transitif chain riskleri kontrol edilmeli.

### Risk → mini plan only

Scope expansion + cross-domain decoupling + admin_rag async helper karmaşıklığı + yeni contract tasarımı → **kullanıcı kuralı: god-file/scope-expansion sadece mini plan only, implementation YASAK.**

## 2. `cluster_assigner.py` → `modules/generations/tasks/cluster_assigner.py` (Phase 6)

### Scope

- **Dosya:** `apps/api/app/workers/tasks/cluster_assigner.py` (350 LoC)
- **Task names (2):**
  - `tasks.research_clustering.assign` (line 71)
  - `tasks.research_clustering.refine_hierarchy` (line 275)
- **Queue:** `tasks.research_clustering.* → embedding_queue`
- **Beat:** `research-cluster-assign`, `research-hierarchy-refine` (master plan'da listelenmiş)
- **Caller surface:** Grep production caller bulamadı (Beat schedule'dan dispatch ediliyor). Lazy import yok.

### Bağlam (master plan §2.4 revize)

- `research_clustering` Pivot Faz 3 (#1015) kullanıcı araştırma kümeleme; **article-event clustering'den (modules/clusters) AYRI**, generations domain'ine ait.
- `models/research_cluster.py` ownership clusters → generations'a kaydırıldı (master plan §2.4 revize).
- Phase 6 generations migration kapsamında `cluster_assigner.py` + `research_clustering.py` (core) + `app_research.py` (route) birlikte ele alınır.

### Risk

**🟡 ORTA — Phase 6 büyük scope:**

- Direct edge yok (Beat string-bound), boundary ihlali doğurmaz
- AMA: generations Phase 6 büyük migration; sadece cluster_assigner taşınamaz — `research_clustering.py` (core, 164 LoC) + `app_research.py` + `app_research_stream.py` (T6 #1085 god-file: 1440 LoC SSE) tüm zinciri birlikte taşınır

### Önerilen yaklaşım

- Phase 6 generations migration tek atomik PR olamaz (1440 LoC SSE god-file + 164 LoC clustering + 350 LoC assigner + admin_research.py + frontend research/* + diğer)
- **god-file facade-first → characterization → kademeli split pipeline** gerekir (T6 #1085 kapsamı)
- Cluster_assigner alone migration: app_research_stream Phase 6 öncesi izole işlem; ama Phase 6 generations bağımsızlığını kırarsa boundary risk doğar

### Risk → mini plan only

god-file facade-first pipeline + Phase 6 büyük scope → **mini plan only**.

## 3. `raptor.py` → `modules/rag/tasks/raptor.py` (Phase 5)

### Scope

- **Dosya:** `apps/api/app/workers/tasks/raptor.py` (460 LoC)
- **Task names (1):**
  - `tasks.raptor.build_weekly_summary_cards` (line 458, bind=True)
- **Queue:** Master plan §13'te `tasks.raptor.* → event_queue` (kontrol edilecek)
- **Beat:** `build-weekly-summary-cards` (haftalık)
- **Caller surface:** Beat string-bound dispatch (production caller'lar grep ile bulundu mu kontrol edilecek pre-flight'ta)

### Bağlam (master plan)

- RAPTOR-Lite hierarchical clustering — RAG retrieval kapsamı (#182)
- T6 #1085 god-file listesinde `core/retrieval.py` (2174 LoC) Phase 5 — RAPTOR-Lite bunun parçası mı, ayrı mı belirsiz
- Master plan §14 Phase 5 retrospective'i henüz yazılmadı (Phase 5 başlamadı)

### Risk

**🟡 ORTA-YÜKSEK — RAG facade-first pipeline kapsamı:**

- `core/retrieval.py` 2174 LoC god-file (T6 #1085 Phase 5)
- raptor.py + retrieval.py + admin_rag.py + frontend rag-page.tsx birlikte ele alınmalı
- facade-first → characterization → kademeli split gerek

### Önerilen yaklaşım

- Phase 5 RAG migration **god-file facade strategy** ile başlar (T6 #1085 checklist):
  1. `core/retrieval.py` için facade kur
  2. Characterization test pack stable green
  3. Internal split: pure → stateless → orchestrator
  4. Snapshot diff = 0
  5. Legacy file deleted in final split PR
- raptor.py bu pipeline'ın **alt-parça**sı; bağımsız migration **risk** taşır (RAG retrieval ile coupling belirsizlik)

### Risk → mini plan only

god-file facade strategy gerekir → **mini plan only**.

## Ortak risk değerlendirmesi

| Faktör | agenda.py | cluster_assigner.py | raptor.py |
|---|---|---|---|
| LoC | 537 | 350 | 460 |
| Direct caller (production) | 2 (admin_rag + clusters) | 0 (Beat) | 0 (Beat) |
| Boundary ihlali doğurur mu? | **EVET** (clusters→generations) | Hayır | Hayır |
| god-file dependency | Hayır | Phase 6 SSE god-file | Phase 5 retrieval god-file |
| Migration türü | A1 decoupling + git mv + yeni contract | god-file facade pipeline | god-file facade pipeline |
| Phase | 6 | 6 | 5 |
| Kullanıcı kuralı | **mini plan only** | **mini plan only** | **mini plan only** |

## Veri güvenliği invariant (her 3 mini plan için geçerli)

Phase 5/6 implementation'ları başladığında:

- Existing chunks/embeddings/vector kayıtlarına müdahale **YOK**
- TRUNCATE/DELETE/UPDATE batch **YOK**
- Bulk reprocess/rechunk/reembed **YOK**
- Manuel admin trigger smoke'ta **YOK**
- Direct DB/Redis manipulation **YOK**
- Pre-existing per-article behavior preserved, not modified

`agenda.py` özelinde:
- `_backfill_country_async` background process; mevcut idempotent batch davranışı korunur
- `refresh_active_cards` Beat-driven; manuel tetiklenmez

`cluster_assigner.py` özelinde:
- Beat-driven assign + refine_hierarchy; manuel tetiklenmez
- research_cluster DB tablosu cluster_assigner tarafından mutate edilir (UPSERT) — bu pre-existing davranış, migration'da dokunulmaz

`raptor.py` özelinde:
- `build_weekly_summary_cards` haftalık Beat; manuel tetiklenmez
- RAPTOR hierarchical clustering chunk-based aggregation; existing chunks dokunulmaz

## Açık sorular (kullanıcı kararı için)

1. **agenda.py:** Phase 6 generations migration ne zaman? Önce A1 decoupling pre-PR'ı mı yoksa atomik full migration mu?
2. **cluster_assigner.py:** Phase 6 generations migration'ın parçası mı (atomik), yoksa cluster_assigner-only pre-migration mı?
3. **raptor.py:** Phase 5 RAG facade-first pipeline ne zaman başlar? T6 #1085 5 god-file öncelik sırası ne?
4. **Generations domain yeni contract:** `generations/ must not import upper layers` veya başka? Forbidden listesi ne olmalı?

## İlişkiler

- [[modular-monolith-transition-master-plan]] §12.2 (açık sorular) + §13 (status table)
- [[refactor-pr-checklist]] §6.9 (transitif chain) + §13 (CI auto-trigger anomaly)
- [[god-file-facade-first]] (T6 #1085 issue kaynağı)
- [[no-internal-backcompat-aliases]] (cleanup discipline)
- T6 [#1085](https://github.com/selmanays/nodrat/issues/1085) — god-file facade strategy tracking
- P5 [#1093](https://github.com/selmanays/nodrat/issues/1093) — Phase 5 RAG issue
- P6 [#1094](https://github.com/selmanays/nodrat/issues/1094) — Phase 6 generations issue

## Kaynaklar

- [wiki/plans/modular-monolith-transition-master-plan.md](modular-monolith-transition-master-plan.md) §12.3 + §13
- [wiki/decisions/god-file-facade-first.md](../decisions/god-file-facade-first.md)
- [docs/engineering/refactor-playbook.md](../../docs/engineering/refactor-playbook.md) §3 (god-file split discipline)
