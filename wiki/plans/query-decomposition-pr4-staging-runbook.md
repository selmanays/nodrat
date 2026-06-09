---
type: plan
title: "Query Decomposition PR-4 — Staging Recall Validation Runbook (#619)"
slug: query-decomposition-pr4-staging-runbook
status: live
created: 2026-06-05
updated: 2026-06-05
github_issue: 619
github_issue_url: https://github.com/selmanays/nodrat/issues/619
sources:
  - wiki/plans/query-decomposition-mini-plan.md§4
  - apps/api/tests/eval/retrieval_benchmark.py
  - apps/api/tests/eval/score_history/snapshot.py
  - apps/api/app/modules/settings_admin/routes.py§1143
  - apps/api/app/api/app_research_stream.py§706
  - apps/api/app/prompts/query_decomposition.py
  - apps/api/app/shared/observability/cost_tracker.py
tags:
  - runbook
  - retrieval
  - query-decomposition
  - validation
  - planned
aliases:
  - pr4-runbook
  - decomposition-staging-runbook
---

# Query Decomposition PR-4 — Staging Recall Validation Runbook (#619)

> **TL;DR:** PR-3 ile query decomposition wiring prod'da **flag OFF** (byte-identical). PR-4 bu feature'ı açmadan önce **recall regresyonu olmadığını** doğrular. **Araç + veri HAZIR** (PR-4A `--decompose` benchmark modu [#1447] + PR-4B `retrieval_golden_multi.yaml` [#1449]); kalan = **gerçek koşum operasyonu** (prod-corpus + ortam seçimi → **AYRI onay**). **Benchmark settings-flag OKUMAZ → `--decompose` CLI flag'i kullanılır; production `research.query_decomposition_enabled` HER ZAMAN OFF kalır.** **Proxy uyarısı:** benchmark *deterministik retrieval-merge* ölçer, prod *3b LLM-driven* e2e recall'ı DEĞİL. Bu sayfa docs-only; gerçek operasyon ayrı kullanıcı onayı gerektirir.

---

## ⚠️ ÖN-KOŞUL UYARISI — runbook'un kalbi (önce oku)

Read-only audit (2026-06-05) şu üç gerçeği ortaya çıkardı. **Bunlar çözülmeden PR-4 ölçümü geçersizdir:**

### Blocker 1 — Benchmark decomposition'ı görmüyordu → PR-4A ile ÇÖZÜLDÜ

`tests/eval/retrieval_benchmark.py` **retrieval-seviyededir**: `hybrid_search_chunks`'ı tek `effective_query` ile çağırır; `_research_stream_body`'den (decomposition orchestration, `app_research_stream.py§706`) geçmez → `research.query_decomposition_enabled` **settings-flag'ini OKUMAZ**. Yani settings-flag'i açıp benchmark koşmak boş kıyastır (ON/OFF byte-identical).

> **Çözüm → PR-4A ([#1447](https://github.com/selmanays/nodrat/pull/1447)):** `retrieval_benchmark.py`'a **`--decompose off|heuristic|llm` CLI modu** eklendi (settings-flag'inden BAĞIMSIZ). `--decompose heuristic|llm` → her golden sorgu için `decompose_query` çağrılır, her alt-sorgu ayrı `hybrid_search_chunks` ile retrieve edilir, benchmark-içi `_merge_rrf_sum` ile article-level `_rrf_score` SUM birleştirilir (merge stratejisi = açık-karar #1 → **`_rrf_score` sum kilitlendi**). **Baseline = `--decompose off`, decomposed = `--decompose heuristic`** — settings-flag DEĞİL, CLI flag'i.
> **⚠️ Proxy sınırı (kalıcı):** Bu benchmark **deterministik retrieval-merge proxy** ölçer; production PR-3 hâlâ **3b LLM-driven prompt-hint** (LLM tool-loop'ta alt-sorguları kendi arar+sentezler, deterministik merge YOK). Benchmark pozitif Δ'sı decomposition'ın *retrieval-katkı potansiyelini* gösterir — **prod e2e recall garantisi DEĞİL**. Gerçek prod doğrulama: manuel `/research` transcript (harness yok) veya kademeli-enable sonrası telemetry (PR-5).

### Blocker 2 — Ayrı staging ortamı YOK

Nodrat'ta ayrı staging VPS/compose/DNS **mevcut değil** — tek prod VPS (`164.68.107.205`, `/opt/nodrat`). `docker-compose.dev.yml` = **local development** (staging değil). `staging.nodrat.com` yalnız smoke-test yorumunda örnek (gerçek değil).

> **"Staging validation" gerçekte:** (a) **local** `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` stack'inde (prod'a sıfır risk; **dezavantaj:** local corpus prod kadar zengin değil → recall prod-temsili zayıf) **VEYA** (b) **prod denetimli flag-canary** (OFF→ON byte-identical tasarlandığı için teknik güvenli, ama **production-data-touch + manuel flag = CLAUDE.md §0 HARD-STOP → kullanıcı onayı + hemen DELETE ile geri-alma şart**).

### Blocker 3 — Golden çok-bileşen subset yok + telemetri boşluğu

- **Golden → PR-4B ile ÇÖZÜLDÜ** ([#1449](https://github.com/selmanays/nodrat/pull/1449)): `retrieval_golden_tr.yaml` (55 sorgu) heuristic-tetikleyen ~0 idi → **yeni `retrieval_golden_multi.yaml` yazıldı** (10 çok-bileşen sorgu: 7 heuristic `ve/ayrıca` + 3 LLM-gerektiren; relevant id'ler mevcut golden_tr card UUID'lerinden birleştirildi, **sıfır mutation**). Benchmark `--golden retrieval_golden_multi.yaml --suite chunks --decompose heuristic` ile çağrılır.
- **`snapshot.py` uyumsuz:** yalnız `niche_chunks_benchmark` şemasını parse eder; `retrieval_benchmark.py` JSON'u (`aggregate_metrics`/`per_query[].metrics`) için adaptör gerekir veya manuel snapshot.
- **Telemetri boşluğu → PR-5 ile KISMEN ÇÖZÜLDÜ** ([#1444](https://github.com/selmanays/nodrat/pull/1444), prod-merged): `_decomposition_telemetry` **PII-suz** payload (`method`/`sub_query_count`/`llm_used`/`fallback_reason`/`duration_ms`) artık HER flag-ON çağrıda `logger.info "query_decomposition {...}"` ile loglanır (single dahil → neden bölünmedi görünür) + `is_decomposed` durumunda `thinking_steps` JSONB meta (SQL-ölçülebilir). `fallback_reason` coarse (empty_query/too_short/llm_disabled/llm_no_result). **Hâlâ açık:** decompose LLM çağrısı `track_provider_call`-suz → **decomposition cost provider_call_logs'ta görünmez** (ayrı küçük PR; coarse cost `operation='chat'` ana tool-loop'tan gelir).

> **Özet:** PR-4 = (Blocker-1 için) decompose+merge benchmark modu **VEYA** manuel transcript + (Blocker-3 için) çok-bileşen golden alt-seti + (opsiyonel) geçici telemetry. **Salt flag-flip yeterli değildir.**

---

## 1. Staging / Production Ayrımı

| Ortam | Gerçek durum | PR-4 kullanımı |
|---|---|---|
| **Production** | Tek VPS `164.68.107.205`, `/opt/nodrat`, `nodrat.com` | Flag **HER ZAMAN OFF** (§2). Yalnız onaylı canary istisnası. |
| **Staging** | **YOK** (ayrı VPS/compose/DNS yok) | — |
| **Local dev** | `docker-compose.yml + docker-compose.dev.yml` (hot-reload, `ENVIRONMENT=development`) | **Önerilen validation ortamı** (prod-risk yok) |

## 2. Production Flag OFF — invariant

**Production'da `research.query_decomposition_enabled` HER ZAMAN OFF kalır.** PR-4 ölçümü local/canary'de yapılır; ölçüm sonucu Δ ≥ 0 ve onaylanırsa ayrı bir "kademeli enable" kararıyla prod açılır (bu runbook'un kapsamı DEĞİL — runbook yalnız *validation*).

**Prod OFF doğrulama (her operasyon öncesi + sonrası):**
```bash
# HTTP (admin JWT gerekli)
curl -s https://nodrat.com/api/admin/settings/research.query_decomposition_enabled \
  -H "Authorization: Bearer <ADMIN_JWT>" | jq '{value, is_overridden}'
# Beklenen temiz OFF: {"value": false, "is_overridden": false}

# VEYA SQL (VPS-side, /opt/nodrat)
# SELECT key, value FROM app_settings WHERE key='research.query_decomposition_enabled';
# Temiz OFF = 0 satır (registry default False geçerli).
```

## 3. Flag Açma / Kapama Komutları (yalnız e2e transcript; benchmark için GEREKMEZ)

> **Not:** `retrieval_benchmark` decompose ölçümü **settings-flag KULLANMAZ** (`--decompose` CLI flag'i — §5). Bu bölüm yalnız **manuel e2e `/research` transcript değerlendirmesi** (Blocker-1 ii) içindir — gerçek production akışını flag ON/OFF sürmek istenirse. Production flag HER ZAMAN OFF (§2); local/canary istisnası.
>
> Aşağıdaki `<HOST>` = local için `http://localhost:8000` (dev compose) / canary için `https://nodrat.com` (yalnız onaylı). `<ADMIN_JWT>` = admin login token.

**Açma (PUT override):**
```bash
curl -X PUT <HOST>/api/admin/settings/research.query_decomposition_enabled \
  -H "Authorization: Bearer <ADMIN_JWT>" -H "Content-Type: application/json" \
  -d '{"value": true}'
```

**Kapama / default'a dönüş (DELETE — KESİN OFF için tercih edilen):**
```bash
curl -X DELETE <HOST>/api/admin/settings/research.query_decomposition_enabled \
  -H "Authorization: Bearer <ADMIN_JWT>"
# → app_settings satırı SİLİNİR → kod default False. PUT {"value": false} satırı override
#   olarak bırakır; restore'da DELETE kullan.
```

**Redis invalidation OTOMATİK** (`settings:invalidate` pub/sub, tüm container'lar; L1 TTL 30s) — restart gerekmez (`requires_restart: False`). Her değişiklik `admin_audit_log`'a (`settings.update`/`settings.reset`) yazılır.

## 4. Baseline vs Decomposed Benchmark Akışı

> **Durum:** Blocker-1 **PR-4A ile çözüldü** (decompose+merge mode hazır), Blocker-3 golden **PR-4B ile çözüldü** (`retrieval_golden_multi.yaml`). Araç+veri hazır; kalan = koşum operasyonu (ayrı onay). **Benchmark settings-flag OKUMAZ → baseline/decomposed `--decompose off|heuristic` CLI flag'iyle ayrılır** (settings-flag yalnız production research-stream içindir, prod OFF kalır → §3 flag aç/kapa benchmark için DEĞİL, yalnız e2e transcript için).

```
1. Prod settings-flag OFF assert (§2)                     [zorunlu, başta + sonda]
2. Ortam: local docker-compose.dev VEYA onaylı prod-canary (Blocker-2; prod-corpus şart)
3. BASELINE run:    --decompose off       → benchmark → /tmp/decomp_baseline.json
4. Artifact'ı host'a al (docker compose cp)  [yeniden-koşum ÖNCESİ — benchmark_artifact dersi]
5. DECOMPOSED run:  --decompose heuristic  → benchmark → /tmp/decomp_heuristic.json
6. Artifact'ı host'a al
7. score_history snapshot (baseline + decomposed) + delta tablosu (manuel; snapshot.py uyumsuz)
8. Gate değerlendir (§7)  →  enable adayı / iterate / reject (§9)
9. (Canary ise) no-mutation assert + prod settings-flag OFF assert (§8)
```

## 5. Benchmark Komutları + env + output + score_history

**Çalışma:** Docker-içi (`docker compose exec -T api`), module `tests.eval.retrieval_benchmark`. DB URL container env'inden (`DATABASE_URL`, ekstra env gerekmez); gerçek corpus + 1024-dim embedding provider zorunlu (corpus-dependent, P5 dersi — local corpus zayıfsa recall sahte-düşük).

```bash
# --suite chunks ZORUNLU (decomposition'ın execute_search_news → hybrid_search_chunks path'i;
# 'cards' alakasız hybrid_search_agenda_cards'ı ölçer). --decompose = CLI flag (settings-flag DEĞİL).

# BASELINE (decompose kapalı — mevcut tek-query retrieval):
docker compose exec -T api python -m tests.eval.retrieval_benchmark \
  --golden retrieval_golden_multi.yaml --suite chunks \
  --decompose off --top-k 20 --pool 50 \
  --output /tmp/decomp_baseline.json
docker compose cp api:/tmp/decomp_baseline.json ./decomp_baseline.json   # yeniden-koşum ÖNCESİ

# DECOMPOSED (heuristic — deterministik, provider-suz, tekrarlanabilir):
docker compose exec -T api python -m tests.eval.retrieval_benchmark \
  --golden retrieval_golden_multi.yaml --suite chunks \
  --decompose heuristic --top-k 20 --pool 50 \
  --output /tmp/decomp_heuristic.json
docker compose cp api:/tmp/decomp_heuristic.json ./decomp_heuristic.json

# (Opsiyonel) --decompose llm — örtük çok-niyet üst-sınırı (non-deterministik, chat-provider; cost).
```

**Argüman default'ları:** `--golden retrieval_golden_tr.yaml` · `--suite cards` · **`--decompose off`** (PR-4A) · `--top-k 20` · `--pool 50` · `--with-planner` (decomposition DEĞİL, plan_query enrich) · `--persist` (eval_runs DB-write; **PR-4'te KULLANMA**, salt-ölçüm).

**Output JSON şeması:** `{golden_set, n_queries, top_k, aggregate_metrics{ndcg@10,map@5,mrr@10,recall@5,recall@10,recall@20,p@5,latency_ms_p50,latency_ms_p95}, config{...}, per_query[{query_id,query_text,relevant_ids,retrieved_ids,latency_ms,metrics}]}`.

**score_history:** `apps/api/tests/eval/score_history/`. Dosya-adı konvansiyonu: `baseline_<YYYY-MM-DD>_decomp-off.json` + `step_decomp_<YYYY-MM-DD>_decomp-on.json`. ⚠️ `snapshot.py` yalnız niche-benchmark şemasını parse eder → retrieval-benchmark JSON'u **manuel** kopyalanır veya adaptör eklenir. `--settings` alanına aktif flag durumu (`{"research.query_decomposition_enabled": true/false}`) manuel yazılır.

## 6. Ölçülecek Metrikler

| Metrik | Kaynak | Durum |
|---|---|---|
| **recall@5 / @10 / @20** | benchmark `aggregate_metrics` | ✅ ölçülür (decompose-mode gerekir) |
| **NDCG@10 / MAP@5 / MRR@10** | benchmark | ✅ ölçülür (yardımcı sinyal) |
| **Çok-bileşenli sorgu subset** | `retrieval_golden_multi.yaml` (PR-4B, 10 sorgu) | ✅ **hazır** (7 heuristic + 3 LLM; subset'i ayrı raporla — §7) |
| **latency p50 / p95** | benchmark `latency_ms_p50/p95` (retrieval); end-to-end için `provider_call_logs` | ✅ retrieval; ⚠️ e2e ayrı SQL |
| **provider cost / call count** | `provider_call_logs` SQL (`operation='chat'`) | ⚠️ ana tool-loop'u verir; decompose LLM call'u YAKALANMAZ (untracked). **PR-4 için ZORUNLU DEĞİL** — `--decompose heuristic` LLM-suz (cost yok); provider/cost ayrımı ayrı küçük PR (opsiyonel) |
| **query decomposition rate** | `messages.thinking_steps @> '[{"phase":"query_decomposition"}]'` | ⚠️ kısmi (tetiklenme oranı; method kırılımı YOK) |
| **fallback rate (method dağılımı)** | `logger.info "query_decomposition"` (PR-5) + `thinking_steps` meta | ✅ **PR-5 ile ölçülür** (method/fallback_reason/llm_used/duration_ms; cost hariç) |

**Cost/latency SQL (provider_call_logs — ana tool-loop):**
```sql
SELECT COUNT(*) AS call_count, SUM(COALESCE(cost_usd,0)) AS total_cost_usd,
       PERCENTILE_DISC(0.5)  WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
       PERCENTILE_DISC(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
       COUNT(*) FILTER (WHERE success) AS success_count
FROM provider_call_logs
WHERE operation='chat' AND created_at >= NOW() - INTERVAL '24 hours';
```

**Decompose tetiklenme oranı SQL:**
```sql
SELECT COUNT(*) FILTER (WHERE thinking_steps @> '[{"phase":"query_decomposition"}]') AS decomposed,
       COUNT(*) AS total
FROM messages
WHERE role='assistant' AND created_at >= NOW() - INTERVAL '24 hours';
```

## 7. Gate Kriterleri

```
🟢 ENABLE adayı : recall delta (decomposed − baseline) ≥ 0  (çok-bileşen subset'te de ≥ 0)
                  + latency p95 kabul edilebilir artış  + citation regression YOK
🛑 DUR / reject : recall delta < −%0.5  (yanlış decomposition niyeti kaybediyor)
🛑 DUR          : citation/cite_n regression (manuel transcript: [n] mis-attribution / zincir bozulması)
🛑 DUR          : kabul edilemez latency/cost (query explosion; p95 aşırı / decompose-call maliyeti yüksek)
🛑 DUR          : benchmark eksik/tekrarlanamaz (corpus farkı, embedding provider yok, golden subset yok)
```

> **Çok-bileşen subset ayrı raporlanmalı** — tek-konu sorgular flag ON/OFF özdeş (decompose tetiklenmez) → genel ortalamayı maskeler. Gate **subset recall delta**'sına bakar.

## 8. Restore Planı (operasyon sonu — zorunlu)

```bash
# 1. Flag restore (local/canary'de açıldıysa → DELETE ile default OFF)
curl -X DELETE <HOST>/api/admin/settings/research.query_decomposition_enabled \
  -H "Authorization: Bearer <ADMIN_JWT>"

# 2. Production flag OFF assertion (untouched)
curl -s https://nodrat.com/api/admin/settings/research.query_decomposition_enabled \
  -H "Authorization: Bearer <ADMIN_JWT>" | jq '{value, is_overridden}'
#   → {"value": false, "is_overridden": false}  (prod hiç dokunulmadıysa zaten böyle)
```

**No-mutation assertion (runbook çıkışında doğrula):**
- ✅ Schema/migration mutation: **YOK** (yalnız `app_settings` key-value flag; benchmark `--persist` KULLANILMADI)
- ✅ DB-data mutation: **YOK** (benchmark salt-okuma; `eval_runs` yazılmadı)
- ✅ Embedding / RAG-index / chunk / vector mutation: **YOK** (benchmark retrieve-only, reembed/rechunk/backfill yok)
- ✅ Production data touch: **YOK** (canary istisnası onaylıysa: flag OFF'a DELETE ile restore edildi + audit_log kaydı var)

## 9. Result Template (kopyala-doldur)

```markdown
### PR-4 Staging Recall Validation — Sonuç (<YYYY-MM-DD>)

**Ortam:** local docker-compose.dev | prod-canary (onaylı)
**Golden:** retrieval_golden_multi.yaml (PR-4B, 10 sorgu)
**Decompose-mode:** `--decompose heuristic` (PR-4A, deterministik) | `--decompose llm` | manuel-transcript (prod e2e)
**Komut:** `retrieval_benchmark --golden retrieval_golden_multi.yaml --suite chunks --decompose {off|heuristic}`

| Metrik | Baseline (OFF) | Decomposed (ON) | Delta |
|---|---|---|---|
| recall@5  | | | |
| recall@10 | | | |
| recall@20 | | | |
| recall@10 (çok-bileşen subset) | | | |
| NDCG@10 | | | |
| latency p50 (ms) | | | |
| latency p95 (ms) | | | |
| provider cost (24h, $) | | | |
| decompose tetiklenme oranı | n/a | | |
| fallback rate (method dağılımı, PR-5) | | | log/SQL |

**Citation kontrolü (manuel transcript):** [n] zinciri korundu / mis-attribution: ...
**Karar:** 🟢 enable adayı | 🔁 iterate (golden/merge ayarı) | 🛑 reject (3b yetersiz → 3a deterministik değerlendir)
**Restore:** flag DELETE ✓ · prod OFF assert ✓ · no-mutation assert ✓
```

**Karar yorumu:**
- **enable adayı** → ayrı "kademeli rollout" kararı (canary → genel; runbook kapsamı dışı, kullanıcı onayı).
- **iterate** → golden subset genişlet / merge stratejisi (`_rrf_score` vs `rerank_rows`) ayarla, tekrar koş.
- **reject** → 3b LLM-driven prompt-hint yetersiz; PR-3 scope verification'daki **3a deterministik pre-retrieval** ayrı PR olarak değerlendir.

---

### ✅ Gerçekleşen Validation — 2026-06-08 (prod-corpus READ-only)

**Ortam:** prod VPS (`/opt/nodrat`, 13 container healthy) — local golden prod-UUID nedeniyle anlamsız olduğundan prod-corpus seçildi (kullanıcı açık onayı, READ-only).
**Golden:** `retrieval_golden_multi.yaml` (10 çok-bileşen sorgu) · **mode:** `--decompose heuristic` (deterministik) · **suite:** chunks · **`--persist`:** YOK
**Flag:** `research.query_decomposition_enabled` = **OFF** (başta+sonda doğrulandı, **hiç açılmadı**)

| Metrik | Baseline (off) | Decomposed (heuristic) | Δ relative |
|---|---|---|---|
| recall@5 | 0.1586 | 0.1911 | **+20.5%** |
| **recall@10** | 0.3474 | 0.3287 | **−5.4% (hard-gate FAIL)** |
| recall@20 | 0.4413 | 0.5190 | **+17.6%** |
| NDCG@10 | 0.2681 | 0.2618 | −2.4% |
| latency p50 / p95 | 35.9s / 165.7s | 30.4s / 60.1s | iyileşti |
| failed query | 0 | 0 | — |
| decompose dağılımı | n/a | 7 heuristic-split + 3 single (marker'sız) | — |

**Per-query recall@10 düşen:** `mq_007` (0.80→0.60), `mq_005` (0.111→0.000).
**Per-query recall@20 iyileşen:** `mq_002` (+0.40), `mq_007` (+0.20), `mq_003` (+0.143), `mq_004` (+0.125).
**Citation:** benchmark article-level (citation gerektirmez); cite_n zinciri PR-1 baseline ile korunur (orchestration ayrıca test edilmedi — benchmark proxy).
**Karar:** 🔁 **iterate** — recall@10 hard-gate fail; ama recall@5/@20 belirgin iyileşme + `mq_007` recall@10↓/recall@20↑ paterni → top-10 **ranking/merge** suboptimal (`_merge_rrf_sum` cross-query rerank-sıra bozulması). Sıradaki: **`rerank_rows` merge denemesi** (PR-4D reality-analysis, read-only önce).
**Restore:** flag hiç açılmadı (DELETE gerekmedi) ✓ · prod OFF assert ✓ · no-mutation assert ✓ (`--persist` yok; DB-read + query-embed inference) · `/tmp` artifact temizlendi ✓

### ✅ Gerçekleşen Validation 2 — 2026-06-08 (deterministik merge-strateji, `--rerank off`)

PR-4D-1 araç (`--merge`/`--rerank`) ile **5 koşum**, LLM-rerank noise izole (`--rerank off`). Prod `retrieval.llm_rerank_enabled=false` doğrulandı; flag OFF başta+sonda (COUNT=0); `--persist` YOK; `/tmp` temizlendi; 13 container healthy.

| metric | r0 no-dec | r1 rrf_sum | r2 **rank_rrf** | r3 rrf_max | r4 union |
|---|---|---|---|---|---|
| recall@5 | 0.1586 | **0.1911** | 0.1368 | **0.1911** | 0.1768 |
| recall@10 | 0.3474 | 0.3287 | 0.3398 | 0.3287 | **0.3489** |
| recall@20 | 0.4413 | **0.5190** | 0.4940 | **0.5190** | 0.4940 |
| ndcg@10 | 0.2691 | 0.2628 | 0.2458 | 0.2768 | **0.2809** |
| map@5 | 0.0953 | 0.1090 | 0.0803 | 0.1210 | **0.1367** |
| mrr@10 | 0.3644 | 0.3650 | 0.3260 | 0.4150 | **0.4242** |
| latency p50 / p95 | 35.9 / 155.1s | 33.7 / 84.0s | 23.1 / 52.6s | **9.5** / 68.4s | 96.7 / 144.5s |

**🔑 Determinizm:** r1 (rerank **off**) recall@10 0.3287 ≈ v144 (rerank **on**) 0.329 → birebir; prod `llm_rerank=false` → benchmark hep deterministikti. recall@10 −5.4% **gerçek merge etkisi** (LLM-noise değil). v144 Bulgu-2 (non-determinizm) çürütüldü.

**Gate (rank_rrf):** recall@10 vs r1 **+3.4%** / vs r0 **−2.2%** (toparlandı ama no-dec altında); **AMA recall@5 −28.4% · recall@20 −4.8% · map@5 −26.3%** (top-5 çöküyor). **mq_005:** 0.111→0.000 (hiçbir merge düzeltMEZ → decomposition zararı). **mq_007:** 0.6→0.8 (rank_rrf + union düzeltir).

**Karar:** 🛑 **DUR — activation YOK, flag OFF, canary ÖNERİLMEZ.** rank_rrf recall@5/20'yi korumadığı için gate-2 ihlal; hiçbir strateji recall@5+@10+@20'yi aynı anda no-dec seviyesinde tutmuyor; `mq_005` decomposition-level (merge-dışı). Sıradaki eksen: **decomposition tetikleme kalitesi** + golden genişletme. Yan: `rrf_max` Pareto-üstün (aynı recall + iyi ranking + 3.5× hız) → opsiyonel default-merge upgrade adayı.
**Restore:** flag hiç açılmadı ✓ · prod OFF assert ✓ · no-mutation (`--persist` yok, score_history yazımı yok) ✓ · `/tmp` (host+container) temizlendi ✓

### ✅ Gerçekleşen Validation 3 — 2026-06-09 (PR-B yeni-heuristic, `--rerank off`)

PR-B (heuristic guard: `ile ilgili` çıkar + noise-strip) sonrası **5 koşum READ-only**. Prod flag OFF başta+sonda (count=0), `retrieval.llm_rerank_enabled=false`, `--persist` YOK, `/tmp` temiz, 13 container healthy, `/health` 200. PR-B kod prod image'da doğrulandı (DIV3 `[]`, mq005 temiz).

| metric | no-dec | rrf_sum | rrf_max | rank_rrf | union |
|---|---|---|---|---|---|
| recall@5 | 0.1586 | 0.1759 | 0.1759 | 0.1859 | **0.2350** |
| recall@10 | **0.3474** | 0.2970 | 0.2970 | 0.3122 | 0.3122 |
| recall@20 | 0.4413 | **0.4543** | **0.4543** | 0.4361 | 0.4361 |
| ndcg@10 | 0.2691 | 0.2716 | 0.2856 | 0.2666 | **0.2877** |
| map@5 | 0.0953 | 0.1520 | 0.1640 | 0.1577 | **0.2127** |
| mrr@10 | 0.3644 | 0.5200 | **0.5700** | 0.4317 | 0.4817 |

**PR-B öncesi→sonrası:** no-dec birebir (determinizm ✓). recall@10 TÜM merge'lerde KÖTÜLEŞTİ (−8…−14.5% vs no-dec; PR-4D-2 rrf_sum −5.4% → PR-C −14.5%). recall@20 −12%. AMA precision/ranking↑ (map@5 +39…+96%, mrr +40%, recall@5 rank_rrf/union +33-36%). rank_rrf top-5 çöküşü düzeldi; rrf_max hâlâ Pareto-üstün; union recall@10 avantajı kayboldu.

**Per-query:** `mq_005` HÂLÂ 0.000 (PR-B temizledi ama recall düzelmedi → cleaning-ötesi). `mq_007` korundu (0.800).

**Karar:** 🛑 **reject activation / iterate.** recall@10 hâlâ no-dec altında (kötüleşti) + recall@20 düştü → activation YOK, canary ÖNERİLMEZ, flag OFF. **no-decompose hâlâ recall@10'da en iyi.** Öğrenim: PR-B precision↑/recall↓ takası; soru-kuyruğu bazı sorgularda recall'a katkı; decomposition trigger/cleaning aktivasyon için hazır değil → sonraki yön trigger/golden iteration (flag-enable değil). **⚠️ Proxy uyarısı:** benchmark deterministik retrieval-merge; prod 3b LLM-driven değil → Δ retrieval-potansiyeli, e2e garanti değil.
**Restore:** flag hiç açılmadı ✓ · prod OFF assert ✓ · no-mutation ✓ · `/tmp` temizlendi ✓ · `/health` 200 ✓

> ⚠️ **Golden-kalibrasyon artefaktı (2026-06-09 reality-analysis):** `retrieval_golden_multi.yaml` sonuçları yorumlanırken dikkate alınmalı. Heuristic relevant'lar `golden_tr`'de **soru-kuyruklu query-formlarına kalibre** (örn. mq_005 relevant `"altın fiyatı **bugün** gram"`a bağlı); noise-strip/rewrite kuyruğu atınca golden-eşleşme zayıflar → recall ölçümü **sahte-düşük** (mq_007 kuyruksuz-relevant = doğal kontrol, recall korundu). N=10 + 2-relevant/q (recall adımı 0.50) istatistiksel zayıf. **Aktivasyon kararı için golden-quality (PR-D1: kuyruk-bağımsız relevant + 10→30 + niş-relevant) iyileştirilmeden benchmark sonucu yeterli kabul EDİLMEMELİ.** Detay: [[query-decomposition-mini-plan]] §4 Trigger/Golden Iteration Reality-Analysis.
>
> ✅ **GÜNCELLEME — PR-D1 done (2026-06-09):** `retrieval_golden_multi.yaml` **10→30 query** genişletildi (5 sınıf dengeli · kuyruklu(8)/kuyruksuz(22) izolasyon · niş-UUID ağırlıklı · 7 `low_confidence` işaret · yeni-card-yok). Artık benchmark sonucu **daha güvenilir** ve kuyruklu/kuyruksuz ayrımı noise-strip artefaktını izole ediyor. Yine de: (a) relevant UUID'ler hâlâ prod-snapshot (`low_confidence` popüler-konularda işaretli) → mutlak recall değil **delta + per-sınıf trend** okunmalı; (b) bir sonraki benchmark (PR-D3) bu 30-query set üzerinde + ayrı prod-corpus onayı ile koşulmalı. Eski 10-query sonuçları (PR-4D-2 / PR-C) bu yeni set ile **birebir kıyaslanamaz** (query kümesi değişti).
>
> ✅ **GÜNCELLEME — PR-D2 done (2026-06-09):** noise-strip gevşetildi → alt-sorgu temizliği artık **yalnız soru-eki** (mı/mi) atar; içerik-taşıyan zaman/soru-kuyruğu (bugün/ne zaman/kaçta/ne kadar) **KORUNUR**. Böylece PR-C'de keşfedilen kuyruk-kalibre cezalandırması azalır (mq_005 → `['altın fiyatı bugün gram', '12 yargı paketi ne zaman çıkacak']`). split-sayısı/sınıf değişmedi (golden expectation korundu). **PR-D3 benchmark bu gevşetilmiş heuristic + 30-query golden ile koşulmalı**; recall@10 düşüşünün golden-artefakt vs gerçek payı bu koşumda ayrışabilir. Flag prod'da OFF kalır.

### ✅ Gerçekleşen Validation 4 — 2026-06-09 (PR-D3: 30-query golden + PR-D2 heuristic, `--rerank off`)

30-query golden (PR-D1) + gevşetilmiş heuristic (PR-D2) ile **5 koşum READ-only**. İnvariant: flag OFF (count=0) başta+sonda, `llm_rerank=false`, PR-D2 prod image doğrulandı (mq_005 kuyruk korundu/ile-ilgili []/mq_007 korundu), `--persist` YOK, DB-write YOK, `/tmp` temiz, 13 container, `/health` 200.

| metric | no-dec | rrf_sum | rrf_max | rank_rrf | **union** |
|---|---|---|---|---|---|
| recall@5 | 0.1001 | 0.1167 | 0.1167 | 0.0848 | 0.1011 |
| recall@10 | 0.2334 | 0.2304 | 0.2304 | 0.2413 | **0.2608** |
| recall@20 | 0.2932 | 0.3402 | 0.3402 | 0.3258 | 0.3258 |
| ndcg@10 | 0.1591 | 0.1634 | 0.1681 | 0.1687 | **0.1826** |
| map@5 | 0.0504 | 0.0618 | 0.0658 | 0.0605 | **0.0774** |
| mrr@10 | 0.1940 | 0.2145 | 0.2312 | 0.2309 | **0.2466** |
| latency p50/p95 | 11.1/22.2s | 6.6/12.7s | 0.8/2.5s | 0.7/2.0s | 0.8/1.8s |

**Sonuç:** 🟡 **`union` canary-adayı** — recall@5/10/20 birlikte korundu/iyileşti (vs no-dec +1.0%/+11.7%/+11.1%); recall@10 no-dec ÜSTÜNDE; ndcg/map/mrr en yüksek. `rrf_max` Pareto-üstün; `rank_rrf` top-5 bozuyor. **Grup:** should_split +27%, kuyruksuz/güvenilir pozitif; kuyruklu/low_confidence zayıf; mq_005 hâlâ 0.000; mq_007 korundu; should_not_split/llm no-dec ile aynı (heuristic doğru). **Golden-artefakt hipotezi doğrulandı** (kuyruksuz/güvenilir pozitif, kuyruklu artefakt-kalıntısı). **Karar: canary-adayı / activation YOK / flag OFF.** ⚠️ PR-C ile mutlak kıyas yok (golden farklı, directional: union recall@10 −10.5%→+11.7% yön döndü). Proxy uyarısı korunur (deterministik-merge ≠ prod 3b LLM-driven).
**Restore:** flag hiç açılmadı ✓ · prod OFF assert ✓ · no-mutation (`--persist` yok) ✓ · `/tmp` temizlendi ✓ · `/health` 200 ✓
**Canary planı:** mini-plan §4 "Canary Planı" — önkoşul/metrik/stop/rollback + allowlist-mekanizması açık-soru (global-bool ile canary YOK → ayrı kod-PR gerekebilir). **Uygulama ayrı onay.**

## İlişkiler

- **Ana plan:** [[query-decomposition-mini-plan]] §4 (PR-4 adımları + risk + hard-stop).
- **Mimari:** [[architecture-final-state-2026-05]] §3 (recall CI-able değil → manuel/staging gate, P5 dersi).
- **Disiplin:** [[god-file-facade-first]] (recall sessiz-regresyon riski). Veri-güvenliği: kök `CLAUDE.md §0` HARD-STOP (embedding/RAG-index/data mutation + manuel trigger = DUR + onay).

## Kaynaklar

- [apps/api/tests/eval/retrieval_benchmark.py](../../apps/api/tests/eval/retrieval_benchmark.py) — benchmark CLI + metrikler
- [apps/api/tests/eval/score_history/snapshot.py](../../apps/api/tests/eval/score_history/snapshot.py) — snapshot (niche-şema; retrieval-benchmark için manuel)
- [apps/api/app/modules/settings_admin/routes.py](../../apps/api/app/modules/settings_admin/routes.py) — flag registry + admin endpoint
- [apps/api/app/api/app_research_stream.py](../../apps/api/app/api/app_research_stream.py) — decomposition wiring (flag okuma + hint)
- [apps/api/app/prompts/query_decomposition.py](../../apps/api/app/prompts/query_decomposition.py) — primitive (method telemetry-suz)
- [apps/api/app/shared/observability/cost_tracker.py](../../apps/api/app/shared/observability/cost_tracker.py) — provider_call_logs
- GitHub issue: [#619](https://github.com/selmanays/nodrat/issues/619)
