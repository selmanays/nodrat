---
type: topic
title: "Modular Monolith v2 — Deferred Deep-Split & Route-Relocation Mini-plan"
slug: modular-monolith-v2-deferred-mini-plan
status: planned
created: 2026-05-30
updated: 2026-05-30
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§8"
  - "wiki/decisions/god-file-facade-first.md"
  - "wiki/decisions/modular-monolith-boundary.md"
tags:
  - modular-monolith
  - refactor
  - deferred
  - v2
aliases:
  - mm-v2
  - v2-deferred
---

# Modular Monolith v2 — Deferred Deep-Split & Route-Relocation Mini-plan

> **TL;DR:** Milestone #18 (Modular Monolith **v1**) reconciliation (2026-05-30) sonucu: v1 **facade-first** strateji ile mimari iskeleti + boundary full-strict + low-risk modüller + domain services + model relocation + god-file characterization safety-net'lerini TAMAMLADI ve kapanabilir hale geldi. **5 track bilinçli ERTELENDİ** (derin god-file iç parçalama + route-file relocation + crawler/public build-out) ve yeni **v2 milestone [#19](https://github.com/selmanays/nodrat/milestone/19)**'a taşındı. Bu sayfa v2 kapsamını + neden ertelendiğini + kanıtı belgeler. **Sahte başarı yok: bu iş v1'de YAPILMADI, v2'de planlı.**

## Bağlam — neden v2?

v1 transition'ın **locked stratejisi** [[god-file-facade-first]]: yüksek-riskli god-file'lar (retrieval.py, app_research_stream.py, extractor.py) için önce **characterization test** (golden/replay/snapshot) + **boundary primitive extraction**, sonra derin iç parçalama. Derin split, characterization safety-net yeterli sayıldığında **alternate criteria (ii)** ile ertelenebilir (T6 #1085, P7b #1096, P8 #1097 bu yolla kapandı).

Reconciliation (2026-05-30) #18'in 10 açık issue'unu kanıtla denetledi. Kod gerçekliği (ground-truth tarama):

| Kanıt | Değer |
|---|---|
| `app/api/` kalan dosya | **20** (boşalmadı — route relocation yapılmadı) |
| `core/retrieval.py` | **1926 satır** (9-step split yapılmadı) |
| `app/api/app_research_stream.py` | **1312 satır** (orchestrator split yapılmadı) |
| `app/api/admin_rag.py` | **1819 satır** |
| `modules/crawler/` | `__init__.py` only (build-out yok) |
| `modules/public/` | `__init__.py` only (build-out yok) |

Bu kalemler **v1'de tamamlanmadı** → DONE diyemeyiz (sahte başarı olur) → **DEFERRED → v2**.

## v2 kapsamı — 5 track

### T5 [#1084](https://github.com/selmanays/nodrat/issues/1084) — Characterization gate'leri
- **v1 ✅:** SSE replay golden 10/10 (`test_research_stream_replay.py`), retrieval benchmark (`tests/eval/retrieval_benchmark.py`), #904 status transition test, citation validator test, extraction (`shared/extraction`).
- **v2 ⏸️:** eval baseline diff **CI hard-gate** (recall delta <%0.5), dedicated tool_choice cache invariant test, derin split'lere (retrieval 9-step + orchestrator) bağlı ek characterization.

### P3 [#1091](https://github.com/selmanays/nodrat/issues/1091) — sources/articles repository-service + accounts + billing
- **v1 ✅:** accounts `deps.py` (T7-7) + `models.py` (T8-21+email); `sources/services` (polling_tier); `billing/services` (plan_features+quota); `generations/services` (conversation_context); auth import migration.
- **v2 ⏸️:** articles service layer (yok); route-file relocation (`auth/app_me/app_consent/admin_users/billing/webhooks` → modules); `app_me.py` (1091 satır) split.

### P4 [#1092](https://github.com/selmanays/nodrat/issues/1092) — crawler facade + ops + public
- **v1 ✅:** `shared/extraction` (PR-D2) + `shared/observability` dizini + `modules/ops` scaffold (ProviderCallLog T8-7a + tasks) + #904 status transition.
- **v2 ⏸️:** `modules/crawler` build-out; `modules/public` (search/health); ops route relocation (`admin_dashboard/audit/queue/system` → modules/ops); `shared/observability/cost_tracker` (T7-6'da core'da raw-SQL kaldı).

### P5 [#1093](https://github.com/selmanays/nodrat/issues/1093) — RAG facade + retrieval characterization
- **v1 ✅:** `modules/rag` scaffold (tasks+models); retrieval benchmark; `_retrieval_phrase/_scoring/_vector` helper extraction.
- **v2 ⏸️ (en yüksek risk):** `core/retrieval.py` **9-step iç parçalama** (1926 satır); rag facade public API; `admin_rag.py` (1819) relocation; 50+ query golden snapshot CI diff gate.

### P6 [#1094](https://github.com/selmanays/nodrat/issues/1094) — generations facade + SSE
- **v1 ✅:** `modules/generations` (services + tasks + models); **SSE replay golden 10/10**; `_research_stream_context/_helpers` extraction; RC3-B lock.
- **v2 ⏸️ (bilinçli):** `_research_stream_body` orchestrator split (1312 satır — master plan: 'BİLİNÇLİ TAŞINMADI'); `app/api/` boşaltma+silme; full TestClient SSE integration.

## Reconciliation sonucu (2026-05-30)

| Aksiyon | Issue'lar |
|---|---|
| **KAPATILDI** (DONE/STALE-DONE, kanıtlı) | T2 #1082 · T3 #1081 · T4 #1083 · P2 #1090 |
| **#18'den çıkarıldı** (perpetual) | T1 #1080 (master-plan maintenance) |
| **v2'ye taşındı** (deferred) | T5 #1084 · P3 #1091 · P4 #1092 · P5 #1093 · P6 #1094 |
| #18 sonuç | **open:0 / closed:47 → kapatılabilir** |

> Bu reconciliation [[refactor-pr-checklist]] disiplini + kanıt-temelli sınıflandırma (DONE / STALE-DONE / LIVE-DISCIPLINE / DEFERRED) ile yapıldı. Production/veri/migration dokunulmadı (status reconciliation turu).

## İlişkiler

- **Master plan:** [[modular-monolith-transition-master-plan]] §8 (P3-P6 + T5 → v2 referansı) + §13.
- **Locked karar:** [[god-file-facade-first]] (ertelemenin gerekçesi) + [[modular-monolith-boundary]].
- **Tamamlanan model relocation:** [[t8-model-relocation-mini-plan]] (v1 T8 — KAPANDI).
- **Disiplin:** [[refactor-pr-checklist]], [[refactor-anti-patterns-do-not-do]].

## Kaynaklar

- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md) §8 / §13 / §14
- [wiki/decisions/god-file-facade-first.md](../decisions/god-file-facade-first.md)
- GitHub milestone v2: https://github.com/selmanays/nodrat/milestone/19
