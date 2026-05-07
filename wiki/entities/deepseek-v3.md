---
type: entity
title: "DeepSeek V3 (NIM endpoint)"
slug: "deepseek-v3"
category: "provider"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/engineering/architecture.md§0"
  - "docs/engineering/architecture.md§4.2"
  - "docs/engineering/architecture.md§4.3"
  - "INDEX.md§4"
tags: ["llm", "provider", "default", "deepseek", "nim"]
aliases: ["DeepSeek", "deepseek-v3.1-terminus", "default-llm"]
---

# DeepSeek V3 (NIM endpoint)

> **TL;DR:** Nodrat'ın default LLM'i. NVIDIA NIM endpoint'i üzerinden `deepseek-ai/deepseek-v3.1-terminus` modeli ile çağrılır. Free / Starter / Trial tier'larındaki tüm generation, agenda card ve summary işlerinde kullanılır. Cost $0 (NIM free tier).

## Tanım

DeepSeek V3, DeepSeek AI tarafından geliştirilen open-weight Mixture-of-Experts (MoE) chat modeli. Nodrat onu **doğrudan DeepSeek API'si yerine NVIDIA NIM endpoint'i üzerinden** çağırır — aynı `NIM_API_KEY` ile embedding ve diğer 30+ chat modeline de erişilebilir, ek API key yönetimi gerekmez.

## Nodrat'ta kullanım

- **Hangi servis kullanır:** `apps/api/app/services/llm_router.py` → `NimChatProvider` (`packages/model-providers/nim_chat.py`).
- **Hangi tier'da aktif:** Free, Starter, Trial — yani `tier in {free, starter, trial}` olan tüm kullanıcılar.
- **Hangi MVP'de devreye girdi:** MVP-1 (Faz 0+1+2+3, 2026 Q1 production'a alındı).
- **Hangi prompt'lar:** generation (X post oluşturma), agenda card synthesis, summary, RAPTOR weekly cluster — tüm LLM-bound görevler default'ta DeepSeek'i çağırır.

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| Model adı | `deepseek-ai/deepseek-v3.1-terminus` | architecture.md §4.2 |
| Endpoint | NIM (NVIDIA Inference Microservice) | architecture.md §4.2 |
| API key env | `NIM_API_KEY` | architecture.md §7.2 |
| Cost (NIM tier) | $0 (free tier) | architecture.md §4.2 |
| Native cost (referans) | $0.27 input / $1.10 output per 1M token | INDEX §4 |
| Adapter sınıfı | `NimChatProvider` (name=`deepseek_v3`) | architecture.md §4.2 |
| Default config flag | `DEFAULT_LLM_PROVIDER=deepseek_v3` | architecture.md §7.2 |

### Model varyantları (NIM endpoint'inde)

| Varyant | Durum | Not |
|---|---|---|
| `deepseek-v3.1-terminus` | ✅ stabil, default | Türkçe iyi, latency stabil — tercih |
| `deepseek-v3.2` | ⚠️ geçici 502 raporlandı | 2026-05-02 #109 |
| `deepseek-v4-flash` | ❌ timeout | test edildi, kararsız |

## Kararlar (locked)

- [[deepseek-default-llm]] — bu varlığın "default LLM" rolü locked karar.

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]] — bu varlık ModelProvider Protocol implementasyonudur.
- **İlgili varlıklar:** [[claude-haiku-4-5]] (premium tier eşdeğeri), [[nim-bge-m3]] (aynı API key paylaşımı).
- **İlgili kararlar:** [[deepseek-default-llm]], [[claude-haiku-premium-llm]] (tier ayrımı).
- **İlgili topics:** [[llm-provider-strategy]] — tier-based routing sentezi.

## Açık sorular / TODO

- **Türkçe eval freshness:** [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) §eval'de DeepSeek V3 baseline ne zaman güncellendi? Yeni model varyantları (terminus → v3.2 vs.) için A/B benchmark var mı?
- **NIM rate limit:** Free tier'ın gerçek limit'leri net dokümante değil. Production'da rate-limit tetiklenirse fallback (OpenRouter, native API) için circuit breaker testi gerekiyor.

## Kaynaklar

- [docs/engineering/architecture.md §0](../../docs/engineering/architecture.md) — yönetici özeti, default config
- [docs/engineering/architecture.md §4.2](../../docs/engineering/architecture.md) — adapter listesi + NIM not
- [docs/engineering/architecture.md §4.3](../../docs/engineering/architecture.md) — tier-based routing
- [INDEX.md §4](../../INDEX.md) — Çekirdek kararlar
- [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) — model-specific prompt tuning
