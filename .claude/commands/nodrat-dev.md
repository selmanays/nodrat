---
description: Nodrat dev workflow — anlamlandırma + doküman taraması + GitHub akışı (issue/branch/PR), MVP-1 cut-list dışı sapma yok
---

# /nodrat-dev — Geliştirme Akışı

Bu komut, herhangi bir Nodrat geliştirme talebini 4 aşamalı protokole göre işler.

---

## Aşama 0 — Ön kontrol (MUTLAKA)

```text
[ ] /Users/selmanay/Desktop/nodrat/INDEX.md okundu mu?
[ ] /Users/selmanay/Desktop/nodrat/wiki/index.md okundu mu? (mevcut decision/entity'ler)
[ ] /Users/selmanay/Desktop/nodrat/wiki/log.md son 3 girişi tarandı mı?
[ ] İlgili klasörler tarandı mı? (docs/product, strategy, engineering, design, legal, validation)
[ ] Şu an aktif milestone biliniyor mu? → gh milestone list
[ ] Açık issue'lar biliniyor mu? → gh issue list --state open
```

> SessionStart hook wiki/index.md + log son 3 başlığı zaten otomatik enjekte eder; ama agent'ın açık tarama disiplinini koruması için checkbox listede tutulur. Detay: kök CLAUDE.md §1.3.

---

## Aşama 1 — İsteği anlamlandır

### 1.1 Niyet sınıflandırma

```text
A. feature   — yeni özellik
B. bugfix    — bug düzeltmesi
C. docs      — doküman güncelleme
D. refactor  — refactor / cleanup
E. test      — test ekleme  → /nodrat-test'e yönlendir
F. research  — araştırma, kod yazma yok, raporla
G. devops    — deploy / monitoring
```

### 1.2 Kapsam doğrulama

```text
- Bu istek mevcut milestone içinde mi?
  → Değilse: "Bu MVP-X'e ait, şu an MVP-Y. Backlog'a alalım mı?"

- MVP-1 cut-list dışı feature mi? (docs/strategy/risk-register.md §4)
  → Cut-list OUT listesindeyse REDDET

- Pricing/tier ihlali var mı?
  → Free user'a Pro feature açılıyorsa REDDET

- Legal/compliance ihlali var mı? (docs/legal/*)
  → PII redaction bypass, paywall, robots.txt → REDDET
```

### 1.3 İlgili doküman taraması

Her istek için minimum:
- INDEX.md
- wiki/index.md (mevcut decision/entity/concept'ler — duplicate önle)
- wiki/sources/<ilgili>.md (varsa kaynak özetleri)
- docs/product/prd.md (ilgili faz)
- docs/product/information-architecture.md
- docs/strategy/risk-register.md §4

Feature işiyse + docs/engineering/* + docs/design/*
Veri işliyse + docs/legal/ropa.md + docs/legal/privacy-policy.md
Pricing/quota + docs/strategy/pricing-strategy.md

### 1.4 Yapılandırılmış özet

```yaml
intent: feature | bugfix | docs | refactor | test | research | devops
title: "<≤70 char>"
phase: faz-0..6 | cross-cutting
mvp_scope: mvp-1 | mvp-2 | mvp-3 | backlog
relevant_docs: [paths]
acceptance_criteria: [test edilebilir]
risks: [Risk Register IDs]
out_of_scope: [yapılmayacaklar]
```

---

## Aşama 2 — GitHub procedure (ZORUNLU)

### 2.1 Issue açma

Hiçbir değişiklik issue olmadan başlamaz.

```bash
gh issue create \
  --title "<title>" \
  --body "<structured body>" \
  --label "<labels>" \
  --milestone "<milestone>"
```

Issue body:
```markdown
## Hedef
<2-3 cümle>

## Kapsam
- 

## Doküman referansları
- docs/...

## Kabul kriterleri
- [ ] 

## Out of scope
- 

## Risk / Bağımlılık
- Bağımlı issue: #
- Risk Register: R-
```

### 2.2 Branch

```bash
git checkout main && git pull --ff-only
git checkout -b <prefix>/<issue-no>-<short-desc>

# Prefix:
# feature/  fix/  docs/  refactor/  test/  chore/
```

### 2.3 Commit konvansiyonu

```text
<type>(<scope>): <kısa açıklama>

<opsiyonel uzun açıklama>

Refs: #<issue-no>
```

```text
type:  feat | fix | docs | refactor | test | chore | perf
scope: api | web | worker | db | infra | docs | rag | crawler
```

### 2.4 PR

```bash
git push -u origin <branch>
gh pr create --title "<title>" --body "Closes #<N>" --base main
```

PR body PR template'i kullanır (.github/pull_request_template.md):
- Doküman uyumu checklist
- Test checklist
- Anti-pattern checklist

### 2.5 Merge

```text
- Self-review zorunlu
- "Closes #N" otomatik issue kapatır
- gh pr merge --squash --delete-branch
```

---

## Aşama 3 — Geliştirme

### 3.1 Anti-patternler (HARD STOP)

🛑 PII redaction'ı atlama
🛑 LLM provider'a kullanıcı email/IP/account ID gönderme
🛑 Robots.txt disallow path'i kazıma
🛑 Paywall arkası kaynak ekleme
🛑 Tam haber metnini son kullanıcıya gösterme
🛑 25 kelimeden uzun direct quote (FSEK)
🛑 Halüsinasyon prompt rule'larını atlama
🛑 Veri yetersizliğinde içerik üretme
🛑 18 yaş gate'i bypass
🛑 Provider key hardcode / log
🛑 SQL injection (parameterized query atlamak)
🛑 Auth check'siz endpoint
🛑 Free tier'a Pro feature açma
🛑 Migration backward-incompatible
🛑 Feature branch'inde wiki/ dosyasına yazma (CLAUDE.md §1.3 ihlali)
   → TODO notu tut; merge sonrası ayrı wiki/<slug> PR aç
🛑 docs/ değişikliği sonrası /wiki-ingest atlamak
   → Yeni karar/persona/kavram ortaya çıktıysa wiki ingest gerek

Bunlardan birini fark edersen DURDUR + kullanıcıya bildir.

### 3.2 Stack lock-in

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
✅ Premium LLM: Claude Haiku 4.5 (Pro+)
✅ Embedding: NIM bge-m3 + local fallback
```

Bu listeden sapma kullanıcı onayı gerektirir.

### 3.3 Doküman güncelleme zorunluluğu

```text
- Yeni endpoint     → docs/engineering/api-contracts.md
- Yeni tablo        → docs/engineering/data-model.md
- Yeni prompt       → docs/engineering/prompt-contracts.md
- Yeni sayfa        → docs/design/ux-wireframes.md + IA
- Pricing değişimi  → docs/strategy/pricing-strategy.md
- Yeni risk         → docs/strategy/risk-register.md
- Yeni locked karar → docs/* + INDEX.md §4 + AYRI PR /wiki-ingest
- Kaynak v0.X bumpı → AYRI PR /wiki-ingest <path> (wiki güncel kalsın)
```

> **Wiki disiplin:** Bu PR feature/fix içeriyorsa wiki yazma. Merge sonrası ayrı `wiki/<slug>` PR aç + `/wiki-ingest` çalıştır. Paralel agent worktree'lerinde write conflict önleme (CLAUDE.md §1.3).

---

## Aşama 4 — Tamamlama

### 4.1 Definition of Done

```text
[ ] Kabul kriterleri karşılandı
[ ] Test'ler yeşil (CI)
[ ] Self-review yapıldı
[ ] PR açıldı, issue link
[ ] Doküman güncellendi (gerekiyorsa)
[ ] Anti-pattern kontrol
[ ] Smoke test yapıldı
[ ] Wiki ingest gerekli mi değerlendirildi (docs/ değiştiyse veya
    yeni locked karar/persona/kavram çıktıysa) → ayrı PR/issue var mı?
```

### 4.2 Kullanıcıya raporlama

```text
- 1-2 cümle özet
- Issue link
- PR link
- Değişen dosya sayısı
- Manuel adım varsa NET belirt
```

---

## Hızlı şablonlar

### Yeni feature
```bash
gh issue create --title "..." --label "type:feature,phase:N,mvp-1" --milestone "MVP-1 — Çalışan minimum (Faz 0+1+2+3)"
git checkout -b feature/<N>-<desc>
# geliştir
gh pr create --title "..." --body "Closes #N"
```

### Bug fix
```bash
gh issue create --title "..." --label "type:bug,priority:high"
git checkout -b fix/<N>-<desc>
# fix + regression test
gh pr create --title "..." --body "Closes #N"
```

---

## Acil durumlar

```text
- Build kırılması    : feature toggle, fix branch
- Production outage  : docs/legal/incident-response.md SEV-1
- KVKK ihlali        : DPO çağrısı + 72h timer
- Cost runaway       : provider quota cap + investigate
- Provider down      : OpenRouter/GPT-4o-mini fallback
```

---

**ZORUNLU:** Bu komutla başlayan her istek 4 aşamalı protokole uymak ZORUNDADIR. Aşama atlamak, dokümanlardan sapmak, anti-patternleri ihlal etmek = STOP + kullanıcıya açıklama.
