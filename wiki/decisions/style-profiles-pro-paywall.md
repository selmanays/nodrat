---
type: decision
title: "Faz 5 stil profili — Pro+ paywall + slot quota (server-side enforced)"
slug: "style-profiles-pro-paywall"
category: "scope"
status: "live"
created: "2026-05-09"
updated: "2026-05-09"
sources:
  - "docs/strategy/pricing-strategy.md§2"
  - "docs/product/prd.md§5"
  - "docs/engineering/data-model.md§8.1"
tags: [faz-5, paywall, pro-tier, server-side, locked]
aliases: ["style profile paywall", "Faz 5 paywall"]
---

# Faz 5 stil profili — Pro+ paywall + slot quota (server-side enforced)

> **TL;DR:** Stil profili Pro+ tier feature'ıdır. Server-side enforcement: `plan.features.style_profiles=true` Free/Starter'da false → 402. Slot quota Pro=3, Agency=10. Frontend paywall görselleştirir ama gerçek kontrol API'da; client-side bypass mümkün değil.

## Karar

| Tier | features.style_profiles | features.style_profiles_slots |
|---|---|---|
| Free | false | 0 |
| Starter | false | 0 |
| Pro | **true** | **3** |
| Agency (3/5/10) | **true** | **10** |

Plan seed migration `20260509_0400` ile gelir; `/admin/plans` üzerinden değiştirilemez (features kolonu admin UI'da read-only — DB migration ile değişir, audit trail için).

## Server-side enforcement noktaları

| Endpoint | Check |
|---|---|
| `POST /app/style-profiles` | `_check_paywall(features)` + slot quota |
| `POST /app/style-profiles/{id}/samples` | profile ownership (paywall dolaylı) |
| `POST /app/generate` (style_profile_id verilirse) | `_resolve_style_profile` → 402 STYLE_PROFILES_REQUIRES_PRO |

Hiçbir endpoint client-side flag'e güvenmez. Admin tier'ı override edebilir mi → hayır, super_admin için ayrı bypass yok (test hesabıyla Pro plana abone olur).

## Alternatifler

| Seçenek | Niye değil |
|---|---|
| Free user'a 1 slot demo | Cost (DeepSeek call user başı), conversion fonksiyonel olmadan stalemate |
| Starter'a 1 slot eklenmesi | Pricing v0.2 §2 Starter generic mass-market; stil profili niş Pro use-case |
| User.tier üzerinden kontrol | tier 'free/starter/pro/agency_seat'; subscription'a güvenmek daha sağlam (downgrade race) |

## Why locked

- 2026-05-09'da implementation server-side gate ile gönderildi, client-side bypass yok
- Plan features.style_profiles boolean + slots integer olarak data-model.md §8 ile uyumlu
- Pricing strategy §2.5 Pro tier'da "stil profili" upsell olarak listeli

## Sonuç

- Free/Starter user `/app/style-profiles` aç → ProAccessGate render
- Free/Starter user `style_profile_id` ile generate → 402 (UI state'te zaten bypass yok ama API koruyor)
- Pro user 3 profile'a kadar yaratır; 4. atanması için 409 STYLE_PROFILES_SLOT_FULL (mevcut sil veya upgrade)

## Kapsam dışı

- A/B test retention impact ölçümü — telemetry layer ayrı (#52 PRD §5.7 son madde, launch sonrası)
- "Junior/onay rolü" stil profili (research-findings.md B2 öneriyor) — Faz 7+
- Bulk CSV import — endpoint var (`csv_import` source_type) ama dedicated upload akışı yok

## İlişkiler

- Bağımlı: [[lemon-squeezy-payment-provider]] — Pro subscription gate
- Servis: [[style-profile-system]]
- Concept: [[style-analyzer-prompt]]
- Plan seed: migration `20260509_0400_lemon_squeezy_billing_schema`

## Kaynaklar

- [docs/strategy/pricing-strategy.md §2](../../docs/strategy/pricing-strategy.md)
- [docs/product/prd.md §5](../../docs/product/prd.md)
- [docs/engineering/data-model.md §8.1 plans.features](../../docs/engineering/data-model.md)
- PR #512 (`api/style_profiles.py` `_check_paywall`, `_check_slot_quota`)
- PR #512 (`api/app_generate.py` `_resolve_style_profile`)
