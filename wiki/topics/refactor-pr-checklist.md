---
type: topic
title: Refactor PR Checklist (Behavior-Preserving Discipline)
slug: refactor-pr-checklist
category: playbook
status: live
created: 2026-05-20
updated: 2026-05-20
sources:
  - .github/PULL_REQUEST_TEMPLATE/refactor.md
  - wiki/decisions/no-internal-backcompat-aliases.md
  - wiki/decisions/god-file-facade-first.md
tags:
  - refactor
  - checklist
  - modular-monolith
  - playbook
aliases:
  - refactor-pr
  - behavior-preserving-checklist
---

# Refactor PR Checklist (Behavior-Preserving Discipline)

> **TL;DR:** Her modüler monolit refactor PR'ı bu checklist'i geçer. **Refactor = davranış değişmez.** Davranış değişikliği gerekiyorsa ayrı issue + ayrı PR. Bu sayfa PR template'inin (`.github/PULL_REQUEST_TEMPLATE/refactor.md`) gerekçesini ve detayını verir.

## Bağlam

Refactor PR'ları "küçük + geri alınabilir + davranış-koruyan" olmadığında: sessiz regresyon riski (god-file dersleri), alias-debt birikimi (backward-compat tuzağı), docs/wiki sync atlanması (paralel worktree karmaşası). Bu checklist üç tuzağı önler.

## Ana içerik — Checklist

### 1. Linked issue

- [ ] PR description'da `Closes #<issue>` veya `Part of #<issue>` var.
- [ ] Issue master plan'a (`wiki/plans/modular-monolith-transition-master-plan.md`) link veriyor.
- [ ] Issue ilgili phase (P0-P8) altında.

### 2. Scope = Refactor

- [ ] PR template'inde "Refactor (behavior-preserving)" işaretli.
- [ ] Feature, fix veya davranış değişikliği **YOK**. Varsa ayrı PR.
- [ ] Tek modülü dokunuyor (5+ modül = big-bang anti-pattern #1).

### 3. Behavior-preserving guarantee

- [ ] Application davranışı değişmedi.
- [ ] URL sözleşmeleri (prefix + endpoint isimleri) değişmedi.
- [ ] Celery task name'leri değişmedi (string-bound; #17 anti-pattern).
- [ ] DB schema değişmedi (Alembic migration refactor PR'ında **yok**).
- [ ] LLM prompt content değişmedi (RC3-B v2 marker-detect dahil).
- [ ] Runtime config key'leri + Redis pub/sub channel adları değişmedi.

### 4. Test gates

**Local pre-flight (before commit / push — MANDATORY after path moves):**

```bash
cd apps/api
ruff check --fix .
ruff format .
```

Phase 2 PR 5 dersi: `git mv` ile dosya taşıma sonrası import sırası bozulabilir; davranış değişmese bile `ruff I001` (import-block sort) CI'da kırmızı verir. CI **import-sort-only** failure'ı yakalamak için ilk yer olmamalı; lokal pre-flight zorunlu.

`ruff` lokal'de yoksa: `pipx install ruff` (sistem Python'a `pip install` PEP 668 nedeniyle önerilmez; pipx izole kurulum sağlar).

**CI test gates:**

- [ ] Lokal pre-flight çalıştırıldı (yukarıdaki blok).
- [ ] Unit test green (`pytest tests/unit`).
- [ ] Integration test green (`pytest tests/integration`).
- [ ] Characterization snapshot (retrieval / SSE / extraction touch ediyorsa) — **delta = 0**.
- [ ] Eval baseline diff (RAG touch ediyorsa) — recall@5/10 delta < 0.5%.
- [ ] Frontend tsc + Playwright smoke (frontend touch ediyorsa).

### 5. Boundary enforcement (import-linter)

- [ ] Yeni `modules/<mod>` veya `shared/<sub>` strict kapsamda (Faz 1'den itibaren).
- [ ] Legacy `app.core.*` veya `app.api.*` taşındıysa strict kapsama promote edildi.
- [ ] Yasaklı ok yok (CI yeşil).
- [ ] Cross-module import'lar yalnız `service.py` / `repository.py` / `schemas.py` üzerinden — `internal/*` import edilmiyor.

### 6. No internal alias-debt

- [ ] Eski path silindi (`app/core/<old>.py` veya `app/api/<old>.py` dosyası yok).
- [ ] **Broader grep pattern** (Phase 2 PR 2 dersi — dot-form ve modül-level her ikisi):
  ```bash
  grep -rE 'from app\.(api|core|workers\.tasks)(\.[a-z_]+)? import' apps/api --include="*.py"
  grep -rE 'import app\.(api|core|workers\.tasks)' apps/api --include="*.py"
  ```
  Test dahil tüm `apps/api/` üstünde **kod/test eski path kalmamalı**.
- [ ] Sonuçları körlemesine değiştirme:
  - Gerçek eski path referanslarını düzelt.
  - Tarihsel `wiki/log.md` veya migration history docstring referansları (README, alembic versions) açıklama amaçlı kalabilir.
  - Kod / test import path'lerinde eski modül yolu kalmamalı.
- [ ] Re-export köprü yok (one-PR atomic).
- [ ] **§6.6 Commit-diff verification (Phase 2 PR 5 dersi — silent regression).** PR description'da listelenen her legacy path değişikliği git diff ile **birebir doğrulanmalı**:
  ```bash
  # PR açmadan ÖNCE:
  git diff --name-status origin/main...HEAD
  git diff --stat origin/main...HEAD | grep -E "(modules|shared|api/|core/|workers)"
  # Her "Updated caller" iddiası için:
  git log -p origin/main..HEAD -- <claimed-caller-file> | grep -E "from app\.(api|core|workers)"
  # Eski path negative-presence + yeni path positive-presence:
  git grep "<old-path>" -- apps/api  # → 0 sonuç beklenir
  git grep "<new-path>" -- apps/api  # → ≥1 sonuç beklenir
  ```
  PR description claim ≠ commit diff = silent regression riski. PR #1105'te `articles.py:573` lazy import claim olmadan da kaçırılmış olabilirdi; checklist disiplini her caller'ı diff'te aramayı zorunlu kılar. **Co-migrated task dosyaları için ayrı grep şart** (örn. `media` taşınırken `image_vlm` ayrı dosya ise iki ayrı pattern ile audit).
- [ ] **§6.7 Per-module legacy import denylist.** Her taşınan modül için PR description'da eski import path'leri **denylist olarak listelenmeli**; her path için negative-presence kanıtı sunulmalı:
  ```
  Module: media (PR #1105)
  Denylist:
    - app.core.media
    - app.core.media_suggest
    - app.core.vlm_postprocess
    - app.workers.tasks.media
    - app.workers.tasks.image_vlm
    - app.api.admin_media
  ```
  Kod / test dosyalarında **0 referans** zorunlu (`git grep '<denied-path>' -- apps/api '*.py'`). Docs/wiki tarihsel referansları (changelog, migration history) açıklama amaçlı kalabilir — yorum: `# legacy reference, see wiki/log.md`.
- [ ] **§6.8 Worker lazy-import grep (Phase 2 PR 5 dersi — runtime path).** Worker/task taşıması olan PR'larda 3 farklı import form'unu ayrı ayrı ara — biri yetmez:
  ```bash
  # Form 1 — submodule deep import (en yaygın, lazy ile aynı pattern):
  grep -rE 'from app\.workers\.tasks\.<old_name> import' apps/api --include="*.py"
  # Form 2 — modül-level import:
  grep -rE 'from app\.workers\.tasks import .*<old_name>' apps/api --include="*.py"
  # Form 3 — absolute import:
  grep -rE 'import app\.workers\.tasks\.<old_name>' apps/api --include="*.py"
  ```
  PR #1105'te Form 1 yalnız `admin/routes.py`'da bulundu, **`articles.py`'daki Form 1 başka dizinde olduğu için kaçırıldı**. Üç form da ayrı ayrı 0 sonuç vermeli — `apps/api` altında full tree (api/, core/, modules/, shared/, workers/, tests/).

### 7. Docs / wiki sync (aynı PR'da)

- [ ] `wiki/log.md` entry eklendi (yapılan iş özeti).
- [ ] `wiki/plans/modular-monolith-transition-master-plan.md` "Current Status" güncel.
- [ ] Yeni decision sayfası varsa `wiki/decisions/<slug>.md` oluşturuldu + index güncel.
- [ ] Mimari/yapı değişimi varsa `docs/engineering/*` ilgili bölüm güncel.
- [ ] Bidirectional backlink kontrol (yeni sayfa A→B varsa B→A da).

### 8. God-file disiplini (touch ediyorsa)

- [ ] Facade önce kuruldu mu?
- [ ] Characterization snapshot test paketi yeşil mi?
- [ ] İç parçalama "pure functions" → "stateless logic" → "orchestrator" sırasıyla mı?
- [ ] Snapshot diff = 0?

### 9. Runtime-sensitive değişiklik (touch ediyorsa)

- [ ] settings_store / prompts_store / cost_tracker / Celery Beat Schedule etkileniyor mu?
- [ ] Staging cluster'da Redis pub/sub davranışı doğrulandı mı?
- [ ] Worker process'in eski-yeni path'i import etmediği log'la doğrulandı mı?
- [ ] **§9.4 Post-deploy worker log scan (Phase 2 PR 5 dersi — silent regression).** Module path taşıması yapan PR'lar için VPS deploy sonrası **≥5 dakikalık pencerede tüm runtime container'larda** hata pattern taraması zorunlu. Tek worker yetmez — domain'e dokunulan tüm worker'lar + api + scheduler kontrol edilir:
  ```bash
  CONTAINERS="nodrat-api nodrat-scheduler nodrat-worker-scraper nodrat-worker-embedding nodrat-worker-rag nodrat-worker-cleaner nodrat-worker-image-vlm"
  # Domain-spesifik worker varsa (örn. media taşıması) eklenir.
  PATTERNS="ModuleNotFoundError|No module named|ImportError|Traceback|<old_module_path>"
  for c in $CONTAINERS; do
    N=$(ssh root@vps "docker logs --since 5m $c 2>&1" | grep -cE "$PATTERNS")
    echo "$c: $N error matches"
  done
  ```
  Tüm container'larda **0 match** zorunlu. **Sadece startup logu yetmez** — Beat scheduler'ın **bir periyodik task fire ettiği** ve **bir worker'ın bunu success ile işlediği** doğrulanmalı (`Task tasks.X[uuid] succeeded`). CI lazy import / runtime dispatch path'lerini exercise edemez (örn. articles.fetch içinde `dispatch_image_vlm` lazy çağrısı: CI'da o branch tetiklenmez). PR 7b'de `articles.backfill_discovered[2c88c025] succeeded in 0.115s` görmek = articles.py import surface'i fonksiyonel kanıtı.
- [ ] **§9.5 Runtime config fallback reporting (PR 7a smoke dersi — yarı-hallüsinasyon).** `settings_store.get_*(db, key, fallback)`, `prompts_store.get(...)`, provider config, quota config gibi alanlarda **fallback ile okunan değer asla DB gerçek değeri gibi raporlanmamalı**. Her raporda dört alan zorunlu:
  ```
  Key: chunker.target_tokens
  DB row exists: no
  Registry default: 500
  Fallback provided: 256
  Returned value: 256
  Conclusion: returned fallback (not persisted DB value, not registry default)
  ```
  PR 7a smoke'unda `get_int(db, "chunker.target_tokens", 256)` → 256 dönen değer "DB'de 256" gibi raporlandı; gerçekte DB'de row yoktu, fallback dönüyordu. UI 500 gösterince yarı-hallüsinasyon olarak ortaya çıktı. **Smoke raporlarında her runtime config okuma için tablo zorunlu.**

### 10. Rollback plan

- [ ] PR revert edilirse ne olur dokümante edildi.
- [ ] Worker restart / cache invalidate / DB rollback gibi özel adım gerek mi?
- [ ] Spike değilse: production deploy edildiyse clean-main restore mecburiyetinde mi?

### 11. PR Evidence Standards (Phase 2 PR 7 cycle dersi — claim verification)

PR description "Summary" kanıt değildir. "CI green" tek başına kanıt değildir. **Her kritik iddianın komut çıktısı veya runtime kanıtı olmalı**, **Claim → Evidence → Result** formatında.

#### 11.1 Zorunlu format

Her refactor PR description'ında bir "Evidence" tablosu / listesi:

```
### Evidence

| Claim | Evidence (command / runtime) | Result |
|---|---|---|
| Legacy `app.workers.tasks.image_vlm` import path removed from app code | `git grep "app.workers.tasks.image_vlm" -- 'apps/api/**/*.py' \| grep -v "wiki\|alembic"` | 0 sonuç |
| New `app.modules.media.tasks.image_vlm` reachable from all callers | `git grep "app.modules.media.tasks.image_vlm" apps/api` | 3 sonuç (admin/routes, articles, tests) |
| `tasks.image_vlm.process` Celery task registered at worker | post-deploy `docker logs nodrat-worker-image-vlm \| grep "tasks.image_vlm"` | 3 task names görünür |
| Runtime config `X.Y` reaches worker process | beat fire → `Task tasks.X[uuid] succeeded` | Y uuid succeeded in Z ms |
| URL contract `/admin/settings/*` korundu | `curl /admin/settings/keys -H "Auth: ..."` | 200, 97 anahtar |
```

#### 11.2 Yasak kanıt formları

- ❌ "Local test green" (paylaşılmadığı için doğrulanamaz)
- ❌ "I checked all callers" (numerik kanıt yok)
- ❌ "Works locally" (cross-environment doğrulama yok)
- ❌ Sadece CI badge (lazy import / runtime dispatch / cross-process davranış exercise etmiyorsa)

#### 11.3 Geçerli kanıt formları

- ✅ Komut + tam çıktı (bash log)
- ✅ CI run linki + relevant log excerpt
- ✅ Post-deploy worker log timestamp + task uuid + succeed metric
- ✅ Production curl response (status + body excerpt)
- ✅ Screenshot (admin UI write smoke için, log yerine)

### 12. Active Runtime Smoke Standard (PR 7a/7b cycle dersi — write path verification)

Runtime-sensitive PR'larda (settings_store / prompts_store / provider config / quota / Celery routing) acceptance şu **6-adımlı sıra**:

#### 12.1 Adım sırası

```
1. READ current state    → API/UI üzerinden mevcut değeri oku, raporla (fallback vs DB ayır)
2. WRITE test value      → Real admin route üzerinden değiştir (UI veya API call)
3. READ same-process     → Aynı process'te yeni değer dönüyor mu?
4. READ other-process    → Worker / scheduler / başka API instance'ı yeni değeri görüyor mu?
                           (Redis pub/sub invalidation < 5s, cross-process consistency)
5. RESTORE original      → "Varsayılana dön" / explicit eski değer + revert
6. READ final            → Eski değer dönüyor mu? Logs clean (ImportError / listener fail / Redis error YOK)?
```

#### 12.2 Yasak kısayollar

- 🛑 **Doğrudan DB row UPDATE/DELETE** — admin route davranışını test etmez, sadece raw DB davranışı
- 🛑 **Doğrudan Redis PUBLISH/DEL** — pub/sub listener wiring'i test etmez
- 🛑 **Same-process only read** (cross-process invalidation eksiklik gizler)
- 🛑 **Restore atlamak** (production state contamination)

Bu kısayollar **debug** için kullanılabilir ama smoke acceptance'ı oluşturmaz. Smoke = end-to-end real route exercise.

#### 12.3 Smoke evidence formatı

```
Step 1 (READ): chunker.target_tokens
  - GET /admin/settings/keys → 500 (registry default, DB row yok)
Step 2 (WRITE): PUT 280
  - PUT /admin/settings/chunker.target_tokens body={"value":"280"} → 200
Step 3 (READ same-process): GET /admin/settings/chunker.target_tokens → 280
Step 4 (READ worker):
  - 10:18:00Z beat fire `tasks.embedding.chunk_and_embed_article`
  - 10:18:00Z worker log: `ChunkingConfig(target_tokens=280, ...)`
  - Cross-process invalidation: 4.2s (< 5s threshold OK)
Step 5 (RESTORE): DELETE /admin/settings/chunker.target_tokens → 200
Step 6 (READ final): GET /admin/settings/chunker.target_tokens → 500 (registry default restored)
Logs scan: 0 ImportError / 0 Redis disconnect / 0 listener fail
```

## Review tarafının kontrolleri

Reviewer:
- [ ] Tüm checkbox'lar dolu mu?
- [ ] CI yeşil mi (lint + import-linter + tests + alembic check)?
- [ ] PR description "What changed" + "What did NOT change" iki bölümü de doldurulmuş mu?
- [ ] Risk seviyesi gerçekçi mi (Low/Medium/High)?
- [ ] Staging doğrulama screenshot/log var mı (uygulanabilirse)?

## Çıkarımlar

1. Bu checklist disiplin değil, **production güvenliği** aracı. Atlanan her madde geçmişte production regresyonuna yol açmıştır.
2. Refactor PR ≠ feature PR. Tek scope. Karıştırma.
3. Docs sync **aynı PR'da** — kullanıcı açık talebi (2026-05-20): "Tam otonom ilerleyeceğin için dokümantasyonu ayrı bir yük gibi görmüyorum."

## İlişkiler

- **Bağlı kararlar:** [[no-internal-backcompat-aliases]], [[god-file-facade-first]], [[import-direction-rules]]
- **İlgili playbook:** [[refactor-anti-patterns-do-not-do]], [[new-feature-module-checklist]]
- **PR template:** [.github/PULL_REQUEST_TEMPLATE/refactor.md](../../.github/PULL_REQUEST_TEMPLATE/refactor.md)

## Açık sorular / TODO

- Checklist GitHub PR template'inde otomatik render olur; her PR'da gözden geçirilir. Yeni öğrenmeler bu sayfaya + template'e eşzamanlı eklenir.

## Kaynaklar

- [.github/PULL_REQUEST_TEMPLATE/refactor.md](../../.github/PULL_REQUEST_TEMPLATE/refactor.md)
- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md)
