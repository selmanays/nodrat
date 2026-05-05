---
name: nodrat-dev
description: Nodrat ürün geliştirme akışı. Kullanıcı "nodrat-dev" ile başlayan komut verdiğinde zorunlu invoke edilir. Her isteği INDEX.md ve ilgili dokümanlarla anlamlandırır, MVP-1 cut-list ve faz hedeflerinden sapmaz, tüm değişiklikleri GitHub issue/branch/PR akışıyla yapar.
---

# Nodrat Dev Skill — Kullanım Protokolü

Bu skill, kullanıcı bir geliştirme talebini "nodrat-dev ..." ile başlattığında zorunlu olarak çalışır. Hiçbir kod yazma, doküman düzenleme veya GitHub aksiyonu, aşağıdaki 4 aşamalı protokol uygulanmadan başlamaz.

---

## Aşama 0 — Ön kontrol (MUTLAKA)

```text
[ ] Kullanıcının isteği "nodrat-dev" ile başlıyor mu?
[ ] /Users/selmanay/Desktop/nodrat/INDEX.md okundu mu?
[ ] İlgili klasörler tarandı mı? (docs/product, docs/strategy,
    docs/engineering, docs/design, docs/legal, docs/validation)
[ ] Şu an ki aktif milestone biliniyor mu? (gh milestone list)
[ ] Şu an ki açık issue'lar biliniyor mu? (gh issue list --state open)
```

Bu maddelerden biri eksikse aşama 1'e geçme. Kullanıcıya nedeni açıkla, eksik bilgiyi sor.

---

## Aşama 1 — İsteği anlamlandır

### 1.1 Niyet sınıflandırma

Kullanıcının talebini şu kategorilerden birine sınıflandır:

```text
A. Yeni özellik geliştirme  (feature)
B. Bug düzeltmesi          (bugfix)
C. Doküman güncelleme      (docs)
D. Refactor / cleanup      (refactor)
E. Test / eval ekleme      (test)  → "nodrat-test" skill'ine yönlendir
F. Soru / araştırma         (research)  → kod yazma, sadece raporla
G. Operasyonel             (devops, deploy, monitoring)
```

### 1.2 Kapsam doğrulama

```text
- Bu istek mevcut milestone içinde mi?
  → Hayır ise: "Bu istek MVP-X'e ait, şu an MVP-Y çalışıyoruz.
                Backlog'a alalım mı?" sor.

- Bu istek MVP-1 cut-list dışı bir feature mi? (docs/strategy/risk-register.md §4)
  → Cut-list OUT listesindeyse: "Bu MVP-1'de yok. MVP-2/3'e mi atalım?"

- Bu istek pricing/tier ihlali yapıyor mu?
  → Free user'a Pro feature açılıyorsa REDDET, gerekçesini açıkla.

- Bu istek legal/compliance ihlali içeriyor mu? (docs/legal/*)
  → PII redaction bypass, paywall kaynak, robots.txt ihlali → REDDET.
```

### 1.3 İlgili doküman taraması

İsteğe göre minimum şu dokümanlara bak:

```text
Her istek için:
  - INDEX.md
  - docs/product/prd.md (ilgili faz)
  - docs/product/information-architecture.md (sayfa/entity)
  - docs/strategy/risk-register.md §4 (kapsam)

Feature işiyse:
  - docs/engineering/architecture.md
  - docs/engineering/data-model.md
  - docs/engineering/api-contracts.md
  - docs/engineering/prompt-contracts.md (LLM içeriyorsa)
  - docs/design/ux-wireframes.md (UI içeriyorsa)
  - docs/design/design-system.md (copy/style)

Veri işliyse:
  - docs/legal/ropa.md (envanter)
  - docs/legal/privacy-policy.md
  - docs/legal/opinion-integration.md (PII redaction kuralları)

Güvenlik konuluysa:
  - docs/engineering/threat-model.md

Pricing/quota konuluysa:
  - docs/strategy/pricing-strategy.md
  - docs/strategy/unit-economics.md
```

### 1.4 İsteği yapılandır

Yapılandırılmış özet hazırla:

```yaml
intent: feature | bugfix | docs | refactor | test | research | devops
title: "<kısa açıklama, ≤70 char>"
phase: faz-0 | faz-1 | faz-2 | faz-3 | faz-4 | faz-5 | faz-6 | cross-cutting
mvp_scope: mvp-1 | mvp-2 | mvp-3 | backlog
relevant_docs:
  - <path>
  - <path>
acceptance_criteria:
  - <test edilebilir kriter>
  - <test edilebilir kriter>
risks:
  - <ilgili Risk Register ID>
out_of_scope:
  - <bu issue'da yapılmayacaklar>
```

---

## Aşama 2 — GitHub procedure (ZORUNLU)

### 2.1 Issue açma

Hiçbir değişiklik issue olmadan başlamaz.

```bash
# Eğer issue yoksa oluştur
gh issue create \
  --title "<title>" \
  --body "<structured body>" \
  --label "<labels>" \
  --milestone "<milestone>"
```

Issue body şablonu:

```markdown
## Hedef
<2-3 cümle: ne yapılacak, neden>

## Kapsam
- <madde 1>
- <madde 2>

## Doküman referansları
- docs/product/prd.md §X
- docs/engineering/data-model.md §Y

## Kabul kriterleri
- [ ] <test edilebilir>
- [ ] <test edilebilir>

## Out of scope
- <bu issue'da yapılmayacaklar>

## Risk / Bağımlılık
- Bağımlı issue: #N
- İlgili Risk Register: R-XXX-NN
```

### 2.2 Branch oluşturma

```bash
git checkout main
git pull --ff-only
git checkout -b <prefix>/<issue-no>-<short-desc>

# Prefix konvansiyonu:
# feature/   yeni özellik
# fix/       bug düzeltmesi
# docs/      doküman
# refactor/  refactor
# test/      test ekleme
# chore/     bakım
```

### 2.3 Commit konvansiyonu

Conventional commits + issue referansı:

```text
<type>(<scope>): <kısa açıklama>

<opsiyonel uzun açıklama>

Refs: #<issue-no>
```

```text
type      : feat | fix | docs | refactor | test | chore | perf
scope     : api | web | worker | db | infra | docs | rag | crawler
```

Örnek:
```
feat(api): /admin/sources/{id}/test-listing endpoint

PRD §1.4 selector test ekranı için backend.

Refs: #12
```

### 2.4 Pull Request

```bash
git push -u origin <branch>
gh pr create \
  --title "<aynı issue başlığı>" \
  --body "<PR body>" \
  --base main
```

PR body şablonu:

```markdown
## Özet
<1-3 cümle>

## Bağlantılı issue
Closes #<issue-no>

## Yapılan değişiklikler
- <madde>
- <madde>

## Doküman uyumu
- [ ] PRD ile tutarlı
- [ ] IA / Data Model güncel mi (gerekiyorsa)
- [ ] API Contracts güncel (varsa endpoint değişimi)
- [ ] Threat Model: yeni risk yok / mitigation eklendi
- [ ] Legal: PII redaction / KVKK / FSEK uyumlu

## Test
- [ ] Unit test eklendi/güncellendi
- [ ] Integration test (varsa)
- [ ] Manuel smoke test
- [ ] LLM eval (prompt değiştiyse)

## Screenshot / demo
<varsa>
```

### 2.5 Review ve merge

```text
- Self-review zorunlu (PR açmadan önce kendi değişikliklerini gözden geçir)
- Issue'da "Closes #N" olmalı (auto-link)
- Merge sonrası branch silinir: gh pr merge --delete-branch
- Issue otomatik kapanır
```

---

## Aşama 3 — Geliştirme (kod yazma)

### 3.1 Anti-patternler (HARD STOP)

Aşağıdaki davranışlardan herhangi birini fark edersen DURDUR ve kullanıcıya bildir:

```text
🛑 PII redaction'ı atlama
🛑 LLM provider'a kullanıcı email/IP/account ID gönderme
🛑 Robots.txt disallow olan path'i kazıma
🛑 Paywall arkasındaki içeriği kaynak olarak ekleme
🛑 Tam haber metnini son kullanıcıya gösterme
🛑 25 kelimeden uzun direct quote (FSEK)
🛑 Halüsinasyon prompt rule'larını atlama
🛑 Veri yetersizliğinde içerik üretme
🛑 18 yaş gate'i bypass etme
🛑 Kullanıcı verisini silmeden hard-code etme
🛑 Provider key'i koda hardcode etme veya log'a yazma
🛑 SQL injection / parameterized query atlamak
🛑 Auth check olmayan endpoint
🛑 Free tier'a Pro feature açma (server-side check yok)
🛑 Migration'ı backward-incompatible yapma (zero-downtime kuralı)
```

### 3.2 Stack ve teknoloji uyumu

Kullanılacak araçlar `docs/engineering/architecture.md` §0'da kilit:

```text
✅ Frontend: Next.js 14 + shadcn/ui + Tailwind
✅ Backend: FastAPI + Pydantic v2
✅ Worker: Celery 5
✅ DB: PostgreSQL 16 + pgvector
✅ Cache/Queue: Redis 7
✅ Storage: MinIO
✅ Proxy: Caddy 2
✅ Container: Docker Compose
✅ Default LLM: DeepSeek V3
✅ Premium LLM: Claude Haiku 4.5 (Pro+ tier)
✅ Embedding: NIM bge-m3 (free) + local fallback
```

Bu listeden sapma kullanıcı onayı gerektirir.

### 3.3 Kod kalitesi

```text
- Lint: ruff + black (Python), eslint + prettier (TS)
- Type: mypy (Python strict), tsc (TS strict)
- Test coverage hedefi: >70% (kritik path'lerde >85%)
- Yorum: kod neden, nasıl değil (PRD anti-pattern)
- Naming: domain-driven (article, source, generation, vs.)
```

### 3.4 Doküman güncelleme

Eğer değişiklik:

```text
- Yeni endpoint  → docs/engineering/api-contracts.md güncelle
- Yeni tablo     → docs/engineering/data-model.md güncelle
- Yeni prompt    → docs/engineering/prompt-contracts.md güncelle
- Yeni sayfa     → docs/design/ux-wireframes.md + IA güncelle
- Pricing değişimi → docs/strategy/pricing-strategy.md güncelle
- Yeni risk      → docs/strategy/risk-register.md güncelle
```

---

## Aşama 4 — Tamamlama

### 4.1 Definition of Done

```text
[ ] Kabul kriterleri tüm karşılandı
[ ] Test'ler yeşil (CI)
[ ] Self-review yapıldı
[ ] PR açıldı, issue'a link verildi
[ ] Doküman güncellendi (gerekiyorsa)
[ ] Anti-patternler kontrolü yapıldı
[ ] Smoke test yapıldı (UI ise tarayıcıda)
```

### 4.2 Kullanıcıya raporlama

```text
- 1-2 cümle özet (ne yapıldı)
- Issue link
- PR link
- Eklendi/değişti dosya sayısı
- Eğer kullanıcının manuel adımı varsa NET belirt
```

### 4.3 Anti-patterns rapor sırasında

```text
🛑 "Yapıldı" deme test çalışmadan
🛑 Tahmin edilen sonucu raporlama (belirsizse "ölçmedim" de)
🛑 Aşama 0 ön kontrolünü atlama
🛑 GitHub procedure'sini atlama
🛑 Doküman değişiklikleriyle ilgili bilgi gizleme
```

---

## Hızlı Komut Şablonları

### Yeni feature başlatma
```bash
# 1. Doküman incele (otomatik)
# 2. Issue oluştur
gh issue create --title "..." --label "type:feature,phase:N" --milestone "MVP-X"
# 3. Branch
git checkout -b feature/<N>-<desc>
# 4. Geliştir
# 5. PR
gh pr create --title "..." --body "Closes #N"
```

### Bug fix
```bash
gh issue create --title "..." --label "type:bug,priority:high"
git checkout -b fix/<N>-<desc>
# fix
gh pr create --title "..." --body "Closes #N"
```

### Doküman değişikliği
```bash
gh issue create --title "..." --label "type:docs"
git checkout -b docs/<N>-<desc>
```

---

## Doğrulama soruları (her istekten sonra kullanıcıya)

```text
1. Bu issue açıldı mı? (#<N>)
2. Branch ismi doğru mu?
3. Anti-patterns kontrol edildi mi?
4. Test yazıldı mı / mevcut testler geçiyor mu?
5. Doküman güncel mi?
```

---

## Acil durumlar

```text
- Build kırılması    : feature toggle ile devre dışı bırak, fix branch
- Production outage  : docs/legal/incident-response.md SEV-1 prosedürü
- KVKK ihlali        : DPO çağrısı + 72h timer (incident-response.md)
- Cost runaway       : provider quota cap aktif et + investigation
- Provider down      : OpenRouter / GPT-4o-mini fallback
```

---

## Manuel deploy fallback (GitHub Actions runner allocation fail)

GitHub Actions runner allocation fail olduğunda (`billable.UBUNTU.total_ms: 0`,
runner_name boş, 3-5 saniyede fail) deploy.yml çalışmaz. Quota / spending limit
veya GitHub-level outage işareti. Bu durumda VPS'e doğrudan SSH ile manuel
deploy yapılır.

### VPS bağlantı bilgileri
```text
Host         : 173.212.238.104
Port         : 2222
User         : root
Path         : /opt/nodrat
SSH key      : ~/.ssh/vps_deploy
```

### Manuel deploy adımları (web servisi için)

```bash
# 1. Local'den VPS'e rsync (deploy.yml'ın rsync adımıyla birebir aynı)
rsync -avz --delete \
  --exclude=".git" --exclude="node_modules" --exclude="__pycache__" \
  --exclude=".pytest_cache" --exclude=".ruff_cache" --exclude=".mypy_cache" \
  --exclude="*.pyc" --exclude=".next" \
  -e "ssh -i $HOME/.ssh/vps_deploy -p 2222 -o StrictHostKeyChecking=yes" \
  apps infra docker-compose.yml docker-compose.dev.yml .env.example \
  "root@173.212.238.104:/opt/nodrat/"

# 2. VPS'de docker compose web build + up (sadece web değiştiyse)
ssh -i ~/.ssh/vps_deploy -p 2222 root@173.212.238.104 "bash -se" <<'EOSSH'
set -euo pipefail
cd /opt/nodrat
docker compose --env-file .env build web
docker compose --env-file .env up -d web
docker compose ps web
EOSSH

# 3. Doğrulama
curl -sS -o /dev/null -w "%{http_code}\n" https://nodrat.com/admin/<page>
# 200 → başarılı

# Süre: rsync ~5s, build ~120s, up ~3s = toplam ~2 dk
```

### API + worker değişikliği için

Web yerine ya da ek olarak ilgili servisleri rebuild et. deploy.yml'daki tam set:
```bash
docker compose --env-file .env build \
  api web worker_scraper worker_cleaner worker_embedding worker_rag scheduler

docker compose --env-file .env up -d \
  postgres redis minio api web \
  worker_scraper worker_cleaner worker_embedding worker_rag scheduler

# Migration gerektiyse
docker compose exec -T api alembic upgrade head
```

### NE ZAMAN MANUEL FALLBACK

```text
✅ GitHub Actions runner allocation fail
✅ GitHub Actions billing/quota dolduğunda
✅ Acil hotfix (Actions sırasında 3 dk beklemek istemediğinde)
🛑 NORMAL durumda — push to main otomatik deploy.yml tetiklenir
```

**Hatırlatma:** kod yine de main'e push edilir (audit trail + diğer
ortamlarda deploy.yml tetiklenebilir). Manuel deploy sadece VPS'e atlama.

---

**Bu skill ile başlayan her istek, yukarıdaki 4 aşamalı protokole uymak ZORUNDADIR. Aşamayı atlamak, dokümanlardan sapmak, anti-patternleri ihlal etmek = STOP + kullanıcıya açıklama.**
