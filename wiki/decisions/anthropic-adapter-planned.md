---
type: decision
title: "Anthropic Claude provider adapter — planlanan iş (Faz 2)"
slug: "anthropic-adapter-planned"
category: "llm"
status: "planned"
created: "2026-05-12"
updated: "2026-05-12"
sources:
  - "docs/strategy/pricing-strategy.md §2.4 Pro tier"
  - "wiki/decisions/claude-haiku-premium-llm.md"
  - "apps/api/app/providers/registry.py (route_for_tier — anthropic_haiku unresolved)"
  - "GitHub Issue #720"
tags: ["llm", "anthropic", "claude", "haiku", "pro-tier", "planned-faz2"]
aliases: ["claude-haiku-pending", "anthropic-faz2"]
---

# Anthropic Claude provider adapter (planlanan iş, Faz 2)

> **TL;DR:** Pro/Agency tier'da premium LLM olarak Claude Haiku 4.5 planlanmış ([[claude-haiku-premium-llm]] kararı), ancak `apps/api/app/providers/anthropic.py` henüz yazılmadı. MVP-1'de tüm tier'lar DeepSeek V4 Flash kullanıyor. UI/docs bu durumu net iletiyor; adapter implementasyonu Faz 2 işi.

## Mevcut durum (MVP-1, 2026-05-12)

`provider_registry.route_for_tier()` mantığı locked karara göre:

```python
if tier in ("pro", "agency_seat"):
    return self._fallback("anthropic_haiku", "deepseek_v3")
if tier in ("agency_seat",) and comparison_mode:
    return self._fallback("anthropic_sonnet", "anthropic_haiku", "deepseek_v3")
```

ama `anthropic_haiku` / `anthropic_sonnet` provider'ları **kayıtlı değil** (modül yok), `_fallback` zinciri `deepseek_v3`'e düşüyor. Yani Pro/Agency müşterisi MVP-1'de DeepSeek alıyor.

**Bunu kullanıcıya net iletmek için (#720):**

- `wiki/concepts/pricing-tier-matrix.md` — LLM kolonu iki satır: "MVP-1 reality" + "planlanan Faz 2"
- `docs/strategy/pricing-strategy.md §2.4` — ⚠️ MVP-1 reality footnote
- UI:
  - `apps/web/src/app/app/billing/page.tsx` — "Premium model (Claude Haiku 4.5) — Faz 2'de aktif"
  - `apps/web/src/app/app/style-profiles/_components/pro-gate.tsx` — "Faz 2'de aktif" notu

## Yapılacaklar (Faz 2 adapter scope)

1. **`apps/api/app/providers/anthropic.py`** — `ModelProvider` interface implementation
   - `name = "anthropic_haiku"` ve `name = "anthropic_sonnet"` iki ayrı factory
   - `claude-haiku-4-5` ve `claude-sonnet-4-6` model ID'leri
   - `generate_text()` + `generate_text_stream()` (SSE benzeri)
   - Cost tracking (`input_tokens` × $0.80 / 1M input, $4.00 / 1M output for Haiku 4.5)
   - Anthropic prompt caching (5 min TTL) — system prompt cache hit ratio telemetrisi
   - Retry / timeout / rate-limit handling

2. **Registry**:
   - `providers/registry.py` `bootstrap_default_providers()` içinde `ANTHROPIC_API_KEY` varsa register
   - `bootstrap_default_providers_async()` içinde `llm.anthropic_haiku_timeout` setting

3. **Settings registry** (`admin_settings.py`):
   - `llm.anthropic_haiku_model` (default: "claude-haiku-4-5")
   - `llm.anthropic_sonnet_model` (default: "claude-sonnet-4-6")
   - `llm.anthropic_haiku_timeout` (default: 60.0)
   - `llm.anthropic_sonnet_timeout` (default: 90.0)

4. **Cost dashboard** (`apps/api/app/api/admin_cost.py`) — Anthropic kalemi eklenmeli

5. **Eval gate** — Haiku 4.5 vs DeepSeek V4 Flash kalite karşılaştırması (#347 benzeri eval gate). Eğer Haiku kalitede üstünse Pro tier flip, değilse Pro fiyatı düşürülmeli.

6. **Prompt cache hesabı** — Anthropic prompt caching (5 min TTL) DeepSeek implicit cache'inden farklı sözleşmeyle gelir; system prompt cache hit ratio Pro tier cost'una direkt yansır.

## Open questions

- Geo-restriction: Anthropic API Türkiye'den erişilebilir mi? (Cloudflare proxy gerekir mi?)
- Cost — Haiku 4.5 prompt cache hit ratio production'da nasıl gerçekleşir? (DeepSeek implicit cache %60+, Haiku 5dk-TTL caching daha sıkı)
- ENV: `ANTHROPIC_API_KEY` Coolify .env'e eklenir, dev/staging için ayrı key (Anthropic key paid'den ayrı isteyebilir)

## Karar / Trade-off

**Şu an YAPMA gerekçesi (2026-05-12):**

- MVP-1 öncelik: niş entity recall sıçraması + NER kalite + boruhatları optimizasyonu (#684, #720)
- DeepSeek V4 Flash MVP-1 kalite eşiğini karşılıyor (ablation #347 referans)
- Anthropic adapter Faz 2'de implementasyon 1-2 günlük iş (eval gate dahil 1 hafta)
- Para harcamak yerine product-market fit'e odaklan

**Sözleşme:** Pricing UI Faz 2'de Haiku ON aşamasına geçinceye kadar tüm tier'ları DeepSeek V4 Flash ile beslemeye devam, "Faz 2'de aktif" notu UI'da net görülecek.

## İlişkiler

- [[claude-haiku-premium-llm]] — Pro+ tier premium LLM kararı (locked)
- [[deepseek-default-llm]] — MVP-1 chat default
- [[pricing-tier-matrix]] — MVP-1 reality + planlanan Faz 2
- [[pricing-strategy-md]] §2.4 Pro tier
- [[mvp-roadmap]] — Faz 2 scope

## Kaynaklar

- [Issue #720](https://github.com/selmanays/nodrat/issues/720) — MVP-1.8 audit sync fixes
- [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) §2.4
- [apps/api/app/providers/registry.py](../../apps/api/app/providers/registry.py) — route_for_tier mantığı
