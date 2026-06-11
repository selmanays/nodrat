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

**Sıradaki: PR-4D / merge-strategy iteration** — reality-analysis tamamlandı (aşağıda).

#### PR-4D Reality-Analysis (2026-06-08, read-only)

**Bulgu 1 — `_merge_rrf_sum` top-10 kök neden** (`retrieval_benchmark.py:180`): her alt-sorgunun `_rrf_score`'unu cross-query **toplar**. `_rrf_score` alt-sorgu-içi mutlak değer (farklı dağılım) → toplam **orijinal-query relevance'ını kaybeder** (tek alt-sorguda yüksek-relevant article düşük sum → top-10↓) + cross-query-konfirmasyona bias. recall@20↑ (union genişler) / recall@10↓ (orijinal-optimal sıra kayıp) tam bu pattern.

**Bulgu 2 — 🔴 Benchmark determinizmi belirsiz (kritik):** `hybrid_search_chunks(rerank=True)` → `_retrieval_chunks.py:749` → **`rerank_rows`** çağrılıyor. `rerank_rows` (#758: cross-encoder kaldırıldı) = `retrieval.llm_rerank_enabled` (DB, default OFF) + question-query → **DeepSeek LLM rerank** (`route_for_tier(chat)` + `track_provider_call(llm_rerank)`); aksi → RRF sırası (no-op). **Eğer prod'da llm_rerank ON → benchmark NON-DETERMINISTIK** (latency p50 35s bunun işareti). → **recall@10 −5.4% tek-koşum kısmen LLM-noise olabilir** (recall@20 iyileşmesi tutarlı/gerçek; recall@10 düşüş kısmen noise). **PR-4D önce determinizmi izole etmeli** (`--rerank off`).

**Merge stratejileri:**

| Strateji | Mekanizma | Deterministik | Cost | top-10 |
|---|---|---|---|---|
| `rrf_sum` (mevcut/default) | `_rrf_score` sum | ✅* | yok | orijinal-relevance kaybı → ↓ |
| `rrf_max` | `_rrf_score` max | ✅* | yok | tek-güçlü; konfirmasyon kaybı |
| **`rank_rrf`** | alt-sorgu **rank**'tan `Σ 1/(K+rank)` | ✅* | yok | **klasik RRF, ölçek-bağımsız — öncelikli düzeltme** |
| `union` | ilk-görülme rank | ✅ | yok | skor-bağımsız baseline |
| `rerank_rows` | birleşik havuz orijinal-query LLM rerank | ❌(llm-ON)/no-op(OFF) | LLM | yalnız benchmark aracı, prod-strateji DEĞİL |

*`--rerank off` (deterministik retrieval) varsayımıyla.

**Prod-uyum:** prod PR-3 = 3b LLM-driven (deterministik-merge YOK) → **hiçbir benchmark-merge prod-3b birebir değil** (hepsi retrieval-merge proxy). `rank_rrf`/`rrf_max`/`union` = saf deterministik proxy.

**CLI:** `--merge rrf_sum|rrf_max|rank_rrf|union` (default `rrf_sum` → byte-identical) + `--rerank on|off` (determinizm kontrolü, default mevcut-davranış-bozmaz).

**PR-4D-1 plan (production-DOKUNMAZ):** `tests/eval/retrieval_benchmark.py` (`--merge`/`--rerank` + deterministik merge fonksiyonları) + `tests/unit/test_benchmark_decompose_merge.py`. `app/` SIFIR satır (`rerank_rows` mevcut public). Öncelik `rank_rrf`; `rerank_rows`/LLM-rerank yalnız benchmark aracı (prod-strateji değil). **Gerçek prod-corpus koşum ayrı onay** (`--rerank off --merge rank_rrf` vs `rrf_sum` → recall@10 noise-suz). Flag prod'da **OFF kalır.**

**PR-4D-1 ✅ done (2026-06-08, PR [#1455](https://github.com/selmanays/nodrat/pull/1455), merged + deploy success):** Plan birebir gerçekleşti — `app/` touch **0** satır. Eklenenler:
- **3 yeni saf merge fonksiyonu** (`retrieval_benchmark.py`): `_merge_rrf_max` (cross-query MAX), `_merge_rank_rrf` (klasik RRF `Σ 1/(k+rank)`, k=60, ölçek-bağımsız — öncelik), `_merge_union_preserve_order` (round-robin interleave). Dispatch `_MERGE_FUNCS` dict.
- **CLI:** `--merge rrf_sum|rrf_max|rank_rrf|union` (default `rrf_sum`) + `--rerank on|off` (default `on`). `evaluate_query`/`run_benchmark` imzalarına `merge`/`rerank` param + config dict'e yazılır.
- **Byte-identical kanıtı:** flag-suz → `merge=rrf_sum` (`_MERGE_FUNCS["rrf_sum"] is _merge_rrf_sum`, PR-4A orijinali) + `rerank=on` (`rerank=True`) → eski davranış birebir. Yeni 3 fonksiyon yalnız opt-in.
- **Doğrulama:** 7 yeni unit test (rrf_max/rank_rrf/union + dispatch + `rank_rrf` ölçek-bağımsızlık) → full suite **1265 passed** (1258+7); ruff + format + lint-imports **16/16**; CI 11/11; deploy success (davranış-nötr, benchmark-only).
- **Kapsam dışı (kasıtlı):** benchmark KOŞULMADI · prod flag/canary YOK · DB write/`--persist` YOK · `rerank_rows` prod-strateji sunulMADI.

> **Sıradaki (ayrı onay bekliyor):** gerçek prod-corpus benchmark — `--rerank off --merge rank_rrf` vs `--rerank off --merge rrf_sum` → recall@10 LLM-noise'suz deterministik kıyas. Flag prod'da OFF kalır.

#### PR-4D-2 Gerçek Prod-Corpus Deterministik Benchmark Sonucu (2026-06-08, READ-only)

Kullanıcı açık onayıyla prod VPS'te 5 koşum READ-only koşuldu (`--rerank off` → LLM-rerank noise izole). **Flag hiç açılmadı** (başta+sonda `app_settings` COUNT=0); `--persist` YOK, `score_history` yazımı YOK, **sıfır mutation**; host+container `/tmp` temizlendi; 13 container healthy. Prod `retrieval.llm_rerank_enabled = false` doğrulandı. Koşum süreleri: r0 461s · r1 331s · r2 276s · r3 164s · r4 848s (BGE-M3 cold-start + çift retrieval; benchmark aracı, prod e2e değil).

**Aggregate (10 multi-component query, top_k=20, deterministik):**

| metric | r0 no-dec | r1 rrf_sum | r2 **rank_rrf** | r3 rrf_max | r4 union |
|---|---|---|---|---|---|
| recall@5 | 0.1586 | **0.1911** | 0.1368 | **0.1911** | 0.1768 |
| recall@10 | 0.3474 | 0.3287 | 0.3398 | 0.3287 | **0.3489** |
| recall@20 | 0.4413 | **0.5190** | 0.4940 | **0.5190** | 0.4940 |
| ndcg@10 | 0.2691 | 0.2628 | 0.2458 | 0.2768 | **0.2809** |
| map@5 | 0.0953 | 0.1090 | 0.0803 | 0.1210 | **0.1367** |
| mrr@10 | 0.3644 | 0.3650 | 0.3260 | 0.4150 | **0.4242** |
| latency p50 | 35.9s | 33.7s | 23.1s | **9.5s** | 96.7s |
| latency p95 | 155.1s | 84.0s | 52.6s | 68.4s | 144.5s |

**🔑 Determinizm doğrulandı → Bulgu-2 ÇÜRÜTÜLDÜ:** r1 (rrf_sum, **rerank OFF**) recall@10 = 0.3287 ≈ v144 (rrf_sum, rerank **ON**) 0.329 → **birebir**. Prod `llm_rerank=false` olduğundan `rerank_rows` v144'te de no-op'tu → benchmark zaten deterministikti. Yani recall@10 −5.4% **gerçek merge etkisi**, LLM-noise değil. **Bulgu-1 (merge kök-neden) doğrulandı; Bulgu-2 (non-determinizm şüphesi) yanlıştı.**

**Gate (öncelik `rank_rrf`):**
- recall@10: vs r1(rrf_sum) **+3.4%** (literal gate geçer) · vs r0(no-decompose) **−2.2%** (v144 −5.4%'ten toparlandı, ~yarıladı; ama hâlâ no-decompose altında).
- **recall@5/20 KORUNMUYOR:** recall@5 0.1911→**0.1368 (−28.4%)** 🔴 · recall@20 0.5190→0.4940 (−4.8%) · map@5 −26.3%. rank_rrf top-10'u marjinal düzeltirken **top-5 precision'ı çökertiyor**.
- **Per-query odak:** `mq_005` 0.111(r0)→**0.000** (tüm decompose; hiçbir merge düzeltMEZ → decomposition-level zarar). `mq_007` 0.800→0.600(rrf_sum/max)→**0.800(rank_rrf/union)** (rank_rrf+union r0 seviyesine getirir).

**Yan bulgular:**
- **`rrf_max` = `rrf_sum`'a Pareto-üstün:** recall@5/10/20 **birebir aynı**, ranking (ndcg/map/mrr) daha iyi, **3.5× hızlı** (p50 9.5s). Decomposition ileride aktive edilirse default merge `rrf_sum`→`rrf_max` upgrade adayı (ayrı karar).
- **`union` = recall@10'da no-decompose'u geçen TEK strateji** (+0.4%) + en yüksek ndcg/map/mrr; AMA recall@5 −7.5% + latency p50 97s (en yavaş).

**🛑 KARAR: DUR — activation YOK, flag OFF kalır, canary ÖNERİLMEZ.** Gerekçe:
1. `rank_rrf` (öncelikli candidate) recall@5'i −28% çökerttiği için gate-2 ("recall@5/20 korunur") **ihlal** → canary önerilmez.
2. Hiçbir strateji recall@5 + recall@10 + recall@20'yi **aynı anda** no-decompose seviyesinde+ tutmuyor (her birinde trade-off).
3. `mq_005` regression decomposition-level (merge ile çözülmez) → bu golden subset'te kök sorun **merge değil, decomposition tetikleme kalitesi**.
4. Latency tüm decompose modlarında yüksek (9.5–97s p50).

**Sıradaki eksen (ileride, ayrı onay):** merge ince-ayarı yerine **decomposition tetikleme kalitesi** (hangi query bölünmeli — `mq_005` gibi tek-niyet query'ler bölünmemeli) + golden subset genişletme (10 query istatistiksel olarak dar). Opsiyonel: `rrf_max` default-merge upgrade'i (Pareto-üstün, düşük-risk) ayrı küçük araç-PR.

#### PR-4E Reality-Analysis: Decomposition Trigger Kalitesi (2026-06-08, read-only)

PR-4D-2 sonrası odak **merge değil trigger kalitesi**. Benchmark proxy `_decompose_sub_queries` → `from app.prompts.query_decomposition import decompose_query` (production primitive birebir) → bulgular doğrudan production'a uygulanır.

**Kök neden:** `decompose_heuristic` (`query_decomposition.py:123`) ` ve ` marker'ında **körlemesine** böler; iki ortogonal eksen karışıyor — **(a) trigger doğruluğu** (` ve ` liste-bağlacı mı niyet-ayracı mı, ayırt edilmiyor) + **(b) split kalitesi** (soru-kuyruğu/zaman/dangling temizlenmiyor). `_clean_and_cap` yalnız uzunluk+dedup+cap; **semantik parça-kalite + noise-strip yok**. recall@10 −5.4% = iyi-bölünenler (mq_007) + zarar-görenler (mq_005) net negatifi.

**Bölünmeli / bölünmemeli taksonomi:**

| Sınıf | Örnek | Mevcut davranış |
|---|---|---|
| ✅ BÖL — 2+ bağımsız özlü konu | mq_007/001/004 | doğru böler |
| 🔴 BÖLME — ` ve ` liste-bağlacı (tek konu) | "faiz **ve** enflasyon kararı" | yanlış böler (golden'da test YOK) |
| 🔴 BÖLME — isim listesi | "Ahmet **ve** Mehmet davası" | yanlış böler |
| 🔴 BÖLME — ` ile ilgili ` tek-konu refine | "deprem **ile ilgili** açıklama" | **marker listesinde YANLIŞ** (`_TR_SPLIT_MARKERS`:48) |
| ⚠️ BÖL ama temizle — konu ayrı, parça gürültülü | mq_005 | böler ama parça bozuk |

**mq_005 vs mq_007 (aynı ` ve ` marker, zıt sonuç → kanıt: sorun marker-trigger değil split-temizleme):**
- `mq_005` "altın fiyatı bugün gram **ve** 12 yargı paketi ne zaman çıkacak": konu-ayrımı doğru (altın\|yargı) AMA parçalar gürültülü ("bugün gram" dangling + "ne zaman çıkacak" soru-kuyruğu) → alt-sorgu embedding seyreltik → **0.111→0.000** (split-kalite hatası).
- `mq_007` "…sosyal medya yasağı **ve** doğum izni 24 hafta yasası": temiz noun-phrase → **0.800 korunur** (rank_rrf/union).

**Trigger guard tasarımı (deterministik, LLM-suz):**
1. **`should_decompose` guard** — marker taksonomisi: ` ayrıca `/` bir de ` = güçlü niyet-ayracı; ` ve ` = zayıf (ek kontrol); ` ile ilgili ` = **listeden çıkar** (tek-konu refine).
2. **Split-sonrası temizleme** — soru-kuyruğu + `_TR_NOISE_WORDS` strip (ne zaman/kaçta/mı), dangling budama, `normalize_tr_query` uygula (`prompts→core` import izinli, [[import-direction-rules]]).
3. **Parça-kalite ön-testi** — her parça noise-strip sonrası ≥2 içerik-kelimesi; aksi → o bölmeyi iptal, tek-query baseline.

**Golden genişletme:** mevcut 10 query dar + **negatif örnek yok**. 30+ query: 10 should-split (mevcut) + 10 **should-NOT-split** (liste/tek-konu/`ile ilgili`) + 10 ambiguous (LLM). Her query'e `expected_decompose: split|none|llm` label → recall-bağımsız CI-able `should_decompose` testi.

**PR planı (küçük parçalar):**

| PR | Kapsam | app/ touch | Onay |
|---|---|---|---|
| **PR-A** characterization + golden labels | `expected_decompose` testi + golden negatif örnek | ❌ salt test/YAML | CI-hard, app/ dokunmaz |
| **PR-B** heuristic guard | `decompose_heuristic` marker-taksonomi + noise-strip + parça-kalite | ✅ **app/ DOKUNUR** | **ayrı onay + DUR**; flag-OFF byte-identical + characterization diff=0 |
| **PR-C** deterministik benchmark re-run | PR-4D-1 aracıyla yeni-heuristic vs eski | ❌ | **benchmark koşma = ayrı onay** |

Sıra: A (test baseline) → B (guard, onaylı) → C (ölç, onaylı).

**Hard-stop:** flag açma/canary/prod-behavior-change YOK (bu tur) · **PR-B app/ kodu → implementation öncesi DUR + onay** · benchmark koşma → ayrı onay (PR-C) · data/schema/embedding/RAG-index mutation YOK · boundary `prompts→core` OK / `core→prompts` yasak / lint-imports 16/16 · characterization diff≠0 → DUR · golden relevant-id mutation / yeni card YOK (mevcut UUID reuse).

#### PR-A ✅ done (2026-06-08, PR [#1459](https://github.com/selmanays/nodrat/pull/1459), merged + deploy success)

Decomposition trigger davranışı CI'da kilitlendi — **app/ touch 0** (yalnız tests/). Yeni card/UUID YOK, golden relevant-id değişmedi (23→23).

**Yeni dosyalar:**
- `tests/eval/golden_sets/decompose_trigger_cases.yaml` — 14 case, 4 sınıf (`should_split` / `should_not_split` / `llm_or_ambiguous` / `split_but_needs_cleaning`), **relevant-id YOK** (recall ölçmez, salt trigger; benchmark okumaz). `current_splits` = sondaj-doğrulanmış mevcut davranış (characterization baseline).
- `tests/unit/test_decompose_trigger_characterization.py` — 49 test; **characterization** (mevcut davranış kilitli, CI-green) + HEDEF `expected`/`divergence` ile belgeli.

**Düzenlenen (salt label):** `retrieval_golden_multi.yaml` 10 query'e `expected_decompose` (relevant DOKUNULMADI).

**Characterization yaklaşımı (kullanıcı sorusu → karar):** hedef-davranışı doğrudan assert etmek PR-A'da CI'ı kırardı (app/ değişmedi) → **characterization-baseline-first**: mevcut davranış kilitlenir, hedef `expected`/`divergence` ile belgelenir. **xfail/TODO KULLANILMADI** (gizler); PR-B'de divergence-assert'leri güncellenince davranış değişimi diff'te explicit.

**3 bilinen divergence (PR-B hedefi — heuristic YANLIŞ bölüyor → guard ile 0'a inecek):**
- tek-kurum-adı: "çevre şehircilik **ve** iklim değişikliği bakanlığı…" → current 2, target []
- liste-bağlacı: "sosyal güvenlik **ve** emeklilik reformu paketi" → current 2, target []
- tek-konu-refine: "kira artışı **ile ilgili** yeni düzenleme kararı" → current 2, target []

`test_known_divergence_set_is_locked` bu 3'ü kilitler → PR-B'de azalış ilerleme metriği.

**Doğrulama:** ruff+format temiz · full unit **1314** (1265+49) · lint-imports 16/16 · CI 11/11 · deploy success (davranış-nötr).

> **Sıradaki: PR-B heuristic guard — `app/` DOKUNUR → ayrı onay + DUR** (flag-OFF byte-identical + characterization diff: yalnız 3 divergence case güncellenecek).

#### PR-B ✅ done (2026-06-08, PR [#1461](https://github.com/selmanays/nodrat/pull/1461), merged + FULL deploy success)

Decomposition heuristic guard — **deterministik, dar**. app/ touch: **yalnız `app/prompts/query_decomposition.py`**. `decompose_query_llm` + LLM davranışı DOKUNULMADI; flag/benchmark/prod/mutation YOK.

**🔑 Tasarım gerilimi → B kararı (kullanıcı onayı):** DIV#1/#2 (tek-kurum/tek-konu ` ve `, örn "sosyal güvenlik ve emeklilik reformu") deterministik **ayrılamaz** — ilk parçaları (`sosyal güvenlik`, `çevre şehircilik` = 2 kelime) PR-2'nin **meşru** çok-konu parçalarıyla (`Türkiye ekonomisi`, `faiz kararları` = 2 kelime) yapısal olarak özdeş. Prototype kanıtladı: `≥3-kelime` guard'ı DIV#1/#2 ile birlikte 3 PR-2 testini (multi-topic/cap/dedup) de bozuyor = geniş diff. **Karar: `≥3` uygulanmadı; heuristic dar tutuldu.**

**Değişiklikler:**
- **` ile ilgili ` split-marker'lıktan çıkarıldı** (`_TR_SPLIT_MARKERS` + `_SPLIT_RE`) — tek-konu refine, niyet-ayracı değil → DIV#3 `2→[]` (çözüldü).
- **`_strip_subquery_noise`** — split-sonrası soru-kuyruğu/zaman temizliği (`_SUBQUERY_NOISE_WORDS`: ne zaman/kaçta/mı-mi/bugün…). **YALNIZ heuristic path** (`decompose_heuristic` içinde, `_clean_and_cap` öncesi) — LLM çıktısı (`parse_decompose_response → _clean_and_cap`) strip'siz, dokunulmadı (kanıt: `parse(["altın fiyatı ne zaman"]) → ['altın fiyatı ne zaman']`).
- **≥2 içerik kelime** kontrolü noise-strip sonrası.

**Sonuç (deterministik, doğrulandı):**
- DIV#3 "kira artışı **ile ilgili**…": `2→[]` ✅ (`should_not_split`, divergence çözüldü)
- mq_005: böl+temizle `['altın fiyatı gram', '12 yargı paketi çıkacak']` ✅
- mq_007 + should_split: korundu (+ noise-strip bonus "açık mı"→"açık")
- PR-2 (Türkiye ekonomisi 2 / cap 4 / dedup 2): **KORUNDU**
- DIV#1/#2 → yeni dürüst sınıf **`heuristic_out_of_scope`** (LLM-fallback alanı; heuristic böler ama kabul edilen kör-nokta). **Aktif-divergence 3→0.**

**Golden re-sınıf (mini-plan §4 madde 9 belgesi):** `decompose_trigger_cases.yaml` 5. sınıf `heuristic_out_of_scope` eklendi; DIV#1/#2 `should_not_split`→`heuristic_out_of_scope`; DIV#3 `should_not_split` (current 2→0). `test_no_active_divergence_after_pr_b` aktif-divergence=0 kilitler.

**Doğrulama:** ruff+format temiz · full unit **1321** · lint-imports 16/16 · CI 11/11 · FULL deploy success. Flag OFF byte-identical (decompose flag-gated; prod flag OFF → `decompose_heuristic` çağrılmaz; PR-1 SSE/orchestrator regression geçti).

> **Sıradaki: PR-C deterministik benchmark re-run — PR-4D-1 aracıyla yeni-heuristic vs eski (`--rerank off`). Benchmark koşma = AYRI ONAY (DUR).**

#### PR-C Validation Sonucu — PR-B yeni-heuristic prod-corpus (2026-06-09, READ-only)

**Durum: 🛑 DUR / activation yok / iterate needed.** Kullanıcı açık onayıyla prod VPS'te 5 koşum READ-only. **Başlangıç+son invariant:** flag `research.query_decomposition_enabled` OFF (count=0, hiç açılmadı), `retrieval.llm_rerank_enabled=false`, `--persist` YOK (score_history yazımı yok), `/tmp` (host+container) temiz, 13 container healthy, `/health` 200. PR-B kod prod image'da aktif doğrulandı (DIV3 `[]`, mq005 temiz).

**Aggregate (10 query, top_k=20, `--rerank off` deterministik):**

| metric | no-dec | rrf_sum | rrf_max | rank_rrf | union |
|---|---|---|---|---|---|
| recall@5 | 0.1586 | 0.1759 | 0.1759 | 0.1859 | **0.2350** |
| recall@10 | **0.3474** | 0.2970 | 0.2970 | 0.3122 | 0.3122 |
| recall@20 | 0.4413 | **0.4543** | **0.4543** | 0.4361 | 0.4361 |
| ndcg@10 | 0.2691 | 0.2716 | 0.2856 | 0.2666 | **0.2877** |
| map@5 | 0.0953 | 0.1520 | 0.1640 | 0.1577 | **0.2127** |
| mrr@10 | 0.3644 | 0.5200 | **0.5700** | 0.4317 | 0.4817 |

**PR-B öncesi (PR-4D-2) → sonrası (PR-C) delta:**
- **no-decompose birebir aynı** (0.3474/0.1586/0.4413) → determinizm + corpus stabilitesi doğrulandı.
- **recall@10 TÜM merge'lerde KÖTÜLEŞTİ:** rrf_sum/max −9.6%, rank_rrf −8.1%, union −10.5% (no-dec'e göre −10…−14.5%). PR-4D-2'de rrf_sum −5.4% idi → PR-C −14.5% (daha kötü).
- **recall@20 DÜŞTÜ:** −11.7…−12.5%.
- **precision/ranking BELİRGİN İYİLEŞTİ:** map@5 +39…+96%, mrr@10 ~+40%, recall@5 (rank_rrf +36%, union +33%), ndcg@10 hafif↑.
- **rank_rrf top-5 çöküşü DÜZELDİ** (PR-4D-2 recall@5 0.1368 → PR-C 0.1859; cleaning kurtardı). **rrf_max hâlâ rrf_sum'a Pareto-üstün.** **union recall@10 avantajı kayboldu** (artık no-dec'i geçmiyor) ama recall@5+map@5 en yüksek.

**Per-query:**
- **mq_005: HÂLÂ 0.000** (tüm decompose). PR-B alt-sorguları temizledi (`['altın fiyatı gram','12 yargı paketi çıkacak']`) ama recall düzelMEDİ → sorun cleaning-ötesi (altın/yargı makaleleri bu corpus'ta top-10'a hiç gelmiyor; decomposition mq_005 için temelde uygunsuz).
- **mq_007: korundu** (no-dec 0.800, rank_rrf/union 0.800).

**🛑 Karar:** **activation YOK · canary ÖNERİLMEZ · flag OFF kalır.** recall@10 hâlâ no-decompose baseline altında (üstelik PR-4D-2'den kötü) + recall@20 düştü. **no-decompose hâlâ recall@10'da en iyi.** PR tarafında hiçbir prod değişikliği yapılmadı.

**Öğrenim:**
- PR-B **precision↑ / recall↓ trade-off** üretti (noise-strip alt-sorguları daralttı → top-5/ranking↑ ama recall@10/@20↓).
- **Soru-kuyruğu ("ne zaman çıkacak") bazı sorgularda recall'a KATKI sağlıyor olabilir** — atmak recall'ı düşürdü.
- **Decomposition trigger/cleaning mevcut haliyle aktivasyon için HAZIR DEĞİL.** Sonraki olası yön: trigger/golden iteration (noise-strip'i recall-koruyacak şekilde gevşet, golden 10→30 genişlet), flag-enable DEĞİL. **⚠️ Proxy uyarısı korunur:** benchmark deterministik retrieval-merge ölçer; prod PR-3 hâlâ 3b LLM-driven → benchmark Δ retrieval-potansiyeli, prod e2e garanti değil.

#### Trigger / Golden Iteration Reality-Analysis (2026-06-09, read-only)

**Durum: read-only analysis complete.** Kod/benchmark/flag/prod/mutation YOK; `decompose_heuristic` local-çağrı + golden dosya okuma (string transform).

**🔑 Merkezi bulgu — golden-kalibrasyon artefaktı:** PR-C recall@10 düşüşünün önemli kısmı gerçek retrieval kaybı **olmayabilir**. `golden_multi`'nin heuristic relevant'ları `golden_tr`'de **soru-kuyruklu query-formlarına kalibre** (kanıtlandı): mq_001 `"…açık **mı**"`, mq_002 `"…**ne kadar** olacak"`, mq_003 `"…**bugün**"`, mq_004 `"…**ne zaman**"`, mq_005 `"altın fiyatı **bugün** gram"`, mq_006 `"…saat **kaçta**"`. PR-B noise-strip bu kuyrukları atınca alt-sorgu golden-kalibre-formdan uzaklaşıyor → retrieval eşleşmesi zayıflıyor → recall↓. Yani golden, **kuyruksuz alt-sorguları haksız cezalandırıyor**.

- **mq_007 doğal kontrol:** relevant'ları kuyruksuz (`"15 yaş altı sosyal medya yasağı"`, `"doğum izni 24 hafta yasası"`) → noise-strip uygulanmadı → **recall korundu (0.800)**. noise-strip-li 6 query (mq_001-006) kaybetti, strip-siz 1 query korundu = kanıt.
- **mq_005:** should_split **sınıfı doğru** (altın\|yargı 2 ayrı konu) ama **relevant-id kalitesi düşük** — tek prod-snapshot article + popüler konu (golden_tr'de 4 ayrı altın query'si → corpus'ta benzerleri çok → tek article gömülü) + kuyruk-kalibre → güvenilir ölçüm zayıf. *ambiguous değil, düşük-kaliteli-relevant.*
- **N=10 çok dar:** 2.3 relevant/q, çoğu 2-relevant → recall adımı **0.50** (kaba); tek query aggregate'i ~0.05 çeviriyor (recall@10 −14.5% ≈ 1 query'nin yarısı). İstatistiksel güç zayıf.
- **Eksik:** `golden_multi`'de negatif örnek (should_not_split / tek-kurum) yok; kuyruk-bağımsız (content-based) relevant yok.

**Soru 9 yanıtı — kod-PR ŞU AN ERKEN:** mevcut golden her recall ölçümünü şüpheli kılıyor (kuyruk-artefakt + kaba granülarite + tek-snapshot relevant) → her kod-PR bu golden'la yanlış-değerlendirilir. **Önce golden-quality.**

**Önerilen sıra (PR-D serisi):**

| PR | Kapsam | app/ touch | Onay |
|---|---|---|---|
| **PR-D1** golden-quality | `retrieval_golden_multi.yaml` 10→30; relevant'lar **kuyruk-bağımsız** (content-based) golden_tr-reuse; niş-relevant (popüler-olmayan, ölçülebilir); negatif kategoriler (should_not_split/tek-kurum); ≥3 relevant/q; istatistik notu | ❌ **salt YAML/test** | CI-hard |
| **PR-D2** noise-strip / trigger guard iteration | `query_decomposition.py` — kuyruğu tamamen atma yerine soru-eki (mı/mi) at + içerik-zaman (bugün/ne zaman) koru/düşük-ağırlık | ✅ **app/ DOKUNUR → DUR + açık onay** | flag-OFF byte-identical |
| **PR-D3** benchmark re-run | PR-4D-1 aracıyla (güvenilir golden üstünde) | ❌ | **prod-corpus benchmark = ayrı onay** |

Sıra: **D1 (ölçümü güvenilir yap) → D2 (kod, onaylı) → D3 (ölç, onaylı)**. **Yeni card/UUID YOK** (golden_tr 55-query reuse). **En kritik içgörü:** sorun decomposition'ın kendisi olmayabilir — golden ölçüm-aracı kuyruksuz alt-sorguları haksız cezalandırıyor; PR-D1 en yüksek değerli + en düşük riskli sonraki adım (kod yazmadan ölçüm güvenilirliğini düzeltir).

#### PR-D1 ✅ done (2026-06-09, PR [#1465](https://github.com/selmanays/nodrat/pull/1465), merged + FULL deploy success)

Golden-quality genişletme — **app/ touch 0** (yalnız tests/), **yeni card/UUID 0** (golden_tr 30-UUID havuzundan reuse).

**`retrieval_golden_multi.yaml` 10→30 query:**
- **5 sınıf dengeli:** 10 should_split / 8 should_not_split / 2 heuristic_out_of_scope / 3 split_but_needs_cleaning / 7 llm_or_ambiguous.
- **kuyruklu(8)/kuyruksuz(22) dengeli** → noise-strip artefaktını izole (mq_007 kuyruksuz doğal-kontrol korundu).
- **niş konu ağırlıklı** (ALES/SAHA/Şanlıurfa/iklim/ABD-İran ×1 niş-UUID), popüler azaltıldı → recall-güvenilir.
- Her query: `expected_decompose` + `rationale`; popüler-UUID'lere `low_confidence` (7, mq_005 dahil — altın popüler + kuyruk-kalibre).
- Eski `decompose: heuristic|llm` alanı kaldırıldı → **tek-etiket** `expected_decompose` (decompose_trigger_cases.yaml ile aynı 5-sınıf).

**Testler (recall ÖLÇMEZ):** `test_golden_multi_subset.py` yeniden (30-yapı + sınıf-dağılım + UUID-reuse + yeni-card-yok + heuristic-expectation split≥2/empty[]/llm-zorunlu-değil + low_confidence + mq_007 kontrol); `test_decompose_trigger` has_expected_decompose 10→30, labels_match kaldırıldı.

**Doğrulama:** 30 query heuristic-expectation sondaj-doğrulandı (sınıf↔gerçek davranış) · ruff+format temiz · full unit **1325** · lint-imports 16/16 · CI 11/11 · FULL deploy success (davranış-nötr, app/ değişmedi). **Recall benchmark KOŞULMADI.**

> **Sıradaki: PR-D2 noise-strip gevşetme (Yol B) — `app/` DOKUNUR → ayrı onay + DUR.** Güvenilir golden hazır; artık noise-strip iterasyonu adil ölçülebilir (kuyruklu/kuyruksuz izolasyon + niş-relevant). PR-D3 benchmark re-run = ayrı prod-corpus onayı.

#### PR-D2 ✅ done (2026-06-09, PR [#1467](https://github.com/selmanays/nodrat/pull/1467), merged + FULL deploy success)

Noise-strip gevşetme (recall-koruyan cleaning) — app/ touch **yalnız `app/prompts/query_decomposition.py`**. `decompose_query_llm` + LLM parse DOKUNULMADI; flag/benchmark/prod/mutation YOK; golden_multi relevant-id DOKUNULMADI.

**Değişiklik:** `_SUBQUERY_NOISE_WORDS` gevşedi → **yalnız soru-eki** `{mı/mi/mu/mü + midir/mıdır/mudur/müdür}`. **Çıkarıldı (artık korunur):** ne/neden/nasıl/nedir/kim/kaç/kaçta/nerede/hangi/niye/niçin/zaman/kadar/bugün/şimdi (içerik-taşıyan zaman/soru-kuyruğu → recall-katkı). Gerekçe: PR-C precision↑/recall↓ + golden kuyruk-kalibre artefaktı → agresif cleaning recall'a zarar veriyordu.

**Davranış (prototype + gerçek doğrulandı):**
- `mq_005` → `['altın fiyatı bugün gram', '12 yargı paketi ne zaman çıkacak']` (kuyruk korundu; PR-B'de atılıyordu).
- `mq_004` → `['kurban bayramı ne zaman', 'üniversiteler tatil']` ('mi' atıldı, 'ne zaman' korundu).
- **split-SAYISI değişen 0/30** (sınıf/expected_decompose korundu) · cleaning-çıktısı gevşeyen 7/30.
- DIV#3 `ile ilgili` → `[]` korundu · mq_007 kuyruksuz kontrol korundu · **PR-2 primitive (multi_topic 2/cap 4/dedup 2) AYNI** · LLM-path strip-siz korundu.

**Geniş-diff kontrolü:** yalnız cleaning-çıktısı gevşedi, split/sınıf hiç değişmedi → **diff hedeflerden dar**. PR-D1 golden expectation korundu; yalnız PR-B'nin 3 cleaning-çıktı testi + `decompose_trigger_cases.yaml` note'ları PR-D2 kararını yansıtacak şekilde güncellendi.

**Doğrulama:** ruff+format temiz · full unit **1325** · lint-imports 16/16 · CI 11/11 · FULL deploy success (flag OFF byte-identical; decompose flag-gated → prod davranışı değişmedi).

> **Sıradaki: PR-D3 deterministik benchmark re-run — PR-4D-1 aracıyla, yeni 30-query golden + PR-D2 gevşetilmiş heuristic (`--rerank off`). Benchmark koşma = AYRI prod-corpus ONAYI (DUR).** Beklenti: kuyruklu/kuyruksuz izolasyon + niş-relevant ile recall@10 düşüşünün ne kadarı golden-artefakt ne kadarı gerçek ayrışabilir.

#### PR-D3 Validation Sonucu — 30-query golden + PR-D2 heuristic prod-corpus (2026-06-09, READ-only)

**Durum: 🟡 canary-adayı / activation YOK / flag OFF.** Kullanıcı onayıyla prod VPS 5 koşum READ-only. **İnvariant (başta+sonda):** flag OFF (count=0), `retrieval.llm_rerank_enabled=false`, **PR-D2 prod image doğrulandı** (mq_005 kuyruk korundu / ile-ilgili `[]` / mq_007 korundu), 30-query golden, `--rerank off`, `--persist` YOK, DB-write YOK, `/tmp` (host+container) temiz, 13 container healthy, `/health` 200.

**Aggregate (30 query, top_k=20, deterministik):**

| metric | no-dec | rrf_sum | rrf_max | rank_rrf | **union** |
|---|---|---|---|---|---|
| recall@5 | 0.1001 | **0.1167** | **0.1167** | 0.0848 | 0.1011 |
| recall@10 | 0.2334 | 0.2304 | 0.2304 | 0.2413 | **0.2608** |
| recall@20 | 0.2932 | **0.3402** | **0.3402** | 0.3258 | 0.3258 |
| ndcg@10 | 0.1591 | 0.1634 | 0.1681 | 0.1687 | **0.1826** |
| map@5 | 0.0504 | 0.0618 | 0.0658 | 0.0605 | **0.0774** |
| mrr@10 | 0.1940 | 0.2145 | 0.2312 | 0.2309 | **0.2466** |
| latency p50 / p95 | 11.1 / 22.2s | 6.6 / 12.7s | 0.8 / 2.5s | 0.7 / 2.0s | 0.8 / 1.8s |

**Ana sonuç:**
- **`union` recall@5/10/20'yi BİRLİKTE koruyor/iyileştiriyor** (vs no-dec: +1.0% / **+11.7%** / +11.1%) — recall@10 **no-decompose ÜSTÜNDE**; ndcg/map/mrr **en yüksek**; latency düşük (0.8s).
- `rrf_max` `rrf_sum`'a **hâlâ Pareto-üstün** (recall@5/10/20 birebir, ndcg/map/mrr daha iyi).
- `rank_rrf` **top-5'i bozuyor** (recall@5 −15.3% vs no-dec / −27% vs rrf_sum).
- `rrf_sum`/`rrf_max`: recall@5 +16.6%, recall@10 −1.3% (marjinal), recall@20 +16%.

**Grup analizi (golden-artefakt hipotezi DOĞRULANDI):**
- **should_split (n=10): union +27%** (0.376→0.480) · kuyruksuz (n=22) +pozitif (0.208→0.249) · güvenilir lc=False (n=23) +pozitif (0.253→0.292).
- should_not_split (n=8) + llm_or_ambiguous (n=7): **no-dec ile AYNI** (heuristic `[]` → decompose etmez, doğru).
- Zayıf: kuyruklu (n=8, artefakt kalıntısı) + low_confidence (n=7, popüler-konu label). `mq_005` hâlâ **0.000** (cleaning-ötesi label sorunu). `mq_007` **korunuyor** (rank_rrf/union 0.800).

**Dürüstlük notları:** (a) **PR-C ile DOĞRUDAN kıyas YOK** (golden farklı; yalnız directional: PR-C'de union recall@10 −10.5% → PR-D3 +11.7%, yön tersine döndü); (b) benchmark **retrieval-merge proxy** — prod PR-3 hâlâ 3b LLM-driven → e2e garanti DEĞİL; (c) N=30 orta-ölçek; (d) `mq_005` + low_confidence label kalıntısı sürüyor (iyileşme güvenilir+kuyruksuz+should_split ağırlıklı).

#### Canary Planı (yalnız PLAN — uygulama YOK, ayrı açık onay gerekir)

**🔑 Karar: `union` merge canary-adayı. Activation/flag açma YOK.** Aşağıdaki plan ayrı bir onay turunda değerlendirilecek; bu turda hiçbir flag/canary/prod işlemi yapılmadı.

**Önkoşullar (canary öncesi doğrulanacak):**
- #619 OPEN kalır · prod flag OFF · production `/health` OK · rollback path net (aşağıda) · telemetry hazırlığı doğrulanacak (PR-5 `_decomposition_telemetry` mevcut: method/sub_query_count/llm_used/fallback_reason/duration_ms — cost hariç).
- ⚠️ **Açık mimari soru (canary öncesi analiz):** mevcut `research.query_decomposition_enabled` global bool. **Allowlist/staff-bazlı** açma için ya (a) yeni bir setting (`research.query_decomposition_allowlist` — user/session id listesi) + orchestrator'da gate, ya da (b) staff-flag kontrolü gerekir → **bu app/ kod değişikliği = ayrı PR (PR-E?) + ayrı onay**. Global bool'u açmak = TÜM trafik (canary değil) → **YAPILMAZ**. Ayrıca `union` merge prod'da deterministik-merge DEĞİL (prod PR-3 3b LLM-driven) → benchmark-merge'i prod'a taşımak ayrı bir orchestration kararı.

**Önerilen canary (uygulama ayrı onay):**
- Küçük **internal/staff veya allowlist'li** kullanıcı grubu · kısa süreli (örn. 48-72h) · **geniş kullanıcı trafiğinde enable YOK**.
- Allowlist mekanizması yoksa önce o eklenmeli (ayrı kod-PR); global-bool ile canary mümkün değil.

**Ölçülecek metrikler (canary sırasında):** decomposition_triggered count · sub_query_count dağılımı · fallback_reason · latency p50/p95 · citation coverage · empty/low-result rate · user-facing error rate · cost/provider impact · qualitative spot-check.

**Stop conditions (canary iptal):** latency p95 belirgin artış · empty-result rate artışı · citation kalitesi düşüşü · error/fallback artışı · maliyet beklenenden yüksek · qualitative spot-check kötüleşmesi.

**Rollback:** flag OFF (DELETE app_settings satırı veya allowlist boşalt) · config revert · **schema/data rollback GEREKMEZ** (flag-gated, mutation yok). Anında etki (Redis pub/sub L1 invalidation).

#### PR-E Allowlist Canary Mechanism Reality-Analysis (2026-06-09, read-only)

**Durum: read-only analysis complete.** Kod/test/benchmark/flag/canary/prod/mutation YOK; yalnız mevcut mimari okundu.

**Problem:** `research.query_decomposition_enabled` **global bool** — global ON = TÜM trafik (gerçek canary değil). Güvenli canary için user-level gate gerekir.

**Mevcut mimari bulguları:**
- **User context:** `app_research_stream.py:204` handler'da `user: User` MEVCUT (`get_current_user`). `User`: `id`(UUID), `email`(CITEXT), `role`(str), `tier`(str). Flag resolve (`:489-523`) handler içinde → user-level karar buraya eklenebilir.
- **Gating pattern:** `require_admin` (deps.py:94) → `if user.role != "super_admin": 403`. Role-bazlı gate mevcut.
- **SettingsStore:** `get(db,key,default)` Any (string/CSV okunabilir) · `set/reset` DB+L1-invalidate+pub/sub · L1 cache + Redis `settings:invalidate` anlık invalidation. **app_settings key-value → string allowlist SCHEMA-SUZ.**
- **Telemetry:** `_decomposition_telemetry` PII-suz (query metni yok) → cohort alanı (allowlist/global/baseline, user_id yazmadan) eklenebilir.
- **Rollback:** global OFF veya allowlist boşalt (reset) → pub/sub anlık; schema/data rollback YOK.

**⚠️ Prod PR-3 vs benchmark-union ayrımı (kritik):** Benchmark kazananı `union` = **deterministic retrieval-merge** — prod'da YOK. Prod PR-3 = **3b LLM-driven prompt-hint** (decompose_query → sub_queries → LLM'e "ayrı ara" hint, merge yok). **PR-E canary benchmark-union'ı prod'a TAŞIMAZ; yalnız "kimin alacağını" gate'ler — alınan şey mevcut prod-3b'dir.** Canary amacı: prod-3b decomposition'ın **benchmark proxy'nin ölçemediği e2e etkisini** ölçmek (latency / citation quality / empty-result rate / cost-provider impact / qualitative). union-merge prod-adoption'ı **tamamen ayrı gelecek-kararı**.

**Alternatifler:**

| | Alt 1: allowlist setting | Alt 2: staff/admin-only | Alt 3: shadow / header |
|---|---|---|---|
| Mekanizma | `global OR (user.id ∈ allowlist)` | `global OR role=="super_admin"` | decompose çalışır sonuç kullanılmaz (log) / internal-header |
| schema | ❌ YOK (app_settings string) | ❌ YOK (role mevcut) | ❌ YOK |
| rollback | allowlist boşalt / global OFF | global OFF | flag OFF / header yok-say |
| telemetry | cohort allowlist/baseline (PII-suz) | cohort staff/baseline | shadow-diff log |
| risk | düşük (parse-hata→OFF) | çok düşük (yalnız admin) | shadow en düşük (sonuç kullanılmaz) |
| canary değeri | **yüksek** (gerçek kullanıcı alt-kümesi) | düşük (admin ≠ gerçek trafik) | shadow ölçüm-only / header manuel-dar |

**Önerilen PR-E scope (Alt 1 — minimum güvenli):**
- Yeni setting `research.query_decomposition_allowlist` (string CSV user-id, default `""`); `SETTING_REGISTRY` entry.
- Flag resolve: `_query_decomposition_enabled = global_bool or (str(user.id) in _parse_allowlist(...))`. Global bool OFF kalır; yalnız allowlist ON. **parse-hata → OFF** (zarif degrade).
- Telemetry cohort: `baseline | allowlist | global` (**PII yazılmaz** — user_id değil, yalnız cohort enum).
- **Dosyalar:** `app_research_stream.py` (flag-resolve + telemetry cohort), `settings_admin/routes.py` (registry), `tests/unit/` (allowlist parse + gate in/out + **OFF+boş-allowlist=byte-identical** + cohort).
- **Byte-identical kanıtı:** global OFF + allowlist boş → `enabled=False` → decompose çağrılmaz (mevcut SSE-replay + yeni "boş-allowlist=OFF" testi). Allowlist parse saf-fonksiyon (DB-suz unit-test).

**Hard-stop:** schema/migration gerekirse DUR (Alt 1 schema-suz → tetiklenmiyor) · prod flag/canary gerekirse DUR · geniş app refactor gerekirse DUR (flag-resolve ~3 satır → dar) · telemetry PII riski çıkarsa DUR (cohort user_id'siz) · benchmark/prod-traffic gerekirse DUR. **Implementation ayrı açık onay.**

#### PR-E ✅ done (2026-06-09, PR [#1471](https://github.com/selmanays/nodrat/pull/1471), merged + FULL deploy success)

Allowlist canary mechanism (Alt 1) — **schema-suz**, app/ touch `app_research_stream.py` + `settings_admin/routes.py`. `union`/orchestration/`decompose_query_llm` DOKUNULMADI; PR-E yalnız "kimin alacağını" gate'ler (alınan = mevcut **prod-3b LLM-driven**).

**Değişiklikler:**
- Yeni setting `research.query_decomposition_allowlist` (string CSV user-id, default `""`) — `SETTING_REGISTRY`.
- `_parse_decomposition_allowlist` (saf): CSV→UUID-canonical set; invalid/whitespace/boş **sessizce atlanır** (raise etmez).
- `_resolve_decomposition_gate` (saf): `(enabled, cohort)` → global ON→`(True,global)` · global OFF+`user.id∈allowlist`→`(True,allowlist)` · aksi→`(False,baseline)`.
- Flag-resolve (`_research_stream_body`): inline bool yerine gate helper (`user.id`).
- `_decomposition_telemetry += cohort` (baseline\|allowlist\|global) — **PII-suz** (user_id/email YOK).

**Davranış:** global true → tüm trafik (cohort global) · global false + allowlist → yalnız o user.id (cohort allowlist) · global false + boş allowlist → **byte-identical** (cohort baseline, decompose çağrılmaz).

**Doğrulama:** 10 yeni test (parse + gate 4-senaryo + cohort PII-free) · full unit **1335** · lint-imports 16/16 · CI 11/11 · FULL deploy success. **Prod byte-identical doğrulandı:** `enabled_count=0` + `allowlist_count=0` → `gate(OFF,boş)=(False,baseline)` → decompose çağrılmaz; `_resolve_decomposition_gate` prod image'da aktif; /health 200. **Prod flag/allowlist SET EDİLMEDİ** (canary başlatılmadı).

> **Sıradaki (ayrı açık onay):** canary başlatma = allowlist'e küçük staff/internal user.id seti doldurma (`settings_store.set research.query_decomposition_allowlist`). Bu **prod-config işlemi** — mini-plan §4 "Canary Planı" (önkoşul/metrik/stop/rollback) izlenir. Mekanizma hazır; **doldurma/flag açma otomatik YAPILMAZ.**

#### Canary Readiness Sonucu (2026-06-09, read-only)

**Durum: 🟡 mekanik HAZIR — dar internal micro-canary mevcut observability ile mümkün; geniş canary öncesi PR-F adayı.** Hiçbir prod-config/allowlist-set/flag/kod değişikliği yapılmadı.

**Prod ayar (read-only doğrulandı):** `research.query_decomposition_enabled` **unset** (count=0 → default OFF) · `research.query_decomposition_allowlist` **unset** (count=0 → default `""`) · `gate(False, baseline)` → decompose çağrılmaz = byte-identical · SettingsStore L1+Redis pub/sub anlık invalidation.

**Telemetry HAZIR (decompose-level, cohort-etiketli, PII-suz):** `logger.info("query_decomposition %s", {cohort, method, sub_query_count, llm_used, fallback_reason, duration_ms})` (`app_research_stream.py:794`). cohort ∈ {baseline, allowlist, global}. Grep: `docker compose logs api --since 1h | grep query_decomposition`. → cohort-sayımı / sub_query dağılımı / fallback / decompose-latency doğrudan filtrelenebilir.

**⚠️ Eksik observability (dar-canary için blocker DEĞİL; geniş-canary öncesi PR-F):**
- **E2E latency / citation coverage / empty-result / error rate — cohort-etiketli DEĞİL.** `_log_step` per-phase SSE'ye; `_log_coverage_gap`→`logger.warning("coverage_gap")` cohort-tag yok (+ question metni içerir). → küçük allowlist'te `user.id`-bazlı manuel DB-filtreleme (`messages`/`conversations`) + spot-check ile ölçülür.
- **🔴 decompose-LLM cost tracking kör noktası:** `decompose_query_llm` raw `provider.generate_text` (`query_decomposition.py:232`) — `_tracked_chat_generate` DEĞİL → llm-fallback cost `provider_call_logs`'a muhtemelen yazılmıyor. heuristic-mod cost-suz (düşük risk); llm-fallback **kör**.

→ **PR-F adayı (opsiyonel, geniş-canary öncesi):** e2e metriklere cohort-tag + decompose-LLM cost tracking. Dar internal canary (1-2 user, manuel spot-check) için **gerekli değil**.

**Canary başlatmak için gereken input (kullanıcıdan):** (1) 1-2 internal/staff `user.id` (PII türetilmez — kullanıcı sağlar) · (2) pencere onayı (30-60dk / 5-10 istek) · (3) trafik: doğal mı manuel-senaryo mu (boş trafik = ölçüm yok) · (4) güncel 5 spot-check query (golden UUID eski-snapshot; canlı için güncel) · (5) stop-eşik onayı. Minimal canary runbook: [[query-decomposition-pr4-staging-runbook|runbook]] "Minimal Canary Runbook".

#### Manual Admin Micro-Canary Sonucu (2026-06-09, READ-only sonuç + tamamlanmış rollback)

**Durum: ✅ teknik başarılı / 🟡 e2e nötr (küçük örneklem) / 🔴 observability bulgusu → PR-F önerilir. Rollback tamamlandı, prod byte-identical.**

**Canary akışı (kullanıcı açık onayıyla, adım adım):** yalnız admin `user.id` (`7a7eb35b-…`) allowlist'e set edildi; **global flag `research.query_decomposition_enabled` HİÇ açılmadı** (unset/OFF kaldı). `gate(admin)=(True, allowlist)`, `gate(diğer)=(False, baseline)` doğrulandı. Admin arayüzünden 8 spot-check sorgusu çalıştırıldı (yeni-konuşma). Sonra allowlist reset edildi.

**Sonuç (thinking_steps DB'den — log-bağımsız):**
- **7/8 decompose tetiklendi** (query_decomposition thinking-step persist). **Q6** (should_not_split, `ile ilgili`) **doğru şekilde tetiklenmedi** (decomp_step=0 — kontrol). **Q8** (virgüllü) **LLM-fallback** bölündü. **Q7** (oos) yanlış böldü (beklenen kör-nokta).
- **error/exception YOK.** Kaynak düşüşü yok: Q1 4→4, Q4 2→2, Q6 2→2 (baseline↔during sources_used aynı).
- **🟡 E2E fayda küçük örneklemde NÖTR:** citation **artışı görülmedi**; baseline agent zaten bazı sorgularda çoklu `search_news` çağırabiliyor (prod-3b LLM-driven — benchmark-union'dan farklı). decompose-hint bu örneklemde ek citation getirmedi.

**🔴 Kritik observability bulgusu:** `logger.info("query_decomposition")` telemetry **prod log-stream'de görünmüyor** (yalnız uvicorn access INFO; `app.*` logger çıktısı yok — tam olarak #1072'nin `coverage_gap`'i info→warning yapma nedeni). Ölçüm **thinking_steps DB persist'inden** yapılabildi (decompose-occurrence + sources_used). **Log üzerinden method/cohort/sub_query_count/fallback_reason/duration_ms izlenemiyor**; decompose-LLM **cost tracking kör** (raw `generate_text`).

**Rollback (tamamlandı):** allowlist reset (`settings_store.reset` → DELETE + L1-invalidate + pub/sub) · `enabled` OFF kaldı · `allowlist` unset (count 0/0) · `gate(admin)=(False, baseline)` → admin artık decompose almıyor · `/health` 200 · **prod byte-identical baseline'a döndü.** Schema/data mutation yok.

#### Önerilen sonraki PR — PR-F Observability (geniş canary öncesi)
- `query_decomposition` telemetry **prod-visible** olmalı (`logger.warning` gibi) **veya DB'ye persist** edilmeli (log-only prod'da ölü).
- **cohort** thinking_steps/DB'ye yazılmalı (allowlist vs baseline kıyası için).
- **decompose-LLM cost tracking** eklenmeli (raw `generate_text` → tracked).
- E2E cohort telemetry (latency/citation/empty/error) **geniş canary öncesi güçlendirilmeli**. Dar micro-canary thinking_steps DB ile ölçülebildi; geniş canary otomatik gözlem ister.

#### PR-F Observability Reality-Analysis (2026-06-09, read-only)

**Durum: read-only analysis complete.** Kod/prod-config/flag/canary/benchmark/mutation YOK.

**🔑 Düzeltilmiş observability bulgusu:** Micro-canary'de "telemetry eksik" sanılan şey aslında **çok daha hazır** — `method` / `sub_query_count` / `fallback_reason` / `duration_ms` **zaten `thinking_steps` DB metadata'sında persist ediliyor** (PR-5 `_log_step(**extra)`). **Prod DB'de kanıtlandı:** admin micro-canary mesajlarında `method=llm subq=3 dur=1197ms` (Q8 LLM-fallback) / `heuristic subq=2` (Q1-7). **Tek eksik ana alan: `cohort=YOK`** (PR-E cohort yalnız `logger.info`'da, thinking_step'e eklenmemiş).

**Prod log görünürlük bulgusu:** `app.*` logger `info` prod log-stream'de **görünmüyor** — kök neden `main.py`'de explicit `logging.basicConfig/dictConfig/setLevel` YOK → root default WARNING (`log_level="INFO"` config'de var ama uygulanmıyor). `coverage_gap` bu yüzden #1072'de warning'e alınmıştı. `query_decomposition` info log'u prod-greppable değil. **Ama thinking_step DB-persist bunu by-pass ediyor** (metadata DB'de).

**Cost tracking:** `decompose_query_llm` raw `provider.generate_text` (Q8'in 1197ms LLM call'ı izlenmedi) → provider cost tracking **kör**. **Minimum PR-F'e DAHİL DEĞİL → ayrı PR-G'ye bırakılmalı** (daha büyük: `decompose_query_llm` veya provider-tracking path'e dokunur).

**Alternatifler:**

| | Alt A: cohort→thinking_step | Alt B: logger.info→warning | Alt C: decompose-LLM cost |
|---|---|---|---|
| Değişiklik | `_log_step(…, cohort=_decomp_cohort)` (1 satır) | `logger.info`→`logger.warning` (1 satır) | `decompose_query_llm` → `track_provider_call` |
| app/ touch | `app_research_stream.py` 1 satır | `app_research_stream.py` 1 satır | `query_decomposition.py` + observability import |
| schema | ❌ yok (thinking_steps JSONB) | ❌ yok | ❌ yok (provider_call_logs mevcut) |
| PII | cohort enum — yok | payload metni yok — yok | cost metrik — yok |
| canary değeri | **yüksek** (DB cohort-filtreli sorgu) | orta (prod-log görünür, single dahil) | orta (LLM-fallback cost) |
| sınır | is_decomposed=False (single) thinking_step yok → cohort+single DB'de görünmez | log-grep manuel | `decompose_query_llm` değişir (PR-B "değişmez" idi; PR-G gerekçesi farklı) |

**Önerilen minimum PR-F: Alt A + Alt B** — yalnız `app/api/app_research_stream.py` (~2 satır davranış-nötr observability). schema yok · PII yok · **flag OFF byte-identical** (flag-OFF'ta thinking_step/log emit edilmez). Alt A tek gerçek eksiği (cohort) DB'ye yazar (micro-canary sorgusu artık `cohort='allowlist'` filtreli); Alt B prod-log'u görünür yapar + Alt A'nın single-cohort boşluğunu kapatır. **Testler:** cohort thinking_step metadata'da var · query_decomposition warning-seviyesinde + PII-free payload · mevcut decomposition testleri korunur.

**PR-G notu (ayrı, sonraki):** decompose-LLM cost tracking — daha büyük risk, `decompose_query_llm` / provider-tracking path'e dokunur. Geniş canary'de cost-matter ederse ayrı onaylı PR.

**Hard-stop:** schema/migration → Alt A+B schema-suz (tetiklenmez) · PII riski → enum/metadata PII-suz (tetiklenmez) · geniş refactor → 2 satır (tetiklenmez) · prod-config/flag/canary/benchmark → yok (tetiklenmez) · **cost tracking PR-F içine kayarsa DUR** (→ PR-G). **Implementation ayrı açık onay.**

#### PR-F ✅ done (2026-06-09, PR [#1476](https://github.com/selmanays/nodrat/pull/1476), merged + FULL deploy success)

Observability minimum (Alt A+B) — app/ touch **yalnız `app/api/app_research_stream.py`** (~2 satır). orchestration/decomposition/query-splitting/`decompose_query_llm` DOKUNULMADI; cost tracking YOK (PR-G); schema/prod-config/flag/mutation YOK.

**Değişiklikler:**
- **Alt A:** `query_decomposition` thinking_step'e `cohort=_decomp_tele["cohort"]` (`_log_step`) → `Message.thinking_steps` JSONB persist → **canary cohort DB-sorgulanabilir** (micro-canary'de eksik olan TEK alan kapandı). Mevcut metadata (method/sub_query_count/llm_used/fallback_reason/duration_ms) korundu.
- **Alt B:** telemetry log `logger.info`→`logger.warning` — `app.*` logger prod effective INFO yutuyordu (`main.py` explicit logging setup yok → root WARNING; `coverage_gap` #1072 ile aynı kök) → **prod-greppable**. Payload metrik-only — **PII (query/user_id/email) içermez**.

**Doğrulama:** 3 yeni test (cohort-in-thinking_step kontrat + cohort-enum + warning-no-PII) · full unit **1338** · lint-imports 16/16 · CI 11/11 · FULL deploy success. **Prod byte-identical doğrulandı:** enabled/allowlist 0/0 · `gate(OFF,boş)=(False,baseline)` · PR-F kod aktif (`cohort=_decomp_tele`) · /health 200. **Flag OFF byte-identical** (decompose flag-gated → flag-OFF'ta thinking_step/log emit edilmez). **Prod flag/allowlist SET EDİLMEDİ.**

> **Sıradaki (ayrı açık onay):** (a) **PR-G** decompose-LLM cost tracking (ayrı, daha büyük) · veya (b) geniş canary (artık cohort DB'de sorgulanabilir + telemetry warning prod-greppable → observability güçlendi). Otomatik YAPILMAZ.

#### Micro-Canary v2 Sonucu — PR-F canlı doğrulama (2026-06-09, READ-only + rollback)

PR-F observability'sini **canlı** doğrulamak için admin-only micro-canary tekrarı (allowlist set→reset; **kod/flag/benchmark/mutation yok**). **PR-F doğrulandı:** warning log'da **8** `query_decomposition` satırı (v1'de 0; info-yutulma kalktı) · payload **PII-suz** · `thinking_steps` DB'de `cohort='allowlist'` persist (method/sub_query_count/fallback_reason/duration_ms ile). **Canary teknik başarılı:** 7/8 decompose · Q3 should_not_split tetiklenmedi (kontrol ✓) · Q8 LLM-fallback (method=llm subq=3 1312ms) · error/coverage_gap 0 · sources düşüşü yok. **E2E fayda nötr** (Q1/Q2/Q3 baseline↔during aynı; prod-3b zaten çoklu search). Q7 oos yanlış-bölme = known blind spot (düşük kaynak). **Karar:** genişletilmiş canary **önerilmez** (observability hazır, sinyal nötr) · **PR-G yalnız LLM-fallback maliyeti önem kazanırsa** · **#619 activation-pending / flag OFF.** Rollback tamam (prod byte-identical). Detay: runbook §9 v2 instance.

> **🧷 Ark kapanışı (2026-06-11):** "neden e2e fayda üretmedi?" derin analizi → [[query-decomposition-postmortem]] (root causes: capability overlap + problem-solution mismatch + evidence-transfer yanılgısı; only-do-if koşulları; PR-G yapılmaz; query expansion ayrı future investigation). #619 rafta/activation-pending, OPEN.

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
- **Post-mortem (kapanış referansı):** [[query-decomposition-postmortem]] — neden e2e fayda üretmedi (root causes + only-do-if + final recommendation; ark 2026-06-11'de rafta/activation-pending kapandı).

## Kaynaklar

- [apps/api/app/core/retrieval.py](../../apps/api/app/core/retrieval.py) — 96-satır facade
- [apps/api/app/core/_retrieval_chunks.py](../../apps/api/app/core/_retrieval_chunks.py) §35 — `hybrid_search_chunks`
- [apps/api/app/api/app_research_stream.py](../../apps/api/app/api/app_research_stream.py) §200 — `_research_stream_body` orchestration
- [apps/api/app/core/research_tools.py](../../apps/api/app/core/research_tools.py) §491 — `execute_search_news`
- [apps/api/app/prompts/query_planner.py](../../apps/api/app/prompts/query_planner.py) §330 — `QueryPlan` (sub_queries yok)
- [apps/api/app/prompts/query_rewrite.py](../../apps/api/app/prompts/query_rewrite.py) — condense (LLM güvenlik altın-standart: timeout+fallback)
- [apps/api/app/shared/runtime_config/settings_store.py](../../apps/api/app/shared/runtime_config/settings_store.py) — flag mekanizması (migration-suz)
- GitHub issue: [#619](https://github.com/selmanays/nodrat/issues/619)
