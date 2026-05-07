---
type: entity
title: "Claude Haiku 4.5"
slug: "claude-haiku-4-5"
category: "provider"
status: "planned"     # Faz 2'de operasyonel
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/engineering/architecture.md§4.2"
  - "docs/engineering/architecture.md§4.3"
  - "INDEX.md§4"
tags: ["llm", "provider", "premium", "anthropic", "tier-pro"]
aliases: ["Haiku", "Claude Haiku", "premium-llm"]
---

# Claude Haiku 4.5

> **TL;DR:** Pro ve Agency tier'larındaki LLM çağrıları için premium provider. Anthropic'in native API'si üzerinden çağrılır. Türkçe kalitesi ve düşük halüsinasyon oranı için seçildi. Aktivasyon: Faz 2 (Pro tier launch — MVP-3 hedefli).

## Tanım

Claude Haiku 4.5, Anthropic'in en hızlı ve uygun fiyatlı frontier-class chat modelidir. Sonnet 4.6'dan ucuz, Opus'tan çok daha ucuz; Türkçe ve safety özelliklerinde DeepSeek V3'ten ileri. Nodrat onu Pro+ tier kullanıcıları için "premium" olarak konumlandırır — fiyat farkını rasyonalize eden algılanan kalite.

## Nodrat'ta kullanım

- **Hangi servis kullanır:** `apps/api/app/services/llm_router.py` → `AnthropicProvider` (`packages/model-providers/anthropic.py`).
- **Hangi tier'da aktif:** Pro (749 TL/ay), Agency (2.499 TL/ay).
- **Özel kural:** Agency tier'da `task_type == "comparison_generation"` ise model `claude-sonnet-4-6`'ya yükseltilir (architecture.md §4.3).
- **Hangi MVP'de devreye girer:** Faz 2 — Pro tier launch ile birlikte. Şu an `status: planned`. MVP-3 milestone (2026-11-30 hedefli) ile production'a alınır.

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| Model adı | `claude-haiku-4-5` | architecture.md §4.3 |
| Sonnet upgrade modeli | `claude-sonnet-4-6` (Agency comparison_generation) | architecture.md §4.3 |
| Endpoint | Anthropic native API | architecture.md §4.2 |
| API key env | `ANTHROPIC_API_KEY` | architecture.md §7.2 |
| Cost (referans) | Haiku ~$0.80/$4 per 1M token; Sonnet ~$3/$15 per 1M token | (sektör genel — Anthropic pricing) |
| Adapter sınıfı | `AnthropicProvider` | architecture.md §4.2 |
| DPA durumu | ⏳ Faz 0 sonu hedefli (INDEX §6.1) | INDEX |

## Routing

```python
# architecture.md §4.3
if user.tier == "agency" and task_type == "comparison_generation":
    return AnthropicProvider(model="claude-sonnet-4-6")
if user.tier in ("pro", "agency"):
    return AnthropicProvider(model="claude-haiku-4-5")
```

## Kararlar (locked)

- [[claude-haiku-premium-llm]] — bu varlığın "premium LLM (Pro+ tier)" rolü locked karar.

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]] — `AnthropicProvider` Protocol implementasyonu.
- **İlgili varlıklar:** [[deepseek]] (default tier eşdeğeri).
- **İlgili kararlar:** [[claude-haiku-premium-llm]], [[deepseek-default-llm]].
- **İlgili topics:** [[llm-provider-strategy]] — tier-based routing.

## Açık sorular / TODO

- **DPA imzası:** Anthropic ile DPA Faz 0 sonu hedefli ([INDEX §6.1](../../INDEX.md)). Eksik kalırsa Pro tier launch blocker. KVKK uyumu için zorunlu.
- **Pricing volatility:** Anthropic pricing zaman içinde değişiyor. Margin hesabı son güncel fiyatlara göre revize gerekebilir — bkz. [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md).
- **Haiku 4.6/5 timing:** MVP-3 launch tarihinde (2026-11) Anthropic yeni Haiku versiyonu çıkarabilir. Upgrade kararı için karşılaştırmalı eval gerekir.

## Kaynaklar

- [docs/engineering/architecture.md §4.2](../../docs/engineering/architecture.md) — adapter listesi
- [docs/engineering/architecture.md §4.3](../../docs/engineering/architecture.md) — routing logic
- [INDEX.md §4](../../INDEX.md) — Çekirdek kararlar
- [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) — tier yapısı
- [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) — Pro+ tier margin hesabı
