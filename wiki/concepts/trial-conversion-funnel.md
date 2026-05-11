---
type: concept
title: "Trial conversion funnel — 7 günlük Trial → Starter/Pro yükselme"
slug: "trial-conversion-funnel"
category: "business"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/strategy/pricing-strategy.md §4 Trial Mekanikleri"
  - "docs/strategy/success-metrics.md AARRR funnel"
tags: ["business", "conversion", "trial", "funnel", "aarrr"]
---

# Trial Conversion Funnel

> **TL;DR:** 7 günlük Trial → Free → Paid (Starter/Pro/Agency) yükselme funnel'i. Trial conversion (Trial → Free aktif) hedef %60+, paid conversion (Free → paid) hedef %5+. Aha moment 1. üretim citation deneyimi (B5 confirmed).

## Funnel Aşamaları (AARRR)

| Aşama | Hedef | Mekanizma |
|---|---|---|
| **Acquisition** | Landing → sign-up | SEO + viral X share + alpha invite |
| **Activation** | Sign-up → 1. üretim | Onboarding §3 ([[ux-wireframes-md]]) |
| **Retention (1g)** | Trial 1g returning | Email reminder + saved generations |
| **Retention (7g)** | Trial 7g engaging | WSGAU metric (North Star) |
| **Revenue** | Free → Paid | Quota nudge: "100 üretim için Starter $8" |
| **Referral** | User → viral X share | Generated post'ta "via Nodrat" footer |

## Trial Detayları

- **Süre:** 7 gün (sign-up'tan itibaren)
- **Kotalar:** 5 üretim
- **Sınırlar:** style profile yok, save 7g
- **Conversion CTA:** trial 5. günde "Free'ye geç veya Starter $8 al" email + in-app

## Aha Moment (B5 confirmed [[discovery-validation-md]])

İlk Nodrat üretiminde **citation source tweet'te link olarak görünür** ve kullanıcı "bu güvenilir, paylaşabilirim" hisseder. Aha → Activation → Retention.

## Hedef Conversion Rate'leri

| Geçiş | Hedef | MVP-1 ölçüm | Aksiyon |
|---|---|---|---|
| Landing → sign-up | %15+ | TBD | Landing redesign #299 |
| Sign-up → 1. üretim | %80+ | TBD | Onboarding hızlandırma |
| Trial → Free aktif | %60+ | TBD | Email reminder |
| Free → Starter $8 | %5+ | TBD | Quota nudge UX |
| Starter → Pro $24 | %20+ | TBD | Style profile aktivasyon |
| Pro → Agency $79 | %5+ (multi-seat) | TBD | B2B sales outreach |

## Quota Nudge Pattern

Kullanıcı Free tier'da 80% üretim quota kullanırken in-app banner:
- "Bu ay 20/25 üretim yaptın. Bir sonraki ay için Starter $8 ile 100 üretim ↑"
- Click → checkout LS MoR flow

## Anti-Pattern (kaçınılan)

- ❌ **Trial → Paid zorunlu** — kullanıcı korkutur, dropout artar
- ❌ **Credit card upfront Trial** — engel; viral loop'u öldürür
- ❌ **Pop-up upsell agresif** — UX kötü, brand zedeler

## Re-evaluation

- Trial conversion < %40 → Trial uzatma (10g) veya quota artırma (5→10)
- Free → Paid < %3 → quota nudge zayıf, in-app UX iyileştir

## İlişkiler

- [[pricing-strategy-md]] §4
- [[pricing-tier-matrix]] — tier yapısı
- [[discovery-validation-md]] — Aha moment B5 confirmed
- [[ux-wireframes-md]] — onboarding §3
- [[success-metrics-md]] — AARRR + WSGAU

## Kaynaklar

- [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) §4
