---
type: topic
title: "T7 Cost-Tracker Core-Consumer Cleanup Mini-Plan"
slug: "t7-cost-tracker-core-consumer-cleanup-mini-plan"
status: planned
created: "2026-05-28"
updated: "2026-05-28"
github_issue: "https://github.com/selmanays/nodrat/issues/1086"
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§2.4"
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
  - "wiki/topics/t8-model-relocation-mini-plan.md"
  - "wiki/topics/refactor-pr-checklist.md"
tags: ["t7", "core-consumer-cleanup", "modular-monolith", "phase-8", "t8-prerequisite"]
aliases: ["T7 core consumer cleanup", "T7 cost_tracker initiative"]
---

## TL;DR

**T7 = core-consumer cleanup initiative** — `apps/api/app/core/` altında modeller'i import eden 7 dosyayı uygun `modules/<x>/services/`'e taşır. v77/v78/v82'de T8 SOFT CEILING (~45%) sebep olan `core/* must not import modules/*` import-linter contract ihlalini ortadan kaldırır. Tamamlandığında T8 ilerleme ~45% → ~75-82% (6-8 model unblock). 7 sub-PR (T7-1..T7-7), en düşük riskli LOW PR'larla başlar, en yüksek riskli HIGH (deps 24 caller) sonda.

> **⚠️ v84 PROOF DÜZELTMESİ (2026-05-28):** İki başlangıç premise'i yanlış çıktı:
> 1. **`Base` `app/core/db.py:18`'de** (`app/models/base.py` DEĞİL — bu dosya mevcut değil).
> 2. **T7-0 Base relocation cost_tracker'ı (T7-6) UNBLOCK ETMİYOR.** cost_tracker bir model (ProviderCallLog) import ediyor; shared/'a taşınırsa `shared/* must not import legacy core/api/models` (contract 14) / `shared/* must not import from modules/*` (contract 1) ihlali doğar — Base konumundan bağımsız. T7-0'ın gerçek faydası **email (T8-9) unblock** (email.py yalnız Base import eder).
> 3. **T7-0 full migration 22 import site > 8 caller budget (hard-stop #14)** + metadata identity nedeniyle split EDİLEMEZ.
>
> **Karar (v84):** T7-0 **DEFERRED** (email unblock prereq olarak; cost_tracker için değil). T7-6 cost_tracker **REDESIGN REQUIRED** (model-import-in-shared sorunu). **T7-1 plan_features SIRADAKI** (T7-0'dan bağımsız, LOW).

## 1. Neden T7 şimdi kritik?

v82 closure ile T8 model relocation initiative **SOFT CEILING ~45%** seviyesine ulaştı. Remaining 12 model'in **10'u BLOCKED** (5 hard-stop tetiği — kümülatif v77+v78+v80+v82):

1. **v77 — `core/* must not import modules/*`** (direct) → 7 model BLOCKED
2. **v78 — POISONED facade transitive** → facade workaround YOK
3. **v82 — domain modules → forbidden contract** → 2 model BLOCKED (failed_job + admin_audit_log → ops)
4. **v80 — shared/* Base prerequisite** → 1 model BLOCKED (email)
5. **v78 user rule — caller > 8** → article (13 caller) sub-PR split gerek

**T7 = tek unblock yolu** — core/ dosyalarını modules/'a taşımak `core/* must not import modules/*` contract'ı için kaynak (core/) tarafında çözüm. Bir kez core/ konsumcuları yok olunca, T8 BLOCKED modeller serbest kalır.

**T7 olmadan article sub-PR split düşük getirili** — article 1 model unblock (10/22 → 11/22), T7 ise 6-8 model unblock (10/22 → 16-18/22).

## 2. Scope dışı olanlar

T7 mini-plan **YALNIZ** şunu kapsar:

- 7 core/ dosyasını uygun `modules/<x>/services/`'e taşıma
- Her dosyanın caller'larını yeni path'e flip
- Import-linter contract korunması (16/16 KEPT)

T7 **kapsamı DEĞİL**:

- `app.models.base.Base` relocation (T7-6 cost_tracker için potansiyel prereq — ayrı mini-plan gerekirse)
- T8 model relocation (T7 sonrası T8 cycle devam eder)
- Phase 8.1+ core/api code migration (T7+T8 sonrası alternative initiative)
- Phase 8.3 raw-SQL → ORM stub (HIGH risk embedding; ayrı initiative)
- `core/db.py` (`get_db`, `get_session_factory`) — infra, taşınmaz
- `core/security.py` (`decode_token`) — infra, taşınmaz
- `core/http_client.py` — infra, taşınmaz
- `app.config.get_settings` — infra, taşınmaz
- Yeni feature ekleme veya behavior change

## 3. Core consumer audit tablosu

| # | core/ dosya | LoC | Model imports (line + lazy/eager) | Downstream caller count | Önerilen hedef |
|---|---|---|---|---|---|
| 1 | `cost_tracker.py` | 165 | `provider_log.ProviderCallLog` (35, eager) | 9 | **`modules/ops/services/`** (BUT v82 risk) veya alternative |
| 2 | `plan_features.py` | 85 | `billing.Plan,Subscription` (22, eager) + `user.User` (23, eager) | 2 | `modules/billing/services/` |
| 3 | `quota.py` | 254 | `generation.UsageEvent` (33, eager) | 2 | `modules/billing/services/` |
| 4 | `deps.py` | 159 | `user.User` (20, eager) | **24** | `modules/accounts/deps.py` |
| 5 | `research_cache_telemetry.py` | 134 | `research_cache_telemetry.ResearchCacheTelemetry` (95, **LAZY**) | 2 | `modules/generations/services/` |
| 6 | `conversation_context.py` | 473 | `conversation.Conversation,Message` (26, eager) | 4 | `modules/generations/services/` |
| 7 | `polling_tier.py` | 247 | `source.Source` (28, eager) | 2 | `modules/sources/services/` |

## 4. Target ownership decisions

| Hedef | İçindeki dosyalar | Neden bu modül |
|---|---|---|
| `modules/billing/services/` | `plan_features.py`, `quota.py` | Plan/Subscription/UsageEvent = billing domain logic |
| `modules/accounts/deps.py` | `deps.py` | User/Session auth dependency = accounts domain |
| `modules/generations/services/` | `research_cache_telemetry.py`, `conversation_context.py` | Research stream telemetry + Conversation context = generations upper layer |
| `modules/sources/services/` | `polling_tier.py` | Source polling tier business logic = sources domain |
| `modules/ops/services/` (risky) | `cost_tracker.py` | Provider call cost telemetry = ops cross-cutting; **ANCAK v82 contract analog'u (domain modules → ops) tetiklenebilir** |

**T7-6 (cost_tracker) için 4 alternatif:**

- **Option A — `shared/observability/services/cost_tracker.py`:** shared/* Base prereq (v80 email lesson tekrar tetiklenir) → Base relocation gerek
- **Option B — `modules/ops/services/cost_tracker.py`:** v82 contract analog'u (modules/embedding, modules/generations, modules/rag → ops yasak) → 4 caller içinde 3'ü BLOCKED
- **Option C — yeni `apps/api/app/telemetry/cost_tracker.py`:** yeni cross-cutting paket — mimari karar gerek (Phase 8 boundary planı dışında)
- **Option D — Base relocation prereq + Option A:** En temiz; `app.models.base.Base` → `app.shared.db.base.Base`; tüm modeller `from app.shared.db.base import Base` kullanır; ayrı PR'da

**Önerilen:** Option D (Base relocation prereq). Bu T7-0 olarak ekleniyor (T7-0 Base relocation → T7-1..T7-7 cleanup).

## 5. PR Sequence

| PR | Scope | Risk | Files | Hard-stop riski | T8 unblock |
|---|---|---|---|---|---|
| ~~**T7-0** (prereq)~~ 🛑 **DEFERRED v84** | `Base` (`app/core/db.py:18`) → `app/shared/db/base.py`; **22 import site** | MED | **22 dosya (hard-stop #14 > 8; un-splittable)** | metadata identity / double-registration v69; un-splittable | **email (T8-9) unblock — cost_tracker DEĞİL** (proof v84) |
| **T7-1** ✅ **DONE v85** | `plan_features.py` → `modules/billing/services/` | LOW | 5 dosya | — | T8-16 partial (plan consumer kaldırıldı) — PR [#1329](https://github.com/selmanays/nodrat/pull/1329) `6ef78a4`; 8/8 pre-flight + FULL deploy + /health=200 |
| **T7-2** ✅ **DONE v86** | `quota.py` → `modules/billing/services/` | LOW | 4 dosya | — | **T8-16 + T8-17 full billing unblock** — PR [#1331](https://github.com/selmanays/nodrat/pull/1331) `c6ae884`; 8/8 pre-flight + FULL deploy + /health=200; **T7-1+T7-2 billing cleanup TAM** |
| **T7-3** ✅ **DONE v87** | `polling_tier.py` → `modules/sources/services/` | LOW | 5 dosya | — | **T8-11 (sources 3 model) unblock** — PR [#1333](https://github.com/selmanays/nodrat/pull/1333) `4e470da`; 8/8 pre-flight + FULL deploy + /health=200; NEW `services/` alt-paket + patch.object test-mock dersi (purge-list A-grubu) |
| **T7-4** 🔵 **SIRADAKI** | `research_cache_telemetry.py` → `modules/generations/services/` | LOW | 4 dosya | Düşük (LAZY import — en düşük risk) | T8-15 (ResearchCacheTelemetry) |
| **T7-5** | `conversation_context.py` → `modules/generations/services/` | MED | 6 dosya | Düşük | T8-10 (Conversation+Message → conversations YENİ modül) |
| **T7-6** 🔴 **REDESIGN REQUIRED v84** | `cost_tracker.py` → ??? (shared/observability OLAMAZ — model import) | MED-HIGH | ~12 dosya | model-import-in-shared (contract 14/1); v82 caller (modules→ops) | T8-7 partial (ProviderCallLog) — ayrı redesign sonrası |
| **T7-7** | `deps.py` → `modules/accounts/deps.py` | **HIGH** | 24+ caller — **sub-PR split zorunlu** | Düşük (modules → accounts izinli) | T8-21 (User+Session — 28 caller HIGH risk Wave D) |

> **v84 T7-0 deferred + T7-6 redesign:** T7-0 (Base relocation) gerçek değeri email (T8-9) unblock; cost_tracker (T7-6) için prereq DEĞİL. T7-6 cost_tracker shared/ olamaz (model import → contract 14/1 ihlali). T7-6 redesign opsiyonları: (a) dependency injection — cost_tracker model import etmesin, çağıran model'i passlar; (b) modules/ops/services + 3 domain caller (embedding/generations/rag) refactor (v82 contract); (c) yeni cross-cutting `apps/api/app/telemetry/` paket. Ayrı karar gerek.

### T7-7 alt-PR split (24+ caller)

| Sub-PR | Scope | Caller count |
|---|---|---|
| T7-7a | admin route caller flips (admin_audit, admin_billing, admin_clusters, admin_dashboard, admin_legal, admin_media, admin_queue, admin_rag, admin_sft, admin_settings, admin_sources, admin_system, admin_users) | ~13 admin route |
| T7-7b | app/api caller flips (app_me, app_research_stream, app_quota, app_setup, etc.) | ~5-6 app route |
| T7-7c | modules/*/routes ve modules/*/admin caller flips (legal, prompts_admin, settings_admin, sft, sources/admin, etc.) | ~6-8 module route |
| T7-7d | Final cleanup + test caller flips + `from app.core.deps` → `from app.modules.accounts.deps` ALL FORMS removal | tests + final sweep |

## 6. Hard-stop kuralları (T7 boyunca)

Her PR'da:

1. **import-linter 16/16 KEPT** — yeni contract eklenmez (existing 16 korunur)
2. **`core/* must not import modules/*`** — T7 core→modules **GEÇIŞ** yapıyor; core/ kaynak boşalır (legal direction)
3. **`domain modules must not import ops/`** — T7-6 cost_tracker hedefi `shared/observability/` (NOT ops/) — bu kuralı tetiklemez (Option D ile)
4. **`shared/* must not import legacy core/api/models`** — T7-6 için T7-0 Base relocation prereq doğru çözer
5. **Caller budget ≤ 8** per PR — T7-7 deps için sub-PR split zorunlu
6. **DB migration YOK** — yalnız Python file rename
7. **Manual trigger YOK** — production smoke read-only
8. **Data invariant korunur** — no rechunk/reembed/backfill/migration
9. **Behavior değişmemeli** — `git mv` + path flip; logic unchanged
10. **8/8 pre-flight matris** zorunlu: ruff + 5-form grep + facade identity + lint-imports + mapper + module_init_lazy + collect-only + TAM tests/unit
11. Eğer herhangi hard-stop tetiklenirse DUR + closure docs PR yaz (T8'deki v77/v78/v82 paterni)

## 7. Test/pre-flight matrix

| # | Test | Beklenen | Tüm T7 PR'larda |
|---|---|---|---|
| 1 | `ruff check` | All passed (isort auto-fix) | ✅ |
| 2 | 5-form grep `app.core.<file>` | 0 stale ref | ✅ |
| 3 | facade identity check | yeni path import OK | ✅ |
| 4 | `lint-imports` | **16/16 kept, 0 broken** | ✅ |
| 5 | `mapper_resolution` | 3/3 PASS | ✅ |
| 6 | `module_init_lazy` | 9/9 PASS | ✅ |
| 7 | `test_admin_rag --collect-only` | 10 tests no ImportError | ✅ |
| 8 | **TAM `pytest tests/unit/`** | **1186 PASS** | ✅ |

Ek:

- T7-7 (deps) için: integration test on auth flow (decode_token + require_admin paths)
- T7-5 (conversation_context) için: integration test on app_research_stream context loading
- T7-6 (cost_tracker) için: provider call cost telemetry round-trip test

## 8. Docs/wiki sync rules

Her T7 PR sonrası closure docs PR zorunlu (T8 paterni):

- `wiki/log.md` v<N> marker + body entry
- `wiki/plans/modular-monolith-transition-master-plan.md` §13 update
- `wiki/topics/t7-cost-tracker-core-consumer-cleanup-mini-plan.md` PR status update
- `wiki/topics/t8-model-relocation-mini-plan.md` T8 unblock matrix update (kaç model açıldı)
- `wiki/index.md` stats marker
- `wiki/topics/refactor-pr-checklist.md` yeni ders eklenirse

## 9. T8 unblock matrix (T7 tamamlanınca beklenen etki)

| T7 PR | Hangi T8 PR'lar unblock olur | T8 model sayısı delta |
|---|---|---|
| T7-1 (plan_features) | T8-16 (billing core 5 model: Plan/Subscription/Invoice/AgencySeat/WebhookEvent) | +1 PR (5 class) |
| T7-2 (quota) | T8-17 (billing UsageEvent — Wave D) | +1 PR |
| T7-3 (polling_tier) | T8-11 (sources 3 model: Source/SourceConfig/SourceHealth — Wave C) | +1 PR (3 class) |
| T7-4 (research_cache_telemetry) | T8-15 (generations/ResearchCacheTelemetry — Wave C) | +1 PR |
| T7-5 (conversation_context) | T8-10 (conversations YENİ modül: Conversation+Message — Wave C) | +1 PR (2 class, NEW scaffold) |
| T7-6 (cost_tracker) + T7-0 (Base) | T8-7 partial (ProviderCallLog → shared/observability/models — yeni hedef) | +1 PR (FailedJob+AdminAuditLog hala v82 BLOCK) |
| T7-7 (deps) | T8-21 (accounts/User+Session — Wave D HIGH risk; alt-PR sequence) | +1 PR (2 class) |
| **TOPLAM** | **7 T8 PR unblock** | **+8 model class (6 PR) — T8 10/22 → 16-17/22 (~75-77%)** |

**T7 sonrası kalan T8 BLOCKED:**

- T8-7 FailedJob + AdminAuditLog → ops (v82 contract — ayrı çözüm gerek)
- T8-9 Email → shared/email (v80 Base prereq — T7-0 ile çözülür ama T7-6 farklı hedef için)
- T8-12 article (13 caller — sub-PR split planning)
- T8-19/20 vector hardening (NOP re-verify; opsiyonel)

## 10. Deferred items

T7 sonrasında değerlendirilecek:

- **T8-7 FailedJob + AdminAuditLog → ops/** — v82 contract aynı kalır; refactor (articles/sources tasks'ı ops kullanmasınlar?) gerek
- **T8-12 article sub-PR split** — caller dependency analysis + 2-3 alt-PR planning
- **T8-19/20 NOP vector re-verify** — düşük değer; opsiyonel
- **Phase 8.1+ core/api code migration** — T7+T8 sonrası
- **Phase 8.3 raw-SQL → ORM stub** — HIGH risk; ayrı initiative

## 11. Final acceptance criteria

T7 initiative DONE kabul edilir:

- ✅ 7 core/ dosyası (cost_tracker, plan_features, quota, deps, research_cache_telemetry, conversation_context, polling_tier) `modules/<x>/services/` veya `modules/accounts/deps.py`'ye taşındı
- ✅ T7-0 Base relocation `app.shared.db.base.Base` aktif
- ✅ Tüm 7 T7 sub-PR + T7-0 prereq + T7-7 sub-PR'lar (a/b/c/d) main'e merge oldu
- ✅ import-linter 16/16 KEPT (her PR sonrası)
- ✅ TAM pytest tests/unit/ 1186 PASS (her PR)
- ✅ Production smoke read-only (her PR)
- ✅ Closure docs/wiki sync her PR sonrası
- ✅ 6-8 T8 BLOCKED model unblock olarak T8 cycle restart edilebilir
- ✅ Issue [#1086](https://github.com/selmanays/nodrat/issues/1086) closure raporu

## İlişkiler

- [[t8-model-relocation-mini-plan]] (T7'nin unblock ettiği T8 PR'lar)
- [[refactor-pr-checklist]] (5 hard-stop tetiği listesi v77+v78+v80+v82)
- [[modular-monolith-boundary]] (16 import-linter contract)
- [[import-direction-rules]] (boundary disiplini)

## Kaynaklar

- [`wiki/plans/modular-monolith-transition-master-plan.md`](../plans/modular-monolith-transition-master-plan.md) §2.4 / §13
- [`wiki/topics/t8-model-relocation-mini-plan.md`](t8-model-relocation-mini-plan.md)
- [`wiki/topics/refactor-pr-checklist.md`](refactor-pr-checklist.md)
- GitHub: [#1086](https://github.com/selmanays/nodrat/issues/1086) (T7 — Runtime-sensitive modules umbrella; bu mini-plan implementation arm'ı)

## Açık sorular / TODO

- **T7-0 Base relocation** — Kullanıcı onayı: `app.models.base.Base` → `app.shared.db.base.Base` kabul ediliyor mu? Bu Phase 8 boundary mimari kararı değişikliğidir.
- **T7-6 cost_tracker alternative** — Option D (Base relocation) onaylanmadığı durumda Option B/C kararı gerek.
- **T7-7 deps sub-PR split** — 24+ caller listelendi; sub-PR sıralaması ve test stratejisi mini-plan'ı ayrı.
- **Mevcut shared/observability paketi** — `apps/api/app/shared/observability/` var mı / boş scaffold mu? T7-6 hazır mı?
