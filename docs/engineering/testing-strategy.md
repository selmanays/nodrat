# Testing Strategy

**Sürüm:** v1.0
**Tarih:** 2026-05-20
**Durum:** Kanonik
**Sahibi:** Engineering lead

> Bu doküman Nodrat'ın test stratejisinin kanonik tanımıdır: test katmanları, characterization test disiplini, CI gate eşikleri, golden snapshot pattern'i.

---

## 0. Yönetici özeti

Test stratejisi 6 katmanda:
1. **Unit** — pure functions, izole.
2. **Integration** — DB + service kombinasyonları.
3. **Golden snapshot** (retrieval) — recall@5/10 + result sequence sabitlenir.
4. **Citation/faithfulness eval** — RC3-B v2 marker-detect + Playwright prod-replay.
5. **SSE streaming replay** — conversation senaryolarının event sequence golden'ı.
6. **HTML extraction fixture** — 88 mevcut test + strategy sequence snapshot.

Modüler monolit refactor için ek 2 gate:
7. **Alembic migration check** — `alembic check` + `alembic current == heads`.
8. **Import boundary CI** — `import-linter` fail-on-violation.

---

## 1. Test katmanları detay

### 1.1 Unit tests

- **Konum:** `apps/api/tests/unit/`
- **Tool:** pytest
- **Kapsam:** Pure functions, izole iş mantığı, validator regex'ler.
- **Mevcut:** 60+ test dosyası, ~1500 test (`test_extractor.py` 88 + `test_research_tools.py` 50+ + diğerleri).
- **Hedef coverage:** Modül service.py'ları için ≥80%.
- **CI gate:** Her push'ta yeşil olmalı; fail → PR merge edilemez.

### 1.2 Integration tests

- **Konum:** `apps/api/tests/integration/`
- **Tool:** pytest + testcontainers (Postgres) veya in-memory SQLite (uygunsa).
- **Kapsam:** Repository + service combinations, FK lifecycle, DB transaction behavior.
- **Mevcut:** 2-3 dosya — **boşluk yüksek.**
- **Hedef:** Her domain modülü için en az 1 integration test (Faz 2-3 sırasında eklenir).
- **CI gate:** Her push'ta yeşil.

### 1.3 Golden snapshot — retrieval

- **Konum:** `apps/api/tests/eval/`
- **Tool:** pytest + custom benchmark harness (`framework.py` 587 satır mevcut).
- **Kapsam:** 50+ query (niche_007, niche_009, RC3-B v2 verifier sorguları, agenda chunks-first) → top-K result snapshot (article_id sequence + RRF scores).
- **Pattern:**
  ```
  tests/eval/retrieval_golden_snapshot.py:
      QUERIES = [...]                       # benchmark corpus
      EXPECTED = {...}                      # baseline snapshot (committed)
      
      @pytest.mark.parametrize("query", QUERIES)
      async def test_retrieval_snapshot(query):
          result = await hybrid_search_chunks(query)
          assert result.article_ids == EXPECTED[query]["article_ids"]
          assert abs(result.recall_at_5 - EXPECTED[query]["recall_at_5"]) < 0.005
  ```
- **CI gate (RAG-touching PR):** Delta = 0 (article_id sequence) + recall@5/10 delta < 0.5%.
- **Faz hedefi:** Phase 5 başlamadan önce snapshot suite **stable yeşil**.

### 1.4 Citation/faithfulness eval

- **Konum:** `apps/api/tests/eval/citation/` + Playwright suite (frontend).
- **Tool:** pytest + Playwright + RC3-B regression set.
- **Kapsam:**
  - Citation parser edge cases ([1], [1,2], [1-3], [1–3])
  - `_is_substantive` heuristic
  - `_has_reconstruction_marker` (#1067 RC3-B v2 regex)
  - RC3-B v1 prod 4 yanlış-pozitif sorgu — `reframed=false` doğrulama
- **CI gate (generations-touching PR):** RC3-B regression set %100 pass.
- **Faz hedefi:** Phase 6 başlamadan önce eval suite stable.

### 1.5 SSE streaming replay

- **Konum:** `apps/api/tests/integration/sse/`
- **Tool:** pytest + httpx async stream + golden event sequence files.
- **Kapsam:** 10 conversation senaryosu:
  1. Yeni soru → response
  2. Follow-up condense
  3. Multi-turn with citation
  4. RC3-B reframe trigger (reconstruction marker)
  5. Tool-loop normal flow
  6. Tool-loop timeout (30s)
  7. Tool-loop max rounds (3)
  8. Quota exceeded (billing integration)
  9. Cancellation (client disconnect)
  10. Reconnect / partial flush
- **Pattern:**
  ```
  tests/integration/sse/test_sse_replay_golden.py:
      @pytest.mark.parametrize("scenario", SCENARIOS)
      async def test_sse_event_sequence(scenario):
          events = await consume_sse(scenario.payload)
          assert event_sequence(events) == EXPECTED[scenario]
  ```
- **Mevcut:** 1 dosya (sınırlı kapsam) — **boşluk yüksek.**
- **CI gate (SSE-touching PR):** Event sequence diff = 0.
- **Faz hedefi:** Phase 6 başlamadan önce 10-senaryo suite yeşil.

### 1.6 HTML extraction fixture

- **Konum:** `apps/api/tests/unit/test_extractor.py` (mevcut, 1496 satır, 88 test).
- **Tool:** pytest + HTML fixture dump'ları (real TR sites: Habertürk, BBC, Bianet, Hürriyet, Evrensel).
- **Mevcut kapsam:** ✅ Zengin (88 test).
- **Eklenecek:** `tests/unit/test_extractor_strategy_sequence.py` — hangi site hangi tier'da yakalanır snapshot.
- **CI gate (extractor-touching PR):** Strategy sequence diff = 0.

### 1.7 Alembic migration check (Faz 1'den)

- **CI step:** `.github/workflows/ci.yml` job.
- **Komutlar:**
  - `alembic check` — no autogenerate diff (schema = code state).
  - `alembic current == alembic heads` — drift yok.
- **CI gate:** Her push'ta yeşil; fail → PR merge edilemez.
- **Spec:** [`docs/engineering/data-model.md`](data-model.md) §1 Migration Stratejisi.

### 1.8 Import boundary CI (Faz 1'den)

- **Tool:** `import-linter`
- **Config:** `apps/api/pyproject.toml` `[tool.importlinter]` (varsayılan tercih) veya `.importlinter.cfg`.
- **CI step:** `lint-imports` job.
- **CI gate (Faz 1'den):**
  - Strict kapsam: `modules/*`, `shared/*` — Faz 1 itibarıyla
  - Report-only: `app.core.*`, `app.api.*` — legacy patikalar
  - Kademeli strict genişleme: her modül taşındıkça strict kapsama alınır
  - Faz 8: genel strict
- **Spec:** [`wiki/decisions/import-direction-rules.md`](../../wiki/decisions/import-direction-rules.md).

---

## 2. Characterization test disiplini (god-file)

### 2.1 Ne zaman gerek

Aşağıdaki dosyalardan herhangi birine dokunan refactor PR'ı:
- `core/retrieval.py` veya bu dosyadan extract edilen modüller
- `api/app_research_stream.py` veya generations stream pipeline
- `core/extractor.py` veya crawler extraction cascade

### 2.2 Disiplin

1. **Önce snapshot** — Mevcut davranışı kayda al (golden output committed).
2. **Sonra refactor** — Davranış değişmemeli (snapshot delta = 0).
3. **Yeni davranış istiyorsan** — Snapshot'ı **bilinçli güncelle** + PR description'da gerekçe + feature PR'a böl.
4. **Hiçbir zaman snapshot'ı "fail olunca güncelle" şeklinde kullanma** — bu disiplin atlatması.

### 2.3 Snapshot dosya konumu

| Dosya | Konum |
|---|---|
| Retrieval golden | `apps/api/tests/eval/retrieval_golden.json` |
| SSE event sequences | `apps/api/tests/integration/sse/golden/<scenario>.json` |
| Extraction strategy | `apps/api/tests/unit/extraction_strategy_baseline.json` |
| Citation parser cases | `apps/api/tests/unit/citation_baseline.json` |

### 2.4 Snapshot update protocol

Snapshot'ı bilinçli güncelleme gerekirse:
1. PR'ın **scope type: Feature** (refactor değil).
2. Ayrı issue + ayrı PR.
3. Snapshot diff PR description'da görünür.
4. Eğer behavior değişimi olumsuz etki yapıyorsa: rollback + tartışma.

---

## 3. CI gate matrisi

### 3.1 Her PR'da çalışan

| Gate | Faz 0 | Faz 1+ |
|---|---|---|
| ruff | ✅ | ✅ |
| pytest unit | ✅ | ✅ |
| pytest integration | ✅ | ✅ |
| alembic check | — | ✅ |
| alembic current == heads | — | ✅ |
| import-linter | — | ✅ (strict kapsam genişler) |
| tsc --noEmit | ✅ (frontend touch) | ✅ |
| next build | ✅ (frontend touch) | ✅ |

### 3.2 Şartlı gate'ler (touch'a göre)

| Gate | Tetik |
|---|---|
| Retrieval golden snapshot | RAG modülü touch |
| Eval baseline diff (recall@5/10) | RAG modülü touch |
| SSE replay golden | Generations / SSE touch |
| Citation eval | Generations touch |
| Extraction strategy sequence | Crawler / extractor touch |
| RC3-B regression set | Generations / faithfulness touch |
| Playwright smoke | Frontend touch (Faz 7+) |

### 3.3 Manual gates

- **Staging verification** — runtime-sensitive PR (Redis pub/sub, Celery Beat, settings_store/prompts_store/cost_tracker). PR description'da screenshot/log.
- **Production deploy doğrulama** — merge sonrası `gh run list --branch main` 8/8 yeşil (memory `feedback_verify_main_post_merge`).
- **Spike deploy restore** — yarım kalan spike main'e restore (memory `feedback_spike_deploy_restore_clean_main`).

---

## 4. Test ekleme protokolü

### 4.1 Yeni feature için

1. Unit test → `tests/unit/test_<mod>_<feature>.py`.
2. Integration test gerekirse → `tests/integration/test_<mod>_<feature>.py`.
3. RAG / SSE / extraction'a dokunuyorsa → ilgili characterization snapshot extend.
4. Frontend touch ediyorsa → Playwright smoke.

### 4.2 Refactor için

- Davranış değişimi varsa: REFACTOR DEĞİL, feature.
- Yeni test paketi gereği varsa (god-file öncesi): characterization snapshot oluştur.
- Yoksa: mevcut test paketi yeşil olmalı (regresyon yok).

### 4.3 Bug fix için

- "Prove-it" pattern: Önce failing test yaz; sonra fix; test geçer.
- Regresyon önleme — fix sonsuza dek korunur.

---

## 5. Test coverage hedefleri

| Modül kategorisi | Unit | Integration | Characterization |
|---|---|---|---|
| Kernel (sources, articles) | 90% | 100% (CRUD pathway) | — |
| Orta (rag, crawler, generations) | 80% | 80% | ✅ god-file için |
| Paralel (accounts, billing, legal, ...) | 80% | 70% | — |
| Frontend modüller | 60% (vitest) + Playwright smoke | — | — |

Coverage **runtime hedef** — refactor sırasında ulaşılması zorunlu değil; **yeni feature** ile birlikte yükselir.

---

## 6. Test araç stack'i

| Tool | Amaç |
|---|---|
| pytest | Python test framework |
| pytest-asyncio | Async test support |
| httpx | Async HTTP client (SSE consume) |
| testcontainers | Postgres integration test |
| import-linter | Boundary CI |
| alembic | Migration check |
| ruff | Lint + format (tek formatter — L1 dersi) |
| vitest | Frontend unit |
| Playwright | Frontend E2E + smoke |
| msw (önerilen, Faz 7) | Frontend API mock |

---

## 7. Cross-references

- [`docs/engineering/modular-monolith-architecture.md`](modular-monolith-architecture.md)
- [`docs/engineering/refactor-playbook.md`](refactor-playbook.md)
- [`docs/engineering/prompt-contracts.md`](prompt-contracts.md) §6 LLM Eval Framework
- [`wiki/decisions/god-file-facade-first.md`](../../wiki/decisions/god-file-facade-first.md)
- [`wiki/decisions/import-direction-rules.md`](../../wiki/decisions/import-direction-rules.md)
- [`wiki/topics/refactor-pr-checklist.md`](../../wiki/topics/refactor-pr-checklist.md)
- [`wiki/topics/refactor-anti-patterns-do-not-do.md`](../../wiki/topics/refactor-anti-patterns-do-not-do.md)
