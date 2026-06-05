# Katkı Rehberi

Bu doküman, Nodrat projesine katkı yapanlar için **GitHub-driven workflow**'u açıklar.

> Tek patikamız GitHub. Her değişiklik issue → branch → commit → PR → merge döngüsünden geçer.

---

## 0. Önce oku

Yeni katkı yapmadan önce şunları oku:

1. [INDEX.md](INDEX.md) — doküman navigasyon hub
2. [docs/product/prd.md](docs/product/prd.md) — kanonik gereksinim kaynağı
3. [docs/strategy/risk-register.md](docs/strategy/risk-register.md) §4 — MVP-1 cut-list (kapsam dışı)
4. [docs/legal/opinion-integration.md](docs/legal/opinion-integration.md) — avukat lock kararları
5. [.claude/skills/nodrat-dev/SKILL.md](.claude/skills/nodrat-dev/SKILL.md) — dev workflow protokolü

---

## 1. GitHub Workflow

### 1.1 Issue açılmadan kod yazılmaz

```bash
gh issue create \
  --title "Faz N — Kısa açıklama" \
  --label "type:feature,phase:N,priority:high,mvp-1" \
  --milestone "MVP-1 — Çalışan minimum (Faz 0+1+2+3)"
```

Issue body için template kullanılır (`.github/ISSUE_TEMPLATE/`).

### 1.2 Branch konvansiyonu

```bash
git checkout main
git pull --ff-only
git checkout -b <prefix>/<issue-no>-<short-desc>
```

| Prefix | Kullanım |
|---|---|
| `feature/` | Yeni özellik |
| `fix/` | Bug düzeltmesi |
| `docs/` | Doküman değişikliği |
| `refactor/` | Refactor / cleanup |
| `test/` | Test ekleme |
| `chore/` | Bakım |

### 1.3 Commit konvansiyonu

Conventional Commits + issue referansı:

```text
<type>(<scope>): <kısa açıklama>

<opsiyonel uzun açıklama>

Refs: #<issue-no>
```

Örnek:
```
feat(api): /admin/sources/{id}/test-listing endpoint

PRD §1.4 selector test ekranı için backend.

Refs: #12
```

### 1.4 Pull Request

```bash
git push -u origin <branch>
gh pr create --title "..." --body "Closes #<N>"
```

PR template otomatik yüklenir (`.github/pull_request_template.md`):
- Doküman uyumu checklist
- Test checklist
- Anti-pattern checklist

### 1.5 Self-review + merge

```bash
# CI yeşil olmadan merge edilemez
gh pr view --web
gh pr merge --squash --delete-branch
```

---

## 2. Anti-Patternler (HARD STOP)

Bu davranışlardan herhangi biri PR rejected:

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
🛑 Provider key'i koda hardcode etme veya log'a yazma
🛑 SQL injection / parameterized query atlamak
🛑 Auth check olmayan endpoint
🛑 Free tier'a Pro feature açma (server-side check yok)
🛑 Migration backward-incompatible (zero-downtime kuralı)
```

---

## 2.5 Mimari Boundary & Data Safety (HARD STOP)

**Modular monolith düzeni** (detay: [`wiki/topics/architecture-final-state-2026-05.md`](wiki/topics/architecture-final-state-2026-05.md) + [`wiki/decisions/modular-monolith-boundary.md`](wiki/decisions/modular-monolith-boundary.md)):

```text
app/modules/<domain>/   Domain ownership (kernel / middle / business)
app/shared/             Seviye-0 primitive / leaf (I/O-suz; modules/core/api/models import EDEMEZ)
app/api/                Cross-domain BFF / aggregator (birden çok domain import eder)
app/core/               model-free; retrieval saf facade + core/_retrieval_*
Model ownership         app/modules/<x>/models.py  (flat exception: FailedJob + AdminAuditLog @ app/models/job.py)
```

**import-linter 16 contract = CI hard-gate.** Yasak yönler: `core→modules` · `shared→{modules,core,api,models}` · `domain→ops` · `accounts→business` · `rag→{crawler,generations}` · `sources→other-domain`. **CI otoriter** — local `lint-imports` cache yanıltabilir.

**🛑 Data-safety HARD STOP — maintainer/kullanıcı onayı şart:**

```text
🛑 schema / migration değişikliği (backward-incompatible = zero-downtime ihlali; alembic check strict gate aktif)
🛑 DB-data mutation (toplu UPDATE / DELETE / truncate)
🛑 embedding / RAG-index / vector / chunk mutation (rechunk / reembed / toplu-backfill)
🛑 manuel task trigger / production data touch
```

→ Bu durumlarda: **DUR**, mini-plan + açık onay iste. (Doğal idempotent backfill normal.)

**High-caution repo konuları** (uygulama DEĞİL — karar gerektirir, decision-backlog): LICENSE · repo visibility · branch protection · SECURITY policy · releases/tags.

---

## 3. Stack Lock

Aşağıdaki stack kilit, sapma kullanıcı onayı gerektirir:

```text
✅ Frontend  : Next.js 14 + shadcn/ui + Tailwind
✅ Backend   : FastAPI + Pydantic v2
✅ Worker    : Celery 5
✅ DB        : PostgreSQL 16 + pgvector
✅ Cache     : Redis 7
✅ Storage   : MinIO
✅ Proxy     : Caddy 2
✅ Container : Docker Compose
✅ Default LLM     : DeepSeek V3
✅ Premium LLM     : Claude Haiku 4.5 (Pro+ tier)
✅ Embedding       : NIM bge-m3 + local fallback
```

---

## 4. Local Development

### 4.1 Önkoşullar

- Docker + Docker Compose v2
- Python 3.12 (lokal lint/test için)
- Node 20+ (lokal dev için)
- gh CLI

### 4.2 İlk kurulum

```bash
# 1. Repo clone
git clone https://github.com/selmanays/nodrat
cd nodrat

# 2. Env dosyası
cp .env.example .env
# .env'yi düzenle (provider key'leri vs.)

# 3. Tüm servisleri ayağa kaldır
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 4. Migration çalıştır
docker compose exec api alembic upgrade head

# 5. Erişim
# Web: http://localhost:3000
# API: http://localhost:8000/docs (sadece dev)
# MinIO Console: http://localhost:9101 (admin: minio_admin)
# Postgres: localhost:5433
# Redis:    localhost:6380
```

### 4.3 Lokal test

API:
```bash
cd apps/api
pip install -e ".[dev]"
ruff check .
mypy app
pytest tests/unit/ -v
```

Web:
```bash
cd apps/web
npm install
npm run lint
npm run type-check
npm test  # vitest gelecek
```

---

## 5. VPS İzolasyon Kuralları

⚠️ **VPS'te başka uygulamalar çalışıyor.** Bu repo'da:

- Tüm container/volume/network adları `nodrat-` / `nodrat_` prefix'li
- Default port'lar (80, 443, 5432, 6379, 9000) **kullanılmıyor**
- Postgres → 5433, Redis → 6380, MinIO → 9100/9101, Caddy → 8080/8443
- Production'da Postgres/Redis/MinIO host port'ları **YORUM YAPILIR** (sadece internal)

---

## 6. Doküman Uyumu

PR'ın doküman uyumu zorunlu:

| Değişiklik | Güncellenen doküman |
|---|---|
| Yeni endpoint | `docs/engineering/api-contracts.md` |
| Yeni tablo | `docs/engineering/data-model.md` |
| Yeni prompt | `docs/engineering/prompt-contracts.md` |
| Yeni sayfa | `docs/design/ux-wireframes.md` + IA |
| Pricing değişimi | `docs/strategy/pricing-strategy.md` |
| Yeni risk | `docs/strategy/risk-register.md` |

---

## 7. Skill Kullanımı (Claude Code ile çalışıyorsanız)

```text
/nodrat-dev <istek>   — geliştirme akışı (4 aşamalı protokol)
/nodrat-test <istek>  — test ve kalite kontrol
```

Detay: `.claude/skills/nodrat-dev/SKILL.md`

---

## 8. İletişim

```text
GitHub: https://github.com/selmanays/nodrat
E-posta: legal@nodrat.com
```
