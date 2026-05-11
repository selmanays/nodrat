---
type: decision
title: "Geographic pricing policy — USD primary, TL display locale, LS MoR"
slug: "geographic-pricing-policy"
category: "business"
status: "locked"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/strategy/pricing-strategy.md §6 Geographic Pricing — Lemon Squeezy MoR"
  - "docs/strategy/risk-register.md R-FIN-05 USD/TRY FX exposure"
  - "INDEX.md §4 locked"
tags: ["business", "pricing", "geographic", "lemon-squeezy", "fx", "kvkk", "locked"]
---

# Geographic Pricing Policy

> **TL;DR:** USD primary fiyat (global). Türkiye kullanıcıya TL display (otomatik dönüşüm). Lemon Squeezy MoR (Merchant of Record) 30+ ülke VAT/sales tax otomatik. FX exposure (R-FIN-05) mitigation: 30-günlük TL hedge yok ama tier price USD anchor sabit.

## Karar

```text
✅ Primary currency: USD ($8 / $24 / $79)
✅ Türkiye display: TL (real-time FX × USD price)
✅ Avrupa display: EUR (~%92 of USD)
✅ Lemon Squeezy MoR: 30+ ülke VAT + sales tax otomatik kesinti
❌ TL primary değil (FX volatility riski + LS US transfer hassasiyeti)
```

## Gerekçeler

1. **FX volatility riski (R-FIN-05):** TL primary olsa USD/TRY %50 değişimi margin'i bozar; USD primary cushion var
2. **LS MoR US/global merchant** — fiat conversion otomatik; tier price USD'de sabit kalır
3. **Birden fazla pazar** — global X creator pazarı; Türkiye sadece bir segment
4. **Türkiye kullanıcı UX** — TL göstermek psikolojik bariyer düşürür ($8 = ~270₺ Mayıs 2026 kuru); ama backend USD
5. **KVKK m.9 yurt dışı transfer** — LS US transferi için ek aydınlatma (R-LGL-13)

## Display Lokalizasyon

| Pazar | Display fiyat | Conversion | Real charge |
|---|---|---|---|
| Türkiye | 270₺ / 810₺ / 2670₺ | Live USD/TRY | $8 / $24 / $79 USD |
| Avrupa | €7.40 / €22 / €73 | Static 0.92x | LS MoR otomatik EUR |
| ABD | $8 / $24 / $79 | — | $8 / $24 / $79 |
| Diğer | USD primary | — | $8 / $24 / $79 |

## Lemon Squeezy MoR İşleyişi

- LS Türkiye'de kullanıcı için VAT (KDV) otomatik kesinti yapmaz (US-based MoR, Türkiye değil)
- ABD/AB pazarda VAT/sales tax otomatik kesinti
- Nodrat tarafı: net USD revenue cüzdana düşer (LS payout)
- Aktif: 2026-05'ten itibaren (Epic #448, [[lemon-squeezy-payment-provider]])

## Re-evaluation Tetikleyicileri

| Olay | Aksiyon |
|---|---|
| USD/TRY %30+ tek günlük değişim | TL display geçici dondur (rate sabit 24h) |
| Türkiye %50+ user share | Yerel Türkiye merchant değerlendir (vergi+e-Fatura karmaşık) |
| LS MoR fee %5 → %7 | Annual plan discount + tier bump |
| AB GDPR specific data residency zorunluluğu | AB merchant ayrı (vergi danışmanı görüş) |

## Bağlantı: Vergi Mükellefiyeti

INDEX.md §4: "Tüzel kişilik: **Şahıs ticari kazanç mükellefi** (vergi danışmanı 2026-05-08 onaylı; Limited Şti. defer). Threshold: $3K MRR review / **$5K MRR plan** / **$10K MRR convert**."

LS MoR ABD'de keser → Türkiye'de Nodrat **şahıs kazancı** olarak gelir vergisi öder. e-Fatura zorunluluğu yok (B2C MoR). $10K MRR sonrası Limited Şti. dönüşüm.

## İlişkiler

- [[pricing-strategy-md]] §6
- [[pricing-tier-matrix]] — tier başına detay
- [[lemon-squeezy-payment-provider]] — MoR
- [[margin-70-target]] — FX cushion gerekçesi
- [[kvkk-aydinlatma-md]] — KVKK m.9 yurt dışı transfer
- [[risk-source-fragility]] — R-FIN-05 FX exposure linki

## Kaynaklar

- [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) §6
- INDEX.md §4 (locked decisions)
