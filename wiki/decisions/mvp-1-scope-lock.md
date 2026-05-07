---
type: decision
title: "MVP-1 scope lock (12 sayfa / 12 tablo / ~20 endpoint)"
slug: "mvp-1-scope-lock"
status: "locked"
decided_on: "2026-05-01"
decided_by: "founder"
created: "2026-05-07"
updated: "2026-05-08"
sources:
  - "docs/strategy/risk-register.md§4.9"
  - "docs/strategy/risk-register.md§4"
  - "docs/strategy/risk-register.md§5.1"
  - "INDEX.md§5b"
tags: ["locked-decision", "scope", "mvp", "cut-list"]
aliases: ["mvp-1-scope", "mvp-cut-list-decision"]
---

# MVP-1 scope lock

> **Karar:** MVP-1 minimum kabul edilebilir ürün PRD'nin 6 fazlı geniş kapsamından şu sınırlara çekilir: **12 sayfa, 12 tablo, ~20 API endpoint**. LLM olarak sadece DeepSeek (default native API + `deepseek-v4-flash`, NIM fallback); embedding olarak NIM bge-m3 + local fallback. Faz 4 (görsel zeka), Faz 5 (stil profili), Faz 6 (ödeme) MVP-1'de **YOK**.
> **Durum:** locked. MVP-1 production'a alındı (https://nodrat.com); bu karar artık tarihsel referans + scope-creep'e karşı bekçi.
> **Tarih:** 2026-05-01 (risk-register.md v0.1).

## Bağlam

R-PEO-01 (solo founder bandwidth, skor 12) ve genel kapsam riski:

```text
PRD 6 faz × ~150 alt-gereksinim
→ Build edilirse ~10–14 ay (gerçekçi)
→ MVP-1 kapsamı 2–3 ay olmalı
```

Cut-list bu hesabı zorlamak için var. Her PRD bölümü için **IN / OUT / LATER** kararı net. Bu disiplin olmadan solo founder + AI agent kombinasyonu sürdürülemez.

## MVP-1 final scope (§4.9 birebir)

### Sayfalar (12)

```
/, /login, /register, /forgot-password, /verify-email
/app/dashboard, /app/generate/new, /app/generate/{id}/result
/app/generations, /app/saved, /app/settings/profile
/admin/sources, /admin/articles, /admin/queue/overview
```

### Entity'ler (12 tablo)

```
users, sessions, sources, source_configs, articles,
article_images, article_chunks, event_clusters,
agenda_cards, generations, usage_events, crawler_jobs
```

### API endpoint'leri (~20)

```
/auth/* (5), /admin/sources/* (4), /admin/articles/* (3),
/admin/queue/* (2), /app/generate (1), /app/generations/* (3)
/health, /readiness
```

### Provider

- **LLM:** [[deepseek]] only.
- **Embedding:** [[nim-bge-m3]] (local fallback hazır ama default değil).

### Tahmini geliştirme süresi

```
Solo founder + AI agent: 8-12 hafta full-time
Standart takım (3 kişi): 4-6 hafta
```

## Faz × IN/OUT özeti

| Faz | IN (MVP-1) | OUT (LATER) |
|---|---|---|
| **Faz 0 — Altyapı** | Docker Compose, Postgres + pgvector + Redis + MinIO, basit auth (2FA YOK), provider abstraction (DeepSeek + bge-m3 NIM), healthcheck | Multiple LLM, rerank, vision, local LLM, k8s, Prometheus |
| **Faz 1 — Kaynak + kazıma** | RSS only (max 3 kaynak), HTTP-only crawler (no JS-render), readability + selector extraction, dedup canonical+hash, image process & discard (#304) | Category page, manual URL, Playwright, selector test UI tam, görsel bytes storage |
| **Faz 2 — RAG / agenda** | Chunking basic, embedding NIM bge-m3, ivfflat index, semantic search, agenda card generator, current mode (24-48h) | Weekly, archive, comparison mode, rerank, importance score |
| **Faz 3 — Dashboard** | Login/register, generate akışı (current only), X post (single), generation history + save, basic settings, quota 10/ay free | X thread, analysis/headline/calendar/briefing, tone variations, regenerate, trial flow |
| **Faz 4 — Görsel zeka** | YOK | TÜMÜ — MVP-3+ veya iptal |
| **Faz 5 — Stil profili** | YOK | TÜMÜ — MVP-3'te dene |
| **Faz 6 — Ödeme** | YOK | TÜMÜ — MVP-3 zorunlu |

> **Not:** MVP-1.4'te (Image Pipeline VLM) Faz 4'ün kısmı erken eklendi — process & discard mimarisi. Bu, scope creep değil; depolama maliyeti riskini sıfırlamak için pivot.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| PRD 6 faz tam build | Güçlü ürün | 10-14 ay, R-PEO-01 burnout | Reddedildi |
| MVP-1 + tüm Faz 1+2+3 | Daha tam | Hala 4-6 ay | Reddedildi |
| Daha ince MVP-1 (sadece Faz 0+1) | Hızlı launch | Üretim akışı yok = "ürün" değil | Reddedildi |
| MVP-1 + ödeme (Faz 6) | Erken revenue | Retention öncesi pricing yanlış | Reddedildi (MVP-3'e bırakıldı) |

## Sonuçlar

- **Etkilenen varlıklar:** Tüm MVP-1 stack ([[deepseek]], [[nim-bge-m3]], [[contabo-vps]], [[celery-worker]]).
- **Etkilenen kavramlar:** [[mvp-cut-list-method]] (bu kararın metodolojisi).
- **Etkilenen kararlar:** [[deepseek-default-llm]] (sadece DeepSeek), [[twenty-five-word-quote-cap]] (output kuralı MVP-1'den itibaren), [[pii-redaction-mandatory]].
- **Etkilenen topics:** [[mvp-1-scope]] (bu kararın detaylı IN/OUT envanteri), [[mvp-roadmap]] (sıradaki MVP'lere zincir).
- **Sonuç (gerçekleşen):** MVP-1 ✅ delivered, production https://nodrat.com (INDEX §5b).

## Geri alma maliyeti

Bu karar geriye dönük değiştirilemez (MVP-1 tamamlandı). Ama benzer disiplin **MVP-2 / MVP-3 / MVP-4** scope kararlarında devam ediyor:

- MVP-2 ✅ delivered 2026-05-07 (-19 hafta) — bkz. [[mvp-roadmap]].
- MVP-3 hedef 2026-11-30 (KS-2 acceptance + Faz 5/6).
- MVP-4+ planlanıyor (comparison mode, Faz 4, EN dil).

## Doğrulama (post-hoc)

MVP-1 production'da olduğu için scope kararı doğrulanabilir:

| Hedef | Gerçekleşen | Durum |
|---|---|---|
| 12 sayfa | (12+ — MVP-1.1/1.2/1.3 ile genişledi: legal pages, settings panel, admin tools) | ✅ overshoot |
| 12 tablo | (12+ — ek tablolar: settings, prompts vb. MVP-1.2'de eklendi) | ✅ overshoot |
| ~20 endpoint | (50+ — INDEX §0'a göre) | ✅ overshoot |
| 8-12 hafta solo + agent | (8 hafta civarı production, sonra 1.1/1.2/1.3/1.4 hardening) | ✅ tahmin doğru |

> **Sürpriz bulgu:** Sayfa/tablo/endpoint sayıları başlangıç hedefinin üzerinde. Bu bir scope creep mi yoksa MVP-1.1/1.2/1.3 hardening fazlarında mı eklendi? **Aksiyon:** [[mvp-roadmap]]'e ek detay eklenmeli.

## İlişkiler

- **Bağlı varlıklar:** [[deepseek]], [[nim-bge-m3]], [[contabo-vps]], [[celery-worker]]
- **Bağlı kavramlar:** [[mvp-cut-list-method]], [[kill-switch]]
- **Bağlı kararlar:** [[deepseek-default-llm]], [[twenty-five-word-quote-cap]], [[pii-redaction-mandatory]]
- **Bağlı topics:** [[mvp-1-scope]], [[mvp-roadmap]]

## Kaynaklar

- [docs/strategy/risk-register.md §4.9 (MVP-1 final scope)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §4 (Cut-list Faz 0/1/2/3/4/5/6)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §5.1 (MVP-1 timeline 12 hafta)](../../docs/strategy/risk-register.md)
- [INDEX.md §5b (Milestone tablosu)](../../INDEX.md)
- [docs/product/information-architecture.md §13](../../docs/product/information-architecture.md) — Faz haritası
