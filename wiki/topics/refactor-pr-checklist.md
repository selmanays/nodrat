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

  **Form 4 — quoted file-path string (PR #1131 dersi).** Bazı testler ve script'ler modülü Python import etmez; **raw filesystem path** olarak açar (örn. `(_REPO_API / "app/workers/tasks/articles.py").read_text()`). Bu form 1-3 grep'lerine kaçar. PR #1131'de `test_articles_cleaned_at.py:60` CI'da `FileNotFoundError` ile yakalandı, 1 satır fix gerektirdi. Pre-flight'a 4. grep şarttı:
  ```bash
  # Form 4 — quoted file-path string (tests + scripts):
  grep -rE '"<old_dir>/<old_name>\.py"' apps/api --include="*.py"
  # Örnek: grep -rE '"app/workers/tasks/articles\.py"' apps/api --include="*.py"
  ```

  **Form 5 — namespace import as alias (PR #1131 dersi).** `from app.workers.tasks import articles as articles_module` formu Form 2'nin alt-türüdür ama farklı dosyalarda izole olabilir (test_admin_queue.py:246'da bu pattern PR 1b silent miss deseninin tekrarıydı, pre-flight'ta yakalandı). `from <old_parent> import <module>(\s+as\s+<alias>)?` regex'i Form 2 grep'ine dahil edilmeli:
  ```bash
  grep -rE 'from app\.<old_parent> import <module_name>(\s+as\s+\w+)?' apps/api --include="*.py"
  ```

### 6.9. Boundary contract transitif chain analizi (PR #1131 dersi)

`app.modules.X` source_modules contract'ı **transitif** tarama yapar; ara katmanın `app.modules.*` veya legacy `app.workers.*` olması ihlali engellemez. Mini plan ya da pre-flight'ta şu hata kalıbı tekrar etmiş:

> "`workers.tasks.embedding` legacy worker path (not `app.modules.*`) → contract scope dışı, ihlal değil"

**Bu yanlış.** import-linter source'tan başlayarak tüm transitive dep graph'ı tarar; **hedef** `app.modules.*` forbidden listesinde ise chain'in tamamı BROKEN sayılır. Örnek (PR #1131 öncesi):

```
modules.articles.tasks.articles
  → workers.tasks.embedding (lazy ×2)
    → modules.clusters.tasks.clustering (embedding.py:434 lazy)
```

Contract: "articles must not import upper layers" forbidden=`[crawler, rag, clusters, generations]`. Chain'in son halkası `modules.clusters` → **BROKEN**.

**Mini plan kontrolünde transitif checklist:**
- [ ] Yeni `modules/X` taşımasından sonra X'in lazy import'larının **dış zinciri** çıkarıldı mı?
- [ ] Chain'de herhangi bir halka X'in forbidden listesindeki `modules/*` modüllerine bağlanıyor mu?
- [ ] Bağlanıyorsa: A1-style send_task decoupling (PR 2a deseni) ile **kaynak Python import'unu sil** — `ignore_imports` muafiyeti EKLEME (kullanıcı kuralı).
- [ ] Yerel `lint-imports` ile chain doğrulaması yapıldı mı (188+ files, 470+ deps full graph)?

**`ignore_imports` muafiyet yasağı:** Transitif chain ihlali tespit edilirse otomatik muafiyet ekleme; ÖNCE kullanıcıya raporla + decoupling planı sun. Sources PR 1b'de transient muafiyet eklendi (legitimate), PR 2a'da kaldırıldı; PR 2b'de aynı sınıf ihlal A1 ile çözüldü. **Muafiyet birikmemeli.**

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

### 11.1. Smoke dili (PR #1131 dersi — caveat doğru yazılsın)

Smoke raporlarında "FULL PASS" olduğundan güçlü iddia kurma; doğal olarak gözlenmemiş yan-kanıt varsa **caveat** doğru yazılsın:

- **Doğal dispatch görülmedi:** "natural fire not observed within window, non-blocking" — pencerede tetikleyici event yoksa task path'i runtime'da kanıtlanamayabilir; bu **decoupling/migration'ı invalidate etmez** ama iddia ona göre yumuşatılır.
- **False positive log hit:** Tek hit görüldüğünde **incelenir + sınıflandırılır** (gerçek hata mı, success log'unun field'ında yakalanan keyword mü?). PR #1131'de `embedding.*(error|fail)` grep `'errors': 0` content'iyle eşleşti — false positive, kanıt olarak yazıldı.
- **Manual trigger yapılmadıysa belirt:** "No manual/synthetic state-changing smoke was performed; no test-induced production mutation." Doğal Beat fires production'un normal davranışıdır; PR ile başlatılmış gibi sunma.

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

### 13. CI auto-trigger anomaly recovery (PR #1133 / #1134 dersi)

**Olay (2026-05-21):** PR #1133 (embedding migration, squash `37f11af`) merge edildi. Beklenen davranış `push:main` event → `ci.yml` çalışır → `workflow_run` → `deploy.yml`. **Gözlem:** `gh run list --commit 37f11af6` boş döndü; `ci.yml` main üzerinde **HİÇ TETİKLENMEDİ** → deploy.yml workflow_run zinciri başlamadı → VPS eski `ed669ed` (PR 2b) state'inde kaldı. PR 1a/1b/2a/2b/2-closure hepsi normal tetiklendi; anomaly **PR #1133'e özgü tek seferlik**.

**Yanıltıcı smoke riski:** ESKİ kod tabanı `tasks.embedding.*` 6 task'ı registry'de yeni-pathmiş gibi gösterdi (decorator string'leri aynı). Ancak runtime probe'lar (`importlib.import_module('app.modules.embedding')` + entities.py `__module__`) doğru FAIL verdi → yeni kod prod'da olmadığı tespit edildi.

**Kurtarma yolu (PR #1134, squash `42c4dcd`):**

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
+ workflow_dispatch:
```

`ci.yml` `on:` bloğuna `workflow_dispatch:` 3. trigger eklendi (1 satır net diff). `gh workflow run ci.yml --ref main` ile main üzerinde CI manuel tetiklenebilir hale geldi. **Recovery test edilmedi** çünkü PR #1134 merge sonrası push:main otomatik tetiklendi (anomaly tekrar yaşanmadı); ama gelecek için garanti var.

**Hard kural — deploy.yml workflow_dispatch direkt tetiklenmemeli:**
- SHA pinning (#1108) tek başına workflow_dispatch ile bozulabilir (workflow_run gate atlanır → deployed SHA = CI head_sha invariant'ı kırılır)
- Recovery yolu **CI üzerinden workflow_run** olmalı: önce `gh workflow run ci.yml --ref main` → CI success → deploy.yml workflow_run otomatik tetiklenir → SHA pinning korunur

**Checklist — merge sonrası 30 dk içinde:**

- [ ] `gh run list --commit <new-main-sha> --limit 5` → main üzerinde **CI run var mı**?
- [ ] CI başlamadıysa `push:main` event tetiklenmemiş → **anomaly**; `gh workflow run ci.yml --ref main` ile recovery
- [ ] CI success sonrası deploy.yml workflow_run otomatik tetiklenmeli → SHA pinning log "Deploy target verified: SHA pinning OK"
- [ ] **Deploy.yml workflow_dispatch direkt başlatma** (kullanıcı kuralı: workflow_run gate atlanır → #1108 invariant kırılır)
- [ ] Smoke'da yanıltıcı yeşil riski: eski kod taban registry/routing/Beat'i AYNI gösterebilir → her zaman **runtime probe** (`importlib`, `__module__`, VPS filesystem `ls`) ile new-vs-old path durumunu kanıtla; sadece registry sayım yetmez

### 13.1. Erken false-fail timing — container restart buffer (PR #1137 dersi)

Auto-merge sonrası **fast smoke probe** koşulurken yanıltıcı sonuç alınabilir: deploy-vps "success" döndüğü ve container CreatedAt güncel olduğu halde, runtime probe için yeterli buffer olmayabilir. PR #1137'de fast probe sırasında `app.modules.ops.tasks.maintenance` `ModuleNotFoundError` + `app.workers.tasks.maintenance` "STILL IMPORTABLE" yanıltıcı sonucu verdi; 30-60sn sonra fresh probe gerçek sonucu (NEW OK + OLD GONE) gösterdi.

**Hard kural — deploy-vps success ≠ runtime ready:**
- Container CreatedAt güncel olabilir ama Python process cold-start henüz tamamlanmamış olabilir
- Runtime probe (`importlib.import_module`, `__module__`, attribute existence) için **deploy-vps tamamlandıktan sonra ≥60sn buffer** öner
- Veya healthcheck endpoint'i (`/health`) ile production hazır olduğunu garantile, sonra runtime probe yap
- Hızlı bg job'larda buffer gözardı edilmemeli; yanıltıcı FAIL/SUCCESS sonuçları kararı yanlış yönlendirir

### 13.2. Bg job worktree cwd-loss anti-pattern (PR #1137 dersi)

Tek bg job içinde `git worktree remove` çalıştırıldıktan sonra `gh run watch` veya başka git/gh komutu cwd kaybolduğu için fail eder:

```
failed to determine base repo: failed to run git: fatal: Unable to read current working directory: No such file or directory
```

**Hard kural:**
- Worktree cleanup işlemleri ayrı bash invocation'da yapılmalı VEYA bg job'un **son adımı** olmalı
- Bg job içinde merge + cleanup + post-merge verification sırayla yapılacaksa: post-merge verification ÖNCE, worktree cleanup SON
- Cwd-bound komutlar (gh, git) worktree remove'dan ÖNCE çalıştırılmalı; sonrası için `cd /Users/selmanay/Desktop/nodrat` veya `git -C <primary>` kullanılmalı

### 13.3. Smoke probe force-load disipline (PR #1141 dersi)

Worker container'da `celery_app.tasks` programatik sorgu sadece import edilen modüllerdeki @task decorator'larla register olur. Celery `include=[...]` listesini auto-load **yalnız `celery worker` command init phase'inde** tetikler — `from app.workers.celery_app import celery_app` çağrısı tek başına yetmez.

**False-negative örnek (PR #1141 ilk smoke):**

```python
# YANLIŞ — registry boş gelir (false-negative)
from app.workers.celery_app import celery_app
tasks = [t for t in celery_app.tasks if "agenda" in t]
print(len(tasks))  # 0 (yanıltıcı; gerçekte 3 task var)
```

**Doğru smoke probe (force-load):**

```python
# DOĞRU — import_default_modules() include list'i eager yükler
from app.workers.celery_app import celery_app
celery_app.loader.import_default_modules()   # ← GEREK
tasks = sorted([t for t in celery_app.tasks if "agenda" in t])
for t in tasks: print(" ", t)
# tasks.agenda.backfill_country
# tasks.agenda.generate_agenda_card
# tasks.agenda.refresh_active_cards
```

**Hard kural:**
- Worker task migration smoke probe'ları `celery_app.loader.import_default_modules()` ile başlamalı
- Probe edilecek container worker olmalı (api container'da auto-load gerçekleşmez; yalnız `from X import agenda` gibi explicit import doldurur)
- Tercih edilen container: queue tüketicisi (`tasks.agenda.* → event_queue` → `worker_rag`; `tasks.research_clustering.* → embedding_queue` → `worker_embedding`)
- "Registry count: 0" sonucu görüldüğünde önce force-load denemeden migration FAIL'i raporlama

**Alternatif: route glob ile dolaylı kanıt** — `celery_app.conf.task_routes` dict'inde `"tasks.X.*"` key'i `{"queue": "..."}` ile mevcutsa konfigürasyon doğru kurulmuştur (registry boş olsa bile); route glob varlığı + new path import OK + old path ModuleNotFoundError üçlüsü minimum kanıt setidir.

### Replay / event-sequence characterization caller-wrap deseni (PR #1160 dersi)

**Bağlam:** Bir generator/iterator helper'ı (örn. SSE `_simulate_stream`) test edilirken **ne yield ettiği** ile **caller'ın bu yield'i nasıl sardığı** ayrı invariant'lardır. Single-call testlerinde helper'ın çıktısı doğrudan test edilir; replay/sequence testlerinde caller wrap davranışı eklenmelidir.

**Vaka (PR #1160):** `_simulate_stream(text)` raw word-group string'leri yield eder (`"word1 word2 word3 "`); SSE-formatted DEĞİL. Production caller `_research_stream_body:1289`:

```python
async for piece in _simulate_stream(content):
    yield _sse("chunk", {"delta": piece})  # caller wrap — helper'ın yield'ini SSE block'a çevirir
```

PR-A3 ilk push'unda replay testi `transcript_parts.extend(raw_chunks)` yaptı → raw text concatenated SSE separator'larıyla yanlış birleşti → `\n\n` boundary parçalandı → `assert lines[0].startswith("event: ")` FAIL.

**Fix:** Replay testte caller davranışını birebir taklit et:

```python
raw_chunks = await _collect(_simulate_stream(content))
chunk_frames = [_sse("chunk", {"delta": piece}) for piece in raw_chunks]  # caller wrap
transcript_parts.extend(chunk_frames)
```

**Hard kural:**
- Helper'ın yield invariant'ı (raw yield format) PR #1150 türü single-call testlerde lock'lanır.
- Caller wrap invariant'ı (yield → final consumer format) replay/sequence testlerde lock'lanır.
- Replay testi yazarken: helper raw çıktısı production consumer formatından FARKLI mı? → caller wrap test'te taklit edilmeli.
- Aksi takdirde: test, helper'ı tek başına yanlış varsayımla kullanır → SSE separator gibi format invariant'ları yanıltıcı şekilde patlar.
- **Production source DEĞİŞMEZ** — test caller davranışını taklit eder.

**Auto-merge gate'in faydası:** PR #1160 ilk push'ta gate `ABORT non-pass` döndü; merge yapılmadı; fix push retry'da PASS → merge. Gate olmasa yanlış test main'e geçebilirdi.

### TypeScript same-file type-ref edge case (PR #1175 dersi)

**Bağlam:** Extract sonrası aynı dosyada kalan fonksiyon eski type'ı kullanıyorsa inline type-only import gerekebilir. Örnek: `as import('./api/auth').TokenResponse`. Runtime impact yok; type-check ile yakalandı.

**Vaka (PR #1175 — `apps/web/src/lib/api/auth.ts` extract):** `TokenResponse` interface api.ts'ten `api/auth.ts`'e taşındı + api.ts re-export edildi. Ancak api.ts içinde KALAN `attemptTokenRefresh` fonksiyonu (concurrent 401 protection core) hâlâ aynı dosya scope'unda `TokenResponse` cast yapıyordu (`(await resp.json()) as TokenResponse`). Re-export `export type {...} from "./api/auth"` modül dışı tüketicilere TokenResponse'u sunar, ancak **modül-içi** function body'de bu re-export'lanmış type kendi scope'unda automatik VAR DEĞİL (re-export ≠ kendi import). TypeScript `TS2304: Cannot find name 'TokenResponse'`.

**Fix:** İki seçenek:

**Seçenek A (tercih edilen — minimal):** Inline type-only import as-cast:

```typescript
// api.ts (core'da kalan attemptTokenRefresh)
const data = (await resp.json()) as import("./api/auth").TokenResponse;
```

- **Runtime impact YOK** — `import("./X").Y` type-only as-cast; erased at compile.
- 1 satır değişiklik; re-export bloğunu sadeleştirmez (modül dışı caller'lar hâlâ `import { TokenResponse } from "@/lib/api"` çalıştırır).

**Seçenek B (daha "konvansiyonel" ama gereksiz):** Top-level explicit `import type`:

```typescript
import type { TokenResponse } from "./api/auth";
```

- Modül-içi scope'a tipi ekler; ancak `api.ts` zaten **facade** dosyası — kendi içinde bir aux helper için ekstra `import type` line ekler.
- Seçenek A 1 satır daha kompakt + same-file-only kullanım daha net.

**Hard kural:**
- Extract sonrası aynı dosyada kalan fonksiyon eski type ile referans veriyorsa: **tsc strict** local pre-flight'ta hatayı yakalayacaktır (`TS2304: Cannot find name`).
- Re-export bloğu modül dışı tüketicileri kapsar; **modül-içi function body** ekstra import gerektirir.
- **Runtime semantic değişmez** (Seçenek A erased; Seçenek B aynı şekilde type-only). Davranış invariant.
- **PR description'da kanıt:** `tsc strict PASS` + `vitest PASS` + manuel `grep` ile aynı-dosya type-ref'lerin tümünün düzeltildiği gösterilir.
- **Test isteği:** Vitest characterization testi cast'i exercise eder (bizim case: token refresh 401 → fetch → JSON parse mock); regression önlenir.

**Production behavior değişikliği YOK** — `attemptTokenRefresh` API contract + storage semantik + retry behavior aynen; sadece cast hedef adı dosyada nasıl resolve olduğu değişti.

### Interleaved read-only / state-changing split (PR #1204 dersi)

**Bağlam:** Bir domain (örn. Admin RAG) read-only (GET/observability) ve state-changing/trigger (POST/benchmark/pipeline) sembollerini **kaynak sırada iç içe** (interleaved) barındırabilir. Smoke güvenliği için read-only'yi önce taşıyıp trigger'ları sonraki PR'a bırakmak istiyorsun (split), ama semboller alfabetik/blok hâlinde ayrılmamış — araya girmişler.

**Vaka (PR #1204 — `apps/web/src/lib/api/admin/rag.ts` Part 1/2):** api.ts'in Admin RAG bölümünde 19 read-only interface + 9 read-only GET fonksiyon ile 9 trigger interface + 3 trigger fonksiyon (`ragBenchmarkRun`/`ragRaptorTrigger`/`ragInspectQuery`) kaynak sırada karışıktı. Hedef: yalnız read-only'yi yeni `api/admin/rag.ts`'e taşı, trigger'ları PR-7a-18b için INLINE bırak. Tek tek satır-aralığı silme riskli (yanlış sembol taşınır / type-ref kırılır).

**Teknik (tercih edilen):** Bölümün **tamamını tek Edit ile yeniden yaz**:
- `old_string` = tüm interleaved bölüm (read-only + trigger, kaynak sırasıyla).
- `new_string` = (a) re-export bloğu (`export type {...}` + `export {...} from "./api/admin/rag"`) + (b) trigger fonksiyon/interface'ler **verbatim INLINE** korunur.
- Yeni modül dosyası SADECE read-only sembolleri içerir.

**Bağımsızlık ön-kontrolü (zorunlu):** Taşımadan önce doğrula ki read-only interface'ler trigger interface'lere **bağlı değil** (tip referansı yok). Bağlıysa split sınırı kayar — ya bağımlı tipi de taşı ya da split noktasını değiştir.

**Hard kural:**
- **`tsc strict` interleaved split'in kanıtıdır:** Eğer read-only modüle taşınan bir sembol, inline kalan trigger sembolüne (veya tersi) type-ref veriyorsa `tsc` `TS2304`/`TS2305` ile patlar. PASS = çapraz-referans kırılmadı = split sınırı doğru.
- **Trigger'lar verbatim kalır** — split PR'ında trigger davranışı/imzası DEĞİŞMEZ; yalnız konumları (api.ts inline) sabit kalır, Part 2/2'de taşınır.
- **Smoke güvenliği split'in amacı:** read-only Part 1 prod'da güvenle smoke edilir (GET); trigger Part 2 yalnız Vitest fetch-mock ile test edilir, prod'da TETİKLENMEZ (benchmark/RAPTOR/pipeline maliyetli + state-changing).
- **PR description'da kanıt:** `tsc strict PASS` + taşınan read-only sembol listesi + inline kalan trigger sembol listesi + "Part 1 of 2" etiketi.

**Production behavior değişikliği YOK** — re-export facade `@/lib/api` import path'lerini korur; read-only fonksiyon imzaları + trigger inline davranışı aynen.

#### Contiguous (interleaved DEĞİL) karşıtı — Part 2/2 (PR #1206 dersi)

**Bağlam:** Interleaved split'in (18a) Part 2/2 tamamlayıcısı. Trigger sembolleri 18a'da inline bırakılmıştı; 18b'de taşındı. Kritik fark: 18b'de trigger sembolleri kaynak sırada **bitişikti** (contiguous), iç içe değildi.

**Vaka (PR #1206 — Admin RAG triggers → `api/admin/rag.ts`):** 3 trigger fn + 9 trigger interface tek bitişik blok (api.ts L692-823). Çözüm interleaved'den **daha basit**: bütün bloğu `rag.ts` sonuna tek append + api.ts'te tek re-export bloğu. Section yeniden yazımı GEREKMEDİ.

**Hard kural:**
- **Önce contiguous mu interleaved mi tespit et.** Bitişik blok → tek append + tek re-export (en ucuz). İç içe → bütün section'ı yeniden yaz (18a deseni). Yanlış teşhis gereksiz iş veya kırık taşıma demektir.
- **Bağımlı tipler bloğun içinde olmalı.** Trigger interface'leri yalnız birbirine ref veriyordu (`InspectQueryResponse` → diğer `Inspect*`), read-only modüle ref YOK → blok kendi kendine yeterli. `tsc` PASS bunu kanıtlar.
- **State-changing kısım Part 2'de prod'da TETİKLENMEZ** — yalnız Vitest fetch mock; POST imzaları + body verbatim korunur.

#### Fresh-worktree pre-flight: `npm ci` zorunlu (PR #1206 dersi)

**Bağlam:** Frontend (apps/web) code PR'ı taze worktree'de Vitest/tsc/lint/build çalıştırmadan önce bağımlılık kurmak gerekir.

**Vaka:** Taze worktree'de `apps/web/node_modules` YOK. `npx vitest` standalone bir vitest çeker → `vitest/config` resolve edilemez → config yüklenemez. Primary repo'nun `node_modules`'una symlink de yetmez: primary **dev dependency'leri** (vitest dahil) içermeyebilir.

**Hard kural:**
- **Taze worktree'de pre-flight'tan önce `cd apps/web && npm ci`** (package-lock.json'dan tüm dev deps; ~20 sn). Symlink veya primary node_modules'a güvenme.
- `node_modules` + `.next` zaten `.gitignore`'da → commit'e sızmaz; worktree cleanup ile silinir.

#### Dead shared-import after extract (PR #1208 dersi)

**Bağlam:** Bir fonksiyonu modülden ayırırken, o fonksiyon paylaşılan bir helper'ın (ör. `buildQuery`) **son kullanıcısıysa**, kaynak dosyadaki import dead olur. tsc bunu yakalamaz; ESLint yakalar → build fail.

**Vaka (PR #1208 — Research non-SSE extract):** `listResearchConversations` api.ts'ten `api/research.ts`'e taşındı; bu, api.ts'te `buildQuery`'nin son kullanıcısıydı. api.ts'teki `import { buildQuery } from "./api/_query"` artık kullanılmıyordu. **`tsc --noEmit` PASS verdi** (kullanılmayan import'u default'ta hata saymaz), ama **`next lint` → `@typescript-eslint/no-unused-vars` Error** → next build FAIL.

**Hard kural:**
- **Extract sonrası kaynak dosyada artık kullanılmayan shared import'u SİL.** Taşınan fonksiyon paylaşılan bir helper'ın son kullanıcısı mıydı? grep ile doğrula (`grep -c buildQuery api.ts`).
- **Pre-flight'ta `next lint` (veya `tsc` değil ESLint) bu sınıfı yakalar** — Vitest + tsc geçse bile lint/build adımını ATLAMA.
- Helper'ın kendisi (ör. `api/_query.ts`) silinmez; yalnız ölü import satırı temizlenir. Taşınan fonksiyon helper'ı yeni modülden import eder.

#### Core-const export for raw-fetch client (PR #1210 dersi)

**Bağlam:** Çoğu fonksiyon `apiFetch` (core helper) üzerinden çalışır ve extract için yalnız `apiFetch`'i import eder. Ama bir fonksiyon **raw `fetch`** kullanıyorsa (ör. SSE/streaming, çünkü `apiFetch` streaming body döndürmez), modül-local core constant'lara (`API_BASE`) doğrudan ihtiyaç duyar. Bu constant exported değilse extract bloklanır.

**Vaka (PR #1210 — `streamResearchMessage` SSE client):** Fonksiyon `${API_BASE}/...` + `getAccessToken()` + `ApiException` ile raw fetch yapıyordu (`resp.body.getReader()` streaming gerektirir, apiFetch JSON parse eder). `getAccessToken`/`ApiException` zaten exported; **`API_BASE` module-local `const`'tu**. Extract için `const API_BASE` → **`export const API_BASE`** (1 kelime; value/logic DEĞİŞMEZ). `api/research.ts` `API_BASE`/`getAccessToken`/`ApiException`'ı `../api`'den import etti.

**Hard kural:**
- **Raw-fetch fonksiyon extract'inde core bağımlılıklarını önce çıkar:** `API_BASE` (module-local mı?), `getAccessToken`, `ApiException`. Module-local olan tek constant'ı **minimal export** et — value/logic değiştirme, yalnız `export` ekle.
- **`apiFetch`/`attemptTokenRefresh`/token-storage TAŞINMAZ** — bunlar core'da kalır; raw-fetch client onları (veya `API_BASE`'i) `../api`'den tüketir.
- **SSE/stream parse gövdesi byte-for-byte korunur** — yalnız konum değişir; davranış invariant. PR description'da "API_BASE exported; value unchanged" + tsc PASS kanıtı.
- Yeni export, facade yüzeyini büyütür ama zararsız bir sabittir (URL base). Re-export gerektirmez; doğrudan core export yeterli.

## Review tarafının kontrolleri

Reviewer:
- [ ] Tüm checkbox'lar dolu mu?
- [ ] CI yeşil mi (lint + import-linter + tests + alembic check)?
- [ ] PR description "What changed" + "What did NOT change" iki bölümü de doldurulmuş mu?
- [ ] Risk seviyesi gerçekçi mi (Low/Medium/High)?
- [ ] Staging doğrulama screenshot/log var mı (uygulanabilirse)?
- [ ] Merge sonrası `gh run list --commit <sha>` ile CI tetiklendi mi doğrulandı mı (§13 dersi)?

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
