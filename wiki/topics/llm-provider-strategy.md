---
type: topic
title: "LLM provider stratejisi — tier-based routing + fallback"
slug: "llm-provider-strategy"
category: "synthesis"
status: "live"
created: "2026-05-07"
updated: "2026-05-08"
sources:
  - "docs/engineering/architecture.md§4"
  - "INDEX.md§4"
  - "wiki/entities/deepseek-v3.md"
  - "wiki/entities/claude-haiku-4-5.md"
  - "wiki/entities/nim-bge-m3.md"
  - "wiki/decisions/deepseek-default-llm.md"
  - "wiki/decisions/claude-haiku-premium-llm.md"
tags: ["llm", "provider", "routing", "tier", "synthesis"]
aliases: ["provider-routing", "tier-llm-mapping"]
---

# LLM provider stratejisi

> **TL;DR:** Nodrat LLM stack'i 3 katmanlı: **default** (DeepSeek native API, `deepseek-v4-flash` thinking-disabled, $0.27/$1.10 per 1M token + 2026-05-31'e kadar %75 kampanya indirimi) Free/Starter/Trial için, **premium** (Claude Haiku 4.5) Pro/Agency için, **özel** (Sonnet 4.6) sadece Agency `comparison_generation` için. Embedding tek katman ([[nim-bge-m3]]). Tüm bunlar [[provider-abstraction]] üzerinden — vendor lock'a immune. DeepSeek default tier'da Haiku'ya kıyasla ~7-10x ucuz.

## Bağlam

Bu sentez şu soruyu cevaplar: "Nodrat'ta hangi tier hangi LLM'i çağırır, neden, alternatif olduğunda ne olur?"

Soru kritik çünkü:
- Cost margin'in en büyük belirleyicisi (≥%75 hedef — INDEX §4)
- Tier value proposition'unun teknik dayanağı
- Provider outage'ında failover stratejisinin temeli

## Tier × Provider mapping

| Tier | Aylık fiyat | Default LLM | Premium use case |
|---|---|---|---|
| **Trial** | 0 TL (limitli) | [[deepseek-v3]] | — |
| **Free** | 0 TL | [[deepseek-v3]] | — |
| **Starter** | 249 TL | [[deepseek-v3]] | — |
| **Pro** | 749 TL | [[claude-haiku-4-5]] | — |
| **Agency** | 2.499 TL | [[claude-haiku-4-5]] | `comparison_generation` → Sonnet 4.6 |

Embedding tüm tier'larda [[nim-bge-m3]] (`nvidia/nv-embedqa-e5-v5`, 1024-dim, $0). Tier-based embedding ayrımı yok — citation kalitesi tüm tier'larda aynı garantili.

## Routing kodu (architecture.md §4.3)

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

> **Not:** Routing içinde `DeepSeekProvider` artık DeepSeek native API'yi kullanır (`api.deepseek.com/v1`). NIM endpoint via `NimChatProvider` registry name `deepseek_v3` ile fallback rolünde — `DEEPSEEK_API_KEY` yoksa devreye girer (#163).

## Cost karşılaştırması (per 1M token, 2026-05-08 itibarıyla)

| Provider | Input (cache miss / cache hit) | Output | Aktivasyon |
|---|---|---|---|
| DeepSeek native (`deepseek-v4-flash`) | $0.27 / $0.07 | $1.10 | MVP-1, default ✅ |
| DeepSeek NIM (NimChatProvider) | $0 (NIM free) | $0 | Fallback (`DEEPSEEK_API_KEY` yoksa) |
| Claude Haiku 4.5 | ~$0.80 | ~$4 | Faz 2 (Pro+) |
| Claude Sonnet 4.6 | ~$3 | ~$15 | Agency comparison_generation |

> **2026-05-31 23:59 UTC'a kadar:** DeepSeek native pricing'inde **%75 kampanya indirimi** aktif (`settings.deepseek_campaign_discount`). Etkili maliyet: $0.07 input cache miss / $0.018 cache hit / $0.275 output per 1M.

Net etki: default tier'larda LLM cost minimal ama sıfır değil — production load'unda kullanıcı başına aylık ≈$0.01-0.10 USD seviyesinde (cache hit oranına bağlı). Margin ≥%75 hedefi DeepSeek native pricing + cache discipline ile korunuyor. Pro+ tier'larda fiyat farkı (Haiku ~3x DeepSeek native, Sonnet ~10x) müşterinin ödediği premium ile karşılanır. NIM düşerse fallback'a inilir, cost şişmez.

## Fallback chain

```text
Primary:     [tier'a göre routing]
Fallback 1:  OpenRouterProvider (chat fallback, generic)
Fallback 2:  OpenAICompatibleProvider (son fallback, OpenAI-compatible endpoint)

Embedding:
Primary:     NimEmbeddingProvider (nvidia/nv-embedqa-e5-v5)
Fallback:    LocalBgeM3Provider (BAAI/bge-m3, sentence-transformers)
             ⚠️ Embedding uzayı orthogonal — re-embed migration gerek (#345)

Rerank:
Primary:     NimRerankProvider (nvidia/rerank-qa-mistral-4b)
Fallback:    LocalBgeRerankerProvider (BAAI/bge-reranker-v2-m3)
             Same embedding space, drop-in OK
```

## Aktif kararlar

- [[deepseek-default-llm]] — DeepSeek V3 default LLM
- [[claude-haiku-premium-llm]] — Claude Haiku 4.5 Pro+ tier

## Çıkarımlar

1. **Default tier net cost minimal ($0.01-0.10/user/ay).** DeepSeek native pricing + cache hit discipline ile margin ≥%75 hedefi korunuyor. Free tier kötüye kullanım rate-limit + per-user cost cap ile yönetilir.
2. **Pro+ tier value proposition** salt LLM kalitesi değil, "bilinçli premium model seçimi"dir. Müşteri 749 TL/ay'da Haiku için ödüyor; bu net bir özellik farkı (Free'de DeepSeek).
3. **Sonnet sadece Agency comparison_generation'da** — bu en pahalı çağrı. Tüm Agency tier için Sonnet açılırsa margin çöker (~$15/1M output). Agency segmentinde "comparison" özelliği farklılaştırıcı.
4. **Embedding tek tier** — citation %100 hedefi tüm tier'larda aynı. Embedding'i tier'lara bölmek mühendislik karmaşıklığı + retrieval kalitesi rastgele bölünmüş corpus.
5. **Vendor lock immune değil ama yumuşatılmış.** Adapter pattern bir günde provider değiştirebilir (1-2 hafta eval re-baseline süresi dahil).

## Risk tabosu

| Risk | Olasılık | Etki | Mitigation |
|---|---|---|---|
| DeepSeek %75 kampanya indirimi sona erer (2026-05-31) | Yüksek (kesin) | Default tier cost ~4x artar (etkili → list price) | Cost re-modelling 2026-06-01 öncesi; gerekirse pricing revize |
| DeepSeek native API outage | Orta | NIM fallback'a düş | NimChatProvider auto-fallback (`DEEPSEEK_API_KEY` boşsa); circuit breaker |
| NIM free tier kapanır | Orta | Fallback path zayıflar; OpenRouter'a düşülür | Cost track + alarm; OpenRouter capacity test |
| Anthropic Haiku 4.5 deprecate | Düşük | Pro+ tier upgrade | Haiku 5/Sonnet test, 1-2 hafta migration |
| `nim_bge_m3` ↔ local bge-m3 migration başarısız | Orta | Embedding kalite kaybı | Re-embed migration #345, eval gate |
| DeepSeek native rate limit (RPM/TPM) | Orta | Generation gecikme | Circuit breaker, NIM fallback, OpenRouter ikinci fallback |
| Tier mapping kod hatası | Düşük | Free user'a Pro feature | nodrat-dev anti-pattern (server-side check) |

## İlişkiler

- **Beslediği kararlar:** [[deepseek-default-llm]], [[claude-haiku-premium-llm]].
- **İlgili varlıklar:** [[deepseek-v3]], [[claude-haiku-4-5]], [[nim-bge-m3]].
- **İlgili kavramlar:** [[provider-abstraction]] — tüm bu sentez bu pattern olmadan mümkün değil.

## Açık sorular / TODO

- **Faz 2 timing:** Pro tier launch tarihi MVP-3 milestone'unda (2026-11-30 hedef). Aradaki 6 ay içinde Anthropic pricing nasıl değişir?
- **comparison_generation tanımı:** Hangi exact endpoint'ler "comparison_generation" task_type'ında çağrılır? `apps/api/app/services/llm_router.py` net bir mapping sağlamalı.
- **Free tier abuse alarm:** DeepSeek native ucuz ama bedava değil — N kullanıcı × M generation × $0.27/$1.10 hesabı, %75 kampanya indirimi sonrası nasıl davranır? Per-user rate limit thresholds dokümante edilmeli (docs/engineering/alarm-thresholds.md var — INDEX'te referans).
- **Kampanya sonrası pricing impact:** 2026-05-31 sonrası etkili input/output rate listprice'a döner. 2026-06-01 öncesi unit-economics yeniden hesaplanmalı (margin ≥%75 hedefi tutuyor mu?).

## Kaynaklar

- [docs/engineering/architecture.md §4 (Provider katmanı)](../../docs/engineering/architecture.md)
- [INDEX.md §4 (Çekirdek kararlar)](../../INDEX.md)
- [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) — tier yapısı
- [docs/strategy/unit-economics.md §4](../../docs/strategy/unit-economics.md) — cost-per-generation
- [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) — model-specific prompt tuning
- [[deepseek-v3]], [[claude-haiku-4-5]], [[nim-bge-m3]] — adapter detayları
