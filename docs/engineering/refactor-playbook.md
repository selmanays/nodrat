# Refactor Playbook — Modular Monolith Transition

**Sürüm:** v1.0
**Tarih:** 2026-05-20
**Durum:** Kanonik
**Sahibi:** Engineering lead

> Bu doküman modüler monolit dönüşümünde refactor süreçlerinin **standart işletim prosedürüdür**. Her refactor PR'ı buraya uyar; sapma gerekçesi PR description'da.

---

## 0. Yönetici özeti

3 ana refactor pattern:
1. **Tam modül taşıma** (low-risk modules): tek PR'da route + service + repository + tasks + admin alt-paketi taşı; eski path'ler **aynı PR'da silinir**.
2. **Facade-first god-file** (retrieval, SSE, extraction): önce facade + tüm çağrı yerlerini facade'a yönlendir + characterization test paketi; sonra kademeli iç parçalama.
3. **Repository/service split** (kernel modüller): modeller flat kalır; repository + service modüle alınır; iş mantığı route'tan ayrılır.

Tüm refactor PR'ları **behavior-preserving** — davranış değişimi varsa ayrı feature PR.

---

## 1. Refactor PR yaşam döngüsü

### 1.1 Önce

1. **Issue kontrol** — Phase issue'sunun checklist'inde bu kapsam var mı? Yoksa ayrı issue + phase issue'ya link.
2. **Master plan oku** — `wiki/plans/modular-monolith-transition-master-plan.md` "Current Status" + ilgili faz §.
3. **Modül kararı** — Hangi modüle giriyor? Yeni modül gerekir mi (nadir)?
4. **Branch aç** — `refactor/modular-monolith-pX-<mod>` veya worktree branch'i.

### 1.2 Sırasında

5. **Kod taşıma + import güncellemeleri** — Eski path silinir, yeni path'e tüm çağrı yerleri yönlendirilir.
6. **import-linter local çalıştır** — `lint-imports` yeşil olmalı.
7. **Test çalıştır** — Unit + integration + (uygulanabilirse) characterization snapshot.
8. **Docs/wiki sync** — Aynı PR'da log entry + master plan "Current Status" + ilgili decision/topic + docs/engineering.

### 1.3 PR açma

9. **PR template seç** — Refactor template (`.github/PULL_REQUEST_TEMPLATE/refactor.md`); URL'ye `?template=refactor.md` ekle.
10. **Checklist doldur** — Behavior-preserving guarantee + test gates + boundary impact + rollback plan.
11. **Linked issue** — Phase issue'suna `Closes` veya `Part of`.

### 1.4 Review + merge

12. **CI green bekle** — lint + import-linter + tests + alembic check.
13. **Staging verification** (runtime-sensitive PR'lar için) — screenshot/log eklenir.
14. **Squash + merge** — main'e atomic commit.
15. **Main CI doğrula** — `gh run list --branch main` ile merge sonrası 8/8 yeşil (memory `feedback_verify_main_post_merge`).
16. **Master plan güncel** — phase issue'sunda sub-task checkbox'lı.

---

## 2. Tam modül taşıma (low-risk modules — Phase 2)

Örnek: `style_profiles`, `sft`, `entities`, `media`, `clusters`, `legal`, `prompts_admin`, `settings_admin`.

### 2.1 Adım adım

1. Modülün hedef yapısını oluştur (boş `__init__.py` + `README.md`).
2. Eski dosyaları (route + core/* + workers/tasks/*) yeni konumlara **taşı** (eski silinir).
3. İmport edilen yerlerde path güncelle (`from app.core.<X> import` → `from modules.<mod>.<X> import`).
4. `app/main.py` router include path güncelle.
5. `shared/workers/celery_app.py` `include=[...]` listesi güncel.
6. Tests çalıştır → green olmalı.
7. import-linter strict kapsamı genişlet (modül yeni eklendi → strict).
8. Docs/wiki sync.

### 2.2 Beklenen PR boyutu

- 5-15 dosya değişikliği.
- 1-2 yeni dosya (modül `__init__.py` + `service.py`).
- 5-10 silinen dosya (eski path'ler).
- 5-20 dosyada import path güncelleme.

### 2.3 Risk seviyesi: Düşük

Eğer modülün testleri yoksa: önce **smoke test ekle**, sonra taşı.

---

## 3. Facade-first god-file (retrieval, SSE, extraction)

Detay: [`wiki/decisions/god-file-facade-first.md`](../../wiki/decisions/god-file-facade-first.md).

### 3.1 Aşamalar

| Aşama | Adım | PR boyutu |
|---|---|---|
| **A** | Facade oluştur (re-export) + çağrı yerlerini yönlendir | Orta (5-15 dosya) |
| **B** | Characterization test paketi yaz | Büyük (yeni test dosyaları) |
| **C** | Pure functions (constants, normalize, scoring) ayrı dosya | Küçük (her biri ayrı PR) |
| **D** | Stateless logic (NER resolver, validator) ayrı dosya | Küçük |
| **E** | Orchestrator (hybrid search entry, SSE stream body) ayrı dosya | Orta |
| **F** | Facade artık iç paketlere işaret eder; legacy dosya silinir | Küçük |

### 3.2 retrieval.py için spesifik sıra

1. Facade: `modules/rag/__init__.py` — `search_chunks`, `search_agenda_cards`.
2. Characterization: `tests/eval/retrieval_golden_snapshot.py` (50+ query) + `tests/unit/test_ner_idf_match.py` + `tests/unit/test_quote_normalize.py`.
3. Pure: `modules/rag/retrieval/types.py` (dataclasses) → `normalize.py` (quote + Turkish query) → `scoring.py` (freshness + score).
4. Stateless: `ner_resolver.py` → `candidates/{bm25,vector,summary,ner}.py` → `fusion.py` (RRF).
5. Orchestrator: `hybrid.py` (hybrid_search_chunks + hybrid_search_agenda_cards) → `postprocess.py` (L2 affinity + parent expand).
6. Facade artık iç paketlere işaret eder; `core/retrieval.py` silinir.

### 3.3 app_research_stream.py için sıra

1. Facade: `modules/generations/__init__.py` — `post_research_message` alias.
2. Characterization: `tests/eval/sse_replay_golden.py` (10 senaryo) + `tests/unit/test_citation_validation.py` + `tests/integration/test_tool_loop_timeout.py` + DeepSeek cache invariant testi.
3. Pure: `modules/generations/citation/validator.py`.
4. Stateless: `conversation/context.py` → `llm/tracked_chat.py` → `streaming/helpers.py` (simulate_stream + style block).
5. Stateful: `followup/generator.py`.
6. Orchestrator: `streaming/orchestrator.py` (state machine).
7. Routes: `routes.py` + `streaming/routes.py`; legacy `api/app_research*.py` silinir.

### 3.4 extractor.py için sıra

1. Facade: `modules/crawler/extraction/__init__.py` — `extract_article`, `extract_listing_cards`.
2. Characterization: mevcut 88 test korunur + `tests/unit/test_extractor_strategy_sequence.py` (cascade ordering snapshot) + status transition snapshot.
3. Iç parçalama: `structured_data.py` → `images.py` → `readability.py` (trafilatura) → `selectors.py` → `fallback.py` → `listing.py` → `cascade.py` (orchestrator).

### 3.5 Eğer characterization test fail olursa

- PR merge edilmez. Test paketi eksik veya hatalı.
- Davranış kayması tespit edildiyse: feature PR (ayrı issue) + fix.
- Snapshot'ın kendisi yanlışsa: snapshot'ı düzelt + PR description'da gerekçe.

---

## 4. Repository/service split

Örnek: `sources`, `articles` (Phase 3).

### 4.1 Adım adım

1. `modules/<kernel>/repository.py` oluştur — model `from app.models.<entity> import X`.
2. `modules/<kernel>/service.py` — repository'yi kullanan iş mantığı.
3. `modules/<kernel>/schemas.py` — Pydantic DTO.
4. `modules/<kernel>/routes.py` — route'lar service'i çağırır.
5. `modules/<kernel>/admin/routes.py` — admin yüzeyi.
6. Eski `api/admin_<kernel>.py` → silindi, route'lar yeni path'ten gelir.
7. Cross-module çağrılar: `modules/<other>/service.py` → `from modules.<kernel>.service import kernel_service`.

### 4.2 Routes thin, services thick

- Route handler kısa: parametre validate → service çağır → response döndür.
- Service iş mantığı taşır: repository + cross-module service + business rules.
- Repository pure data access: SQLAlchemy session + sorgu.

---

## 5. Frontend modülerleşme

### 5.1 api.ts split (Phase 7a — ilk)

1. `src/lib/api.ts` küçülür: yalnız base (`apiFetch`, token refresh, retry, rate limit).
2. Domain api'leri `src/lib/<domain>-api.ts` → `src/modules/<domain>/api/<domain>-api.ts` taşınır.
3. Type definitions `api.ts`'in 1800 satırlık alt kısmı → modüllere dağıtılır (`<module>/api/types.ts`).
4. Tüm component import'ları güncel.

### 5.2 Domain modüller (Phase 7a)

Düşük-risk: legal, billing, accounts, style_profiles, settings_admin, prompts_admin, sft.

Her domain için:
- `src/modules/<mod>/<Page>.tsx` — eski `src/app/<route>/page.tsx`'ten taşınır.
- `src/modules/<mod>/components/*.tsx` — domain-spesifik bileşenler.
- `src/modules/<mod>/api/<mod>-api.ts` — fetch wrappers.
- `src/app/<route>/page.tsx` — minimal route shell, modülü import eder.

### 5.3 God-page split (Phase 7b)

Backend RAG/generations stabilize sonrası:
- `src/app/admin/rag/page.tsx` (2356) → `RagDashboard`, `RagTuneDashboard`, `HybridSearchTester`, `CitationDebugger`.
- `src/app/admin/queue/page.tsx` (1035) → `QueueOverview`, `TaskDetail`, `DeadLetterQueue`.
- `src/app/admin/sft/page.tsx` (1026) → `TrainingSampleCollector`, `ExportManager`, `JobMonitor`.
- `src/components/research/*` (8 dosya) → `src/modules/generations/research/components/`.

---

## 6. Anti-pattern'lere düşmeme

Yaşayan liste: [`wiki/topics/refactor-anti-patterns-do-not-do.md`](../../wiki/topics/refactor-anti-patterns-do-not-do.md).

Tetik konuları:
- Refactor PR'ı 5+ modülü dokunuyor → **böl**.
- Eski path silinmiyor, "geçici alias bırakıyorum" → **silmen lazım**.
- God-file'a doğrudan dokunulacak, characterization yok → **dur, önce test paketi**.
- `core/` veya `api/` klasörüne yeni dosya eklenmek isteniyor → **yanlış**, modüle yaz.
- Refactor PR'ında prompt/eval/schema/URL/task name değişiyor → **feature PR'a böl**.

---

## 7. Rollback prosedürü

### 7.1 Tek PR rollback

- `git revert <commit>` → yeni revert commit.
- CI rerun → yeşil.
- Worker process'ler eski path'i bulamıyorsa: `docker compose restart <worker>` (Beat schedule yeniden başlar).

### 7.2 Faz seviyesinde rollback

- Eğer bir faz fazla riskli çıkarsa: faz issue'sunu `blocked` etiketle, gerekçeyi master plan §12.2 "Açık sorular"a yaz.
- Master plan "Current Status" güncel.

### 7.3 Spike deploy rollback

memory `feedback_spike_deploy_restore_clean_main` (2026-05-18): production'a deploy edilmiş bir spike/refactor merge edilmediyse, **clean-main restore SON benchmark sonrası HEMEN** yapılır. Analiz/PR/docs öncesi.

---

## 8. CI gates (ne zaman tetiklenir)

| Gate | Tetik | Fail davranışı |
|---|---|---|
| `ruff` | Her push | PR merge edilemez |
| `import-linter` | Her push (Faz 1'den) | PR merge edilemez (strict kapsam içindeyse) |
| `pytest unit` | Her push | PR merge edilemez |
| `pytest integration` | Her push | PR merge edilemez |
| `alembic check` | Her push (Faz 1'den) | PR merge edilemez |
| `alembic current == heads` | Her push (Faz 1'den) | PR merge edilemez |
| Characterization snapshot (delta=0) | God-file PR | PR merge edilemez |
| Eval baseline diff (< 0.5%) | RAG-touching PR | PR merge edilemez |
| `tsc --noEmit` | Frontend PR | PR merge edilemez |
| `next build` | Frontend PR | PR merge edilemez |
| Playwright smoke | Frontend PR (P7+) | Warning |

---

## 9. Cross-references

- [`docs/engineering/modular-monolith-architecture.md`](modular-monolith-architecture.md) — kanonik mimari
- [`docs/engineering/testing-strategy.md`](testing-strategy.md) — test detayları
- [`wiki/plans/modular-monolith-transition-master-plan.md`](../../wiki/plans/modular-monolith-transition-master-plan.md) — master plan
- [`wiki/decisions/god-file-facade-first.md`](../../wiki/decisions/god-file-facade-first.md)
- [`wiki/topics/refactor-pr-checklist.md`](../../wiki/topics/refactor-pr-checklist.md)
- [`wiki/topics/refactor-anti-patterns-do-not-do.md`](../../wiki/topics/refactor-anti-patterns-do-not-do.md)
