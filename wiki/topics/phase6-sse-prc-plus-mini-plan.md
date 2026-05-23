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
progress: "🏁 PHASE 6 PR-C+ DONE (closure docs v32, kullanıcı 2026-05-23 onayı). C+0..C+4 tamam (#1212/#1213/#1215/#1217/#1219). Mini-plan kapanış kriteri (ii) yolu seçildi: replay+helper yeterli güvenlik ağı; full TestClient integration bilinçli deferred. _research_stream_body BİLİNÇLİ TAŞINMADI (son durum 1274 LoC). Safety-net final: research-stream char 101, 4-god-file char 141, safety-net 251, import-linter 13/0, full unit collect 1174. Bilinçli deferred: full TestClient / tool-loop timeout / persist / RC3-B orchestrator-coupling / negative-no-rewrite (her biri mock>6 / integration / data-safety sınıfı). Production data safety: research stream production tetiklenmedi; DB/Redis/rechunk/reembed/backfill/manual task yok; veri güvenliği invariant korundu. T6 #1085 AÇIK kalır (extractor boundary + P4/5 + housekeeping + dead-code cleanup)."
---

## TL;DR

**🏁 Phase 6 PR-C+ DONE** (closure docs v32, 2026-05-23). `app_research_stream.py` SSE god-file için kalan derin orchestration characterization borcunu küçük, test-first, düşük-riskli PR'lara böldü (5 PR: C+0 mini-plan + C+1..C+4). SSE çıktı kontratı kilitli (15 P6 PR, **101 research-stream test**); first-yield ✅ + 2nd-yield ✅ + replay 10/10+1 ✅ + context/condense extraction ✅ + RC3-B helper+decision ✅. **Mini-plan kapanış kriteri (ii) yolu seçildi:** *replay+helper yeterli güvenlik ağı; full TestClient integration bilinçli deferred*. **`_research_stream_body` BİLİNÇLİ TAŞINMADI** (son durum 1274 LoC). Bilinçli deferred: full TestClient / tool-loop timeout / persist / RC3-B orchestrator-coupling / negative-path (her biri mock>6 / integration / data-safety sınıfı). **T6 #1085 AÇIK kalır** (extractor boundary + P4/5 + housekeeping + dead-code cleanup).

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
| Research-stream characterization testi | **101** (7 dosya): helpers **39** (33 + 6 PR-C+4 `_maybe_reframe`) · async_helpers 17 · tracked_chat_generate 12 · replay 11 · followups 9 · orchestrator **8** (2 + 5 PR-C+1 + 1 PR-C+3) · context 5 (PR-C+2) — *önceki "96" sayımı `generate_sse`'yi `tracked_chat_generate`'den ayrı saymıştı; gerçek pytest-collect 89→94→95→101* |
| Inline fonksiyonlar | pure: `_cited_numbers`/`_cite_to_int`/`_is_substantive`/`_has_reconstruction_marker`/**`_maybe_reframe_for_faithfulness`** (PR-C+4) · async: `_resolve_style_block`/`_generate_followups` · endpoint `post_research_message` · `_tracked_chat_generate` · `_research_stream_body` — **`_recent_conversation_context` → `_research_stream_context.py`'e taşındı** |

**Tamamlanan (14 P6 PR, hepsi MERGED):** PR-A pure-helper (#1150) · PR-B internal split (#1153) · PR-A1 async helper (#1155) · PR-A2a followups (#1157) · PR-A2b tracked-chat (#1159) · PR-A3..A7 replay (#1160/#1162/#1164/#1166/#1168) · PR-A8 RC3-B `_has_reconstruction_marker` helper (#1170) · **PR-C+1/PR-A9 first-yield branch-matrix (#1213, test-only)** · **PR-C+2 context/condense extraction (#1215, behavior-preserving prod refactor → `_research_stream_context.py`)** · **PR-C+3 2nd-yield positive-path char (#1217, test-only, mock=4)** · **PR-C+4 RC3-B reframe-decision extraction (#1219, behavior-preserving pure-helper → `_maybe_reframe_for_faithfulness`, mock=0)**. İlk-yield orchestration testi **mevcut** (#1164/PR-A5, 2 test + #1213 +5 branch-matrix); **2nd-yield (`query_rewrite`) positive-path testi mevcut** (#1217, `_prepare_research_context` mock'lu). Replay/format testleri **mevcut**. RC3-B marker **helper-level** (PR-A8) + **decision-level** (PR-C+4 `_maybe_reframe_for_faithfulness`, 4-predicate gate + reframe byte-lock + #1058 dışlama) kilitli. **`_prepare_research_context` helper** (#1215) Step 1.5 condense'i tek mockable birime indirger; **PR-C+3 bu mock düşüşünü (2. yield mock=4) testle kanıtladı.**

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
| C+4 | **#1219** | **RC3-B reframe-decision extraction** (option A2) → saf `_maybe_reframe_for_faithfulness(final_text, all_sources, guard) -> str\|None` + `_FAITHFULNESS_REFRAME_TEXT`; yield + `_log_coverage_gap` + atama orchestrator'da | **behavior-preserving pure-helper refactor + char** | düşük | ✅ **DONE** ([#1219](https://github.com/selmanays/nodrat/pull/1219); +6 pure test **mock=0**, byte-lock + #1058 dışlama; deep-drive A1 mock 10+ elendi) |
| Değerlendirme | — | **Phase 6 PR-C+ kapanış değerlendirmesi** (3 tablo + net karar) | docs/read-only | yok | 🔜 **SIRADA** (closure v31 sonrası) |
| Deferred | — | RC3-B orchestrator-coupling (`faithfulness_reframed` tam-sürüş) / negative-no-rewrite path / tool-loop timeout / persist/write-path | test/integration | yüksek (mock>6) | ⏳ **BİLİNÇLİ DEFERRED** |
| Son | — | **Full TestClient endpoint/SSE integration** | integration | **yüksek** | ⏳ **DEFERRED** (ayrı mini-plan'lı initiative) |

C+1 (first-yield) + C+2 (context/condense extraction) + C+3 (2nd-yield positive-path, mock=4) + C+4 (RC3-B reframe-decision extraction, mock=0) **tamamlandı**. Sıradaki **Phase 6 PR-C+ kapanış değerlendirmesi** (read-only). Kalan derin path'ler (RC3-B orchestrator-coupling tam-sürüş, negative-path, tool-loop timeout, persist) ve full TestClient integration **bilinçli deferred** (mock>6 / flaky / data-safety).

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
