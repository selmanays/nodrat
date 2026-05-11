---
type: decision
title: "Margin hedef ≥ %70 paid tier (locked)"
slug: "margin-70-target"
category: "business"
status: "locked"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/strategy/unit-economics.md §5 Margin Hesaplaması"
  - "docs/strategy/pricing-strategy.md §2 Tier Yapısı"
  - "INDEX.md §4 locked"
tags: ["business", "margin", "unit-economics", "decision", "locked"]
---

# Margin Hedef ≥ %70 (Paid Tier)

> **TL;DR:** Tüm paid tier'ların (Starter / Pro / Agency) **net margin'i ≥ %70** olmalı. Variable cost (LLM, embedding) + LS MoR fee (%5 + $0.50) düşüldükten sonra. Margin altı düşerse tier yeniden konumlandırma zorunlu.

## Karar

```text
✅ Starter $8 → net margin ≥ $5.60 (≥%70)
✅ Pro $24 → net margin ≥ $16.80 (≥%70)
✅ Agency $79 → net margin ≥ $55.30 (≥%70)
❌ Free tier margin hedef DEĞİL (LTV pozitif değil, viral loop motivasyonu)
```

## Gerekçeler

1. **Yıllık paid revenue / cost ratio** — Series A öncesi sürdürülebilir profitability için ≥%70 endüstri standart (SaaS)
2. **LLM cost dalgalanması** — DeepSeek V3 fiyat artarsa veya Claude Haiku 4.5 fiyat değişirse, %70 cushion var
3. **LS MoR dependency (R-FIN-04)** — fee %5+50¢ değişirse cushion'ın koruması
4. **Anti-cannibalization** — Agency $79 vs Pro × 5 = $120 → margin tutarlılığı

## Mevcut Hesap (2026-05)

| Tier | Fiyat | LS MoR fee | Variable | Net | Margin |
|---|---|---|---|---|---|
| Starter | $8 | -$0.90 | -$0.50 (DeepSeek × 100 üretim) | $6.60 | **82.5%** ✅ |
| Pro | $24 | -$1.70 | -$3.00 (DeepSeek + Claude Haiku) | $19.30 | **80.4%** ✅ |
| Agency | $79 | -$4.45 | -$12.00 (Haiku × 2500 + extras) | $62.55 | **79.2%** ✅ |

## Re-evaluation Tetikleyicileri

| Olay | Tetik | Aksiyon |
|---|---|---|
| LLM provider %20+ fiyat artışı | Variable cost ≥ %30 büyür | Tier price bump veya provider switch |
| LS MoR fee artar (%5 → %7) | -$2/üretim | Annual plan discount + bump |
| Türkiye TL parite >%50 değişim | FX exposure (R-FIN-05) | Geographic pricing review |
| Claude Haiku 4.5 quality regresyon | Pro UX kötüleşir | DeepSeek-only fallback Pro |

## Monitoring

- **Aylık:** admin /pipeline-comparison provider cost trend
- **Quarterly:** Unit economics review (Unit Economics §5)
- **Annual:** Pricing strategy review + tier reposition

## Bağlantı: own-slm-strategy

[[own-slm-strategy]] (kendi Türkçe SLM 12-18 ay yol) margin'i daha agresif yükseltebilir — DeepSeek bağımlılığını azalt → variable cost düş → margin %85+. Bu locked decision o stratejinin destekleyicisi.

## İlişkiler

- [[unit-economics-md]] §5
- [[pricing-strategy-md]] §2
- [[pricing-tier-matrix]] — tier başına detay
- [[lemon-squeezy-payment-provider]] — MoR fee
- [[deepseek-default-llm]] — variable cost dominant
- [[own-slm-strategy]] — uzun vade margin agresif yükseltme

## Kaynaklar

- [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) §5
- INDEX.md §4 (locked decisions)
