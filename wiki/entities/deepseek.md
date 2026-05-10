---
type: entity
title: "DeepSeek (default LLM)"
slug: "deepseek"
category: "provider"
status: "live"
created: "2026-05-07"
updated: "2026-05-08"
sources:
  - "apps/api/app/providers/deepseek.py§DEEPSEEK_CHAT_DEFAULT_MODEL"
  - "apps/api/app/providers/registry.py§route_for_tier"
  - "docs/engineering/architecture.md§0"
  - "docs/engineering/architecture.md§4.2"
  - "docs/engineering/architecture.md§4.3"
  - "INDEX.md§4"
  - "PR #163, #361, #378, #379"
tags: ["llm", "provider", "default", "deepseek"]
aliases: ["DeepSeek", "deepseek-v3", "deepseek-v4-flash", "default-llm", "deepseek-default"]
---

# DeepSeek (default LLM)

> **TL;DR:** Nodrat'ın default LLM'i. **DeepSeek native API** (`api.deepseek.com/v1`) üzerinden `deepseek-v4-flash` modeli ile çağrılır (thinking-disabled). Free / Starter / Trial tier'larındaki tüm generation, agenda card ve summary işlerinde kullanılır. Slug `deepseek` (eski `deepseek-v3` aliases içinde — Obsidian search çalışmaya devam eder); kod tarafında registry name `deepseek_v3` backward-compat için korundu (`generation_log.provider_name` aynı kalıyor).

## Tanım

DeepSeek, DeepSeek AI tarafından geliştirilen open-weight Mixture-of-Experts (MoE) chat modeli. Nodrat onu **DeepSeek native API üzerinden** çağırır. Eski mimari NIM endpoint kullanıyordu (PR #163 öncesi); 2026-04-29'dan beri (#361 + #163) native API primary, NIM endpoint fallback rolünde tutuldu (`DEEPSEEK_API_KEY` yoksa devreye giriyor). Native tercih nedeni: düşük latency + güncel model varyantlarına direkt erişim.

## Nodrat'ta kullanım

- **Hangi servis kullanır:** Provider: `DeepSeekProvider` ([apps/api/app/providers/deepseek.py:72](../../apps/api/app/providers/deepseek.py)). Routing: [registry.py:71-76](../../apps/api/app/providers/registry.py:71) — `route_for_tier(operation="chat", tier=...)` `_fallback("deepseek_v3", "openrouter")` ile DeepSeek primary. ⚠️ `services/llm_router.py` mevcut DEĞİL — routing doğrudan `app.providers.registry.registry` singleton'ı üzerinden yapılır (önceki wiki yanlış path veriyordu).
- **Hangi tier'da aktif:** Free, Starter, Trial — yani `tier in {free, starter, trial}` olan tüm kullanıcılar.
- **Hangi MVP'de devreye girdi:** MVP-1 (Faz 0+1+2+3, 2026 Q1 production'a alındı). Native API migration #163 ile MVP-1.5 sırasında.
- **Hangi prompt'lar:** generation (X post oluşturma), agenda card synthesis, summary, RAPTOR weekly cluster — tüm LLM-bound görevler default'ta DeepSeek'i çağırır.

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| Production model | `deepseek-v4-flash` | [apps/api/app/providers/deepseek.py:61](../../apps/api/app/providers/deepseek.py) |
| Endpoint | `api.deepseek.com/v1` (native API) | DeepSeekProvider |
| Thinking mode | **disabled** (payload flag) | #379 hotfix |
| API key env | `DEEPSEEK_API_KEY` (NIM_API_KEY fallback) | config.py |
| Cost — input cache miss | $0.27 per 1M token | deepseek.py:67 |
| Cost — input cache hit | $0.07 per 1M token | deepseek.py:68 |
| Cost — output | $1.10 per 1M token | deepseek.py:69 |
| Kampanya indirimi | %75 (2026-05-31'e kadar) | `settings.deepseek_campaign_discount` |
| Adapter sınıfı | `DeepSeekProvider` (registry name=`deepseek_v3`) | deepseek.py:72-77 |
| Default config flag | `DEFAULT_LLM_PROVIDER=deepseek_v3` | config.py |
| Streaming desteği | ✅ `generate_text_stream()` async iterator (issue #527) | deepseek.py:304-471 |
| Streaming flags | `stream:true` + `stream_options.include_usage:true` | PR #528 |

### Model migration timeline

| Tarih | Commit | Değişiklik |
|---|---|---|
| 2026-04-XX | #163 (PR-A) | DeepSeek native API chat provider eklendi, NIM fallback'e indi |
| 2026-04-29 | #361 | Model adı `deepseek-chat` → `deepseek-v4-flash` (audit/log netliği) |
| 2026-05-06 | #378 | Smoke feedback fixes (UI polish + model field) |
| 2026-05-07 | #379 | v4-flash thinking-disabled hotfix (response.content boş sorunu) |
| 2026-05-09 | #528 (#527) | `generate_text_stream()` SSE streaming async iterator — TTFT 5s→~700ms, [[sse-streaming-default]] kararı; final chunk usage+cost dolu, cost tracking eski path ile birebir aynı |

> **Not:** Eski model adları (`deepseek-chat`, `deepseek-v3.1-terminus`) sunucu tarafında redirect ediyor. Explicit `deepseek-v4-flash` kullanımı audit/log netliği için tercih edildi.

## Kararlar (locked)

- [[deepseek-default-llm]] — bu varlığın "default LLM" rolü locked karar.
- [[own-slm-strategy]] — DeepSeek output'ları MVP-1.7'den itibaren Nodrat'ın kendi SLM'inin SFT eğitim verisi olarak biriktirilir (2026-05-10).

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]] — bu varlık ModelProvider Protocol implementasyonudur. [[sft-data-pipeline]] — DeepSeek output'ları `training_samples` kaynağı.
- **İlgili varlıklar:** [[claude-haiku-4-5]] (premium tier eşdeğeri), [[trendyol-llm-base]] (DeepSeek output'larıyla fine-tune edilecek base).
- **İlgili kararlar:** [[deepseek-default-llm]], [[claude-haiku-premium-llm]] (tier ayrımı), [[own-slm-strategy]] (uzun vade SFT rolü).
- **İlgili topics:** [[llm-provider-strategy]] — tier-based routing sentezi.

## Açık sorular / TODO

- **Türkçe eval freshness:** [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) §eval'de DeepSeek baseline `v4-flash` ile yeniden koşuldu mu, yoksa hâlâ `v3.1-terminus` baseline'ında mı? Migration sonrası halü <%2 / citation %100 regresyon kontrolü yapıldı mı?
- **NIM fallback test:** `DEEPSEEK_API_KEY` boş veya 5xx durumunda NIM fallback path'i smoke test'te doğrulandı mı?
- **Native API rate limit:** DeepSeek native API'nin gerçek limit'leri (RPM/TPM) production load'unda nasıl davranıyor? Circuit breaker threshold güncel mi?

## Kaynaklar

- [apps/api/app/providers/deepseek.py](../../apps/api/app/providers/deepseek.py) — DeepSeekProvider class + DEEPSEEK_CHAT_DEFAULT_MODEL
- [docs/engineering/architecture.md §0](../../docs/engineering/architecture.md) — yönetici özeti, LLM stack (v0.2)
- [docs/engineering/architecture.md §4.2](../../docs/engineering/architecture.md) — adapter listesi: DeepSeekProvider primary, NimChatProvider fallback (#405)
- [docs/engineering/architecture.md §4.3](../../docs/engineering/architecture.md) — tier-based routing pseudocode `deepseek-v4-flash` (#405)
- [INDEX.md §4](../../INDEX.md) — Çekirdek kararlar
- [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) — model-specific prompt tuning
- PR #163 (native API), #361 (v4-flash adı), #378 (smoke fixes), #379 (thinking-disabled)
