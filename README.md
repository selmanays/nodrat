# Nodrat

> Türkçe gündemi kaynaklı X içeriklerine dönüştüren editör odaklı üretim aracı.

[![Status](https://img.shields.io/badge/status-pre--MVP-orange)]()
[![Phase](https://img.shields.io/badge/phase-faz--0-yellow)]()
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
- **MVP-1 hedef süre:** 8-12 hafta
- **North Star:** WSGAU (Weekly Saved Generations per Active User)

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
```

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
Web            : https://nodrat.com (yakında)
NodratBot info : https://nodrat.com/bot (Faz 1)
```

---

**Bu repo MVP-1 öncesi hazırlık fazındadır. Public release tarihi belirsiz.**
