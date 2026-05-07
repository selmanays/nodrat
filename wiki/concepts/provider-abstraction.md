---
type: concept
title: "Provider abstraction (LLM/embedding/rerank)"
slug: "provider-abstraction"
category: "architecture-pattern"
status: "live"
created: "2026-05-07"
updated: "2026-05-08"
sources:
  - "docs/engineering/architecture.md§1"
  - "docs/engineering/architecture.md§4"
  - "docs/product/prd.md§F0-R4"
tags: ["architecture", "provider", "abstraction", "vendor-lock"]
aliases: ["model-provider-protocol", "adapter-pattern-llm"]
---

# Provider abstraction

> **TL;DR:** Nodrat'ta tüm LLM, embedding, rerank ve (gelecekte) payment çağrıları `ModelProvider` Protocol'ü üzerinden yapılır. Hiçbir kod doğrudan provider SDK'sına (DeepSeek SDK, Anthropic SDK vb.) bağlı olmaz. A3 mimari prensibi (architecture.md §1) — vendor lock-in'i engelleyen, tier-based routing'i mümkün kılan, fallback chain'lerin temeli.

## Tanım

Provider abstraction, "Adapter pattern"in LLM/AI provider'lara uygulanmış halidir. Tek bir `ModelProvider` Protocol arayüzü, n farklı sağlayıcı için tek arabirim sunar. Servis kodu (worker'lar, generation handler) hiçbir zaman concrete provider seçmez — bunu `llm_router` yapar.

### Protocol arayüzü (architecture.md §4.1)

```python
class ModelProvider(Protocol):
    name: str
    supports_chat: bool
    supports_embeddings: bool
    supports_rerank: bool
    supports_vision: bool

    async def generate_text(messages, model, max_tokens, temperature, timeout) -> GenerationResult: ...
    async def generate_structured_json(messages, schema, model) -> dict: ...
    async def create_embedding(texts, model) -> list[list[float]]: ...
    async def rerank(query, documents, top_k) -> list[RerankResult]: ...
    async def healthcheck() -> ProviderHealth: ...
```

## Neden Nodrat'ta var

Üç temel motivasyon:

1. **Vendor lock-in riski.** PRD F0-R4 zorunlu kılıyor. LLM endüstrisi hızla değişiyor — bugünün ucuz/kaliteli sağlayıcısı yarın kapanabilir veya fiyat artırabilir. Adapter pattern bir günde provider değiştirmeyi mümkün kılar.
2. **Tier-based routing.** Free → DeepSeek, Pro → Haiku, Agency comparison → Sonnet. Bu logic concrete SDK'lara bağlı kod ile yazılırsa her tier için ayrı pipeline gerekir; abstraction'la tek `route_request()` yapılır.
3. **Cost tracking + circuit breaker + fallback.** Tek arayüz olduğu için her çağrının cost'unu, latency'sini, error rate'ini aynı `provider_call_logs` tablosuna yazmak ve fallback chain kurmak triviallikle mümkün olur.

> **MVP-2.1 PR [#411](https://github.com/selmanays/nodrat/pull/411)/[#416](https://github.com/selmanays/nodrat/pull/416)/[#418](https://github.com/selmanays/nodrat/pull/418) güncellemeleri (2026-05-08):** `validate_citations_batch` ([citation.py](../../apps/api/app/core/citation.py)) artık embedding provider'ı tek mega-batch'le çağırıyor — N post için N+1 round-trip yerine 1. Provider abstraction'ın `create_embedding(texts: list[str])` arayüzü zaten batch destekliyordu; refactor sadece caller'ı (app_generate handler) batch'e çevirdi. Embedding call sayısı citation phase'de **%83 azaldı**.

## Adapter listesi (production state — 2026-05-08)

Registry'ye iki katman halinde adapter kaydedilir: factory başarılıysa concrete provider, başarısızsa fallback. **Mevcut prod default'ları (admin panel runtime override'ları dahil):**

```text
═══════ Chat (LLM) ═══════════════════════════════════════════════
DeepSeekProvider (name='deepseek_v3')          — ✅ AKTİF (production primary)
                                                 native API, deepseek-v4-flash, thinking-disabled
                                                 (#163, #361, #378, #379)
NimChatProvider (name='deepseek_v3')           — fallback (deprecated, DEEPSEEK_API_KEY yoksa)
OpenRouterProvider                             — chat fallback (generic, registry'de)
AnthropicProvider                              — ⏳ Faz 2'de Pro tier (Haiku 4.5)
OpenAICompatibleProvider                       — son fallback (registry'de)

═══════ Embedding ════════════════════════════════════════════════
LocalBgeM3Provider (name='local_bge_m3')       — ✅ AKTİF (production primary)
                                                 BAAI/bge-m3 ~2.3 GB FP32 CPU
                                                 admin panel `llm.use_local_embedding=true`
                                                 #350 ile migration tamam (2026-05-06)
NimEmbeddingProvider (name='nim_bge_m3')       — fallback only (admin panel kapatırsa)
                                                 NIM nvidia/nv-embedqa-e5-v5, 1024-dim
                                                 son 24 saat: 0 çağrı

═══════ Rerank ═══════════════════════════════════════════════════
NimRerankProvider (name='nim_rerank')          — ✅ AKTİF (production primary, hâlâ NIM)
                                                 NIM nv-rerankqa-mistral-4b-v3
LocalBgeRerankerProvider (name='local_bge_reranker') — ⏳ scaffold hazır (#224 MVP-1.5)
                                                 GATE: USE_LOCAL_RERANK (admin panel — false)
                                                 NDCG@10 ≥0.90 eval gate (#347) bekliyor
                                                 BAAI/bge-reranker-v2-m3, CrossEncoder

═══════ VLM (görsel zeka) ═════════════════════════════════════════
NimVlmProvider                                 — ✅ AKTİF (NIM Llama 4 Maverick, 40 RPM free)

Faz 4+:  AnthropicVisionProvider, OpenAIVisionProvider
Faz 6+:  IyzicoPaymentProvider, StripePaymentProvider
```

> 💡 **Önemli — runtime config'in rolü:** `LocalBgeM3Provider` ve `LocalBgeRerankerProvider` factory'leri ([local_embedding.py:152](../../apps/api/app/providers/local_embedding.py:152), [local_rerank.py:163](../../apps/api/app/providers/local_rerank.py:163)) `app_settings` DB tablosundaki `llm.use_local_embedding` ve `llm.use_local_rerank` flag'lerine bağlı. `config.py` default'ları sadece DB row yoksa kullanılır (env-var fallback). Production'da admin panel telemetry kanıtı: embedding flag TRUE (NIM yedek 0 çağrı), rerank flag FALSE (NIM rerank 62 çağrı/gün). MVP-1.2 #262/#264 settings panel mekanizması — bkz. [[deepseek-default-llm]] §Backward-compat.

## Routing kuralı (architecture.md §4.3)

```python
def route_request(user: User, task_type: str) -> Provider:
    if user.tier == "agency" and task_type == "comparison_generation":
        return AnthropicProvider(model="claude-sonnet-4-6")
    if user.tier in ("pro", "agency"):
        return AnthropicProvider(model="claude-haiku-4-5")
    if user.tier in ("starter", "free", "trial"):
        return DeepSeekProvider(model="deepseek-v4-flash")
    raise ValueError("Unknown tier")

def with_fallback(primary: Provider, fallbacks: list[Provider]):
    # Circuit breaker pattern + retry
    ...
```

## Cost tracking (architecture.md §4.4)

Her provider çağrısı sonrası `provider_call_logs` tablosuna yazılır:

| Alan | Anlam |
|---|---|
| `request_id` | generation_id ile bağlı |
| `provider`, `model` | hangi adapter, hangi model |
| `input_tokens`, `output_tokens` | NIM/OpenRouter response'undan parse |
| `cost_estimate_usd` | sağlayıcı pricing × token sayısı |
| `latency_ms` | wall clock |
| `error` | varsa exception class |

Aggregate dashboard'lar: daily provider spend, per-user cost (P95 alarm), top 20 spender flag — Faz 2+ Prometheus + Grafana ile birlikte canlı.

## Provider key encryption at rest (architecture.md §7.3)

Provider key'leri (NIM_API_KEY, ANTHROPIC_API_KEY vb.) `.env`/`.env.sops`'tan okunur ama dinamik provider eklemesi (admin panelinden) için `model_providers` tablosunda Fernet ile şifrelenir:

```text
model_providers tablosu:
  api_key_secret_ref VARCHAR(255)  → Fernet encrypted

Decryption:
  API_SECRET_KEY → Fernet.decrypt
  Sadece request anında decrypt edilir, log'a yazılmaz
```

## İlişkiler

- **İlgili kavramlar:** [[hot-cold-tier]] (storage abstraction'ın eşdeğeri — aynı "swap-able backend" prensibi).
- **İlgili varlıklar:** [[deepseek]], [[claude-haiku-4-5]], [[nim-bge-m3]] — concrete adapter implementasyonları.
- **İlgili kararlar:** [[deepseek-default-llm]], [[claude-haiku-premium-llm]] — bu abstraction olmasa locked decision çoklu pipeline gerektirirdi.
- **İlgili topics:** [[llm-provider-strategy]] — routing stratejisinin somutlanması.

## Açık sorular / TODO

- **Provider health check periyodu:** `healthcheck()` ne sıklıkta çağrılır? Source health check beat task'ı (6 saatte bir) ile aynı sıklıkta mı, yoksa her N request'te bir mi?
- **Circuit breaker thresholds:** "with_fallback"in concrete implementasyonu nedir? Failure rate ≥ %X ise primary kapatılıp fallback aktif gibi bir kural var mı? (`docs/engineering/architecture.md` §4.3 pseudo-code, gerçek implementasyon `packages/model-providers/router.py`'de.)
- **Provider eklemek için runbook:** Yeni adapter eklenirken hangi adımlar gerekli (test, eval, registry)? Skill veya playbook olarak dökümante edilmeli mi?

## Kaynaklar

- [docs/engineering/architecture.md §1 (A3 prensibi)](../../docs/engineering/architecture.md)
- [docs/engineering/architecture.md §4 (Provider katmanı)](../../docs/engineering/architecture.md)
- [docs/product/prd.md §F0-R4](../../docs/product/prd.md) — gereksinim
- [docs/strategy/unit-economics.md §6](../../docs/strategy/unit-economics.md) — cost tracking integrasyon
