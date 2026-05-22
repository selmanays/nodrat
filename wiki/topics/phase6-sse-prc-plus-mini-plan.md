---
type: topic
title: "Phase 6 PR-C+ — SSE Research Stream Deep-Characterization Mini Plan"
slug: "phase6-sse-prc-plus-mini-plan"
status: live
created: 2026-05-22
updated: 2026-05-22
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
  - "wiki/topics/refactor-pr-checklist.md"
tags: [refactor, t6, phase6, sse, characterization, research-stream]
aliases: ["PR-C+", "Phase 6 deep tests", "app_research_stream characterization"]
progress: "C+0 mini-plan DONE (#1212). C+1/PR-A9 DONE (#1213, first-yield branch-matrix char, test-only, +5 test; mock=3). C+2 DONE (#1215, context/condense extraction → YENİ _research_stream_context.py 234 LoC, behavior-preserving PROD refactor, +5 helper test, 17 async-helper korundu; app_research_stream.py 1416→1274 LoC). C+3 DONE (#1217, 2nd-yield positive-path char, test-only, +1 test, mock=4 — PR-C+2 mock düşüşü testle kanıtlandı; context_check→query_rewrite + aclose, 3. yield/tool-loop YOK). research-stream SSE char 89→95 (orchestrator 8; önceki '96' generate_sse mis-split düzeltildi). Sıradaki: C+4 scope analizi (read-only; RC3-B coupling / negative path / tool-loop timeout / persist). Full TestClient endpoint integration DEFERRED."
---

## TL;DR

T6 #1085'in Phase 6 alt-kalemi (`app_research_stream.py` SSE god-file) için kalan **derin orchestration characterization** borcunu küçük, test-first, düşük-riskli PR'lara böler. SSE çıktı kontratı (yield şekli/sırası) zaten kilitli (14 P6 PR, 95 research-stream test); açık olan **yield-arası 3.+ orchestrator path** + **full endpoint integration**. C+1 first-yield ✅ + C+2 context/condense extraction ✅ (behavior-preserving prod refactor) + C+3 2nd-yield positive-path ✅ (test-only, mock=4); sıradaki **C+4 scope analizi** (RC3-B coupling / negative path / tool-loop timeout / persist); full TestClient SSE integration **şimdilik deferred**.

## Bağlam / Neden

Phase 7a (frontend `api.ts` split) kapandı (#1095 CLOSED). **T6 #1085 açık kalır** — backend god-file stratejisinin Phase 6 (SSE) tarafında derin test borcu var. Bu mini-plan, [[phase7a-frontend-mini-plan]] disiplinini (küçük PR + characterization-first + production tetiklememe) Phase 6 SSE'ye taşır.

> Hard kural (tüm PR-C+): production code değişikliği minimum (tercihen test-only); mock count kontrollü; **production'da SSE/research/LLM/provider/persist TETİKLENMEZ**; DB/Redis gerçek erişim yok.

## Current state (2026-05-23, main `69b045c`)

| Metrik | Değer |
|---|---|
| `apps/api/app/api/app_research_stream.py` | **1274 LoC** (PR-C+2 öncesi 1416; net −142) |
| `_research_stream_body` (orchestrator generator) | **~753 LoC** (L521→1274; dosyanın ~%59'u) |
| `apps/api/app/api/_research_stream_context.py` | **234 LoC** (`_recent_conversation_context` + `ResearchContextResult` + `_prepare_research_context`; PR-C+2/#1215) |
| `apps/api/app/api/_research_stream_helpers.py` | **64 LoC** (`_log_coverage_gap`/`_sse`/`_simulate_stream`; PR-B/#1153) |
| Research-stream characterization testi | **95** (7 dosya): helpers 33 · async_helpers 17 · tracked_chat_generate 12 · replay 11 · followups 9 · orchestrator **8** (2 + 5 PR-C+1 + 1 PR-C+3) · context 5 (PR-C+2) — *önceki "96" sayımı `generate_sse`'yi `tracked_chat_generate`'den ayrı saymıştı; gerçek pytest-collect 89→94→95* |
| Inline fonksiyonlar | pure: `_cited_numbers`/`_cite_to_int`/`_is_substantive`/`_has_reconstruction_marker` · async: `_resolve_style_block`/`_generate_followups` · endpoint `post_research_message` · `_tracked_chat_generate` · `_research_stream_body` — **`_recent_conversation_context` → `_research_stream_context.py`'e taşındı** |

**Tamamlanan (14 P6 PR, hepsi MERGED):** PR-A pure-helper (#1150) · PR-B internal split (#1153) · PR-A1 async helper (#1155) · PR-A2a followups (#1157) · PR-A2b tracked-chat (#1159) · PR-A3..A7 replay (#1160/#1162/#1164/#1166/#1168) · PR-A8 RC3-B `_has_reconstruction_marker` helper (#1170) · **PR-C+1/PR-A9 first-yield branch-matrix (#1213, test-only)** · **PR-C+2 context/condense extraction (#1215, behavior-preserving prod refactor → `_research_stream_context.py`)** · **PR-C+3 2nd-yield positive-path char (#1217, test-only, mock=4)**. İlk-yield orchestration testi **mevcut** (#1164/PR-A5, 2 test + #1213 +5 branch-matrix); **2nd-yield (`query_rewrite`) positive-path testi mevcut** (#1217, `_prepare_research_context` mock'lu). Replay/format testleri **mevcut**. RC3-B marker **helper-level** kilitli. **`_prepare_research_context` helper** (#1215) Step 1.5 condense'i tek mockable birime indirger; **PR-C+3 bu mock düşüşünü (2. yield mock=4) testle kanıtladı.**

## Gap (kalan borç)

- **Yield-arası orchestrator path** zayıf — `_research_stream_body` yalnız *first yield* doğrudan test edildi; 2.-3. yield (planner→research_tools tool-loop→provider) replay-dışı gerçek sürüş test edilmedi.
- **Full endpoint integration yok** — `post_research_message` TestClient ile (auth/JWT/DB/quota/provider/research_tools + SSE parse) test edilmedi.
- **persistence / tool-loop / provider deep integration** yok — replay downstream'i canned mock'lar; gerçek persist write-path + tool-loop timeout + RC3-B orchestrator coupling açık.

## Strateji

- **Test-first**; production code değişikliği minimum (PR-C+1 test-only).
- **Mock count kontrollü** — yüzey 6'yı aşarsa DUR + yeniden planla.
- **Production SSE/research/LLM/provider TETİKLENMEZ** — yalnız pytest mock; TestClient bile gerçek bağımlılığa gitmez.
- Her PR replay güvenlik ağı altında ilerler; davranış invariant.

## Önerilen PR sırası

| Sıra | PR | Kapsam | Tür | Risk | Durum |
|---|---|---|---|---|---|
| C+0 | bu mini-plan | docs/wiki | docs-only | yok | ✅ **DONE** ([#1212](https://github.com/selmanays/nodrat/pull/1212)) |
| C+1 | **PR-A9** | `_research_stream_body` **first-yield branch-matrix** char (`anext`+`aclose`; 2./3. yield guard-trip mock>6 → first-yield'e küçültüldü) | **test-only** | düşük | ✅ **DONE** ([#1213](https://github.com/selmanays/nodrat/pull/1213); +5 test, mock=3; truthiness-gate gerçek-davranış; research-stream 91→96) |
| C+2 | **#1215** | **context/condense prep extraction** (option A) → YENİ `_research_stream_context.py` (`_recent_conversation_context` verbatim + `_prepare_research_context` + `ResearchContextResult`) | **behavior-preserving prod refactor + char** | orta | ✅ **DONE** ([#1215](https://github.com/selmanays/nodrat/pull/1215); +5 helper test, 17 async-helper korundu; 1416→1274 LoC; scope guard → X onayı) |
| C+3 | **#1217** | **2nd-yield positive-path char** — `_prepare_research_context` mock'lu canned `ResearchContextResult(contextualized=True)`; 2 yield `context_check→query_rewrite` + `aclose()`; detail+latency+5-arg+`db.execute`=0 | **test-only** | düşük | ✅ **DONE** ([#1217](https://github.com/selmanays/nodrat/pull/1217); +1 test → orchestrator 8/8, **mock=4** — PR-C+2 mock düşüşü kanıtlandı; negative path ertelendi) |
| C+4 | — | RC3-B coupling / negative-no-rewrite path / tool-loop timeout / done-error helper / persist — **yalnız mock düşükse / gerekirse** | test-only / refactor | orta (brittle) | 🔜 **SIRADA** (scope analizi; closure v30 sonrası) |
| Son | — | **Full TestClient endpoint/SSE integration** | integration | **yüksek** | ⏳ **DEFERRED** (ayrı mini-plan'lı initiative) |

C+1 (first-yield) + C+2 (context/condense extraction) + C+3 (2nd-yield positive-path, mock=4) **tamamlandı**. Sıradaki **C+4 scope analizi** (RC3-B coupling / negative path / tool-loop timeout / done-error / persist; önce read-only). 3.+ yield (tool-loop) ve full TestClient integration şimdilik **deferred** (yüksek mock/flaky).

## Phase 6 kapanma kriterleri

`_research_stream_body` orkestrasyonu gelecekteki refactor'u güvenli kılacak kadar karakterize: first-yield ✅ + replay-sequence ✅ + **shallow-yield orchestration (C+1)** + (opsiyonel) persist/tool-loop branch — VEYA "replay+helper kapsamı yeterli güvenlik ağı; full TestClient integration bilinçli deferred" **kararı**. Phase 6, `_research_stream_body`'yi taşımayı zorunlu kılmaz.

## T6 #1085'in Phase 6 dışı kalanları

Extractor boundary kararı (PR #1146; P4) · Phase 4/5 derin migration kalanları · genel god-file facade strategy sign-off. T6 ancak bunlar + Phase 6 kapanınca kapanır.

## İlişkiler

- [[modular-monolith-transition-master-plan]] — §13 status board; T6 #1085.
- [[phase7a-frontend-mini-plan]] — kapanan kardeş alt-plan (aynı disiplin).
- [[refactor-pr-checklist]] — characterization + smoke + replay caller-wrap dersleri.

## Kaynaklar

- [modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md) §13
- [refactor-pr-checklist.md](refactor-pr-checklist.md)
