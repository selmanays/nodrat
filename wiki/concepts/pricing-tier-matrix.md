---
type: concept
title: "Pricing tier matrisi — Trial / Free / Starter / Pro / Agency"
slug: "pricing-tier-matrix"
category: "business"
status: "live"
created: "2026-05-11"
updated: "2026-05-12"
sources:
  - "docs/strategy/pricing-strategy.md §2 Tier Yapısı, §3 Karşılaştırma Matrisi"
tags: ["business", "pricing", "tier", "monetization"]
---

# Pricing Tier Matrisi

> **TL;DR:** 5 tier: Trial / Free / Starter $8 / Pro $24 / Agency $79. USD primary, TL display locale. Lemon Squeezy MoR (Merchant of Record). Margin hedef ≥ %70 paid tier. Agency multi-seat MUST.
>
> **MVP-1 reality (#720, 2026-05-12):** Tüm tier'lar şu an **DeepSeek V4 Flash** kullanıyor. Pro / Agency için planlanan **Claude Haiku 4.5** Faz 2'de devreye alınacak — Anthropic provider adapter henüz yazılmadı ([[anthropic-adapter-planned]]). UI/pricing sayfası "Pro+ tier'larda Premium LLM Faz 2'de" notu ile bunu net iletiyor.

## Matris

| Özellik | Trial | Free | Starter $8 | Pro $24 | Agency $79 |
|---|---|---|---|---|---|
| Aylık üretim | 5 | 25 | 100 | 500 | 2500 |
| Seat sayısı | 1 | 1 | 1 | 1 | **5 (+$10/seat)** |
| LLM (MVP-1 reality) | DeepSeek V4 | DeepSeek V4 | DeepSeek V4 | DeepSeek V4 | DeepSeek V4 |
| LLM (planlanan, Faz 2) | DeepSeek V4 | DeepSeek V4 | DeepSeek V4 | **Claude Haiku 4.5** | DeepSeek + **Claude Haiku** |
| Style profile | ❌ | ❌ | 1 | 5 | **Sınırsız** |
| Save generations | 30g | 30g | 90g | 1y | Sınırsız |
| Citation/Source | ✅ | ✅ | ✅ | ✅ | ✅ |
| Saved tags | ❌ | ❌ | ✅ | ✅ | ✅ |
| API access | ❌ | ❌ | ❌ | ❌ | ✅ Faz 6 |
| Priority support | ❌ | ❌ | ❌ | ✅ email | ✅ slack |
| KVKK DPO contact | Auto | Auto | Auto | Email | **Dedicated** |

## Tier Karar Mantığı

### Trial (7 gün)
- Conversion funnel öğesi; sign-up barrier düşük
- 5 üretim "aha moment" deneyimi sağlar ([[discovery-validation-md]])

### Free
- Long-tail engagement
- Sürdürülebilir cost: ~$0.005/üretim × 25 = $0.13/ay/user → bedel altı (LTV negatif)
- Sebep: viral loop + brand awareness + Pro upsell pipeline

### Starter $8 (entry paid)
- Çoğu birey content creator için yeterli
- DeepSeek-only, basit özellikler
- Pro'ya doğal yükselme (style profile, save 1y)

### Pro $24 (ana revenue driver)
- Birincil persona ([[persona-p1a-politik-creator]]) için
- Claude Haiku premium ([[claude-haiku-premium-llm]]) — **MVP-1'de pending** ([[anthropic-adapter-planned]]), Faz 2'de devreye alınacak; şu an Pro tier de DeepSeek V4 Flash alıyor
- 500 üretim — yoğun creator için (15-20/gün)

### Agency $79 (multi-seat MUST)
- İkincil persona ([[persona-p1b-ajans]]) için
- 5 seat + dedicated DPO
- Anti-cannibalization: Pro × 5 = $120 → Agency $79 cazip

## Margin Hedef (≥ %70)

| Tier | Aylık fiyat | LS MoR fee ~%5+50¢ | Variable cost | Net margin |
|---|---|---|---|---|
| Starter $8 | $8 | -$0.90 | -$0.50 (DeepSeek × 100) | $6.60 (83%) ✅ |
| Pro $24 | $24 | -$1.70 | -$3.00 (DeepSeek + Haiku) | $19.30 (80%) ✅ |
| Agency $79 | $79 | -$4.45 | -$12.00 (Haiku × 2500) | $62.55 (79%) ✅ |

## Geographic Pricing (LS MoR)

USD primary (global), TL display locale (Türkiye). Lemon Squeezy MoR otomatik dönüşüm:
- Türkiye fiyat: 24×TL parite (FX exposure R-FIN-05)
- US fiyat: $24 sabit
- AB fiyat: €22 (LS MoR 30 ülke VAT yönetim)

## İlişkiler

- [[pricing-strategy-md]] §2 + §3
- [[persona-p1a-politik-creator]] — Pro
- [[persona-p1b-ajans]] — Agency multi-seat
- [[claude-haiku-premium-llm]] — Pro+ tier (planned, Faz 2)
- [[anthropic-adapter-planned]] — Faz 2 implementation issue (#720)
- [[lemon-squeezy-payment-provider]] — MoR
- [[unit-economics-md]] — margin recalc

## Kaynaklar

- [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) §2, §3
