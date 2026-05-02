# Nodrat

> Türkçe gündemi kaynaklı X içeriklerine dönüştüren editör odaklı üretim aracı.

[![Status](https://img.shields.io/badge/status-MVP--1%20alpha--ready-green)]()
[![Phase](https://img.shields.io/badge/phase-faz--3%20delivered-brightgreen)]()
[![Production](https://img.shields.io/badge/prod-nodrat.com-blue)](https://nodrat.com)
[![Privacy](https://img.shields.io/badge/repo-private-red)]()

---

## Pozisyon

**Nodrat bir haber yayıncısı değildir.** Hizmet, kullanıcının içerik üretim ve araştırma sürecini destekleyen bir yazılım aracıdır. ChatGPT'nin yerine değil, yanında — gündem için özel araç.

---

## Hızlı bakış

- **Birincil hedef:** Bağımsız politik creator (P1A — 30K-300K X takipçisi)
- **İkincil hedef:** SoMe ajansları (P1B — 3-8 marka, multi-seat şart)
- **Pricing:** Trial / Free / Starter 249 TL / Pro 749 TL / Agency 2.499 TL
- **Stack:** Next.js + FastAPI + PostgreSQL+pgvector + Redis + MinIO + Caddy
- **MVP-1 durumu:** ✅ alpha-ready (97% — 55/57 issue closed, 42 PR merged)
- **North Star:** WSGAU (Weekly Saved Generations per Active User)

---

## MVP-1 durumu

```text
✅ Faz 0 (altyapı)        — 100% (Docker, Auth, NIM, Sentry, sops, CI/CD)
✅ Faz 1 (source pipeline) — 100% (RSS, robots, scraper, cleaning, DLQ, Beat)
✅ Faz 2 (RAG)            — 100% (chunker, embedding, vector search, clustering)
✅ Faz 3 (user generation) — 100% (planner, content, dashboard, history)
✅ Cross-cutting          — 100% (4 takedown forms, 8 legal pages, admin UIs)
🟡 #41  B2 backup         — blocked-external (B2 hesap gerekli)
🟡 #68  Resend email      — blocked-external (Resend API key gerekli)
```

Sürüm geçmişi: [CHANGELOG.md](CHANGELOG.md)

---

## Doküman haritası

Tüm proje dokümantasyonu için: **[INDEX.md](INDEX.md)**

```
INDEX.md                                    ← navigasyon hub
docs/
├── product/        (PRD + IA — kanonik)
├── strategy/       (discovery, competitive, pricing, metrics, risk, economics)
├── engineering/    (architecture, data-model, api, prompt, threat)
├── design/         (UX wireframes, design system)
├── legal/          (compliance, ToS, privacy, KVKK, ROPA, DPO, incident)
└── validation/     (research findings)

apps/                                       ← uygulama kodu (Faz 0+)
├── api/            FastAPI + Celery + Alembic
└── web/            Next.js 14 + shadcn/ui

infra/                                      ← deployment
├── Caddyfile
└── postgres/init.sql

packages/                                   ← paylaşılan paketler
└── shared-types/   Pydantic ↔ TS codegen (gelecek)
```

---

## Hızlı başlangıç (local dev)

```bash
# 1. Env
cp .env.example .env
# .env'yi düzenle (provider key'leri vs.)

# 2. Tüm stack'i ayağa kaldır
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 3. Migration
docker compose exec api alembic upgrade head

# 4. Erişim
# Web:           http://localhost:3000
# API docs:      http://localhost:8000/docs (sadece dev)
# MinIO console: http://localhost:9101
# Postgres:      localhost:5433
```

Detaylı katkı rehberi: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Production smoke test

```bash
# 18 sayfa + 3 admin endpoint + health endpoint kontrol
./infra/smoke-test.sh

# Custom base URL
SMOKE_BASE=https://staging.nodrat.com ./infra/smoke-test.sh
```

Manuel deployment adımları: [docs/operations/deployment-manual-steps.md](docs/operations/deployment-manual-steps.md)

---

## Geliştirme akışı

Bu repo **GitHub-driven** çalışır. Tüm iş:

1. **Issue açılır** → milestone + label
2. **Branch** → `feature/<issue-no>-<desc>` veya `fix/...`
3. **Commit** → `feat(scope): description` + `Refs: #N`
4. **PR** → `Closes #N` + doküman uyumu checklist
5. **Merge** → squash + branch delete

Detay: [.claude/skills/nodrat-dev/SKILL.md](.claude/skills/nodrat-dev/SKILL.md)

---

## Test stratejisi

```text
Unit            : pytest, vitest
Integration     : pytest + testcontainers
E2E             : Playwright
LLM Evaluation  : golden test set + LLM-as-judge
                  Halüsinasyon < %2, citation %100
```

Detay: [.claude/skills/nodrat-test/SKILL.md](.claude/skills/nodrat-test/SKILL.md)

---

## Faz haritası

| Faz | İçerik | Hedef süre |
|---|---|---|
| 0 | Altyapı (Docker, DB, Redis, MinIO, Auth, Provider abstraction) | 2 hafta |
| 1 | RSS source pipeline + scraping + media | 3 hafta |
| 2 | RAG (embedding, clustering, agenda cards) | 2-3 hafta |
| 3 | User dashboard + content generation | 2-3 hafta |
| 4 | Visual intelligence (görsel etiketleme) | MVP-3+ |
| 5 | Stil profili (Pro tier upsell) | MVP-3+ |
| 6 | Plan + ödeme + e-Arşiv | MVP-3 launch |

---

## Çekirdek kararlar (locked)

```text
✅ Default LLM:       DeepSeek V3 ($0.27/$1.10 per 1M)
✅ Premium LLM:       Claude Haiku 4.5 (Pro+ tier)
✅ Embedding:         NIM bge-m3 (free) + local fallback
✅ Tam metin:         Internal RAG'de, kullanıcıya gösterme
✅ Direct quote:      25 kelime hard cap (FSEK)
✅ Robots.txt:        Sıfır tolerans, admin override yok
✅ Yaş gate:          18+ (16+ değil)
✅ PII redaction:     LLM çağrısı öncesi şart (avukat eklemesi)
✅ Multi-seat agency: MUST (yapısal şart)
✅ Pozisyon:          "Editör odaklı üretim aracı"
```

---

## Hukuki durum

```text
✅ Avukat ön-görüş tamamlandı (docs/legal/opinion-integration.md)
🟡 ToS / Privacy / KVKK Aydınlatma → DRAFT (avukat final review bekliyor)
🟡 DPO/KVKK uzmanı → outsource sözleşme şablonu hazır
🟡 Şirket kuruluşu → Faz 6 öncesi (backlog)
🟡 Provider DPA imzaları → Faz 0 sonu hedef
```

---

## Lisans

Private repo. Tüm hakları saklıdır.

---

## İletişim

```text
Founder        : Selman Ay
E-posta        : legal@nodrat.com
DPO            : dpo@nodrat.com
Web            : https://nodrat.com (live, alpha)
NodratBot info : https://nodrat.com/bot
```

---

**Durum:** MVP-1 alpha-ready · production deployed · alpha kullanıcı kabulü için hazır.
