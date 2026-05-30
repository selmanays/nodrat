# Nodrat

> Türkçe gündemi kaynaklı X içeriklerine dönüştüren editör odaklı üretim aracı.

[![Production](https://img.shields.io/badge/prod-nodrat.com-blue)](https://nodrat.com)
[![Architecture](https://img.shields.io/badge/architecture-modular%20monolith-0E8A16)](wiki/topics/architecture-final-state-2026-05.md)
[![Boundary](https://img.shields.io/badge/import--linter-16%20contracts%2C%200%20broken-blue)]()

---

## Pozisyon

**Nodrat bir haber yayıncısı değildir.** Hizmet, kullanıcının içerik üretim ve araştırma sürecini destekleyen bir yazılım aracıdır. ChatGPT'nin yerine değil, yanında — gündem için özel araç.

---

## Hızlı bakış

- **Birincil hedef:** Bağımsız politik creator (P1A — 30K-300K X takipçisi)
- **İkincil hedef:** SoMe ajansları (P1B — 3-8 marka, multi-seat şart)
- **Pricing:** Trial / Free / Starter 249 TL / Pro 749 TL / Agency 2.499 TL
- **Stack:** Next.js + FastAPI + PostgreSQL+pgvector + Redis + MinIO + NIM Llama 4 Maverick (VLM) + Caddy
- **MVP-1 durumu:** ✅ delivered (production'da, MVP-1.1/1.2/1.3/1.4 tamamlandı)
- **North Star:** WSGAU (Weekly Saved Generations per Active User)

---

## Milestone durumu

```text
✅ MVP-1    (Faz 0+1+2+3)          — production (https://nodrat.com)
✅ MVP-1.1  Production Hardening   — eval framework, citation, reranker, RAPTOR
✅ MVP-1.2  Admin Settings Panel   — runtime-tunable setting + LLM prompt
✅ MVP-1.3  UI Modernization       — shadcn radix-luma
✅ MVP-1.4  Image Pipeline (VLM)   — process & discard, site profile sistemi
✅ MVP-1.5  Infra Migration        — Contabo VPS 40 + Object Storage
✅ MVP-1.6/1.7  Admin UI Polish + SFT Foundation
✅ MVP-2    Kullanılabilir SaaS
✅ Modular Monolith v1/v2/v3 (#18/#19/#20) — domain-based mimari; retrieval
                                    god-file 1926→96 facade; 16 import-linter
                                    contract (CI-gate). → wiki Architecture Final State
🔄 MVP-1.8  RAG Quality (Perplexity-style) — devam ediyor (#16)
⏳ MVP-3    Paid Launch             — billing, multi-seat, premium LLM
```

Güncel mimari durum: [wiki/topics/architecture-final-state-2026-05.md](wiki/topics/architecture-final-state-2026-05.md)

Sürüm geçmişi: [CHANGELOG.md](CHANGELOG.md)

---

## Doküman haritası

Tüm proje dokümantasyonu için: **[INDEX.md](INDEX.md)**

```
INDEX.md                                    ← navigasyon hub (kanonik doküman indeksi)
CLAUDE.md                                    ← LLM iş akışı + proje sözleşmesi
docs/                                        ← KAYNAK katmanı (immutable kanonik)
├── product/        (PRD + IA)
├── strategy/       (discovery, competitive, pricing, metrics, risk, economics)
├── engineering/    (architecture, data-model, api, prompt, threat)
├── design/         (UX wireframes, design system)
├── legal/          (compliance, ToS, privacy, KVKK, ROPA, DPO, incident)
└── validation/     (research findings)

wiki/                                        ← LLM-sürdürülen "ikinci beyin"
├── topics/architecture-final-state-2026-05.md      ← güncel mimari durum
├── plans/modular-monolith-transition-master-plan.md
└── entities/ concepts/ topics/ decisions/ sources/

apps/                                        ← uygulama kodu
├── api/            FastAPI + Celery + Alembic — domain-based modular monolith
│                   (modules/ + shared/ + api/ aggregator + core/)
└── web/            Next.js + shadcn/ui

infra/ (Caddyfile, postgres) · packages/ (shared-types)
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

License: Not yet specified. Until a `LICENSE` file is added, all rights are reserved by default (GitHub default — no reuse or distribution rights are granted). Lisans/konumlandırma kararı beklemede.

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

**Durum:** production deployed ([nodrat.com](https://nodrat.com)) · domain-based modular monolith mimari (v1/v2/v3 complete — #18/#19/#20) · MVP-1.8 RAG quality ongoing · güncel mimari: [Architecture Final State](wiki/topics/architecture-final-state-2026-05.md).
