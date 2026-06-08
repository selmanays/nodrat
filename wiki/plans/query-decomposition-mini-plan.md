---
type: plan
title: "Query Decomposition — Mini-Plan (#619)"
slug: query-decomposition-mini-plan
status: live
created: 2026-06-05
updated: 2026-06-05
github_issue: 619
github_issue_url: https://github.com/selmanays/nodrat/issues/619
sources:
  - wiki/topics/architecture-final-state-2026-05.md§5
  - wiki/decisions/import-direction-rules.md
  - wiki/decisions/god-file-facade-first.md
  - apps/api/app/core/retrieval.py
  - apps/api/app/core/_retrieval_chunks.py§35
  - apps/api/app/api/app_research_stream.py§200
  - apps/api/app/core/research_tools.py§491
  - apps/api/app/prompts/query_planner.py§330
  - apps/api/app/prompts/query_rewrite.py
  - apps/api/app/shared/runtime_config/settings_store.py
tags:
  - feature
  - retrieval
  - query-decomposition
  - rag
  - planned
aliases:
  - query-decomposition
  - "619-mini-plan"
---

# Query Decomposition — Mini-Plan (#619)

> **TL;DR:** Karmaşık/çok-parçalı Türkçe haber-research sorgularını retrieval kalitesini artırmak için alt-sorgulara bölen **retrieval-time, query-side** feature. **Sıfır data/schema/embedding/RAG-index mutation.** Saf transform `app/prompts/query_decomposition.py`'de (planner/rewrite komşusu), orchestration `app/api` aggregator'da (`_research_stream_body`). Feature-flag default **OFF** → kapalıyken byte-identical. Hibrit LLM+heuristic; fail/timeout/parse-error → **tek-query baseline** fallback. En büyük risk **retrieval recall regression** (CI-able değil → staging/manuel benchmark). Modular-monolith sonrası **ilk feature**; facade-first disiplini (characterization-baseline-first) geçerli.

Örnek: *"Son 24 saatte Türkiye ekonomisi, faiz, döviz ve muhalefetin tepkileri ne oldu?"* → 4 alt-sorgu (ekonomi / faiz / döviz / muhalefet tepkileri, hepsi son-24-saat).

---

## Karar kilitleri (locked)

| Konu | Karar |
|---|---|
| Feature | #619 Query Decomposition |
| Feature tipi | Retrieval-time, query-side feature |
| Data mutation | **Yok** |
| Schema/migration | **Yok** (settings jenerik key-value; migration-suz) |
| Embedding/RAG-index mutation | **Yok** (alt-query embed = normal okuma) |
| İlk implementation | **PR-1 characterization baseline** |
| İlk gerçek feature kodu | **PR-2 saf decompose primitive** |
| Hedef saf transform katmanı | `app/prompts/query_decomposition.py` |
| Hedef orchestration katmanı | `app/api` aggregator / `_research_stream_body` çevresi |
| Feature flag | **Zorunlu, default OFF** (`research.query_decomposition_enabled`) |
| LLM stratejisi | **Hibrit:** heuristic fast-path + LLM; timeout/fallback şart |
| Fallback | Fail/timeout/parse-error → **tek-query baseline** |
| En büyük risk | **Retrieval recall regression** |
| Recall doğrulama | **CI dışı** staging/manuel benchmark (`retrieval_benchmark.py`) |
| Citation güvenliği | `cite_n` zincir korunacak; regression test şart |
| Rollout | Flag OFF → characterization → primitive → flag-gated integration → staging recall → kademeli enable |

---

## 1. Context

Modular monolith geçişi kapandı (#18/#19/#20 + T7/T8/N+1 closed; [[architecture-final-state-2026-05]]). Agent Operating System güncellendi (CLAUDE.md §0 + CONTRIBUTING §2.5 + nodrat-dev/nodrat-test). Bu, feature-development fazının **ilk** feature'ı.

**Amaç:** Kullanıcının çok-bileşenli/örtük-çok-niyetli sorgularını alt-sorgulara ayırıp her birini ayrı retrieve ederek recall'u artırmak — fakat mevcut RAG/embedding/index verisine **dokunmadan** ve mevcut research-stream davranışını **bozmadan**.

**Mevcut durum (read-only audit, 2026-06-05):** Query decomposition/multi-query/fan-out kodu **YOK** (teyit: `decompos|sub.?query|multi.?query|fan.?out` araması yalnız RRF çoklu-stream docstring'lerine ve SQL `.subquery()`'lerine denk geldi). Mevcut query-işleme decomposition değil: condense (#833, 1→1 standalone rewrite), planner topic-rewrite (`plan_query`), RC3-B reframe (post-generation *answer* reframe). **LLM tool-loop zaten implicit decomposition yapabiliyor** (`MAX_TOOL_ROUNDS=3`, çok-tur retrieval) ama planlı değil.

## 2. Pipeline reality map

Kullanıcı sorgusunun retrieval'a giden tam zinciri:

```
POST /research/conversations/{id}/messages   (ResearchMessageCreate.content: str)
 → _research_stream_body                            app_research_stream.py:200
   → _prepare_research_context → effective_query     :392  (condense #833, 1→1 rewrite)
   → tool-loop  while round < MAX_TOOL_ROUNDS=3      :691  (admin-tunable, clamp 1-6)
       → _tracked_chat_generate (LLM tool kararı)
       → execute_search_news                         research_tools.py:491
           → plan_query → topic_query+critical_entities   :523
           → create_embedding([topic])               :544   ← embedding CALLER'da üretilir
           → hybrid_search_chunks(query_text, query_vector, ...)  :561  ← RETRIEVAL TABANI
```

Net gerçekler:
- **Ham query retrieval'a doğrudan gitmez** — iki kez dönüşür (condense → `effective_query`; LLM tool-call `query` argümanı → planner `topic_query`).
- **Retrieval:** 96-satır saf facade (`core/retrieval.py`) + 10 `_retrieval_*` submodül; `hybrid_search_chunks` = RRF 6-stream + critical-entity rescue/filter + rerank + parent-doc + Redis cache. İmza: `hybrid_search_chunks(db, *, query_text: str, query_vector: list[float]|None, top_k, ...) → list[dict]`.
- **Embedding pipeline-dışı** (caller `create_embedding`, research_tools.py:544) — fonksiyon hazır vektör bekler.
- **Citation:** `cite_n` global sayaç (#851) + `cite_start` offset → **multi-call'a yapısal dayanıklı** (her alt-query ayrı tool-turu olursa bozulmaz).
- **SSE:** `thinking_step` serbest-form `phase`/`detail` taşır → yeni `_log_step("query_decomposition", …)` event'i tek satır.

## 3. Placement decision

5 yerleşim seçeneği değerlendirildi; **hiçbiri import-linter 16-contract'ı kırmıyor** — fark boundary semantiği:

| Seçenek | Değerlendirme |
|---|---|
| A `core/_retrieval_query_decomposition.py` | retrieval-mekaniğine yapışır; T7 "core orchestration-azalt" ruhuna kısmen ters → **hayır** |
| B `modules/rag/services/query_decomposition.py` | `services/` yok; **rag→generations YASAK** → follow-up bağlamı gerekirse hard-stop → kırılgan |
| C `modules/generations/services/query_decomposition.py` | `services/` hazır ama **core→generations YASAK** → core call-site'tan çağrılamaz → kısıtlı |
| D `app/api` aggregator helper | **orchestration parçası için doğru** (cross-domain, SSE, citation; api kısıtsız) |
| **★ E `app/prompts/query_decomposition.py`** | **saf transform için en idiomatic** — `query_planner.py`+`query_rewrite.py` zaten burada; `app.prompts` hiçbir contract'ta yok → core/api/generations hepsinden çağrılabilir; core→generations sorununu atlar |

**Karar (iki parçalı):**
1. **Saf decompose primitive → `app/prompts/query_decomposition.py`** (E): `render_decompose_payload` + `parse_decompose_response` (saf) + `async decompose_query` (LLM, condense pattern) + heuristic fast-path.
2. **Orchestration → `app/api`** (D): `_research_stream_body` / `_research_stream_context.py` helper — flag-check → `decompose_query` → alt-sorguları tool-loop/retrieval'a besle (cite_n zincir korunur) → SSE `thinking_step`.

> **Boundary kanıtı:** `app.prompts` + `app.providers` hiçbir contract'ta source/target değil (kısıtsız). `app.api` aggregator forbidden-source değil ([[import-direction-rules]]). `generations→rag` izinli; `rag→generations` + `core→generations` yasak. QueryPlan `app/prompts/query_planner.py:330`'da (sub_queries alanı **yok** — eklenebilir).

## 4. PR sequence

| PR | Hedef dosyalar | Risk | Test | Deploy | Hard-stop |
|---|---|---|---|---|---|
| **PR-1** Characterization baseline | `tests/unit/test_research_tools.py` (genişlet) + SSE-replay baseline | düşük (yalnız test) | tool-contract `hybrid_search_chunks` AsyncMock→canned; cite `[1]/[2]` blok sırası | FULL (davranış değişmez) | snapshot kurulamıyorsa DUR |
| **PR-2** Decompose primitive | **yeni** `app/prompts/query_decomposition.py` + `tests/unit/test_query_decomposition.py` | düşük (wiring yok → çağrılmaz) | render/parse/clamp/dedup/fallback canned-string + provider AsyncMock | FULL (davranış değişmez) | LLM-call fallback'siz ise DUR |
| **PR-3** Orchestration + flag | `settings_admin/routes.py` (SETTING_REGISTRY +1) + `_research_stream_context.py`/`_research_stream_body` wiring (flag-gated) + SSE event | **orta** (davranış-kritik) | flag-OFF SSE-replay diff=0; flag-ON mock event-sequence + cite_n zincir | FULL; flag OFF → prod byte-identical | SSE-replay diff≠0 / lint-imports<16 → DUR |
| **PR-4** Staging recall validation | `tests/eval/retrieval_benchmark.py` (manuel) + `score_history/*.json` | **yüksek** (recall) | staging Docker baseline vs decomposed recall@5/10/20 | yok (manuel/staging op) | recall delta < −%0.5 → flag açma, DUR + rapor |
| **PR-5** docs/wiki/telemetry | `wiki/` + decompose telemetry + kademeli rollout | düşük | telemetry assertion | docs/wiki SKIP | — |

### İlerleme durumu (2026-06-05)

- **PR-1 ✅ done** ([#1438](https://github.com/selmanays/nodrat/pull/1438), prod-merged, FULL deploy success) — `tests/unit/test_query_decomposition_baseline.py`, 2 characterization test (ardışık `search_news` cite_start zinciri + cross-query namespace). Production kod 0; full unit 1191. Not: baseline `test_research_tools.py` genişletme yerine **yeni dosya** olarak yazıldı (mevcut contract zaten güçlüydü — `test_execute_search_news_contract` + `test_search_news_collapse_respects_cite_start` cite zincirini zaten kapsıyor). Full tool-loop TestClient gate kurulmadı (#1421 future-optional, kapsam dışı).
- **PR-2 ✅ done** ([#1439](https://github.com/selmanays/nodrat/pull/1439), prod-merged, FULL deploy success) — `app/prompts/query_decomposition.py` + `tests/unit/test_query_decomposition.py` (35 test). **Wiring yok → davranış-nötr.** full unit 1226, lint-imports 16/16.
  - **PR-2 locked kararlar:** aktivasyon **heuristic + LLM-fallback** (kullanıcı 2026-06-05) · `MAX_SUB_QUERIES = 4` · normalize-bazlı **dedup** zorunlu · `parse_decompose_response` **never-raise** · fail/timeout/parse-error → **tek-query baseline** · `llm_enabled` default **False** (PR-3 flag'ten gelecek) · primitive **wiring'siz**. Public API: `decompose_query` / `decompose_query_llm` / `decompose_heuristic` / `parse_decompose_response` / `render_decompose_payload` + `DecompositionResult` dataclass (`method: single|heuristic|llm`).
- **PR-3 ✅ done** ([#1441](https://github.com/selmanays/nodrat/pull/1441), prod-merged, FULL deploy success) — flag-gated orchestration wiring. `research.query_decomposition_enabled` (default **OFF**) + `app_research_stream.py` 2 module-level helper (`_build_decomposition_hint` + `_decompose_for_research`) + `convo_messages` init sonrası flag-gated blok (`is_decomposed` → `thinking_step` phase=`query_decomposition` yield + hint `convo_messages`'a user-mesajı append). **Kararlar (onaylı):** sequential tool-turn · `thinking_step` · **3b LLM-driven prompt-hint** (deterministik pre-retrieval YOK; tool-loop/`_dispatch`/`cite_n`/`execute_search_news`/`hybrid_search_chunks` **dokunulmadı**). **Flag OFF → byte-identical** (SSE-replay+orchestrator+PR-1 baseline **21 test pass** kanıtı). 7 yeni test (helper-odaklı; orchestrator full-mock proje "first-yield only" disipliniyle atlandı). full unit 1233, lint-imports 16/16.
- **PR-5 ✅ done** ([#1444](https://github.com/selmanays/nodrat/pull/1444), prod-merged, FULL deploy success) — decomposition telemetry (gözlem-only). `DecompositionResult += fallback_reason` (coarse: empty_query/too_short/llm_disabled/llm_no_result) + `_decomposition_telemetry` **PII-suz** payload (method/sub_query_count/llm_used/fallback_reason/duration_ms) → `logger.info` HER flag-ON çağrı (single dahil) + `is_decomposed` thinking_step meta. **Flag OFF byte-identical** (`_log_step` extra default boş; 21 test). Schema/data/embedding YOK. Cost ayrımı PR-5 DIŞI (decompose LLM `track_provider_call` ayrı PR). full unit 1245, lint 16/16.
- **PR-4 ⏳ next — staging recall validation (CI-DIŞI, manuel).** **PR-5 telemetry prerequisite ✅ kapandı** → fallback-rate/method/duration artık ölçülebilir (cost hariç). Operasyonel detay: [[query-decomposition-pr4-staging-runbook]].

#### PR-4 — Staging Recall Validation Planı (next)

> **Operasyonel runbook + ön-koşul uyarısı:** [[query-decomposition-pr4-staging-runbook]] (exact flag/benchmark/SQL komutları + result template). **3 blocker (read-only audit 2026-06-05):** (1) mevcut `retrieval_benchmark.py` decomposition'ı **ÖLÇEMEZ** (retrieval-level vs orchestration-level → salt flag-flip = boş kıyas; decompose+merge benchmark modu **veya** manuel transcript gerek; bu, açık-karar #1 merge stratejisini de kilitler); (2) ayrı **staging ortamı YOK** (local docker-compose.dev **veya** onaylı prod-canary); (3) golden **çok-bileşen subset yok** + `method`/fallback-rate **telemetri yok**. **Salt flag-flip yeterli değildir.**

**Amaç:** decomposition'ın (flag ON) baseline'a (flag OFF) göre retrieval recall'u **düşürmediğini** (ideali artırdığını) ölç. **CI-able değil** (corpus-dependent → P5 dersi); manuel/local/canary gate.

**Adımlar:**
1. **Staging'de flag aç** (`research.query_decomposition_enabled=true`, admin panel / settings_store) — yalnız staging; prod OFF kalır.
2. **Benchmark koş** (`tests/eval/retrieval_benchmark.py`, production-Docker): aynı golden sorgu setiyle iki ölçüm — baseline (flag OFF) vs decomposed (flag ON). Metrik: recall@5/10/20 + NDCG@10 + MAP@5.
3. **Snapshot** `tests/eval/score_history/*.json` — baseline↔decomposed delta raporu.
4. **Gate:** recall delta **< −%0.5** → flag açma **DUR + rapor** (yanlış decomposition niyeti kaybediyor). Δ ≥ 0 → güvenli.
5. **Çok-bileşen alt-küme:** decomposition yalnız çok-bileşenli sorgularda tetiklenir → benchmark setinde bu alt-küme **ayrıca** raporlanmalı (tek-konu sorgularda flag ON ≈ baseline, ortalamayı maskeler).
6. **Latency/cost:** decomposed turlarda ekstra LLM-call (+1 decompose) + olası ek tool-round latency ölç (query explosion guard: cap 4 + `max_tool_rounds` clamp 6 dokunulmadı).

**Hard-stop (PR-4):** recall delta < −%0.5 · citation/cite_n regression (manuel transcript) · kabul-edilemez latency/cost · embedding/RAG-index/corpus mutation ihtiyacı → DUR.

**Sonuç → kademeli enable:** staging Δ ≥ 0 + latency kabul → prod flag kademeli aç (canary → genel). Aksi halde 3b yetersiz → (3a) deterministik pre-retrieval ayrı PR olarak değerlendir (PR-3 scope verification'da analiz edildi).

#### PR-4 ön-koşul alt-planı (read-only reality-analysis 2026-06-05)

PR-4 operasyonu (benchmark koşma) öncesi **altyapı** üç ayrı PR'la hazırlanır. **Hiçbiri benchmark koşmaz / flag açmaz / prod-corpus'a dokunmaz** — yalnız *ölçüm aracı* üretir; gerçek ölçüm ayrı onay + ortam bekler.

| PR | Hedef dosyalar | Değişiklik | Deploy | Hard-stop |
|---|---|---|---|---|
| **PR-4A ✅ done** ([#1447](https://github.com/selmanays/nodrat/pull/1447), prod-merged, FULL deploy success) | `tests/eval/retrieval_benchmark.py` + `tests/unit/test_benchmark_decompose_merge.py` (9 test) | `--decompose off\|heuristic\|llm` (default **off** → byte-identical, mevcut chunks blok AYNEN ayrı dal); `_merge_rrf_sum` SAF helper (article-level `_rrf_score` sum, deterministik) + `_decompose_sub_queries`; evaluate_query/run_benchmark imza+config. **`app/` SIFIR satır** (diff-kanıtlı). full unit 1254, lint 16/16. **Benchmark koşulmadı.** | FULL (davranış-nötr) | ✅ tutuldu (app/ dokunulmadı · merge prod'a sızmaz · --persist yok) |
| **PR-4B ✅ done** ([#1449](https://github.com/selmanays/nodrat/pull/1449), prod-merged, FULL deploy success) | `tests/eval/golden_sets/retrieval_golden_multi.yaml` + `tests/unit/test_golden_multi_subset.py` (4 test) | **10 sorgu** (7 heuristic `ve/ayrıca` + 3 LLM-gerektiren); relevant id'ler **mevcut golden_tr card UUID'lerinden birleştirildi** (test-kanıtlı reuse, yeni card YOK). **SALT YAML, sıfır mutation.** `app/` SIFIR satır. full unit 1258. | FULL (davranış-nötr) | ✅ tutuldu (yeni card yok · mutation yok · benchmark koşulmadı) |
| **PR-4C ✅ done** ([#1451](https://github.com/selmanays/nodrat/pull/1451), docs-only SKIP) | `wiki/plans/query-decomposition-pr4-staging-runbook.md` | Runbook operasyonel-kesin: baseline `--decompose off` + decomposed `--decompose heuristic` + `retrieval_golden_multi.yaml` komutları · **benchmark settings-flag OKUMAZ → CLI flag** netleştirildi · proxy-dürüstlük (deterministik retrieval-merge ≠ prod 3b LLM-driven) · local-recall uyarısı korundu · cost-PR-4-için-gereksiz notu · operasyon ayrı-onay | docs-only **SKIP** | — |

**Kritik dürüstlük (2 madde):**
1. **Benchmark = proxy.** Prod PR-3 **3b LLM-driven** (LLM tool-loop merge); benchmark **deterministik retrieval-merge**. → benchmark decomposition'ın *retrieval-katkı üst-sınırını* ölçer, prod LLM-driven recall'unu **değil**. Pozitif Δ gerekli-ama-yeterli-değil (gerçek prod → manuel e2e transcript, harness yok).
2. **Local anlamsız.** Golden relevant UUID'leri yalnız prod snapshot (2026-05-01/02); **local corpus'ta recall sahte-düşük**. Gerçek gate = prod-canary (CLAUDE.md §0 HARD-STOP onay+restore) veya snapshot-yüklü ortam. PR-4A/B/C **aracı** üretir, **ölçümü değil**.

**Telemetry readiness (PR-5 sonrası):** method/sub_query_count/llm_used/fallback_reason/duration_ms + decompose-rate ölçülür (logger.info + thinking_steps meta, PII-suz). **Cost PR-4 için GEREKSİZ** (heuristic-mod LLM-suz) → ayrı PR. Sıra: **PR-4A → PR-4B → PR-4C (üçü de ✅ done)**.

**📍 Statü (2026-06-08): VALIDATION KOŞULDU → 🔁 ITERATE NEEDED.** Araç (PR-4A) + veri (PR-4B) + runbook (PR-4C) ile prod-corpus benchmark READ-only koşuldu (aşağıda). **Activation YOK, canary YOK; flag OFF kalır.**

#### PR-4 Validation Sonucu — prod-corpus READ-only (2026-06-08)

Prod VPS'te benchmark READ-only koşuldu (kullanıcı açık onayıyla). **Flag `research.query_decomposition_enabled` hiç açılmadı** (başta+sonda OFF doğrulandı); `--persist` YOK, DB-write YOK, **sıfır mutation** (DB-read + query-embedding inference). Golden card'lar prod corpus'ta mevcut (baseline recall > 0 → benchmark anlamlı).

| Metrik | Baseline `--decompose off` | Decomposed `--decompose heuristic` | Δ relative | Gate |
|---|---|---|---|---|
| recall@5 | 0.1586 | 0.1911 | **+20.5%** | ✅ |
| **recall@10** | 0.3474 | 0.3287 | **−5.4%** | 🛑 `< −0.5%` **fail** |
| recall@20 | 0.4413 | 0.5190 | **+17.6%** | ✅ |
| ndcg@10 | 0.2681 | 0.2618 | −2.4% | ⚠️ |
| map@5 | 0.0933 | 0.1070 | +14.7% | ✅ |
| latency p50 / p95 | 35.9s / 165.7s | 30.4s / 60.1s | iyileşti | ✅ |

**failed query: 0.** Per-query `recall@10` düşen: **mq_007** (0.80→0.60), **mq_005** (0.111→0.000). `recall@20` iyileşen: **mq_002** (+0.40), **mq_007** (+0.20), **mq_003** (+0.143), **mq_004** (+0.125).

**Karar: 🔁 ITERATE NEEDED — reject değil.** recall@10 gate tetiklendi (−5.4%) → flag açma YOK. Ama recall@5 (+20.5%) ve recall@20 (+17.6%) belirgin iyileşme + **mq_007 recall@10↓ / recall@20↑** paterni → decomposition **doğru article'ları buluyor** (retrieval-katkısı pozitif) ama **top-10 ranking/merge suboptimal** (`_merge_rrf_sum` cross-query rerank sırasını bozuyor). **Kök neden adayı:** merge stratejisi (`_rrf_score` sum) → iterate ekseni **`rerank_rows`** (merge-c, açık-karar #1).

**⚠️ Proxy uyarısı:** benchmark **deterministik retrieval-merge**; prod PR-3 hâlâ **3b LLM-driven** → benchmark Δ retrieval-**potansiyeli**, prod e2e recall garantisi DEĞİL. Tam sonuç: [[query-decomposition-pr4-staging-runbook]] §9.

**Sıradaki ayrı tur (read-only ÖNCE, implementation ayrı onay): PR-4D / merge-strategy iteration reality-analysis** — benchmark-side `--merge rerank` / `rerank_rows` deneyi; recall@10 kurtarılıyor mu. Flag prod'da **OFF kalır.**

## 5. Risk matrix

| Risk | Olasılık | Etki | Azaltma |
|---|---|---|---|
| Retrieval recall regression (yanlış decomposition niyeti kaybeder) | orta | **yüksek** | flag OFF default + staging recall benchmark (PR-4) + fail→tek-query |
| Query explosion (N retrieval = N× latency/cost) | orta | orta | sub-query **cap (≤4)** + marker-gating (yalnız çok-bileşen tetikle) |
| Citation mis-attribution | düşük | yüksek | API-seviye `cite_n` zincir (her alt-query ayrı tool-turu) + regression test |
| Result ordering kayması | yüksek | orta | `_rrf_score` merge (affinity.py:106-111 pattern) veya birleşik `rerank_rows`; staging doğrula |
| LLM timeout/cost | orta | orta | condense pattern (`asyncio.wait_for` + cache + marker-gating); v4-flash ~$0.001/call |
| SSE/tool-loop behavior break | düşük | yüksek | flag-OFF byte-identical + SSE-replay 11-senaryo diff=0 |

## 6. Hard-stop conditions

```
🛑 DB-data mutation (toplu UPDATE/DELETE/truncate)              → beklenmiyor; çıkarsa DUR
🛑 embedding/rechunk/reembed/RAG-index/vector mutation          → beklenmiyor; çıkarsa DUR + onay
🛑 schema/migration (settings migration-suz olmalı)             → migration gerekirse DUR + rapor
🛑 boundary violation (lint-imports < 16/16)                    → CI-fail = DUR
🛑 retrieval recall regression (staging delta < −%0.5)          → flag açma, DUR + rapor
🛑 citation regression (cite_n zincir / SSE-replay diff≠0)      → DUR
🛑 kabul edilemez latency/cost (query explosion, cap yok)       → DUR, sub-query cap
🛑 LLM fallback yokluğu (fail→tek-query yoksa)                  → DUR
🛑 full research-stream behavior break (SSE-replay 11-senaryo)  → DUR
```

## 7. Test strategy

- **CI-hard (DB-suz):** decompose render/parse/clamp/dedup/fallback (canned-string, `test_query_planner_prompt.py` pattern — `parse` asla raise etmez); provider AsyncMock + `route_for_tier` patch.
- **Characterization (CI-hard, mock'lu):** flag-OFF orchestrator SSE-replay **diff=0**; flag-ON event-sequence + cite_n zincir (`test_research_stream_orchestrator.py` monkeypatch pattern); tool-contract `hybrid_search_chunks` AsyncMock→canned (retrieval bozulmadı kanıtı).
- **Recall/quality (CI-DIŞI, manuel):** `tests/eval/retrieval_benchmark.py` staging Docker + `score_history` snapshot. **Recall CI-able değil** (corpus-dependent) — P5 dersi ([[architecture-final-state-2026-05]] §3).
- **Edge cases:** tek-konu (decompose etme), çok-konu, zamansal, kişi+olay+kurum, TR bağlaçlar (ve/ama/hem/ayrıca/ile ilgili), query explosion (cap), duplicate alt-sorgu (dedup).

## 8. Rollout plan

```
1. Flag OFF default (byte-identical)        ← PR-3
2. Characterization yeşil (diff=0)          ← PR-1 + PR-3
3. Decompose primitive + unit yeşil         ← PR-2
4. Flag-gated integration (prod OFF)        ← PR-3 merge
5. Staging recall benchmark (baseline↔decomposed) + score_history snapshot   ← PR-4
6. Kademeli enable (staging-doğrulandıysa)  ← manuel, kullanıcı kararı
```

LLM stratejisi: hibrit — heuristic fast-path (TR bağlaç `ve/ayrıca/hem/bir de` + `normalize_tr_query` + `_TR_NOISE_WORDS`) bariz vakaları yakalar; LLM (flag-gated, marker-tetikli, condense güvenlik pattern'i) örtük çok-niyeti çözer; her ikisi fail → tek-query baseline (= decomposition kapalı).

## 9. Açık kararlar

**✅ Kararlaştı (PR-2, 2026-06-05):**
- **İlk aktivasyon modu:** heuristic fast-path + LLM-fallback (kullanıcı kararı).
- **Sub-query cap:** `MAX_SUB_QUERIES = 4`.

**⏳ PR-3'e devredilen açık kararlar (taze turda netleşecek):**
1. **Sub-query retrieval merge stratejisi:** `_rrf_score` toplamı (affinity.py:106-111 pattern) mı yoksa birleşik `rerank_rows` mı — PR-4 staging recall sonucuna göre kilitlenir.
2. **SSE event tipi / kullanıcıya gösterim:** serbest-form `thinking_step` phase (`_log_step("query_decomposition", …)`) mı yoksa ayrı `subquery_planned` event mi; alt-sorgular kullanıcıya gösterilsin mi.
3. **Yürütme şekli:** her alt-sorgu ayrı tool-turu (cite_n zincir; citation yapısal-güvenli) mi yoksa tek `execute_search_news` içinde N retrieval merge (cite-dedup yeniden yazım gerekir) mi. PR-1 baseline ardışık-tur cite zincirini zaten kilitledi.

## İlişkiler

- **Mimari bağlam:** [[architecture-final-state-2026-05]] §5 (feature-dev kuralları) + §6 (backlog).
- **Boundary:** [[import-direction-rules]] (`app.prompts`/`app.api` kısıtsız; `core→generations` yasak), [[modular-monolith-boundary]].
- **Disiplin:** [[god-file-facade-first]] (characterization-baseline-first; retrieval recall sessiz-regresyon riski), [[refactor-pr-checklist]]. Veri-güvenliği invariant: kök `CLAUDE.md §0` HARD-STOP (embedding/RAG-index/vector/chunk mutation = DUR + onay) + kullanıcı MEMORY `feedback_embedding_rag_index_safety`.
- **Master plan:** [[modular-monolith-transition-master-plan]] (modular-monolith tamamlandı; bu post-transition feature).

## Kaynaklar

- [apps/api/app/core/retrieval.py](../../apps/api/app/core/retrieval.py) — 96-satır facade
- [apps/api/app/core/_retrieval_chunks.py](../../apps/api/app/core/_retrieval_chunks.py) §35 — `hybrid_search_chunks`
- [apps/api/app/api/app_research_stream.py](../../apps/api/app/api/app_research_stream.py) §200 — `_research_stream_body` orchestration
- [apps/api/app/core/research_tools.py](../../apps/api/app/core/research_tools.py) §491 — `execute_search_news`
- [apps/api/app/prompts/query_planner.py](../../apps/api/app/prompts/query_planner.py) §330 — `QueryPlan` (sub_queries yok)
- [apps/api/app/prompts/query_rewrite.py](../../apps/api/app/prompts/query_rewrite.py) — condense (LLM güvenlik altın-standart: timeout+fallback)
- [apps/api/app/shared/runtime_config/settings_store.py](../../apps/api/app/shared/runtime_config/settings_store.py) — flag mekanizması (migration-suz)
- GitHub issue: [#619](https://github.com/selmanays/nodrat/issues/619)
