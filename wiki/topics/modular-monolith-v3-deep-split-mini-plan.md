---
type: topic
title: "Modular Monolith v3 — God-file Deep Internal Split Mini-plan"
slug: modular-monolith-v3-deep-split-mini-plan
status: completed
created: 2026-05-30
updated: 2026-05-30
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§6"
  - "wiki/decisions/god-file-facade-first.md"
  - "wiki/topics/modular-monolith-v2-deferred-mini-plan.md"
tags:
  - modular-monolith
  - refactor
  - god-file
  - v3
aliases:
  - mm-v3
  - v3-deep-split
---

# Modular Monolith v3 — God-file Deep Internal Split Mini-plan

> **TL;DR:** Milestone #19 (v2) facade-first modularization'ı KAPATTI (route/primitive relocation + facades + characterization + boundary full-strict). v3 [#20](https://github.com/selmanays/nodrat/milestone/20) = **bilinçli ertelenen DERİN god-file iç parçalama** (locked [[god-file-facade-first]]): T5 eval/safety gate hardening + P5 retrieval.py 9-step split + P6 _research_stream_body orchestrator split. **En yüksek risk: silent recall regression (P5) + SSE/tool-loop davranış kayması (P6).** Strateji: **önce safety-net'i tamamla, sonra parçala**; her step tek PR, behavior-preserving, no schema/migration/data. **🏁 DURUM: v3 [#20] KAPANDI (2026-05-30).** Step A1 (tool_choice test #1411) ✅ + **Step B (P5 retrieval 1926→97 saf facade, 8 PR #1412-#1419, 10 submodül) ✅ prod-verified** + Step C (P6) → facade+char DONE, orchestrator `_research_stream_body` deep-split **kalıcı deferred → future [#1421](https://github.com/selmanays/nodrat/issues/1421)** (Option A, kullanıcı kararı) + **Step D reconciliation: T5 #1084 + P5 #1093 closed, P6 #1094 closed-with-documented-deferred → #20 open:0/closed:11 closed.** Sahte-kapanış YOK.

## v3-0 Reality Analysis (2026-05-30)

### Test gate envanteri — CI hard-gate vs script/manual

| Test | Tür | CI hard-gate? | Kapsam |
|---|---|---|---|
| `tests/unit/` (full suite, 1186) | unit | ✅ **CI kırıcı** | replay 11 + citation_validator 30 + retrieval-logic 52 + retrieval_metrics 15 + #904 status (admin_queue/article_worker_registry) |
| `tests/eval/test_pii_eval` (8) + `test_prompt_eval` (24) | eval (golden-YAML) | ✅ **CI kırıcı** (`assert_threshold`) | PII redaction ≥0.85/0.99; prompt eval pass_rate=1.0 |
| `tests/eval/retrieval_benchmark.py` | **SCRIPT** (`if __name__`) | ❌ **CI-collected DEĞİL** | recall@5/@10 — **DB-corpus gerektirir** |
| `tests/eval/niche_chunks_benchmark_v2.py` | **SCRIPT** | ❌ | niche recall — DB-corpus |

**Sonuç:** retrieval recall **CI hard-gate'e wire EDİLEMEZ** (corpus bağımlılığı; v2 kararı doğrulandı). → P5 için **manuel/staging snapshot gate**.

### P5 retrieval safety-net yeterliliği
- ✅ **Pure-logic CI char (52 unit):** scoring/freshness (13) + NER-resolve multi-AND/rare/common/threshold (10) + pgvector parse (7) + phrase/quote/grams (9) + weights-sum + hydration. → `_retrieval_phrase/_scoring/_vector` + NER logic split'leri **CI-safe**.
- ⚠️ **RRF fusion + candidate-fetch + parent-doc expansion (DB):** yalnız corpus benchmark (script/manual). → bu step'ler **manuel snapshot gate** gerektirir (recall@5≥0.727 / recall@10≥0.818 / snapshot diff=0 / niche_007-009 NF→NF).

### P6 orchestrator safety-net yeterliliği
- ✅ **CI char:** SSE replay golden 10/10 (11 test) + orchestrator first/2nd-yield + async helpers (17) + context (6) + tracked_chat + citation (30).
- ⚠️ **Deep `_research_stream_body` (tool-loop) split için ek gate gerek:** tool-loop round/timeout characterization + tool_choice cache invariant (şu an yalnız source-level grep) + RC3-B v2 marker regression (yapısal) + (opsiyonel) TestClient SSE integration.

### T5 checklist boşlukları (deep-split öncesi kapatılacak)
| T5 madde | Durum |
|---|---|
| Retrieval golden suite (≥50 query) | ✅ var (golden-YAML + benchmark script; corpus-manual) |
| Eval baseline diff **CI gate** | ❌ corpus → **manuel/staging** (CI-able değil; belgelendi) |
| SSE replay golden (10) | ✅ CI |
| Citation parser edge | ✅ CI (30) |
| **tool_choice cache invariant** | ⚠️ yalnız source-level → **dedicated behavioral test EKLE (v3 T5-A1)** |
| Extraction sequence snapshot | ❌ yok — **deferred** (P5/P6 için gerekmez; extraction v2'de shared'a taşındı) |
| Status transition (#904) | ✅ CI |

## Execution Plan (v3) — safety-net-first

### Step A — T5 safety/eval gate hardening (önce güvenlik ağı)
- **A1:** dedicated **tool_choice cache invariant** behavioral test (CI unit) — tool-loop'taki tüm chat çağrıları aynı `tool_choice="auto"` kullanmalı (cache-prefix korunur; [[feedback_deepseek_toolchoice_cache]]). Şu an yalnız `test_research_cited_numbers:105` source-level grep.
- **A2:** retrieval **manuel/staging snapshot gate** disiplinini [[refactor-pr-checklist]]'e + bu plana yaz (corpus benchmark CI-able değil; P5 split PR'ları öncesi/sonrası `retrieval_benchmark` + `snapshot.py` baseline diff=0).
- **A3 (opsiyonel/deferred):** extraction sequence snapshot — P5/P6 kapsamı dışı; gerekmez.

### Step B — P5 retrieval 9-step ✅ **TAMAMLANDI (2026-05-30, prod-verified)**
- **B0 (karar uygulandı):** `core/research_tools.py` retrieval'i import ettiği için move `core→modules` ihlali olurdu → **IN-PLACE split** seçildi: retrieval.py `core/` içinde kaldı, alt-parçalar `core/_retrieval_*.py` submodüllerine taşındı, retrieval.py **saf facade + re-export** oldu (caller'lar `from app.core.retrieval import X` çalışmaya devam eder).
- **Sonuç:** `core/retrieval.py` **1926 → 97 satır** (module-level fonksiyon = []). **8 ardışık pure-move PR** (#1412-#1419), her biri behavior-preserving + FULL deploy + SSH prod-verify + lint 16/16 + 1189:
  - **B1** #1412 NER subsystem → `_retrieval_ner` · **B2** #1413 `_fetch_candidates` → `_retrieval_fetch` · **B3** #1414 parent-doc → `_retrieval_parent` · **B4** #1415 settings+RRF → `_retrieval_settings` · **B5** #1416 `apply_l2_affinity_boost` → `_retrieval_affinity` · **B6** #1417 `hybrid_search_agenda_cards` → `_retrieval_agenda` · **B7** #1418 `hybrid_search_chunks` (801) → `_retrieval_chunks` · **B8** #1419 dead `search()` removal + facade polish.
  - **10 `_retrieval_*` submodül** (7 v3-yeni + 3 v2: phrase/scoring/vector).
- **Recall gate gerçekliği:** Tüm extraction'lar **pure-move** (logic dokunulmadı) → recall **by-construction sabit** → corpus snapshot gate gerekmedi; CI unit (test_retrieval 52) + identity + prod-verify yeterli oldu. (Snapshot gate yalnız logic-RESTRUCTURE için gerekliydi; pure-move'da değil.)
- **Kritik ders:** ruff `--fix`, retrieval-içi tek-kullanıcısı kalmayan re-export'u F401 sanıp kaldırır → dış caller kırılır (B7: `_ner_idf_match_aids`→admin_rag + `_load_retrieval_settings`→`_retrieval_ner` lazy circular-break) → `# noqa: F401` ile korundu (re-export 14/14 doğrulandı).

### Step C — P6 orchestrator split ⏸️ **DEEP-SPLIT KALICI DEFERRED (Option A, 2026-05-30)**
- **C0 audit yapıldı:** `_research_stream_body` (app_research_stream.py, 341-1087) = **747 satır async-generator**, **17 yield dağılmış** + tool-loop (`While` 691-815, 125 satır) + 2 closure (`_log_step`, `_dispatch` — 6 closure/local-var: db/now/user/query_vec/content_top_k + `execute_*` circular-lazy import).
- **Karar (kullanıcı Option A):** alt-bölümler closure-state + yield + lazy-import-circular'a bağlı → **logic-restructure (pure-move DEĞİL)**, P5'ten temelde farklı. En küçük aday `_dispatch` (18 satır) bile 6-var→param + circular-lazy + tool-loop çağrı değişimi gerektirir (production research-stream path). **Full tool-loop TestClient gate CI'da YOK** → silent SSE/tool-loop regression riski. **Characterization safety-net 98+ test yeterli** (SSE replay 10/10 + orchestrator first/2nd-yield + async-helper 17 + RC3-B + tool_choice #1411) → locked [[god-file-facade-first]] uyarınca deep-split **future-optional**.
- **Tamamlanan (v2+v3, P6 #1094 closed):** facade + SSE replay 10/10 + citation/context/tracked_chat/agenda/research_tools/followup + RC3-B (marker+decision) + tool_choice test.
- **Deferred (açıkça ayrıldı):** orchestrator `_research_stream_body` deep-split → **future [#1421](https://github.com/selmanays/nodrat/issues/1421)** ("P6.1 Full tool-loop TestClient gate + orchestrator split", milestone'suz → #20'yi bloklamaz).

### Step D — #20 reconciliation ✅ **TAMAMLANDI (2026-05-30)**
- **T5 [#1084] ✅ closed** (char done; 2 deferred-belgeli: eval-CI-gate corpus-imkansız + extraction-snapshot P4-kapsamı).
- **P5 [#1093] ✅ closed** (retrieval 1926→97, 8 PR, 10 submodül, prod-verified).
- **P6 [#1094] ✅ closed-with-documented-deferred** (facade+char DONE; deep-split → future #1421).
- **#20 milestone open:0/closed:11 → state=closed.** Sahte-kapanış YOK: tamamlanan vs deferred açıkça ayrıldı + future issue açıldı.

## Mimari kararlar (v2'den devralınan + v3)
1. **CI otoriter** (local lint-imports cache yanıltabilir — P5b dersi). Boundary kararlarında CI sonucu kaynak.
2. **Cross-domain aggregator route'ları app/api/'de meşru kalır** (app_me/app_research/app_research_stream/admin_clusters/admin_rag) — zorla modüle taşınmaz.
3. **Retrieval recall gate = manuel/staging** (corpus → CI-able değil).
4. **Deep split = behavior-preserving**, no schema/migration/data/embedding mutation; silent regression → DUR.

## İlişkiler
- **Sonuç:** [[architecture-final-state-2026-05]] — v3 kapanışı sonrası repo mimari final state + invariants + feature-dev kuralları.
- **Önceki:** [[modular-monolith-v2-deferred-mini-plan]] (v2 KAPANDI), [[modular-monolith-transition-master-plan]] §6/§10.1.
- **Locked karar:** [[god-file-facade-first]], [[modular-monolith-boundary]].
- **Disiplin:** [[refactor-pr-checklist]], [[feedback_deepseek_toolchoice_cache]].

## Kaynaklar
- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md) §6 / §10.1
- [wiki/decisions/god-file-facade-first.md](../decisions/god-file-facade-first.md)
- GitHub milestone v3: https://github.com/selmanays/nodrat/milestone/20
