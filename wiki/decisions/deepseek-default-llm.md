---
type: decision
title: "DeepSeek V3 default LLM"
slug: "deepseek-default-llm"
status: "locked"
decided_on: "2026-05-01"
decided_by: "tech"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/engineering/architecture.md§0"
  - "docs/engineering/architecture.md§4.2"
  - "docs/engineering/architecture.md§4.3"
  - "INDEX.md§4"
  - "README.md§Çekirdek kararlar"
tags: ["locked-decision", "llm", "provider", "cost"]
aliases: ["deepseek-default", "default-llm-decision"]
---

# DeepSeek V3 default LLM

> **Karar:** Free, Starter ve Trial tier'larındaki tüm LLM çağrıları (generation, agenda card, summary) varsayılan olarak DeepSeek V3 (NIM endpoint, model `deepseek-ai/deepseek-v3.1-terminus`) ile yapılır.
> **Durum:** locked
> **Tarih:** 2026-05-01 (architecture.md v0.1 yayını), 2026-05-02'de NIM endpoint geçişiyle güncellendi (#109, #111).

## Bağlam

LLM cost-per-1M-token Nodrat'ın unit economics'inin en büyük kalemi. MVP-1 hedef margin ≥%75 (paid tier'da) için ucuz default şart. Aynı zamanda Türkçe kalitesi, latency, ve provider kilitlenmesi (vendor lock-in) endişesi var.

Karar üç problemi çözüyor:

1. **Cost** — DeepSeek V3 endüstrideki en ucuz frontier-class model ($0.27 input / $1.10 output per 1M token). Margin hedefini destekler.
2. **Türkçe** — DeepSeek V3 Türkçe'de iyi performans veriyor (eval'lere göre — [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) §eval).
3. **Tek API key** — NIM endpoint üzerinden DeepSeek V3'e erişim 30+ chat modeli ile aynı `NIM_API_KEY` üzerinden geliyor (free tier). Native DeepSeek API key gerekmez.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| GPT-4o-mini | Olgun, Türkçe iyi | Cost ~3x DeepSeek, OpenAI vendor lock | Reddedildi (sadece son fallback) |
| Claude Haiku 4.5 default | En iyi Türkçe + güvenlik | Cost 7-10x DeepSeek | Premium tier'a (Pro+) bırakıldı — bkz. [[claude-haiku-premium-llm]] |
| Native DeepSeek API | Resmi sağlayıcı, gecikmesiz | Ek API key, NIM ekosistem dışı | Reddedildi (NIM zaten gerekli — embedding) |
| Llama 3.3 70B (Together/Replicate) | Açık model | Türkçe daha zayıf, latency | Reddedildi |
| Mistral Large 3 (NIM) | NIM'de free | Cost-perf benchmark'ta DeepSeek üstün | Fallback olarak tutuldu |

## Sonuçlar

- **Etkilenen varlıklar:** [[deepseek-v3]], [[nim-bge-m3]] (aynı API key)
- **Etkilenen kavramlar:** [[provider-abstraction]] (NimChatProvider adapter)
- **Etkilenen topics:** [[llm-provider-strategy]]
- **Etkilenen kod:** `packages/model-providers/nim_chat.py`, `app/core/config.py` (`DEFAULT_LLM_PROVIDER=deepseek_v3`).
- **Etkilenen dokümanlar:** [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) §4 (cost-per-generation), [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) (tier yapısı), [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) (model-specific tuning).

## Geri alma maliyeti

Bu karar değiştirilirse:

1. **Cost re-modelling.** Margin hesabı sıfırdan: yeni provider $/1M token × token bütçesi × free user başına.
2. **Provider adapter.** Yeni `ModelProvider` implementasyonu (eğer NIM/OpenRouter dışıysa).
3. **Eval re-baseline.** [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) §eval — yeni model için golden test set yeniden koşulur, halü < %2 ve citation %100 hedeflerinde regresyon kontrol edilir.
4. **Pricing tier güncellemesi.** Eğer cost önemli ölçüde artarsa tier fiyatları (249/749/2499 TL) revize gerekebilir.
5. **Tüm prompt'lar.** Model-specific tone/format değişikliği gerekirse prompt-contracts re-tune.

Tahmini değişiklik süresi: 2-4 hafta (eval + tuning dahil).

## Ek not — model varyantları (#109, #111)

NIM endpoint'i üzerinde DeepSeek model adları değişir:

- **Stabil + tercih:** `deepseek-ai/deepseek-v3.1-terminus` (Türkçe iyi, latency stabil)
- **Alternatif:** `deepseek-v3.2` (geçici 502'ler raporlandı 2026-05-02)
- **Test:** `v4-flash` (timeout sorunları)

Default model kararı kod düzeyinde `app/core/config.py`'de tutulur, runtime tunable değildir (settings panel kapsamı dışı — bkz. INDEX MVP-1.2).

## İlişkiler

- **Bağlı varlıklar:** [[deepseek-v3]]
- **Bağlı kavramlar:** [[provider-abstraction]]
- **Bağlı topics:** [[llm-provider-strategy]]
- **İlgili kararlar:** [[claude-haiku-premium-llm]] (premium tier eşdeğeri)

## Kaynaklar

- [docs/engineering/architecture.md §0](../../docs/engineering/architecture.md) — yönetici özeti, default config
- [docs/engineering/architecture.md §4.2](../../docs/engineering/architecture.md) — adapter listesi, NIM not
- [docs/engineering/architecture.md §4.3](../../docs/engineering/architecture.md) — tier-based routing
- [INDEX.md §4 (Çekirdek kararlar — locked)](../../INDEX.md)
- [README.md (Çekirdek kararlar)](../../README.md)
