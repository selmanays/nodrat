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

> **TL;DR:** PR-3 ile query decomposition wiring prod'da **flag OFF** (byte-identical). PR-4 bu feature'ı açmadan önce **recall regresyonu olmadığını** doğrulayan operasyonel runbook'tur. **Bu runbook salt "flag aç + benchmark koş" DEĞİLDİR** — read-only audit 3 blocker ortaya çıkardı (aşağıda); bunlar çözülmeden ölçüm **yanıltıcıdır**. Production flag **HER ZAMAN OFF** kalır; doğrulama local stack veya denetimli prod-canary'de yapılır. Bu sayfa docs-only; gerçek operasyon ayrı kullanıcı onayı gerektirir.

---

## ⚠️ ÖN-KOŞUL UYARISI — runbook'un kalbi (önce oku)

Read-only audit (2026-06-05) şu üç gerçeği ortaya çıkardı. **Bunlar çözülmeden PR-4 ölçümü geçersizdir:**

### Blocker 1 — Mevcut benchmark decomposition'ı ÖLÇEMEZ (en kritik)

`tests/eval/retrieval_benchmark.py` **retrieval-seviyededir**: `hybrid_search_chunks`'ı tek `effective_query` ile **doğrudan** çağırır. Decomposition ise **orchestration-seviyededir**: `_research_stream_body` LLM tool-loop'unda alt-sorgu hint'i (`app_research_stream.py§706`). Benchmark `_research_stream_body`'den **hiç geçmez** → `research.query_decomposition_enabled` flag'ini **okumaz**.

> **Sonuç:** staging'de flag'i açıp mevcut benchmark'ı koşmak **boş kıyastır** — flag ON/OFF iki koşum **byte-identical** çıkar. Decomposition'ı ölçmek için iki gerçek yol:
> - **(i) Decompose+merge benchmark modu (ayrı küçük kod-PR):** `retrieval_benchmark.py`'a çok-bileşenli golden sorgu için `decompose_query` çağırıp her alt-sorguyu `hybrid_search_chunks` ile ayrı koşturan + `_rrf_score`/`rerank_rows` ile birleştiren mod ekle. **Bu, mini-plan açık-karar #1'i (merge stratejisi) kilitler** — yani PR-4 fiilen merge'i koşmalı, salt flag-flip değil.
> - **(ii) End-to-end research-stream transcript değerlendirme (manuel):** gerçek `/research` SSE akışını flag ON vs OFF sürerek dönen `sources_used` + citation'ı çok-bileşenli golden ile manuel kıyasla. Harness repo'da YOK; manuel.

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

## 3. Flag Açma / Kapama Komutları (yalnız local/canary)

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

> **ÖN-KOŞUL:** Blocker-1 çözülmeden bu akış geçersiz. Aşağıdaki akış **decompose+merge benchmark modu (i)** varsayar; yoksa manuel transcript (ii)'ye düş.

```
1. Prod OFF assert (§2)                                   [zorunlu, başta]
2. Local/canary stack ayağa  +  çok-bileşen golden alt-seti hazır (Blocker-3)
3. BASELINE run: flag OFF (veya decompose-mode kapalı) → benchmark → /tmp/decomp_baseline.json
4. Artifact'ı host'a al (docker compose cp)  [restart ÖNCESİ — benchmark_artifact dersi]
5. DECOMPOSED run: flag ON (veya decompose-mode açık) → benchmark → /tmp/decomp_on.json
6. Artifact'ı host'a al
7. score_history snapshot (baseline + decomposed) + delta tablosu
8. Gate değerlendir (§7)  →  enable / iterate / reject (§9)
9. Restore (§8): flag DELETE + prod-OFF assert + no-mutation assert
```

## 5. Benchmark Komutları + env + output + score_history

**Çalışma:** Docker-içi (`docker compose exec -T api`), module `tests.eval.retrieval_benchmark`. DB URL container env'inden (`DATABASE_URL`, ekstra env gerekmez); gerçek corpus + 1024-dim embedding provider zorunlu (corpus-dependent, P5 dersi — local corpus zayıfsa recall sahte-düşük).

```bash
# --suite chunks ZORUNLU (decomposition'ın execute_search_news → hybrid_search_chunks path'i;
# 'cards' alakasız hybrid_search_agenda_cards'ı ölçer)
docker compose exec -T api python -m tests.eval.retrieval_benchmark \
  --golden retrieval_golden_multi.yaml \   # PR-4 yeni çok-bileşen golden (Blocker-3)
  --suite chunks --top-k 20 --pool 50 \
  --output /tmp/decomp_baseline.json
# Artifact'ı host'a al (container restart/flag-flip ÖNCESİ):
docker compose cp api:/tmp/decomp_baseline.json ./decomp_baseline.json
```

**Argüman default'ları:** `--golden retrieval_golden_tr.yaml` · `--suite cards` · `--top-k 20` · `--pool 50` · `--with-planner` (decomposition DEĞİL, yalnız plan_query enrich) · `--persist` (eval_runs DB-write; **PR-4'te kullanma**, salt-ölçüm).

**Output JSON şeması:** `{golden_set, n_queries, top_k, aggregate_metrics{ndcg@10,map@5,mrr@10,recall@5,recall@10,recall@20,p@5,latency_ms_p50,latency_ms_p95}, config{...}, per_query[{query_id,query_text,relevant_ids,retrieved_ids,latency_ms,metrics}]}`.

**score_history:** `apps/api/tests/eval/score_history/`. Dosya-adı konvansiyonu: `baseline_<YYYY-MM-DD>_decomp-off.json` + `step_decomp_<YYYY-MM-DD>_decomp-on.json`. ⚠️ `snapshot.py` yalnız niche-benchmark şemasını parse eder → retrieval-benchmark JSON'u **manuel** kopyalanır veya adaptör eklenir. `--settings` alanına aktif flag durumu (`{"research.query_decomposition_enabled": true/false}`) manuel yazılır.

## 6. Ölçülecek Metrikler

| Metrik | Kaynak | Durum |
|---|---|---|
| **recall@5 / @10 / @20** | benchmark `aggregate_metrics` | ✅ ölçülür (decompose-mode gerekir) |
| **NDCG@10 / MAP@5 / MRR@10** | benchmark | ✅ ölçülür (yardımcı sinyal) |
| **Çok-bileşenli sorgu subset** | yeni golden alt-seti (Blocker-3) | ⚠️ yeni golden yazılmalı; mevcut golden'da ~yok |
| **latency p50 / p95** | benchmark `latency_ms_p50/p95` (retrieval); end-to-end için `provider_call_logs` | ✅ retrieval; ⚠️ e2e ayrı SQL |
| **provider cost / call count** | `provider_call_logs` SQL (`operation='chat'`) | ⚠️ **ana tool-loop'u verir; decompose LLM call'u YAKALANMAZ** (untracked) |
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
**Golden:** retrieval_golden_multi.yaml (N=<çok-bileşen sorgu sayısı>)
**Decompose-mode:** benchmark-mode (i) | manuel-transcript (ii)

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
