---
type: topic
title: "Modular Monolith v2 — Deferred Deep-Split & Route-Relocation Mini-plan"
slug: modular-monolith-v2-deferred-mini-plan
status: in-progress
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

## Execution Plan (v2) — dependency + risk ordered waves

> Reality analysis 2026-05-30 (4 paralel read-only agent + T5 CI taraması). Her PR ≤8 dosya, behavior-preserving; pre-PR audit + lint-imports/mapper/unit + main CI + (kod ise) FULL deploy + /health + container/log smoke / (docs ise) SKIP dogfooding + wiki sync. Production/veri/embedding/migration/manual-trigger dokunulmaz.

### Mimari kararlar (read-only analiz → en güvenli yol seçildi; kullanıcı talimatı: karar gerektiğinde analiz et + en güvenliyi uygula)

1. **cleaning.py / content_quality boundary (P4) — ⚠️ kabul kriteri DEĞİŞTİ:** Issue `modules/crawler/cleaning` diyor AMA `shared/extraction/extractor.py` cleaning'i import ediyor → crawler'a taşımak `shared/* must not import modules/*` contract'ını bozar. **Karar: cleaning.py + content_quality `shared/extraction/`'da KALIR** (extraction primitive, crawler orchestration değil). crawler modülüne yalnız `robots`/`rss` (sources-only primitive) taşınır. Bu, v1/v2 boundary gerçeğiyle dürüst kabul-kriteri güncellemesidir.
2. **Retrieval recall CI-gate (T5/P5) — ⚠️ kabul kriteri DEĞİŞTİ:** CI'da embedded corpus yok (`assert_threshold` PII/prompt golden-YAML ile çalışır; `retrieval_benchmark.py` DB-corpus ister → script, CI-collected değil). **Karar: retrieval recall hard-gate CI'a wire EDİLEMEZ** (corpus bağımlılığı — v1'in erteleme nedeni). P5 split'leri için **snapshot diff=0 manuel/staging gate** (her split PR öncesi/sonrası `retrieval_benchmark` + `snapshot.py`; recall@5≥0.727 / recall@10≥0.818 baseline). "CI gate" → "manuel/staging snapshot gate" olarak güncellendi.
3. **research_tools (P6):** `core/research_tools.py`, app_research_stream kullanıyor. **Karar: facade-first** (`modules/generations/research_tools` re-export); full move ayrı/sonra.

### T5 #1084 durumu: ~%90 TAM (test-only)
✅ CI `api-eval` job (golden sets) + `framework.assert_threshold` gate (PII ≥0.85/0.99, prompt =1.0) + SSE replay 11 + citation_validator 30 + retrieval unit 52 + retrieval_metrics 15 + tool_choice source-level invariant (`test_research_cited_numbers:105`) + #904 status transition (admin_queue/article_worker_registry/cleaning).
⏸️ Kalan refinement: (a) retrieval recall snapshot-diff disiplini (manuel/staging — karar #2); (b) opsiyonel dedicated tool_choice cache invariant unit test. → T5, P5/P6 ilerledikçe paralel kapanır.

### Wave tablosu (sub-PR breakdown)

| Wave | Sub-PR | Issue | Risk | ~Dosya | Caller flip |
|---|---|---|---|---|---|
| **1** | P4.1 observability `core/` → `shared/observability/` (cost_tracker+maintenance_tracker+celery_introspect+warmup_state) | P4 | LOW | 4 | ~14 |
| **1** | P4.2 public routes (public_search+health) → `modules/public/` | P4 | LOW | 2 | 0 |
| **1** | P3.1 billing routes (billing+admin_billing+webhooks) → `modules/billing/` | P3 | LOW | 3 | 0 |
| **2** | P4.3 ops admin (dashboard+audit) → `modules/ops/admin/` | P4 | MED | 2 | 0 |
| **2** | P4.4 ops admin (queue+system) → `modules/ops/admin/` [P4.1 sonrası] | P4 | MED | 2 | 1 |
| **2** | P6.1 `citation/validator` + reconstruction marker (pure helper extraction) | P6 | LOW | 3 | tests |
| **2** | P6.2 `followup/generator` + `llm/tracked_chat` + `streaming/helpers` | P6 | LOW-MED | 4 | tests |
| **3** | P3.2 auth helper extract → auth+auth_2fa+app_consent → `accounts/` (circular dep çöz) | P3 | MED-HIGH | 5 | 2 |
| **3** | P3.3 admin_users → `accounts/admin/` | P3 | MED | 2 | 9 |
| **3** | P4.5 crawler `robots`+`rss` → `modules/crawler/` | P4 | MED | 2 | 6 |
| **3** | P6.3 `streaming/routes` + `research_tools` facade | P6 | MED | 3 | tests |
| **4** | P3.4 app_me split (profile/history/settings) | P3 | HIGH | 4 | 6 |
| **4** | P5.1 rag facade (search_chunks/search_agenda_cards) + 5 call-site flip | P5 | MED | 6 | 5 |
| **4** | P5.2 retrieval snapshot baseline lock (test) | P5 | LOW | 2 | 0 |
| **4** | P5.3-9 retrieval 9-step split (her biri snapshot diff=0 manuel gate) | P5 | HIGH | ≤2/PR | — |
| **5** | P6.4 orchestrator `_research_stream_body` split [5 yeni test-gate sonrası: TestClient+tool-timeout+persist+negative+RC3-B] | P6 | VERY HIGH | — | — |

**Başlangıç sırası:** Wave 1 (P4.1 → P4.2 → P3.1) → Wave 2 → ... Her wave sonrası master plan/log/index sync. P5/P6 derin split'ler en sona (gate'ler hazır olunca). Hiçbir issue sahte kapatılmaz; tamamlananlar kanıtla, tamamlanamayanlar gerekçeyle deferred kalır.


## İlişkiler

- **Master plan:** [[modular-monolith-transition-master-plan]] §8 (P3-P6 + T5 → v2 referansı) + §13.
- **Locked karar:** [[god-file-facade-first]] (ertelemenin gerekçesi) + [[modular-monolith-boundary]].
- **Tamamlanan model relocation:** [[t8-model-relocation-mini-plan]] (v1 T8 — KAPANDI).
- **Disiplin:** [[refactor-pr-checklist]], [[refactor-anti-patterns-do-not-do]].

## Kaynaklar

- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md) §8 / §13 / §14
- [wiki/decisions/god-file-facade-first.md](../decisions/god-file-facade-first.md)
- GitHub milestone v2: https://github.com/selmanays/nodrat/milestone/19
