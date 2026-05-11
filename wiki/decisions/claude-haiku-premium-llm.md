---
type: decision
title: "Claude Haiku 4.5 premium LLM (Pro+ tier)"
slug: "claude-haiku-premium-llm"
status: "locked"
decided_on: "2026-05-01"
decided_by: "tech"
created: "2026-05-07"
updated: "2026-05-08"
sources:
  - "docs/engineering/architecture.md§4.3"
  - "INDEX.md§4"
  - "README.md§Çekirdek kararlar"
tags: ["locked-decision", "llm", "provider", "tier"]
aliases: ["haiku-premium", "anthropic-pro-tier"]
---

# Claude Haiku 4.5 premium LLM (Pro+ tier)

> **Karar:** Pro ve Agency tier'larında premium LLM olarak Claude Haiku 4.5 kullanılır. Agency tier'da `comparison_generation` görevi için Sonnet 4.6'ya yükseltme yapılır.
> **Durum:** locked
> **Tarih:** 2026-05-01 (architecture.md v0.1 yayını). Faz 2'de operasyonel olur (Pro tier launch sonrası).

## Bağlam

Default DeepSeek V3 ([[deepseek-default-llm]]) Free/Starter/Trial için yeterli ama Pro/Agency müşterileri:

1. **Daha yüksek kalite Türkçe** ister (özellikle nüanslı politik içerik için).
2. **Daha düşük halüsinasyon** bekler (citation %100, halü < %2 eşiklerini destekler).
3. **Premium "feel"** ister — fiyat farkını rasyonalize eden algılanan değer.

Karar Anthropic Haiku 4.5'i bu üç ihtiyacı karşılayan en uygun denge olarak seçti — Sonnet 4.6'dan ucuz, Opus'tan çok daha ucuz, DeepSeek'ten kaliteli.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Sonnet 4.6 default (tüm tier) | En yüksek kalite | Cost margin'i öldürür | Reddedildi (sadece Agency comparison_generation için) |
| GPT-4o (premium) | Olgun ekosistem | Türkçe Haiku'dan zayıf, OpenAI vendor lock | Reddedildi |
| DeepSeek V3 (tüm tier'lar) | Cost düşer | Premium algı yok, kalite tavanı düşük | Reddedildi (default için tutuldu) |
| Haiku 3.5 (eski sürüm) | Daha ucuz | Kalite düşük, deprecation riski | Reddedildi |
| Llama 3.3 70B premium | Açık model, predictable cost | Türkçe + safety daha zayıf | Reddedildi |

## Routing logic (architecture.md §4.3)

```python
def route_request(user: User, task_type: str) -> Provider:
    if user.tier == "agency" and task_type == "comparison_generation":
        return AnthropicProvider(model="claude-sonnet-4-6")
    if user.tier in ("pro", "agency"):
        return AnthropicProvider(model="claude-haiku-4-5")
    if user.tier in ("starter", "free", "trial"):
        return DeepSeekProvider(model="deepseek-v4-flash")
    raise ValueError("Unknown tier")
```

## Sonuçlar

- **Etkilenen varlıklar:** [[claude-haiku-4-5]]
- **Etkilenen kavramlar:** [[provider-abstraction]] (AnthropicProvider adapter)
- **Etkilenen topics:** [[llm-provider-strategy]]
- **Etkilenen tier'lar:** Pro (749 TL/ay), Agency (2.499 TL/ay) — bkz. [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md)
- **Etkilenen kod:** `packages/model-providers/anthropic.py`, `app/services/llm_router.py`.
- **Aktivasyon:** Faz 2 (Pro tier launch). MVP-3 paid launch ile birlikte canlı.

## Geri alma maliyeti

Bu karar değiştirilirse:

1. **Tier value proposition** yeniden yazılmalı (premium müşteri değer algısı).
2. **Pricing revize** — fiyat kalmasına rağmen maliyet düşerse margin artar (yeniden yatırım); maliyet artarsa fiyat artırma riski.
3. **Adapter değişimi** — `AnthropicProvider`'dan başka adapter'a geçiş.
4. **Eval re-baseline** Pro/Agency için ayrı.

Tahmini değişiklik süresi: 1-2 hafta.

## Açık sorular

- **Faz 2 timing:** Pro tier launch tarihi MVP-3 milestone'unda (2026-11-30 hedef). Bu kadar uzun bir ilerleme süresinde Anthropic Haiku 4.6/5 çıkarsa upgrade kararı gerekecek.
- **Anthropic provider DPA:** Faz 0 sonu hedefli (INDEX §6.1) — eksik kalırsa launch blocker.

## İlişkiler

- **Bağlı varlıklar:** [[claude-haiku-4-5]]
- **Bağlı kavramlar:** [[provider-abstraction]]
- **Bağlı topics:** [[llm-provider-strategy]]
- **İlgili kararlar:** [[deepseek-default-llm]] (default tier eşdeğeri)
- [[deepseek]]
- [[own-slm-strategy]]
- [[pipeline-performance-baseline]]
- [[trendyol-llm-base]]
- [[architecture-md]]

## Kaynaklar

- [docs/engineering/architecture.md §4.3](../../docs/engineering/architecture.md) — routing logic
- [INDEX.md §4 (Çekirdek kararlar — locked)](../../INDEX.md)
- [README.md (Çekirdek kararlar)](../../README.md)
- [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) — tier yapısı
